"""主窗口框架。

布局：左侧 QListWidget 侧边栏 + 右侧 QStackedWidget 页面容器。
"""

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QListWidget, QListWidgetItem, QStackedWidget, QLabel,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QIcon


class MainWindow(QMainWindow):
    """主窗口。

    用法:
        window = MainWindow(close_to_tray=True)
        window.register_page("clip", clip_page_widget)
        window.register_page("note", note_page_widget)
        window.switch_to_page("clip")
        window.show()
    """

    close_requested = Signal()  # 关闭窗口时发射（用于清理等）

    def __init__(self, close_to_tray: bool = False):
        super().__init__()
        self.setWindowTitle("trove")
        self.resize(960, 680)
        self.setMinimumSize(720, 480)

        # 窗口图标
        import os
        icon_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "icon.ico")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        self._close_to_tray = close_to_tray
        self._pages: dict[str, QWidget] = {}
        self._init_ui()

    def _init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ---- 左侧导航栏 ----
        self.nav_list = QListWidget()
        self.nav_list.setFixedWidth(180)
        self.nav_list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.nav_list.currentRowChanged.connect(self._on_nav_changed)
        main_layout.addWidget(self.nav_list)

        # ---- 右侧页面容器 ----
        self.stack = QStackedWidget()
        main_layout.addWidget(self.stack, 1)

        # 添加入口占位项
        self._add_nav_item("剪贴板历史", "clip")
        self._add_nav_item("微笔记", "note")
        self._add_nav_item("定时助手", "task")
        self._add_nav_item("设置", "settings")

    def _add_nav_item(self, label: str, key: str):
        item = QListWidgetItem(label)
        item.setData(Qt.ItemDataRole.UserRole, key)
        self.nav_list.addItem(item)

    def _on_nav_changed(self, row: int):
        if row < 0:
            return
        key = self.nav_list.item(row).data(Qt.ItemDataRole.UserRole)
        self.switch_to_page(key)

    # ---- 公开接口 ----
    def register_page(self, key: str, widget: QWidget):
        """注册页面控件到容器。"""
        self._pages[key] = widget
        self.stack.addWidget(widget)

    def switch_to_page(self, key: str):
        """切换到指定页面。"""
        if key in self._pages:
            self.stack.setCurrentWidget(self._pages[key])
            # 同步导航栏选中
            for i in range(self.nav_list.count()):
                item = self.nav_list.item(i)
                if item.data(Qt.ItemDataRole.UserRole) == key:
                    self.nav_list.setCurrentRow(i)
                    break

    def set_close_to_tray(self, value: bool):
        """运行时切换关闭到托盘行为。"""
        self._close_to_tray = value

    def closeEvent(self, event):
        self.close_requested.emit()
        if self._close_to_tray:
            self.hide()
            event.ignore()
        else:
            event.accept()