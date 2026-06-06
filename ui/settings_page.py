"""设置页面 - Settings。

配置项：最大剪贴板条数、自动删除天数、备份间隔/保留版本、热键、主题、关闭到托盘、开机自启动。
"""

import os
import sys
import winreg
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QSpinBox,
    QComboBox, QCheckBox, QPushButton, QGroupBox,
    QScrollArea, QMessageBox, QKeySequenceEdit,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeySequence

from config import AppConfig


class _NoWheelSpinBox(QSpinBox):
    """禁用鼠标滚轮调整的 QSpinBox。"""

    def wheelEvent(self, event):
        event.ignore()


class SettingsPage(QWidget):
    """应用设置页面。"""

    close_to_tray_changed = Signal(bool)  # 关闭到托盘设置变更
    note_font_size_changed = Signal(int)  # 笔记字体大小变更

    def __init__(self, config: AppConfig):
        super().__init__()
        self._config = config
        self._init_ui()
        self._load_values()

    def _init_ui(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setSpacing(12)

        # ---- 剪贴板 ----
        clip_group = QGroupBox("剪贴板历史")
        clip_form = QFormLayout(clip_group)
        self._max_history = _NoWheelSpinBox()
        self._max_history.setRange(100, 50000)
        self._max_history.setSingleStep(100)
        clip_form.addRow("最大条数", self._max_history)

        # 自动删除超过 N 天的剪贴内容
        self._clip_auto_delete_days = _NoWheelSpinBox()
        self._clip_auto_delete_days.setRange(0, 365)
        self._clip_auto_delete_days.setSuffix(" 天（0=禁用）")
        self._clip_auto_delete_days.setToolTip("超过此天数的剪贴内容将被自动删除，0 表示禁用")
        clip_form.addRow("自动删除超过", self._clip_auto_delete_days)
        layout.addWidget(clip_group)

        # ---- 备份 ----
        backup_group = QGroupBox("备份")
        backup_form = QFormLayout(backup_group)
        self._backup_interval = _NoWheelSpinBox()
        self._backup_interval.setRange(5, 1440)
        self._backup_interval.setSuffix(" 分钟")
        backup_form.addRow("自动备份间隔", self._backup_interval)
        self._backup_versions = _NoWheelSpinBox()
        self._backup_versions.setRange(1, 50)
        backup_form.addRow("保留版本数", self._backup_versions)
        layout.addWidget(backup_group)

        # ---- 热键 ----
        hotkey_group = QGroupBox("全局热键")
        hotkey_form = QFormLayout(hotkey_group)
        self._hotkey_search = QKeySequenceEdit()
        hotkey_form.addRow("全局搜索", self._hotkey_search)
        self._hotkey_note = QKeySequenceEdit()
        hotkey_form.addRow("新建笔记", self._hotkey_note)
        self._hotkey_paste = QKeySequenceEdit()
        hotkey_form.addRow("粘贴历史", self._hotkey_paste)
        layout.addWidget(hotkey_group)

        # ---- 外观 ----
        ui_group = QGroupBox("外观")
        ui_form = QFormLayout(ui_group)
        self._theme_combo = QComboBox()
        self._theme_combo.addItems([
            "light_blue.xml", "light_cyan.xml", "light_teal.xml",
            "dark_blue.xml", "dark_cyan.xml", "dark_teal.xml",
            "dark_amber.xml", "dark_pink.xml",
        ])
        ui_form.addRow("主题", self._theme_combo)
        self._close_to_tray = QCheckBox("关闭窗口时隐藏到系统托盘")
        ui_form.addRow("", self._close_to_tray)
        self._auto_start = QCheckBox("开机时自动启动")
        ui_form.addRow("", self._auto_start)
        self._note_font_size = _NoWheelSpinBox()
        self._note_font_size.setRange(10, 36)
        self._note_font_size.setSuffix(" pt")
        ui_form.addRow("笔记字体大小", self._note_font_size)
        layout.addWidget(ui_group)

        layout.addStretch()

        # 按钮
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        save_btn = QPushButton("保存设置")
        save_btn.setFixedWidth(120)
        save_btn.clicked.connect(self._on_save)
        btn_layout.addWidget(save_btn)
        layout.addLayout(btn_layout)

        scroll.setWidget(container)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(scroll)

    def _load_values(self):
        c = self._config
        self._max_history.setValue(c.CLIP_MAX_HISTORY)
        self._clip_auto_delete_days.setValue(c.CLIP_AUTO_DELETE_DAYS)
        self._backup_interval.setValue(c.BACKUP_INTERVAL_MIN)
        self._backup_versions.setValue(c.BACKUP_MAX_VERSIONS)
        self._hotkey_search.setKeySequence(QKeySequence(c.HOTKEY_SEARCH))
        self._hotkey_note.setKeySequence(QKeySequence(c.HOTKEY_NEW_NOTE))
        self._hotkey_paste.setKeySequence(QKeySequence(c.HOTKEY_PASTE))
        self._close_to_tray.setChecked(c.CLOSE_TO_TRAY)
        self._auto_start.setChecked(c.AUTO_START)
        idx = self._theme_combo.findText(c.THEME)
        if idx >= 0:
            self._theme_combo.setCurrentIndex(idx)
        self._note_font_size.setValue(c.NOTE_FONT_SIZE)

    def _set_auto_start(self, enable: bool):
        """通过 Windows 注册表设置开机自启动。"""
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        app_name = "trove"
        try:
            if enable:
                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE)
                # 获取当前 exe 路径（PyInstaller 打包后）或 python 脚本路径
                if getattr(sys, 'frozen', False):
                    exe_path = sys.executable
                else:
                    exe_path = sys.executable
                    # 开发模式下使用脚本路径
                    script_path = os.path.abspath(sys.argv[0])
                    exe_path = f'"{sys.executable}" "{script_path}"'
                winreg.SetValueEx(key, app_name, 0, winreg.REG_SZ, exe_path)
                winreg.CloseKey(key)
            else:
                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE)
                try:
                    winreg.DeleteValue(key, app_name)
                except FileNotFoundError:
                    pass
                winreg.CloseKey(key)
        except Exception as e:
            QMessageBox.warning(self, "错误", f"设置开机自启动失败: {e}")

    def _on_save(self):
        c = self._config
        c.CLIP_MAX_HISTORY = self._max_history.value()
        c.CLIP_AUTO_DELETE_DAYS = self._clip_auto_delete_days.value()
        c.BACKUP_INTERVAL_MIN = self._backup_interval.value()
        c.BACKUP_MAX_VERSIONS = self._backup_versions.value()
        c.HOTKEY_SEARCH = self._hotkey_search.keySequence().toString()
        c.HOTKEY_NEW_NOTE = self._hotkey_note.keySequence().toString()
        c.HOTKEY_PASTE = self._hotkey_paste.keySequence().toString()
        c.CLOSE_TO_TRAY = self._close_to_tray.isChecked()
        self.close_to_tray_changed.emit(c.CLOSE_TO_TRAY)

        new_auto_start = self._auto_start.isChecked()
        c.AUTO_START = new_auto_start
        self._set_auto_start(new_auto_start)

        new_note_font_size = self._note_font_size.value()
        c.NOTE_FONT_SIZE = new_note_font_size
        self.note_font_size_changed.emit(new_note_font_size)

        new_theme = self._theme_combo.currentText()
        theme_changed = c.THEME != new_theme
        c.THEME = new_theme

        c.save()

        if theme_changed:
            QMessageBox.information(self, "提示", "主题将在下次启动时生效。")
        else:
            QMessageBox.information(self, "提示", "设置已保存。")


def create_page(config: AppConfig = None) -> QWidget:
    """创建设置页面（工厂函数）。"""
    if config is None:
        config = AppConfig.instance()
    return SettingsPage(config)