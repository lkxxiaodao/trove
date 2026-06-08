"""任务笔记卡片 - TaskNoteCard。

显示为带勾选框的清单列表，支持悬浮和定时展示。
"""

import json
from PySide6.QtWidgets import QFrame, QVBoxLayout, QHBoxLayout, QLabel, QCheckBox, QWidget
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont


class TaskNoteCard(QFrame):
    """任务笔记卡片（清单视图）。"""

    double_clicked = Signal(int)
    delete_requested = Signal(int)
    float_toggled = Signal(int, bool)
    ghost_exit_requested = Signal(int)  # 点击幽灵按钮时发射
    item_checked = Signal(int, int, bool)  # note_id, item_index, checked

    def __init__(self, note_data: dict, parent=None):
        super().__init__(parent)
        self._note_id = note_data["id"]
        self._note_data = note_data
        self._items: list[dict] = []
        self._checkboxes: list[QCheckBox] = []
        self._is_floating = bool(note_data.get("is_floating", 0))
        self._is_ghost = False  # 幽灵模式指示（由 NotePage 设置）
        self._select_mode = False
        self._selected = False

        self.setFixedSize(220, 150)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._parse_content()
        self._build_ui()
        self._apply_color()

    def _parse_content(self):
        content = self._note_data.get("content", "")
        try:
            self._items = json.loads(content)
        except (json.JSONDecodeError, TypeError):
            lines = [l.strip() for l in content.split("\n") if l.strip()]
            self._items = [{"text": line, "checked": False} for line in lines]

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 6)
        layout.setSpacing(4)

        # 标题行（标题 + 浮动 + 删除）
        title_row = QHBoxLayout()
        title_row.setSpacing(6)

        self._title_label = QLabel(self._note_data.get("title") or "未命名")
        title_font = QFont()
        title_font.setPointSize(11)
        title_font.setBold(True)
        self._title_label.setFont(title_font)
        self._title_label.setMaximumHeight(22)
        title_row.addWidget(self._title_label, 1)

        # 浮动按钮
        self._float_btn = QLabel("📍" if not self._is_floating else "📌")
        self._float_btn.setFixedSize(22, 22)
        self._float_btn.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._float_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._float_btn.setToolTip("悬浮置顶" if not self._is_floating else "取消悬浮")
        self._float_btn.mousePressEvent = self._on_float_click
        title_row.addWidget(self._float_btn)

        # 删除按钮
        del_btn = QLabel("✕")
        del_btn.setFixedSize(22, 22)
        del_btn.setAlignment(Qt.AlignmentFlag.AlignCenter)
        del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        del_btn.setToolTip("删除笔记")
        del_btn.setStyleSheet("""
            QLabel { border: none; font-size: 14px; font-weight: bold; color: #999; background: transparent; padding: 2px; }
            QLabel:hover { color: #d32f2f; background: rgba(211,47,47,0.1); border-radius: 4px; }
        """)
        del_btn.mousePressEvent = lambda e: self.delete_requested.emit(self._note_id)
        title_row.addWidget(del_btn)

        layout.addLayout(title_row)

        # 任务条目（最多显示 4 条）
        self._item_widget = QWidget()
        self._item_widget.setStyleSheet("background: transparent;")
        item_layout = QVBoxLayout(self._item_widget)
        item_layout.setContentsMargins(0, 2, 0, 0)
        item_layout.setSpacing(1)

        self._checkboxes.clear()
        for i, item in enumerate(self._items):
            cb = QCheckBox(item["text"])
            cb.setChecked(item.get("checked", False))
            cb.setStyleSheet("font-size: 12px;")
            if item.get("checked"):
                cb.setStyleSheet("color: #999; font-size: 12px; text-decoration: line-through;")
            cb.toggled.connect(lambda checked, idx=i: self._on_check(idx, checked))
            item_layout.addWidget(cb)
            self._checkboxes.append(cb)

        item_layout.addStretch()
        layout.addWidget(self._item_widget, 1)

    def _apply_color(self):
        d = self._note_data
        color = d.get("color") or "#FFFFFF"
        font_color = d.get("font_color") or "#000000"
        border = "3px solid #1a73e8" if self._select_mode and self._selected else "1px solid #ddd"
        self.setStyleSheet(f"""
            TaskNoteCard {{
                background: {color};
                border: {border};
                border-radius: 8px;
            }}
            TaskNoteCard:hover {{
                border-color: #4a9eff;
            }}
        """)
        self._title_label.setStyleSheet(f"color: {font_color};")
        # 应用到勾选框
        for i, cb in enumerate(self._checkboxes):
            if i < len(self._items) and self._items[i].get("checked"):
                cb.setStyleSheet("color: #999; font-size: 12px; text-decoration: line-through;")
            else:
                cb.setStyleSheet(f"color: {font_color}; font-size: 12px;")

    def _on_check(self, idx: int, checked: bool):
        if idx < len(self._items):
            self._items[idx]["checked"] = checked
        cb = self._checkboxes[idx]
        font_color = self._note_data.get("font_color", "#000000")
        if checked:
            cb.setStyleSheet("color: #999; font-size: 12px; text-decoration: line-through;")
        else:
            cb.setStyleSheet(f"color: {font_color}; font-size: 12px;")
        self.item_checked.emit(self._note_id, idx, checked)

    def _on_float_click(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self._is_ghost:
                # 幽灵模式下点击 → 退出幽灵模式
                self.ghost_exit_requested.emit(self._note_id)
            else:
                self._is_floating = not self._is_floating
                self._refresh_float_btn()
                self.float_toggled.emit(self._note_id, self._is_floating)

    def _refresh_float_btn(self):
        """刷新浮动按钮的文字和样式。"""
        if self._is_ghost:
            self._float_btn.setText("👻")
            self._float_btn.setToolTip("幽灵模式中 — 点击退出幽灵模式")
            self._float_btn.setStyleSheet("""
                QLabel {
                    border: none;
                    font-size: 14px;
                    background: transparent;
                    padding: 2px;
                }
                QLabel:hover {
                    background: rgba(128, 0, 128, 0.15);
                    border-radius: 4px;
                }
            """)
        elif self._is_floating:
            self._float_btn.setText("📌")
            self._float_btn.setToolTip("取消悬浮")
            self._float_btn.setStyleSheet("""
                QLabel {
                    border: none;
                    font-size: 14px;
                    background: transparent;
                    padding: 2px;
                }
                QLabel:hover {
                    background: rgba(0, 0, 0, 0.08);
                    border-radius: 4px;
                }
            """)
        else:
            self._float_btn.setText("📍")
            self._float_btn.setToolTip("悬浮置顶")
            self._float_btn.setStyleSheet("""
                QLabel {
                    border: none;
                    font-size: 12px;
                    background: transparent;
                    padding: 2px;
                }
                QLabel:hover {
                    background: rgba(0, 0, 0, 0.08);
                    border-radius: 4px;
                }
            """)

    def mouseDoubleClickEvent(self, event):
        if not self._select_mode:
            self.double_clicked.emit(self._note_id)
        super().mouseDoubleClickEvent(event)

    def mousePressEvent(self, event):
        if self._select_mode and event.button() == Qt.MouseButton.LeftButton:
            self._selected = not self._selected
            self._apply_color()
        super().mousePressEvent(event)

    def set_floating_state(self, floating: bool):
        self._is_floating = floating
        self._refresh_float_btn()

    def set_ghost_state(self, ghost: bool):
        """外部设置幽灵状态指示器（不触发信号）。"""
        self._is_ghost = ghost
        self._refresh_float_btn()

    def get_items(self) -> list[dict]:
        return self._items

    def set_select_mode(self, enabled: bool):
        """切换选择模式（点击卡片切换选中状态）。"""
        self._select_mode = enabled
        self._selected = False
        self._apply_color()

    def is_checked(self) -> bool:
        return self._selected

    def update_data(self, note_data: dict):
        self._note_data = note_data
        self._is_floating = bool(note_data.get("is_floating", 0))
        self._is_ghost = False  # 重置幽灵状态，由 NotePage 重新同步
        self._parse_content()
        # 增量更新勾选框状态（避免重建整个 UI）
        for i, cb in enumerate(self._checkboxes):
            if i < len(self._items):
                cb.setChecked(self._items[i].get("checked", False))
                font_color = self._note_data.get("font_color", "#000000")
                if self._items[i].get("checked"):
                    cb.setStyleSheet("color: #999; font-size: 12px; text-decoration: line-through;")
                else:
                    cb.setStyleSheet(f"color: {font_color}; font-size: 12px;")
        self._apply_color()
