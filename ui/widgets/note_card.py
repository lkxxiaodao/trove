"""笔记卡片控件 - NoteCard。

管理页面中的笔记卡片，显示标题、内容摘要、颜色、标签、浮动开关。
"""

from PySide6.QtWidgets import QFrame, QVBoxLayout, QHBoxLayout, QLabel, QCheckBox
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QMouseEvent, QTextDocument


class NoteCard(QFrame):
    """笔记卡片。

    信号:
        double_clicked(note_id): 双击编辑
        float_toggled(note_id, is_floating): 浮动开关切换
        delete_requested(note_id): 请求删除
    """

    double_clicked = Signal(int)
    float_toggled = Signal(int, bool)
    delete_requested = Signal(int)
    ghost_exit_requested = Signal(int)  # 点击幽灵按钮时发射

    def __init__(self, note_data: dict, parent=None):
        super().__init__(parent)
        self._note_id = note_data["id"]
        self._note_data = note_data
        self._is_floating = bool(note_data.get("is_floating", 0))
        self._is_ghost = False  # 幽灵模式指示（由 NotePage 设置）
        self._select_mode = False

        self.setFixedSize(220, 150)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._build_ui()
        self._apply_data()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 8)
        layout.setSpacing(4)

        # 标题行（选择框 + 颜色条 + 标题 + 浮动 / 删除按钮）
        top = QHBoxLayout()
        top.setSpacing(6)

        self._check_box = QCheckBox()
        self._check_box.setFixedSize(16, 16)
        self._check_box.hide()
        top.addWidget(self._check_box)

        self._color_bar = QLabel()
        self._color_bar.setFixedSize(4, 20)
        self._color_bar.setStyleSheet("border-radius: 2px; background: #ccc;")
        top.addWidget(self._color_bar)

        self._title_label = QLabel("未命名")
        title_font = QFont()
        title_font.setPointSize(11)
        title_font.setBold(True)
        self._title_label.setFont(title_font)
        self._title_label.setMaximumHeight(22)
        top.addWidget(self._title_label, 1)

        # ---- 浮动按钮（QLabel 模拟） ----
        self._float_btn = self._make_icon_label("📍", "悬浮置顶")
        self._float_btn.mousePressEvent = self._on_float_click
        top.addWidget(self._float_btn)

        # ---- 删除按钮（QLabel 模拟） ----
        self._del_btn = self._make_icon_label("✕", "删除笔记")
        self._del_btn.setStyleSheet("""
            QLabel {
                border: none;
                font-size: 14px;
                font-weight: bold;
                color: #999;
                background: transparent;
                padding: 2px;
            }
            QLabel:hover {
                color: #d32f2f;
                background: rgba(211, 47, 47, 0.1);
                border-radius: 4px;
            }
        """)
        self._del_btn.mousePressEvent = self._on_del_click
        top.addWidget(self._del_btn)

        layout.addLayout(top)

        # 内容摘要
        self._content_label = QLabel()
        self._content_label.setWordWrap(True)
        self._content_label.setStyleSheet(
            "color: #666; font-size: 12px;"
            "padding-top: 2px;"
            "line-height: 1.4;"
        )
        self._content_label.setMaximumHeight(44)
        layout.addWidget(self._content_label)

        layout.addStretch()

        # 底部：时间 + 标签（标签在右下角）
        bottom = QHBoxLayout()
        bottom.setSpacing(4)
        self._time_label = QLabel()
        self._time_label.setStyleSheet("color: #999; font-size: 10px;")
        bottom.addWidget(self._time_label)
        bottom.addStretch()
        self._tag_label = QLabel()
        self._tag_label.setMinimumWidth(40)
        self._tag_label.setStyleSheet(
            "color: #666; font-size: 10px;"
            "background: rgba(0,0,0,0.06); border-radius: 3px;"
            "padding: 2px 5px;"
        )
        self._tag_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        bottom.addWidget(self._tag_label)
        layout.addLayout(bottom)

        self._apply_float_style()

    def _apply_data(self):
        d = self._note_data
        self._title_label.setText(d.get("title") or "未命名")
        content = d.get("content") or ""
        # 如果是 HTML，用 QTextDocument 正确解析出纯文本
        if content.strip().startswith("<!DOCTYPE") or content.strip().startswith("<html") or "<" in content:
            doc = QTextDocument()
            doc.setHtml(content)
            plain = doc.toPlainText()
            self._content_label.setText(plain[:80] + ("..." if len(plain) > 80 else ""))
        else:
            self._content_label.setText(content[:80] + ("..." if len(content) > 80 else ""))

        color = d.get("color") or "#FFFFFF"
        font_color = d.get("font_color") or "#000000"
        self._color_bar.setStyleSheet(f"border-radius: 2px; background: {color};")
        self._refresh_border()
        # 应用字体颜色
        self._title_label.setStyleSheet(f"color: {font_color};")
        self._content_label.setStyleSheet(f"color: {font_color}; opacity: 0.7; font-size: 12px; padding-top: 2px;")

        self._apply_float_style()

        # 标签（右下角，最多 1 个）
        tags = d.get("tags") or []
        if tags:
            self._tag_label.setText(tags[0]["name"][:5])
            self._tag_label.show()
        else:
            self._tag_label.hide()

        # 时间
        import datetime
        ts = d.get("modified") or 0
        self._time_label.setText(
            datetime.datetime.fromtimestamp(ts).strftime("%m-%d %H:%M") if ts else ""
        )

    # ---- 按钮辅助 ----

    def _make_icon_label(self, text: str, tooltip: str) -> QLabel:
        """创建图标标签（用于模拟按钮，避开主题覆盖）。"""
        lbl = QLabel(text)
        lbl.setFixedSize(22, 22)
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setToolTip(tooltip)
        lbl.setCursor(Qt.CursorShape.PointingHandCursor)
        return lbl

    def _on_float_click(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            if self._is_ghost:
                # 幽灵模式下点击 → 退出幽灵模式
                self.ghost_exit_requested.emit(self._note_id)
            else:
                self._is_floating = not self._is_floating
                self._apply_float_style()
                self.float_toggled.emit(self._note_id, self._is_floating)

    def _on_del_click(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self.delete_requested.emit(self._note_id)

    def _apply_float_style(self):
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

    def set_floating_state(self, floating: bool):
        """外部设置浮动状态（不触发信号）。"""
        self._is_floating = floating
        self._apply_float_style()

    def set_ghost_state(self, ghost: bool):
        """外部设置幽灵状态指示器（不触发信号）。"""
        self._is_ghost = ghost
        self._apply_float_style()

    def update_data(self, note_data: dict):
        self._note_data = note_data
        self._is_floating = bool(note_data.get("is_floating", 0))
        self._is_ghost = False  # 重置幽灵状态，由 NotePage 重新同步
        self._apply_data()

    def mouseDoubleClickEvent(self, event):
        if not self._select_mode:
            self.double_clicked.emit(self._note_id)
        super().mouseDoubleClickEvent(event)

    def mousePressEvent(self, event):
        if self._select_mode and event.button() == Qt.MouseButton.LeftButton:
            self._check_box.setChecked(not self._check_box.isChecked())
            self._refresh_border()
        super().mousePressEvent(event)

    def _refresh_border(self):
        """刷新选择模式下的边框高亮。"""
        d = self._note_data
        color = d.get("color") or "#FFFFFF"
        border_style = "1px solid #ddd"
        if self._select_mode and self._check_box.isChecked():
            border_style = "3px solid #1a73e8"
        self.setStyleSheet(f"""
            NoteCard {{
                background: {color};
                border: {border_style};
                border-radius: 8px;
            }}
            NoteCard:hover {{
                border-color: #4a9eff;
            }}
        """)

    # ---- 选择模式 ----

    def set_select_mode(self, enabled: bool):
        """切换选择模式，显示/隐藏复选框。"""
        self._select_mode = enabled
        self._check_box.setVisible(enabled)
        self._del_btn.setVisible(not enabled)
        if not enabled:
            self._check_box.setChecked(False)
        # 刷新边框以显示/隐藏选中高亮
        self._refresh_border()

    def is_checked(self) -> bool:
        return self._check_box.isChecked()