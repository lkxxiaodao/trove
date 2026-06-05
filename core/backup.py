"""备份系统 - BackupManager。

功能：
- QTimer 定时备份 → 按时间戳创建子目录，复制 .db 文件
- 自动清理超过保留版本数的旧备份
- 手动备份：打包为 ZIP
- 手动恢复：从 ZIP 或文件夹恢复
"""

import os
import shutil
import zipfile
import time
import re
from PySide6.QtCore import QObject, QTimer, Signal

from config import AppConfig


class BackupManager(QObject):
    """备份管理器。

    用法:
        mgr = BackupManager(config)
        mgr.start_auto_backup()
        # ... 应用运行中 ...
        mgr.manual_backup("/path/to/backup.zip")
    """

    backup_completed = Signal(bool, str)  # 成功/失败, 消息

    def __init__(self, config: AppConfig):
        super().__init__()
        self._config = config
        self._timer: QTimer | None = None

    # ---- 自动备份 ----
    def start_auto_backup(self):
        """启动定时备份。"""
        if self._timer:
            return
        interval_ms = self._config.BACKUP_INTERVAL_MIN * 60 * 1000
        self._timer = QTimer()
        self._timer.timeout.connect(self._auto_backup)
        self._timer.start(interval_ms)

    def stop_auto_backup(self):
        """停止定时备份。"""
        if self._timer:
            self._timer.stop()
            self._timer = None

    def reschedule(self):
        """重新设置定时器间隔（配置变更后调用）。"""
        self.stop_auto_backup()
        self.start_auto_backup()

    def _auto_backup(self):
        """执行一次自动备份。"""
        try:
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            dest = os.path.join(self._config.BACKUP_DIR, f"auto_{timestamp}")
            os.makedirs(dest, exist_ok=True)
            self._copy_files(dest)
            self._cleanup_old()
            self.backup_completed.emit(True, f"自动备份完成: {dest}")
        except Exception as e:
            self.backup_completed.emit(False, f"自动备份失败: {e}")

    # ---- 手动备份 ----
    def manual_backup(self, dest_zip: str) -> bool:
        """手动打包为 ZIP 文件。"""
        try:
            with zipfile.ZipFile(dest_zip, "w", zipfile.ZIP_DEFLATED) as zf:
                for path in self._source_files():
                    if os.path.exists(path):
                        zf.write(path, os.path.basename(path))
            self.backup_completed.emit(True, f"手动备份完成: {dest_zip}")
            return True
        except Exception as e:
            self.backup_completed.emit(False, f"手动备份失败: {e}")
            return False

    # ---- 恢复 ----
    def restore(self, source: str) -> bool:
        """从 ZIP 或文件夹恢复数据。

        恢复前会先备份当前数据。
        """
        try:
            # 先备份当前数据
            ts = time.strftime("%Y%m%d_%H%M%S")
            pre_restore = os.path.join(self._config.BACKUP_DIR, f"pre_restore_{ts}")
            os.makedirs(pre_restore, exist_ok=True)
            self._copy_files(pre_restore)

            if source.endswith(".zip"):
                # 从 ZIP 恢复
                with zipfile.ZipFile(source, "r") as zf:
                    zf.extractall(self._config.DATA_DIR)
            else:
                # 从文件夹恢复
                for fname in ["clipboard.db", "notes.db", "tasks.db"]:
                    src = os.path.join(source, fname)
                    if os.path.exists(src):
                        dst = os.path.join(self._config.DATA_DIR, fname)
                        shutil.copy2(src, dst)

            self.backup_completed.emit(True, f"恢复完成。恢复前数据已备份至: {pre_restore}")
            return True
        except Exception as e:
            self.backup_completed.emit(False, f"恢复失败: {e}")
            return False

    # ---- 清理 ----
    def _cleanup_old(self):
        """清理超过保留版本数的旧备份。"""
        pattern = re.compile(r"^auto_\d{8}_\d{6}$")
        backups = []
        for name in os.listdir(self._config.BACKUP_DIR):
            full = os.path.join(self._config.BACKUP_DIR, name)
            if os.path.isdir(full) and pattern.match(name):
                backups.append(full)
        backups.sort(reverse=True)  # 新在前

        max_versions = self._config.BACKUP_MAX_VERSIONS
        for old in backups[max_versions:]:
            try:
                shutil.rmtree(old)
            except Exception:
                pass

    # ---- 工具方法 ----
    def _source_files(self) -> list[str]:
        """返回需要备份的源文件路径列表。"""
        data = self._config.DATA_DIR
        return [
            os.path.join(data, "clipboard.db"),
            os.path.join(data, "notes.db"),
            os.path.join(data, "tasks.db"),
        ]

    def _copy_files(self, dest_dir: str):
        """将源文件复制到目标目录。"""
        for src in self._source_files():
            if os.path.exists(src):
                shutil.copy2(src, dest_dir)