"""备份系统 - BackupManager。

功能：
- 自动备份：按间隔创建独立命名的备份文件（clipboard/notes/tasks）
- 手动备份：用户触发，命名含时间戳
- 恢复：选择备份文件，自动识别类型，仅恢复对应模块数据
- 清理：超过保留版本数的旧备份自动删除
"""

import os
import shutil
import time
import re
from PySide6.QtCore import QObject, QTimer, Signal

from config import AppConfig

FILE_PREFIX = {"clipboard": "clipboard_backup", "notes": "notes_backup", "tasks": "tasks_backup"}


class BackupManager(QObject):
    """备份管理器。"""

    backup_completed = Signal(bool, str)

    def __init__(self, config: AppConfig):
        super().__init__()
        self._config = config
        self._timer: QTimer | None = None

    # ---- 自动备份 ----
    def start_auto_backup(self):
        if self._timer:
            return
        interval_ms = self._config.BACKUP_INTERVAL_MIN * 60 * 1000
        self._timer = QTimer()
        self._timer.timeout.connect(self._auto_backup)
        self._timer.start(interval_ms)

    def stop_auto_backup(self):
        if self._timer:
            self._timer.stop()
            self._timer = None

    def reschedule(self):
        self.stop_auto_backup()
        self.start_auto_backup()

    def _auto_backup(self):
        try:
            self._do_backup("auto")
            self._cleanup_old()
            self.backup_completed.emit(True, "自动备份完成")
        except Exception as e:
            self.backup_completed.emit(False, f"自动备份失败: {e}")

    # ---- 手动备份 ----
    def manual_backup(self) -> bool:
        try:
            self._do_backup("manual")
            self.backup_completed.emit(True, "手动备份完成")
            return True
        except Exception as e:
            self.backup_completed.emit(False, f"手动备份失败: {e}")
            return False

    def _do_backup(self, tag: str):
        """执行备份：为三个模块各创建一个独立备份文件。"""
        ts = time.strftime("%Y%m%d_%H%M%S")
        dest_dir = self._config.BACKUP_DIR
        os.makedirs(dest_dir, exist_ok=True)

        sources = {
            "clipboard": os.path.join(self._config.DATA_DIR, "clipboard.db"),
            "notes": os.path.join(self._config.DATA_DIR, "notes.db"),
            "tasks": os.path.join(self._config.DATA_DIR, "tasks.db"),
        }
        for key, src in sources.items():
            if os.path.exists(src):
                fname = f"{FILE_PREFIX[key]}_{tag}_{ts}.db"
                shutil.copy2(src, os.path.join(dest_dir, fname))

    # ---- 恢复 ----
    def restore(self, backup_path: str) -> bool:
        """从指定备份文件恢复对应模块数据。自动识别文件类型。"""
        fname = os.path.basename(backup_path)
        # 识别类型
        module_key = None
        for key, prefix in FILE_PREFIX.items():
            if fname.startswith(prefix):
                module_key = key
                break
        if not module_key:
            self.backup_completed.emit(False, "无法识别备份文件类型")
            return False

        module_name = {"clipboard": "剪贴板", "notes": "笔记", "tasks": "定时任务"}[module_key]
        db_name = f"{module_key}.db"
        target = os.path.join(self._config.DATA_DIR, db_name)

        try:
            # 恢复前先备份当前数据
            ts = time.strftime("%Y%m%d_%H%M%S")
            if os.path.exists(target):
                pre_bak = os.path.join(
                    self._config.BACKUP_DIR,
                    f"{FILE_PREFIX[module_key]}_pre_restore_{ts}.db"
                )
                shutil.copy2(target, pre_bak)

            # 复制备份文件覆盖当前数据
            shutil.copy2(backup_path, target)
            self.backup_completed.emit(True, f"{module_name}数据恢复成功")
            return True
        except Exception as e:
            self.backup_completed.emit(False, f"恢复失败: {e}")
            return False

    # ---- 清理 ----
    def _cleanup_old(self):
        """清理超过保留版本数的旧备份（每个模块独立计数）。"""
        dest_dir = self._config.BACKUP_DIR
        if not os.path.isdir(dest_dir):
            return
        max_ver = self._config.BACKUP_MAX_VERSIONS
        for key, prefix in FILE_PREFIX.items():
            pattern = re.compile(rf"^{prefix}_auto_\d{{8}}_\d{{6}}\.db$")
            files = []
            for fname in os.listdir(dest_dir):
                if pattern.match(fname):
                    full = os.path.join(dest_dir, fname)
                    files.append((os.path.getmtime(full), full))
            files.sort(reverse=True)  # 新在前
            for _, p in files[max_ver:]:
                try:
                    os.remove(p)
                except Exception:
                    pass
