"""trove 全局配置管理。

通过 JSON 文件持久化用户偏好，提供默认值和运行时路径。
当 PySide6 可用时，将自动切换为 QSettings 后端。
"""

import os
import json
import threading
import logging

log = logging.getLogger("trove.config")


# ---- 配置后端接口 ----
class _JsonBackend:
    """基于 JSON 文件的配置后端。"""

    def __init__(self, filepath: str):
        self._filepath = filepath
        self._data: dict = {}
        self._lock = threading.Lock()
        self._load()

    def _load(self):
        try:
            with open(self._filepath, "r", encoding="utf-8") as f:
                self._data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            self._data = {}

    def get(self, key: str, default=None):
        with self._lock:
            keys = key.split("/")
            node = self._data
            for k in keys:
                if isinstance(node, dict) and k in node:
                    node = node[k]
                else:
                    return default
            return node if node is not None else default

    def set(self, key: str, value):
        with self._lock:
            keys = key.split("/")
            node = self._data
            for k in keys[:-1]:
                if k not in node:
                    node[k] = {}
                node = node[k]
            node[keys[-1]] = value

    def save(self):
        with self._lock:
            os.makedirs(os.path.dirname(self._filepath), exist_ok=True)
            with open(self._filepath, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2, ensure_ascii=False)


# ---- AppConfig ----
class AppConfig:
    """应用全局配置（单例访问）。

    用法:
        config = AppConfig.instance()
        print(config.CLIP_MAX_HISTORY)
    """

    _instance = None

    @classmethod
    def instance(cls) -> "AppConfig":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        appdata = os.getenv("APPDATA", os.path.expanduser("~"))
        base_dir = os.path.join(appdata, "trove")
        settings_path = os.path.join(base_dir, "settings.json")
        self._backend = _JsonBackend(settings_path)
        self._init_paths(base_dir)
        self._init_defaults()

    # ---- 路径 ----
    def _init_paths(self, base_dir: str):
        self.DATA_DIR = os.path.join(base_dir, "data")
        self.BACKUP_DIR = os.path.join(base_dir, "backups")
        self.LOG_DIR = os.path.join(base_dir, "logs")

    # ---- 默认值加载 ----
    def _init_defaults(self):
        b = self._backend
        self.CLIP_MAX_HISTORY = int(b.get("clip/max_history", 1000))
        self.BACKUP_INTERVAL_MIN = int(b.get("backup/interval_min", 30))
        self.BACKUP_MAX_VERSIONS = int(b.get("backup/max_versions", 5))
        self.HOTKEY_SEARCH = b.get("hotkey/search", "Ctrl+Alt+V")
        self.HOTKEY_NEW_NOTE = b.get("hotkey/new_note", "Ctrl+Alt+N")
        self.HOTKEY_PASTE = b.get("hotkey/paste", "Ctrl+Shift+V")
        self.CLOSE_TO_TRAY = str(b.get("ui/close_to_tray", "true")).lower() == "true"
        self.THEME = b.get("ui/theme", "light_blue.xml")
        self.PRIVACY_FILTERS = b.get("privacy/filters", [])
        self.NOTE_FONT_SIZE = int(b.get("note/font_size", 14))

    # ---- 持久化 ----
    def save(self):
        b = self._backend
        b.set("clip/max_history", self.CLIP_MAX_HISTORY)
        b.set("backup/interval_min", self.BACKUP_INTERVAL_MIN)
        b.set("backup/max_versions", self.BACKUP_MAX_VERSIONS)
        b.set("hotkey/search", self.HOTKEY_SEARCH)
        b.set("hotkey/new_note", self.HOTKEY_NEW_NOTE)
        b.set("hotkey/paste", self.HOTKEY_PASTE)
        b.set("ui/close_to_tray", str(self.CLOSE_TO_TRAY).lower())
        b.set("ui/theme", self.THEME)
        b.set("privacy/filters", self.PRIVACY_FILTERS)
        b.set("note/font_size", self.NOTE_FONT_SIZE)
        b.save()

    # ---- 便捷属性 ----
    @property
    def clipboard_db_path(self) -> str:
        return os.path.join(self.DATA_DIR, "clipboard.db")

    @property
    def notes_db_path(self) -> str:
        return os.path.join(self.DATA_DIR, "notes.db")

    @property
    def tasks_db_path(self) -> str:
        return os.path.join(self.DATA_DIR, "tasks.db")

    @property
    def sounds_dir(self) -> str:
        return os.path.join(self.DATA_DIR, "sounds")


def ensure_directories(config: AppConfig):
    """确保运行时所需目录存在。"""
    for d in [config.DATA_DIR, config.BACKUP_DIR, config.LOG_DIR, config.sounds_dir]:
        os.makedirs(d, exist_ok=True)