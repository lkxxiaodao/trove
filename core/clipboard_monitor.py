"""剪贴板监控模块。

包含：
- ClipStore: 剪贴板历史数据 CRUD（M03.1）
- ClipboardMonitor: Windows 剪贴板实时监听（M03.2）
"""

import hashlib
import json
from typing import Optional
from data.db import Database

# ============================================================
# M03.1 - ClipStore
# ============================================================

class ClipStore:
    """剪贴板历史数据操作。

    封装 history 表的增删改查，支持文本/文件/图片三种类型。
    去重策略：重复内容 → 删除旧条目 → 新建（提升到顶部）。
    """

    def __init__(self, db: Database):
        self._db = db
        self._last_hash: Optional[str] = None

    # ---- 写入 ----
    def add_text(self, content: str) -> bool:
        """插入文本条目，去重并提升到顶部。"""
        content = content.strip()
        if not content:
            return False

        h = hashlib.md5(content.encode("utf-8")).hexdigest()
        if h == self._last_hash:
            return False
        self._last_hash = h

        return self._insert(ClipEntry(
            content=content,
            clip_type="text",
            content_hash=h,
        ))

    def add_files(self, file_paths: list[str]) -> bool:
        """插入文件条目。"""
        if not file_paths:
            return False

        paths_json = json.dumps(file_paths, ensure_ascii=False)
        content = "\n".join(file_paths)
        h = hashlib.md5(paths_json.encode("utf-8")).hexdigest()
        if h == self._last_hash:
            return False
        self._last_hash = h

        return self._insert(ClipEntry(
            content=content,
            clip_type="file",
            file_paths=paths_json,
            content_hash=h,
        ))

    def add_image(self, image_bytes: bytes) -> bool:
        """插入图片条目。"""
        if not image_bytes:
            return False

        h = hashlib.md5(image_bytes).hexdigest()
        if h == self._last_hash:
            return False
        self._last_hash = h

        # 内容显示为 "[图片]"
        return self._insert(ClipEntry(
            content="[图片]",
            clip_type="image",
            image_data=image_bytes,
            content_hash=h,
        ))

    def _insert(self, entry: "ClipEntry") -> bool:
        """通用插入：先删除 content_hash 匹配的旧条目，再插入新条目。"""
        import time

        if entry.content_hash:
            self._db.execute(
                "DELETE FROM history WHERE content_hash = ?",
                (entry.content_hash,),
            )

        self._db.execute(
            """INSERT INTO history (content, timestamp, clip_type, file_paths, image_data, content_hash)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                entry.content,
                int(time.time()),
                entry.clip_type,
                entry.file_paths,
                entry.image_data,
                entry.content_hash,
            ),
        )
        return True

    # ---- 删除 ----
    def delete(self, clip_id: int):
        self._db.execute("DELETE FROM history WHERE id = ?", (clip_id,))

    # ---- 星标 ----
    def toggle_star(self, clip_id: int) -> bool:
        row = self._db.fetchone("SELECT starred FROM history WHERE id = ?", (clip_id,))
        if not row:
            return False
        new_val = 0 if row["starred"] else 1
        self._db.execute("UPDATE history SET starred = ? WHERE id = ?", (new_val, clip_id))
        return bool(new_val)

    # ---- 查询 ----
    def get_recent(self, limit: int = 50, offset: int = 0,
                   starred_only: bool = False) -> list[dict]:
        where = "WHERE starred = 1" if starred_only else ""
        return self._db.fetchall(
            f"SELECT * FROM history {where} ORDER BY timestamp DESC LIMIT ? OFFSET ?",
            (limit, offset),
        )

    def get_count(self) -> int:
        row = self._db.fetchone("SELECT COUNT(*) as cnt FROM history")
        return row["cnt"] if row else 0

    def search(self, keyword: str, starred_only: bool = False,
               limit: int = 50, offset: int = 0) -> list[dict]:
        where = "WHERE content LIKE ?"
        params = [f"%{keyword}%"]
        if starred_only:
            where += " AND starred = 1"
        return self._db.fetchall(
            f"SELECT * FROM history {where} ORDER BY timestamp DESC LIMIT ? OFFSET ?",
            (*params, limit, offset),
        )

    # ---- 上限清理 ----
    def enforce_cap(self, max_count: int):
        current = self.get_count()
        if current <= max_count:
            return
        excess = current - max_count
        self._db.execute(
            """DELETE FROM history WHERE id IN (
                SELECT id FROM history
                WHERE starred = 0
                ORDER BY timestamp ASC LIMIT ?
            )""",
            (excess,),
        )


class ClipEntry:
    """剪贴板条目数据类。"""
    __slots__ = ("content", "clip_type", "file_paths", "image_data", "content_hash")

    def __init__(self, content: str, clip_type: str = "text",
                 file_paths: str = None, image_data: bytes = None,
                 content_hash: str = None):
        self.content = content
        self.clip_type = clip_type
        self.file_paths = file_paths
        self.image_data = image_data
        self.content_hash = content_hash


# ============================================================
# M03.2 - ClipboardMonitor
# ============================================================

import re
import ctypes
import ctypes.wintypes
from PySide6.QtCore import QObject, Signal, QAbstractNativeEventFilter
from PySide6.QtWidgets import QApplication, QWidget
from PySide6.QtGui import QImage


class _ClipboardNativeFilter(QAbstractNativeEventFilter):
    """内部类：作为 QAbstractNativeEventFilter 转发剪贴板事件。"""

    def __init__(self, monitor: "ClipboardMonitor"):
        super().__init__()
        self._monitor = monitor

    def nativeEventFilter(self, event_type, message):
        msg = ctypes.wintypes.MSG.from_address(int(message))
        if msg.message == ClipboardMonitor.WM_CLIPBOARDUPDATE:
            self._monitor._on_clipboard_changed()
        return False, None


class ClipboardMonitor(QObject):
    """Windows 剪贴板实时监听器。

    通过 AddClipboardFormatListener + WM_CLIPBOARDUPDATE 实现钩子监听。
    支持文本、文件路径（CF_HDROP）、图片（CF_DIB）三种类型。
    """

    new_content = Signal(object)  # 发射 ClipEntry 或 None（文本时发射 str 兼容旧逻辑）

    WM_CLIPBOARDUPDATE = 0x031D

    # Windows 剪贴板格式常量
    CF_HDROP = 15
    CF_DIB = 8

    def __init__(self, clip_store: ClipStore, parent=None):
        super().__init__(parent)
        self._store = clip_store
        self._privacy_filters: list[re.Pattern] = []
        self._hidden_window: Optional[QWidget] = None
        self._native_filter: Optional[_ClipboardNativeFilter] = None
        self._running = False

    def set_privacy_filters(self, patterns: list[str]):
        """设置隐私过滤正则列表。"""
        self._privacy_filters = [re.compile(p) for p in patterns]

    def start(self):
        """启动剪贴板监听。"""
        if self._running:
            return
        self._hidden_window = QWidget()
        self._hidden_window.setWindowTitle("InfoVault-ClipMonitor")
        self._native_filter = _ClipboardNativeFilter(self)
        QApplication.instance().installNativeEventFilter(self._native_filter)
        hwnd = int(self._hidden_window.winId())
        user32 = ctypes.windll.user32
        if not user32.AddClipboardFormatListener(hwnd):
            raise OSError("AddClipboardFormatListener 失败")
        self._running = True

    def stop(self):
        """停止监听并注销钩子。"""
        if not self._running:
            return
        if self._hidden_window:
            ctypes.windll.user32.RemoveClipboardFormatListener(
                int(self._hidden_window.winId())
            )
            if self._native_filter:
                QApplication.instance().removeNativeEventFilter(self._native_filter)
                self._native_filter = None
            self._hidden_window.deleteLater()
            self._hidden_window = None
        self._running = False

    def _on_clipboard_changed(self):
        """检测剪贴板内容类型并分类存储。"""
        clipboard = QApplication.clipboard()
        mime = clipboard.mimeData()

        # 优先级：文件 > 图片 > 文本
        if mime.hasUrls() and not mime.hasImage():
            # 文件路径（CF_HDROP）
            paths = [url.toLocalFile() for url in mime.urls() if url.isLocalFile()]
            if paths:
                if self._store.add_files(paths):
                    self._store.enforce_cap(1000)
                    self.new_content.emit(paths)
                return

        if mime.hasImage():
            # 图片（CF_DIB / CF_BITMAP）
            image = mime.imageData()
            if image and not image.isNull():
                ba = QImage(image).save(None, "PNG")  # 返回 bytes
                # 实际上 QImage.save() 返回 bool，需要 QByteArray
                from PySide6.QtCore import QByteArray, QBuffer, QIODevice
                buffer = QBuffer()
                buffer.open(QIODevice.OpenModeFlag.WriteOnly)
                image.save(buffer, "PNG")
                image_bytes = bytes(buffer.data())
                buffer.close()
                if self._store.add_image(image_bytes):
                    self._store.enforce_cap(1000)
                    self.new_content.emit("[图片]")
                return

        # 纯文本
        text = clipboard.text()
        if text:
            # 隐私过滤
            for pattern in self._privacy_filters:
                if pattern.search(text):
                    return
            if self._store.add_text(text):
                self._store.enforce_cap(1000)
                self.new_content.emit(text)