"""任务笔记悬浮窗口 - TaskNoteFloat。

与 TaskNoteCard 类似的交互式勾选框清单，可拖拽移动和缩放。
"""

import json
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QCheckBox,
    QSizeGrip,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QMouseEvent


class TaskNoteFloat(QWidget):
    """任务笔记悬浮窗（可交互勾选）。"""

    unfloated = Signal(int)
    items_changed = Signal(int, list)  # note_id, items

    def __init__(self, note_data: dict, parent=None):
        flags = Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
        super().__init__(parent, flags)
        self._note_id = note_data["id"]
        self._note_data = note_data
        self._items: list[dict] = []
        self._checkboxes: list[QCheckBox] = []
        self._drag_pos = None
        self._parse_content()

        self.setMinimumSize(200, 160)
        self._build_ui()
        self.resize(300, 240)
        self._show_smart()

    def _parse_content(self):
        content = self._note_data.get("content", "")
        try:
            self._items = json.loads(content)
            # 深拷贝以保留原始数据用于对比
            self._items = [dict(it) for it in self._items]
        except (json.JSONDecodeError, TypeError):
            lines = [l.strip() for l in content.split("\n") if l.strip()]
            self._items = [{"text": line, "checked": False} for line in lines]

    def _build_ui(self):
        d = self._note_data
        color = d.get("color") or "#FFFFFF"
        font_color = d.get("font_color") or "#000000"

        self.setObjectName("TaskNoteFloat")
        self.setStyleSheet(f"""
            #TaskNoteFloat {{
                background: {color};
                border: 1px solid #ccc;
                border-radius: 6px;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ---- 标题栏（拖拽手柄） ----
        title_bar = QWidget()
        title_bar.setFixedHeight(32)
        title_bar.setCursor(Qt.CursorShape.SizeAllCursor)
        title_bar.setStyleSheet("background: rgba(0,0,0,0.04); border-radius: 6px 6px 0 0;")
        title_bar.mousePressEvent = self._title_press
        title_bar.mouseMoveEvent = self._title_move
        title_bar.mouseReleaseEvent = self._title_release

        tb_layout = QHBoxLayout(title_bar)
        tb_layout.setContentsMargins(10, 0, 4, 0)
        tb_layout.setSpacing(6)

        title_lbl = QLabel(d.get("title", "任务笔记"))
        title_font = QFont()
        title_font.setBold(True)
        title_lbl.setFont(title_font)
        title_lbl.setStyleSheet(f"color: {font_color}; background: transparent;")
        tb_layout.addWidget(title_lbl, 1)

        close_btn = QLabel("✕")
        close_btn.setFixedSize(24, 24)
        close_btn.setAlignment(Qt.AlignmentFlag.AlignCenter)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setToolTip("关闭悬浮")
        close_btn.setStyleSheet("""
            QLabel { border: none; font-size: 14px; font-weight: bold; color: #999; background: transparent; padding: 2px; }
            QLabel:hover { color: #d32f2f; background: rgba(211,47,47,0.1); border-radius: 4px; }
        """)
        close_btn.mousePressEvent = lambda e: self.unfloated.emit(self._note_id)
        tb_layout.addWidget(close_btn)

        layout.addWidget(title_bar)

        # ---- 任务条目 ----
        items_layout = QVBoxLayout()
        items_layout.setContentsMargins(10, 8, 10, 8)
        items_layout.setSpacing(4)

        for i, item in enumerate(self._items):
            cb = QCheckBox(item["text"])
            cb.setChecked(item.get("checked", False))
            cb.setStyleSheet(f"color: {font_color}; font-size: 13px;")
            if item.get("checked"):
                cb.setStyleSheet("color: #999; font-size: 13px; text-decoration: line-through;")
            cb.toggled.connect(lambda checked, idx=i: self._on_check(idx, checked))
            items_layout.addWidget(cb)
            self._checkboxes.append(cb)

        items_layout.addStretch()
        layout.addLayout(items_layout, 1)

        # ---- 底部：调整手柄 ----
        bottom = QHBoxLayout()
        bottom.setContentsMargins(6, 2, 6, 4)
        grip = QSizeGrip(self)
        grip.setFixedSize(16, 16)
        grip.setStyleSheet("background: transparent;")
        bottom.addWidget(grip)
        bottom.addStretch()
        layout.addLayout(bottom)

    def _on_check(self, idx: int, checked: bool):
        if idx < len(self._items):
            self._items[idx]["checked"] = checked
        cb = self._checkboxes[idx]
        font_color = self._note_data.get("font_color", "#000000")
        if checked:
            cb.setStyleSheet("color: #999; font-size: 13px; text-decoration: line-through;")
        else:
            cb.setStyleSheet(f"color: {font_color}; font-size: 13px;")
        self.items_changed.emit(self._note_id, list(self._items))

    def _show_smart(self):
        from PySide6.QtWidgets import QApplication
        screen = QApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            self.move(geo.right() - 320, geo.top() + 100)
        self.show()

    # ---- 拖拽 ----
    def _title_press(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint()

    def _title_move(self, event: QMouseEvent):
        if self._drag_pos is not None:
            delta = event.globalPosition().toPoint() - self._drag_pos
            self.move(self.pos() + delta)
            self._drag_pos = event.globalPosition().toPoint()

    def _title_release(self, event: QMouseEvent):
        self._drag_pos = None

    def update_data(self, note_data: dict):
        self._note_data = note_data
        self._parse_content()
        # 简单重建 — close 后由页面重新打开
