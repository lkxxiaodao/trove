"""系统托盘管理器 - TrayManager。

功能：
- QSystemTrayIcon 托盘图标 + 右键菜单
- 关闭窗口 → 隐藏到托盘（可配置）
- 全局热键注册（RegisterHotKey + nativeEvent WM_HOTKEY）
"""

import ctypes
import ctypes.wintypes
from PySide6.QtWidgets import (
    QSystemTrayIcon, QMenu, QApplication, QWidget, QInputDialog, QLineEdit,
)
from PySide6.QtCore import QObject, Signal, QTimer, QAbstractNativeEventFilter
from PySide6.QtGui import QIcon, QAction

from config import AppConfig

# Windows 热键常量
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
WM_HOTKEY = 0x0312


def _parse_hotkey(hotkey_str: str) -> tuple[int, int]:
    """解析热键字符串如 'Ctrl+Alt+V' 为 (modifiers, vk_code)。"""
    parts = hotkey_str.upper().split("+")
    mod = 0
    vk = 0
    for p in parts:
        p = p.strip()
        if p == "CTRL":
            mod |= MOD_CONTROL
        elif p == "ALT":
            mod |= MOD_ALT
        elif p == "SHIFT":
            mod |= MOD_SHIFT
        elif p == "WIN":
            mod |= MOD_WIN
        else:
            vk = ord(p)
    return mod, vk


class _HotkeyNativeFilter(QAbstractNativeEventFilter):
    """内部类：作为 QAbstractNativeEventFilter 处理 WM_HOTKEY。"""

    def __init__(self, manager: "TrayManager"):
        super().__init__()
        self._manager = manager

    def nativeEventFilter(self, event_type, message):
        if not self._manager._hotkey_window:
            return False, None
        msg = ctypes.wintypes.MSG.from_address(int(message))
        if msg.message == WM_HOTKEY:
            hid = msg.wParam
            if hid in self._manager._hotkey_ids:
                _, callback = self._manager._hotkey_ids[hid]
                if callback:
                    callback()
            return True, None
        return False, None


class TrayManager(QObject):
    """系统托盘 + 全局热键。"""

    def __init__(self):
        super().__init__()
        self._tray: QSystemTrayIcon | None = None
        self._hotkey_window: QWidget | None = None
        self._native_filter: _HotkeyNativeFilter | None = None
        self._hotkey_ids: dict[int, tuple[str, callable]] = {}  # id → (name, callback)
        self._next_hotkey_id = 1

    # ---- 托盘 ----
    def setup_tray(self, app: QApplication, main_window,
                   on_show=None, on_new_note=None, on_quit=None,
                   on_pause=None):
        """初始化系统托盘。"""
        self._tray = QSystemTrayIcon()
        # 使用自定义图标
        import os
        icon_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "icon.ico")
        if os.path.exists(icon_path):
            self._tray.setIcon(QIcon(icon_path))
        else:
            icon = main_window.style().standardIcon(
                main_window.style().StandardPixmap.SP_FileDialogListView
            )
            self._tray.setIcon(icon)
        self._tray.setToolTip("trove")

        menu = QMenu()

        show_action = QAction("显示/隐藏", menu)
        show_action.triggered.connect(lambda: self._toggle_window(main_window))
        menu.addAction(show_action)

        if on_new_note:
            note_action = QAction("新建笔记", menu)
            note_action.triggered.connect(on_new_note)
            menu.addAction(note_action)

        menu.addSeparator()

        quit_action = QAction("退出", menu)
        quit_action.triggered.connect(on_quit if on_quit else app.quit)
        menu.addAction(quit_action)

        self._tray.setContextMenu(menu)
        self._tray.activated.connect(
            lambda reason: self._on_tray_activated(reason, main_window)
        )
        self._tray.show()

    def _toggle_window(self, main_window):
        if main_window.isVisible():
            main_window.hide()
        else:
            main_window.show()
            main_window.raise_()
            main_window.activateWindow()

    def _on_tray_activated(self, reason, main_window):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self._toggle_window(main_window)

    def is_tray_setup(self) -> bool:
        return self._tray is not None

    # ---- 全局热键 ----
    def setup_hotkeys(self, config: AppConfig,
                      on_search=None, on_new_note=None, on_paste=None):
        """注册全局热键。"""
        if self._hotkey_window:
            self.unregister_all()

        self._hotkey_window = QWidget()
        self._hotkey_window.setWindowTitle("trove-Hotkey")
        self._native_filter = _HotkeyNativeFilter(self)
        QApplication.instance().installNativeEventFilter(self._native_filter)

        hwnd = int(self._hotkey_window.winId())
        user32 = ctypes.windll.user32

        search_mod, search_vk = _parse_hotkey(config.HOTKEY_SEARCH)
        if search_vk and on_search:
            hid = self._next_hotkey_id
            self._next_hotkey_id += 1
            if user32.RegisterHotKey(hwnd, hid, search_mod, search_vk):
                self._hotkey_ids[hid] = ("search", on_search)

        note_mod, note_vk = _parse_hotkey(config.HOTKEY_NEW_NOTE)
        if note_vk and on_new_note:
            hid = self._next_hotkey_id
            self._next_hotkey_id += 1
            if user32.RegisterHotKey(hwnd, hid, note_mod, note_vk):
                self._hotkey_ids[hid] = ("note", on_new_note)

        paste_mod, paste_vk = _parse_hotkey(config.HOTKEY_PASTE)
        if paste_vk and on_paste:
            hid = self._next_hotkey_id
            self._next_hotkey_id += 1
            if user32.RegisterHotKey(hwnd, hid, paste_mod, paste_vk):
                self._hotkey_ids[hid] = ("paste", on_paste)

    def refresh_hotkeys(self, config: AppConfig, on_search=None, on_new_note=None):
        """更新热键注册（设置变更后调用）。"""
        self.unregister_all()
        self.setup_hotkeys(config, on_search, on_new_note)

    def unregister_all(self):
        """注销所有热键。"""
        if self._hotkey_window:
            user32 = ctypes.windll.user32
            hwnd = int(self._hotkey_window.winId())
            for hid in self._hotkey_ids:
                user32.UnregisterHotKey(hwnd, hid)
            self._hotkey_ids.clear()
            if self._native_filter:
                QApplication.instance().removeNativeEventFilter(self._native_filter)
                self._native_filter = None
            self._hotkey_window.deleteLater()
            self._hotkey_window = None

    def shutdown(self):
        """彻底清理。"""
        if self._tray:
            self._tray.hide()
            self._tray = None
        self.unregister_all()