"""粘贴选择弹出窗口 - PastePopup。

Ctrl+Shift+V 热键触发，在光标附近显示最近剪贴板历史，
用户选择后自动复制并模拟 Ctrl+V 粘贴到目标窗口。

支持文本、文件（CF_HDROP）、图片三种类型的粘贴。
"""

import json
import ctypes
import ctypes.wintypes
import time
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QListWidget, QListWidgetItem, QLabel,
)
from PySide6.QtCore import Qt, Signal, QTimer, QPoint, QUrl, QMimeData
from PySide6.QtGui import QFont, QKeyEvent, QImage, QPixmap, QCursor, QMouseEvent
from PySide6.QtWidgets import QApplication

from core.clipboard_monitor import ClipStore

# Windows API
user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
VK_CONTROL = 0x11
VK_V = 0x56


def _send_ctrl_v():
    """模拟 Ctrl+V 按键到当前前台窗口。"""
    time.sleep(0.05)

    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [
            ("wVk", ctypes.wintypes.WORD),
            ("wScan", ctypes.wintypes.WORD),
            ("dwFlags", ctypes.wintypes.DWORD),
            ("time", ctypes.wintypes.DWORD),
            ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
        ]

    class INPUT(ctypes.Structure):
        _fields_ = [
            ("type", ctypes.wintypes.DWORD),
            ("ki", KEYBDINPUT),
            ("padding", ctypes.c_ubyte * 8),
        ]

    inputs = (INPUT * 4)()
    inputs[0].type = INPUT_KEYBOARD
    inputs[0].ki.wVk = VK_CONTROL
    inputs[1].type = INPUT_KEYBOARD
    inputs[1].ki.wVk = VK_V
    inputs[2].type = INPUT_KEYBOARD
    inputs[2].ki.wVk = VK_V
    inputs[2].ki.dwFlags = KEYEVENTF_KEYUP
    inputs[3].type = INPUT_KEYBOARD
    inputs[3].ki.wVk = VK_CONTROL
    inputs[3].ki.dwFlags = KEYEVENTF_KEYUP
    ctypes.windll.user32.SendInput(4, ctypes.pointer(inputs), ctypes.sizeof(INPUT))


class PastePopup(QWidget):
    """粘贴选择弹窗（可拖拽移动）。"""

    MAX_ITEMS = 50

    def __init__(self, clip_store: ClipStore):
        super().__init__()
        self._store = clip_store
        self._drag_pos = None
        self._init_ui()
        self._init_flags()

    def _init_flags(self):
        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)

    def _init_ui(self):
        self.setFixedSize(420, 360)
        self.setStyleSheet("""
            PastePopup {
                background: #ffffff;
                border: 1px solid #ccc;
                border-radius: 8px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 8, 4, 4)
        layout.setSpacing(0)

        header = QLabel("选择要粘贴的内容  — 拖拽移动")
        header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header.setStyleSheet("color: #888; font-size: 11px; padding: 6px 4px; background: #f5f5f5; border-radius: 8px 8px 0 0;")
        header.setCursor(Qt.CursorShape.SizeAllCursor)
        header.mousePressEvent = self._header_press
        header.mouseMoveEvent = self._header_move
        header.mouseReleaseEvent = self._header_release
        layout.addWidget(header)

        self._list = QListWidget()
        self._list.setStyleSheet("""
            QListWidget {
                border: none;
                outline: none;
                font-size: 13px;
            }
            QListWidget::item {
                padding: 8px 10px;
                border-bottom: 1px solid #eee;
            }
            QListWidget::item:selected {
                background: #e3f2fd;
                color: #000;
            }
        """)
        self._list.itemClicked.connect(self._on_item_clicked)
        self._list.installEventFilter(self)
        layout.addWidget(self._list)

    # ---- 拖拽移动 ----
    def _header_press(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint()

    def _header_move(self, event: QMouseEvent):
        if self._drag_pos is not None:
            delta = event.globalPosition().toPoint() - self._drag_pos
            self.move(self.pos() + delta)
            self._drag_pos = event.globalPosition().toPoint()

    def _header_release(self, event: QMouseEvent):
        self._drag_pos = None

    def mousePressEvent(self, event: QMouseEvent):
        """点击窗口外部区域时关闭弹窗。"""
        if self._drag_pos is None:
            # Not in drag mode, check if click is outside
            pass
        super().mousePressEvent(event)

    def changeEvent(self, event):
        """窗口失去焦点时自动隐藏。"""
        if event.type() == event.Type.ActivationChange and not self.isActiveWindow():
            self.hide()
        super().changeEvent(event)

    def eventFilter(self, obj, event):
        if obj is self._list and event.type() == event.Type.KeyPress:
            key_event = event
            if key_event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                item = self._list.currentItem()
                if item:
                    self._paste_item(item)
                return True
            elif key_event.key() == Qt.Key.Key_Escape:
                self.hide()
                return True
        return super().eventFilter(obj, event)

    def show_near_cursor(self):
        """刷新列表并在光标附近显示。"""
        self._list.clear()

        rows = self._store.get_recent(limit=self.MAX_ITEMS)
        if not rows:
            self.hide()
            return

        for row in rows:
            clip_type = row.get("clip_type", "text")
            content = row.get("content", "")

            # 格式化显示文本
            if clip_type == "file":
                paths = json.loads(row.get("file_paths", "[]"))
                names = [p.rsplit("\\", 1)[-1] for p in paths]
                display = "📁 " + ", ".join(names[:3])
                if len(names) > 3:
                    display += f" 等 {len(names)} 个文件"
            elif clip_type == "image":
                display = "🖼 [图片]"
            else:
                display = content.replace("\n", " ")[:80]

            item = QListWidgetItem(display)
            # 存储完整行数据用于粘贴
            item.setData(Qt.ItemDataRole.UserRole, dict(row))
            if row.get("starred"):
                item.setText("★ " + display)
            self._list.addItem(item)

        self._list.setCurrentRow(0)

        cursor_pos = QCursor.pos()
        screen = QApplication.screenAt(cursor_pos)
        if screen:
            screen_geo = screen.availableGeometry()
            x = cursor_pos.x()
            y = cursor_pos.y()
            if x + self.width() > screen_geo.right():
                x = screen_geo.right() - self.width()
            if y + self.height() > screen_geo.bottom():
                y = screen_geo.bottom() - self.height()
            if x < screen_geo.left():
                x = screen_geo.left()
            if y < screen_geo.top():
                y = screen_geo.top()
            self.move(x, y)

        self.show()
        self._list.setFocus()

    def _on_item_clicked(self, item: QListWidgetItem):
        self._paste_item(item)

    def _paste_item(self, item: QListWidgetItem):
        """根据条目类型设置剪贴板并模拟粘贴。"""
        data = item.data(Qt.ItemDataRole.UserRole)
        if not data:
            return

        clipboard = QApplication.clipboard()
        clip_type = data.get("clip_type", "text")

        if clip_type == "file":
            # 恢复文件路径到剪贴板（CF_HDROP）
            paths = json.loads(data.get("file_paths", "[]"))
            if paths:
                mime = QMimeData()
                mime.setUrls([QUrl.fromLocalFile(p) for p in paths])
                clipboard.setMimeData(mime)
        elif clip_type == "image":
            # 恢复图片到剪贴板
            image_data = data.get("image_data")
            if image_data:
                pixmap = QPixmap()
                pixmap.loadFromData(image_data)
                clipboard.setPixmap(pixmap)
        else:
            # 文本
            clipboard.setText(data.get("content", ""))

        self.hide()
        # 确保剪贴板操作在事件循环中完成
        QApplication.instance().processEvents()
        QTimer.singleShot(150, _send_ctrl_v)


def create_paste_popup(clip_store: ClipStore) -> PastePopup:
    return PastePopup(clip_store)