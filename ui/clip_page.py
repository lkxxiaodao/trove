"""剪贴板历史页面 - ClipCache。

功能：搜索框、星标过滤、历史列表（自定义委托）、右键菜单、一键复制、转笔记、正则删除。
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton,
    QListView, QMenu, QLabel, QDialog, QTextEdit, QDialogButtonBox,
    QGroupBox, QFormLayout, QMessageBox,
)
from PySide6.QtCore import Qt, QTimer, Signal, QSize
from PySide6.QtGui import QStandardItemModel, QStandardItem, QAction
from PySide6.QtGui import QClipboard
from PySide6.QtWidgets import QApplication

from core.clipboard_monitor import ClipStore, ClipboardMonitor
from ui.widgets.clip_item_delegate import ClipItemDelegate


class RegexDemoDialog(QDialog):
    """正则表达式演示对话框，帮助用户理解正则表达式。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("正则表达式演示")
        self.setMinimumSize(500, 450)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)

        desc = QLabel(
            "正则表达式用于匹配文本模式，删除匹配的剪贴板条目。\n"
            "输入正则表达式后点击「预览匹配」，可以查看哪些条目会被删除。"
        )
        desc.setWordWrap(True)
        layout.addWidget(desc)

        # 常用示例
        examples_group = QGroupBox("常用正则示例")
        examples_layout = QFormLayout(examples_group)
        examples = [
            ("\\d{15,19}", "匹配 15-19 位数字（如银行卡号、身份证号）"),
            ("\\d{3,4}-\\d{7,8}", "匹配电话号码（如 010-12345678）"),
            ("[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}", "匹配邮箱地址"),
            ("https?://[^\\s]+", "匹配网址（http/https）"),
            ("^\\s*$", "匹配空行或空白内容"),
            ("password|密码|secret", "匹配包含敏感词的内容"),
            (".{100,}", "匹配长度超过 100 个字符的内容"),
            ("^\\d+$", "匹配纯数字内容"),
        ]
        for pattern, desc_text in examples:
            label = QLabel(f"<b>{pattern}</b>")
            label.setTextFormat(Qt.TextFormat.RichText)
            label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            desc_label = QLabel(desc_text)
            desc_label.setStyleSheet("color: #888;")
            examples_layout.addRow(label, desc_label)

        layout.addWidget(examples_group)

        # 提示
        tip = QLabel(
            "提示：\n"
            "- \\d 匹配数字，\\w 匹配字母数字下划线，\\s 匹配空白\n"
            "- . 匹配任意字符，* 表示0次或多次，+ 表示1次或多次\n"
            "- ^ 匹配开头，$ 匹配结尾，| 表示或\n"
            "- {n,m} 表示重复 n 到 m 次\n"
            "- 特殊字符如 . * + ? ( ) [ ] { } \\ 需要加 \\ 转义"
        )
        tip.setWordWrap(True)
        tip.setStyleSheet("color: #666; padding: 8px; background: #f0f0f0; border-radius: 4px;")
        layout.addWidget(tip)

        btn_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        btn_box.accepted.connect(self.accept)
        layout.addWidget(btn_box)


class RegexDeleteDialog(QDialog):
    """正则表达式删除对话框。"""

    def __init__(self, clip_store: ClipStore, parent=None):
        super().__init__(parent)
        self._store = clip_store
        self.setWindowTitle("正则表达式删除剪贴板条目")
        self.setMinimumSize(500, 350)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)

        desc = QLabel("输入正则表达式，匹配的剪贴板条目将被删除。\n此操作不可撤销，请谨慎使用。")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        # 正则输入
        input_layout = QHBoxLayout()
        self._regex_input = QLineEdit()
        self._regex_input.setPlaceholderText("输入正则表达式，如 \\d{15,19}")
        self._regex_input.textChanged.connect(self._on_regex_changed)
        input_layout.addWidget(self._regex_input, 1)

        demo_btn = QPushButton("正则演示")
        demo_btn.clicked.connect(self._show_demo)
        input_layout.addWidget(demo_btn)
        layout.addLayout(input_layout)

        # 预览区域
        self._preview_label = QLabel("")
        self._preview_label.setWordWrap(True)
        self._preview_label.setStyleSheet("color: #888; min-height: 20px;")
        layout.addWidget(self._preview_label)

        self._preview_text = QTextEdit()
        self._preview_text.setReadOnly(True)
        self._preview_text.setPlaceholderText("匹配预览将在此显示...")
        self._preview_text.setMaximumHeight(150)
        layout.addWidget(self._preview_text)

        # 预览按钮
        preview_btn = QPushButton("预览匹配条目")
        preview_btn.clicked.connect(self._preview_matches)
        layout.addWidget(preview_btn)

        # 按钮
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)
        self._delete_btn = QPushButton("删除匹配条目")
        self._delete_btn.setStyleSheet("color: red; font-weight: bold;")
        self._delete_btn.clicked.connect(self._delete_matches)
        self._delete_btn.setEnabled(False)
        btn_layout.addWidget(self._delete_btn)
        layout.addLayout(btn_layout)

    def _on_regex_changed(self):
        self._delete_btn.setEnabled(False)
        self._preview_text.clear()
        self._preview_label.clear()

    def _show_demo(self):
        dlg = RegexDemoDialog(self)
        dlg.exec()

    def _preview_matches(self):
        pattern = self._regex_input.text().strip()
        if not pattern:
            self._preview_label.setText("请输入正则表达式")
            return
        import re
        try:
            regex = re.compile(pattern)
        except re.error as e:
            self._preview_label.setText(f"正则表达式无效: {e}")
            return

        rows = self._store.get_recent(limit=10000)
        matches = [row for row in rows if regex.search(row["content"])]
        if not matches:
            self._preview_label.setText("没有匹配的条目")
            self._preview_text.clear()
            return

        self._preview_label.setText(f"共匹配 {len(matches)} 条")
        preview_lines = []
        for row in matches[:20]:
            content = row["content"][:80].replace("\n", " ")
            preview_lines.append(f"[ID:{row['id']}] {content}...")
        if len(matches) > 20:
            preview_lines.append(f"... 还有 {len(matches) - 20} 条")
        self._preview_text.setPlainText("\n".join(preview_lines))
        self._delete_btn.setEnabled(True)

    def _delete_matches(self):
        pattern = self._regex_input.text().strip()
        if not pattern:
            return
        try:
            count = self._store.delete_by_regex(pattern)
            QMessageBox.information(self, "删除完成", f"已删除 {count} 条匹配的剪贴板条目。")
            self.accept()
        except ValueError as e:
            QMessageBox.warning(self, "错误", str(e))


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
        self._star_btn.setFixedWidth(64)
        self._star_btn.toggled.connect(self._on_star_filter)
        toolbar.addWidget(self._star_btn)

        self._regex_delete_btn = QPushButton("正则删除")
        self._regex_delete_btn.setFixedWidth(100)
        self._regex_delete_btn.clicked.connect(self._on_regex_delete)
        toolbar.addWidget(self._regex_delete_btn)

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

    def _on_regex_delete(self):
        """打开正则删除对话框。"""
        dlg = RegexDeleteDialog(self._store, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
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