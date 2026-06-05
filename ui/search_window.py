"""全局搜索窗口 - SearchWindow。

浮动搜索框 + 分组展示 ClipCache / NoteNest / SafePass 结果。
点击结果可跳转到对应页面的具体条目。
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QLineEdit, QTreeWidget, QTreeWidgetItem,
    QLabel, QHBoxLayout, QPushButton,
)
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QClipboard
from PySide6.QtWidgets import QApplication

from core.search_engine import SearchEngine


class SearchWindow(QDialog):
    """浮动全局搜索窗口。"""

    # 信号：请求跳转到某模块的某条目
    jump_to = Signal(str, object)  # module_name, entry_data

    def __init__(self, engine: SearchEngine, parent=None):
        super().__init__(parent)
        self._engine = engine
        self._engine.search_completed.connect(self._on_results)
        self._debounce_timer = QTimer()
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.timeout.connect(self._do_search)
        self._debounce_interval = 200  # ms

        self.setWindowTitle("全局搜索")
        self.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.FramelessWindowHint
        )
        self.resize(480, 420)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # 搜索框
        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("搜索剪贴板、笔记、密码...")
        self._search_input.textChanged.connect(self._on_text_changed)
        layout.addWidget(self._search_input)

        # 结果树
        self._tree = QTreeWidget()
        self._tree.setHeaderHidden(True)
        self._tree.setIndentation(16)
        self._tree.itemDoubleClicked.connect(self._on_item_double_click)
        layout.addWidget(self._tree, 1)

        # 底部提示
        hint = QLabel("双击结果可跳转到对应条目")
        hint.setStyleSheet("color: #888; font-size: 11px;")
        layout.addWidget(hint)

    # ---- 搜索 ----
    def _on_text_changed(self, text):
        self._debounce_timer.start(self._debounce_interval)

    def _do_search(self):
        keyword = self._search_input.text()
        self._engine.search(keyword)

    def _on_results(self, groups):
        self._tree.clear()
        if not groups:
            return
        for group in groups:
            if not group.get("results") and not group.get("locked"):
                continue

            label = group["label"]
            if group.get("locked"):
                label += " (未解锁)"

            root = QTreeWidgetItem([label])
            root.setFlags(root.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            font = root.font(0)
            font.setBold(True)
            root.setFont(0, font)

            if group.get("locked"):
                self._tree.addTopLevelItem(root)
                continue

            for entry in group["results"]:
                if group["module"] == "clip":
                    text = entry.get("content", "")[:60]
                    child = QTreeWidgetItem([text])
                    child.setData(0, Qt.ItemDataRole.UserRole, entry)
                    child.setToolTip(0, entry.get("content", ""))
                elif group["module"] == "note":
                    text = entry.get("title", "未命名")
                    child = QTreeWidgetItem([text])
                    child.setData(0, Qt.ItemDataRole.UserRole, entry)
                elif group["module"] == "safe":
                    text = f"{entry.get('name', '')} — {entry.get('username', '')}"
                    child = QTreeWidgetItem([text])
                    child.setData(0, Qt.ItemDataRole.UserRole, entry)
                root.addChild(child)

            if root.childCount() == 0:
                no_result = QTreeWidgetItem(["无结果"])
                no_result.setFlags(no_result.flags() & ~Qt.ItemFlag.ItemIsSelectable)
                no_result.setForeground(0, Qt.GlobalColor.gray)
                root.addChild(no_result)

            self._tree.addTopLevelItem(root)
        self._tree.expandAll()

    def _on_item_double_click(self, item, column):
        entry = item.data(0, Qt.ItemDataRole.UserRole)
        if not entry:
            return
        parent = item.parent()
        if not parent:
            return
        module_label = parent.text(0)
        if "剪贴板" in module_label:
            self.jump_to.emit("clip", entry)
        elif "笔记" in module_label:
            self.jump_to.emit("note", entry)
        elif "密码" in module_label:
            self.jump_to.emit("safe", entry)

    # ---- 公共方法 ----
    def show_and_focus(self, x=None, y=None):
        """显示并聚焦搜索框。"""
        if x is not None and y is not None:
            self.move(x, y)
        self.show()
        self.raise_()
        self.activateWindow()
        self._search_input.setFocus()
        self._search_input.selectAll()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.hide()
        elif event.key() == Qt.Key.Key_Return and self._search_input.hasFocus():
            self._do_search()
        else:
            super().keyPressEvent(event)