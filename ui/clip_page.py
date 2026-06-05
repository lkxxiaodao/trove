"""剪贴板历史页面 - ClipCache。

功能：搜索框、星标过滤、历史列表（自定义委托）、右键菜单、一键复制、转笔记。
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton,
    QListView, QMenu, QLabel,
)
from PySide6.QtCore import Qt, QTimer, Signal, QSize
from PySide6.QtGui import QStandardItemModel, QStandardItem, QAction
from PySide6.QtGui import QClipboard
from PySide6.QtWidgets import QApplication

from core.clipboard_monitor import ClipStore, ClipboardMonitor
from ui.widgets.clip_item_delegate import ClipItemDelegate


class ClipPage(QWidget):
    """剪贴板历史页面。"""

    convert_to_note = Signal(str)  # 转笔记信号，携带内容

    def __init__(self, clip_store: ClipStore, monitor: ClipboardMonitor = None):
        super().__init__()
        self._store = clip_store
        self._monitor = monitor
        self._starred_only = False
        self._init_ui()
        self._load_data()

        # 监听新内容
        if self._monitor:
            self._monitor.new_content.connect(self._on_new_content)

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        # ---- 顶部工具栏 ----
        toolbar = QHBoxLayout()

        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("搜索剪贴板历史...")
        self._search_input.setClearButtonEnabled(True)
        self._search_input.textChanged.connect(self._on_search)
        toolbar.addWidget(self._search_input, 1)

        self._star_btn = QPushButton("星标")
        self._star_btn.setCheckable(True)
        self._star_btn.setFixedWidth(60)
        self._star_btn.toggled.connect(self._on_star_filter)
        toolbar.addWidget(self._star_btn)

        layout.addLayout(toolbar)

        # ---- 列表 ----
        self._model = QStandardItemModel()
        self._list_view = QListView()
        self._list_view.setModel(self._model)
        self._delegate = ClipItemDelegate()
        self._delegate.set_star_callback(self._on_star_clicked)
        self._list_view.setItemDelegate(self._delegate)
        self._list_view.setEditTriggers(QListView.EditTrigger.NoEditTriggers)
        self._list_view.setSelectionMode(QListView.SelectionMode.SingleSelection)
        self._list_view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._list_view.customContextMenuRequested.connect(self._on_context_menu)
        self._list_view.doubleClicked.connect(self._on_double_click)
        self._list_view.setVerticalScrollMode(QListView.ScrollMode.ScrollPerPixel)
        layout.addWidget(self._list_view, 1)

        # ---- 底部状态栏 ----
        self._status_label = QLabel("共 0 条")
        self._status_label.setStyleSheet("color: #888; padding: 4px;")
        layout.addWidget(self._status_label)

    # ---- 数据加载 ----
    def _load_data(self):
        keyword = self._search_input.text().strip()
        if keyword:
            rows = self._store.search(keyword, self._starred_only)
        else:
            rows = self._store.get_recent(starred_only=self._starred_only)

        self._model.clear()
        for row in rows:
            item = QStandardItem()
            item.setData(dict(row), Qt.ItemDataRole.UserRole)
            item.setSizeHint(QSize(0, 48))
            self._model.appendRow(item)

        self._status_label.setText(f"共 {len(rows)} 条")

    def _on_new_content(self, text: str):
        self._load_data()

    def _on_search(self):
        self._load_data()

    def _on_star_filter(self, checked: bool):
        self._starred_only = checked
        self._star_btn.setText("星标 ★" if checked else "星标")
        self._load_data()

    # ---- 交互 ----
    def _on_double_click(self, index):
        data = index.data(Qt.ItemDataRole.UserRole)
        if data:
            QApplication.clipboard().setText(data["content"])

    def _on_context_menu(self, pos):
        index = self._list_view.indexAt(pos)
        if not index.isValid():
            return
        data = index.data(Qt.ItemDataRole.UserRole)
        if not data:
            return

        menu = QMenu(self)

        copy_action = QAction("复制", menu)
        copy_action.triggered.connect(lambda: QApplication.clipboard().setText(data["content"]))
        menu.addAction(copy_action)

        menu.addSeparator()

        convert_action = QAction("转为笔记", menu)
        convert_action.triggered.connect(lambda: self.convert_to_note.emit(data["content"]))
        menu.addAction(convert_action)

        menu.addSeparator()

        delete_action = QAction("删除", menu)
        delete_action.triggered.connect(lambda: self._delete_item(data["id"]))
        menu.addAction(delete_action)

        menu.exec(self._list_view.viewport().mapToGlobal(pos))

    def _toggle_star(self, clip_id: int):
        self._store.toggle_star(clip_id)
        self._load_data()

    def _on_star_clicked(self, clip_id: int):
        """星标按钮点击回调。"""
        self._toggle_star(clip_id)

    def _delete_item(self, clip_id: int):
        self._store.delete(clip_id)
        self._load_data()


def create_page(clip_store: ClipStore, monitor: ClipboardMonitor = None) -> QWidget:
    """创建 ClipCache 页面（工厂函数）。"""
    return ClipPage(clip_store, monitor)