"""笔记编辑对话框 - NoteEditor。

编辑标题、内容、颜色、标签。
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLineEdit, QTextEdit,
    QPushButton, QLabel, QMessageBox,
)
from PySide6.QtCore import Signal

from core.note_manager import NoteStore


class NoteEditor(QDialog):
    """笔记编辑对话框。

    信号:
        saved(note_id): 保存成功后发出
    """

    saved = Signal(int)

    COLORS = {
        "默认": "#FFFFFF",
        "黄色": "#FFF9C4",
        "绿色": "#C8E6C9",
        "蓝色": "#BBDEFB",
        "粉色": "#F8BBD0",
        "紫色": "#E1BEE7",
        "灰色": "#F5F5F5",
        "橙色": "#FFE0B2",
    }

    def __init__(self, note_store: NoteStore, note_data: dict = None, parent=None):
        super().__init__(parent)
        self._store = note_store
        self._note_data = note_data
        self._is_new = note_data is None
        self._selected_color = note_data.get("color", "#FFFFFF") if note_data else "#FFFFFF"
        tags = note_data.get("tags", []) if note_data else []
        self._tag_id = tags[0]["id"] if tags else None  # 最多 1 个标签

        self.setWindowTitle("新建笔记" if self._is_new else "编辑笔记")
        self.resize(480, 480)
        self.setMinimumSize(400, 350)
        self._init_ui()
        self._load_data()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # ---- 标题 ----
        layout.addWidget(QLabel("标题"))
        self._title_edit = QLineEdit()
        self._title_edit.setPlaceholderText("输入笔记标题...")
        layout.addWidget(self._title_edit)

        # ---- 内容 ----
        layout.addWidget(QLabel("内容"))
        self._content_edit = QTextEdit()
        self._content_edit.setPlaceholderText("输入笔记内容...")
        self._content_edit.setMinimumHeight(120)
        layout.addWidget(self._content_edit, 1)

        # ---- 颜色 ----
        layout.addWidget(QLabel("颜色"))
        color_layout = QHBoxLayout()
        color_layout.setSpacing(4)
        self._color_buttons = {}
        for name, color in self.COLORS.items():
            btn = QPushButton()
            btn.setFixedSize(28, 28)
            btn.setToolTip(name)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: {color};
                    border: 2px solid #ccc;
                    border-radius: 4px;
                }}
                QPushButton:hover {{
                    border-color: #888;
                }}
            """)
            btn.clicked.connect(lambda checked, c=color: self._on_color_pick(c))
            color_layout.addWidget(btn)
            self._color_buttons[name] = btn
        color_layout.addStretch()
        layout.addLayout(color_layout)

        # ---- 标签（最多 1 个，最多 5 字） ----
        layout.addWidget(QLabel("标签（最多 5 字）"))
        tag_layout = QHBoxLayout()
        tag_layout.setSpacing(6)
        self._tag_input = QLineEdit()
        self._tag_input.setPlaceholderText("输入标签名后回车添加...")
        self._tag_input.setMaxLength(5)
        self._tag_input.returnPressed.connect(self._add_tag)
        tag_layout.addWidget(self._tag_input, 1)
        layout.addLayout(tag_layout)

        self._current_tag_chip = QPushButton()
        self._current_tag_chip.setFixedHeight(24)
        self._current_tag_chip.setStyleSheet("""
            QPushButton {
                background: #e0e0e0;
                border: none;
                border-radius: 4px;
                padding: 0 8px;
                font-size: 12px;
            }
            QPushButton:hover {
                background: #ccc;
            }
        """)
        self._current_tag_chip.hide()
        self._current_tag_chip.clicked.connect(self._remove_tag)
        layout.addWidget(self._current_tag_chip)

        # ---- 按钮 ----
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)
        save_btn = QPushButton("保存")
        save_btn.setDefault(True)
        save_btn.clicked.connect(self._on_save)
        btn_layout.addWidget(save_btn)
        layout.addLayout(btn_layout)

    def _load_data(self):
        if self._note_data:
            self._title_edit.setText(self._note_data.get("title", ""))
            self._content_edit.setPlainText(self._note_data.get("content", ""))
            self._selected_color = self._note_data.get("color", "#FFFFFF")
            tags = self._note_data.get("tags", [])
            self._tag_id = tags[0]["id"] if tags else None
        self._refresh_tag_chip()

    def _on_color_pick(self, color: str):
        self._selected_color = color

    def _add_tag(self):
        name = self._tag_input.text().strip()[:5]
        if not name:
            return
        tag_id = self._store.add_tag(name)
        if tag_id > 0:
            self._tag_id = tag_id  # 只保留 1 个，新标签替换旧标签
        self._tag_input.clear()
        self._refresh_tag_chip()

    def _refresh_tag_chip(self):
        if self._tag_id:
            all_tags = self._store.get_all_tags()
            tag_name = next((t["name"] for t in all_tags if t["id"] == self._tag_id), str(self._tag_id))
            self._current_tag_chip.setText(f"× {tag_name}")
            self._current_tag_chip.show()
        else:
            self._current_tag_chip.hide()

    def _remove_tag(self):
        self._tag_id = None
        self._refresh_tag_chip()

    def _on_save(self):
        title = self._title_edit.text().strip()
        if not title:
            QMessageBox.warning(self, "提示", "标题不能为空")
            return

        # 先处理输入框中还未回车确认的标签
        self._flush_tag_input()

        content = self._content_edit.toPlainText()

        if self._is_new:
            note_id = self._store.create(title, content)
        else:
            note_id = self._note_data["id"]
            self._store.update(note_id, title=title, content=content)

        self._store.update(note_id, color=self._selected_color)
        self._store.set_note_tags(note_id, [self._tag_id] if self._tag_id else [])
        self.saved.emit(note_id)
        self.accept()

    def _flush_tag_input(self):
        """将输入框中的未回车文本转为标签（供保存时调用）。"""
        name = self._tag_input.text().strip()[:5]
        if name:
            tag_id = self._store.add_tag(name)
            if tag_id > 0:
                self._tag_id = tag_id
            self._tag_input.clear()
            self._refresh_tag_chip()