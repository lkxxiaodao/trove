"""任务笔记悬浮窗口 - TaskNoteFloat。

与 TaskNoteCard 类似的交互式勾选框清单，可拖拽移动和缩放。
支持锁定（锁定后禁止移动和缩放，可勾选）。
"""

import os
import json
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QCheckBox,
    QSizeGrip, QPushButton, QColorDialog,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QMouseEvent, QPixmap, QColor

_ASSETS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "assets")


class TaskNoteFloat(QWidget):
    """任务笔记悬浮窗（可交互勾选）。"""

    unfloated = Signal(int)
    items_changed = Signal(int, list)  # note_id, items
    ghost_changed = Signal(int, bool)  # note_id, is_ghost

    def __init__(self, note_data: dict, parent=None):
        flags = Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
        super().__init__(parent, flags)
        self._note_id = note_data["id"]
        self._note_data = note_data
        self._items: list[dict] = []
        self._checkboxes: list[QCheckBox] = []
        self._drag_pos = None
        self._is_locked = False
        self._is_ghost = False
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

        self._title_lbl = QLabel(d.get("title", "任务笔记"))
        title_font = QFont()
        title_font.setBold(True)
        self._title_lbl.setFont(title_font)
        self._title_lbl.setStyleSheet(f"color: {font_color}; background: transparent;")
        tb_layout.addWidget(self._title_lbl, 1)

        # 颜色切换按钮（前 5 个预设）
        from config import AppConfig
        config = AppConfig.instance()
        preset = config.NOTE_PRESET_COLORS
        for entry in preset[:5]:
            btn = QPushButton()
            btn.setFixedSize(14, 14)
            btn.setStyleSheet(f"background: {entry['bg']}; border: 1px solid #bbb; border-radius: 3px;")
            btn.setToolTip(f"{entry['name']} (字体: {entry['font']})")
            btn.clicked.connect(lambda checked, bg=entry['bg'], fg=entry['font']: self._set_color(bg, fg))
            tb_layout.addWidget(btn)

        # 自定义颜色按钮
        custom_btn = QPushButton("🎨")
        custom_btn.setFixedSize(18, 18)
        custom_btn.setStyleSheet(
            "QPushButton { border: none; font-size: 12px; padding: 0; }"
            "QPushButton:hover { background: rgba(0,0,0,0.1); border-radius: 3px; }"
        )
        custom_btn.setToolTip("自定义背景色")
        custom_btn.clicked.connect(self._on_custom_color)
        tb_layout.addWidget(custom_btn)

        # 透明度调控（-/+ 按钮）
        self._opacity_label = QLabel("100%")
        self._opacity_label.setFixedWidth(30)
        self._opacity_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._opacity_label.setStyleSheet("color: #888; font-size: 10px; background: transparent;")
        tb_layout.addWidget(self._opacity_label)

        minus_btn = QPushButton("−")
        minus_btn.setFixedSize(16, 16)
        minus_btn.setStyleSheet("QPushButton { border: 1px solid #ccc; border-radius: 3px; font-size: 10px; padding: 0; } QPushButton:hover { background: #eee; }")
        minus_btn.clicked.connect(lambda: self._adjust_opacity(-5))
        tb_layout.addWidget(minus_btn)

        plus_btn = QPushButton("+")
        plus_btn.setFixedSize(16, 16)
        plus_btn.setStyleSheet("QPushButton { border: 1px solid #ccc; border-radius: 3px; font-size: 10px; padding: 0; } QPushButton:hover { background: #eee; }")
        plus_btn.clicked.connect(lambda: self._adjust_opacity(5))
        tb_layout.addWidget(plus_btn)

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
        self._items_layout = QVBoxLayout()
        self._items_layout.setContentsMargins(10, 8, 10, 8)
        self._items_layout.setSpacing(4)
        self._build_checkboxes(font_color)
        self._items_layout.addStretch()
        layout.addLayout(self._items_layout, 1)

        # ---- 底部：锁 + 调整手柄 ----
        bottom = QHBoxLayout()
        bottom.setContentsMargins(8, 2, 6, 4)
        bottom.setSpacing(4)

        self._lock_btn = QLabel()
        self._lock_btn.setFixedSize(20, 20)
        self._lock_btn.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._lock_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._lock_btn.setToolTip("解锁 — 点击锁定（锁定后不可移动和缩放）")
        self._lock_btn.mousePressEvent = self._on_lock_toggle
        bottom.addWidget(self._lock_btn)

        bottom.addStretch()

        self._resize_grip = QSizeGrip(self)
        self._resize_grip.setFixedSize(16, 16)
        self._resize_grip.setStyleSheet("background: transparent;")
        bottom.addWidget(self._resize_grip)
        layout.addLayout(bottom)
        self._refresh_lock_icon()

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
        if self._is_locked:
            return
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint()

    def _title_move(self, event: QMouseEvent):
        if self._is_locked or self._drag_pos is None:
            return
        delta = event.globalPosition().toPoint() - self._drag_pos
        self.move(self.pos() + delta)
        self._drag_pos = event.globalPosition().toPoint()

    def _title_release(self, event: QMouseEvent):
        self._drag_pos = None

    # ---- 锁 ----
    def _refresh_lock_icon(self):
        icon_name = "锁定.png" if self._is_locked else "解锁.png"
        icon_path = os.path.join(_ASSETS_DIR, icon_name)
        if os.path.exists(icon_path):
            pixmap = QPixmap(icon_path).scaled(16, 16, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            self._lock_btn.setPixmap(pixmap)
        else:
            self._lock_btn.setText("🔒" if self._is_locked else "🔓")
        self._lock_btn.setToolTip(
            "已锁定 — 点击解锁" if self._is_locked
            else "解锁 — 点击锁定（锁定后不可移动和缩放）"
        )

    def _adjust_opacity(self, delta: int):
        current = round(self.windowOpacity() * 100)
        new_val = max(20, min(100, current + delta))
        self.setWindowOpacity(new_val / 100.0)
        self._opacity_label.setText(f"{new_val}%")

    def _set_color(self, bg: str, fg: str):
        """切换背景色和字体色。"""
        self._note_data["color"] = bg
        self._note_data["font_color"] = fg
        self.setStyleSheet(f"""
            #TaskNoteFloat {{
                background: {bg};
                border: 1px solid #ccc;
                border-radius: 6px;
            }}
        """)
        for cb in self._checkboxes:
            if "text-decoration" not in (cb.styleSheet() or ""):
                cb.setStyleSheet(f"color: {fg}; font-size: 13px;")

    def _on_custom_color(self):
        """自定义背景色。"""
        current = QColor(self._note_data.get("color", "#FFFFFF"))
        color = QColorDialog.getColor(current, self, "选择背景颜色")
        if color.isValid():
            self._set_color(color.name(), self._note_data.get("font_color", "#000000"))

    def _on_lock_toggle(self, event: QMouseEvent):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        self._is_locked = not self._is_locked
        self._resize_grip.setVisible(not self._is_locked)
        self._refresh_lock_icon()

    # ---- 右键菜单 ----
    def contextMenuEvent(self, event):
        from PySide6.QtWidgets import QMenu
        menu = QMenu(self)
        ghost_action = menu.addAction("幽灵模式")
        ghost_action.setCheckable(True)
        ghost_action.setChecked(self._is_ghost)
        menu.addSeparator()
        unfollow_action = menu.addAction("取消悬浮")
        action = menu.exec(event.globalPos())
        if action == ghost_action:
            self._toggle_ghost()
        elif action == unfollow_action:
            self.unfloated.emit(self._note_id)

    def _toggle_ghost(self):
        """切换幽灵模式（鼠标点击穿透）。"""
        self._is_ghost = not self._is_ghost
        self._apply_ghost_flags()
        self.ghost_changed.emit(self._note_id, self._is_ghost)

    def exit_ghost(self):
        """退出幽灵模式（供外部调用，如热键或页面按钮）。"""
        if not self._is_ghost:
            return
        self._is_ghost = False
        self._apply_ghost_flags()
        self.ghost_changed.emit(self._note_id, False)

    def is_ghost(self) -> bool:
        """返回当前是否处于幽灵模式。"""
        return self._is_ghost

    def _apply_ghost_flags(self):
        """根据 _is_ghost 状态应用/移除 WindowTransparentForInput 标志。"""
        flags = self.windowFlags()
        if self._is_ghost:
            flags |= Qt.WindowType.WindowTransparentForInput
        else:
            flags &= ~Qt.WindowType.WindowTransparentForInput
        self.hide()
        self.setWindowFlags(flags)
        self.show()

    def _build_checkboxes(self, font_color: str):
        """重建任务条目勾选框（先清空再重建）。"""
        # 清空旧勾选框
        while self._items_layout.count() > 0:
            item = self._items_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._checkboxes.clear()

        for i, item in enumerate(self._items):
            cb = QCheckBox(item["text"])
            cb.setChecked(item.get("checked", False))
            cb.setStyleSheet(f"color: {font_color}; font-size: 13px;")
            if item.get("checked"):
                cb.setStyleSheet("color: #999; font-size: 13px; text-decoration: line-through;")
            cb.toggled.connect(lambda checked, idx=i: self._on_check(idx, checked))
            self._items_layout.addWidget(cb)
            self._checkboxes.append(cb)

    def update_data(self, note_data: dict):
        """更新数据并刷新界面。"""
        self._note_data = note_data
        self._parse_content()
        # 更新标题
        self._title_lbl.setText(note_data.get("title", "任务笔记"))
        # 更新颜色
        color = note_data.get("color") or "#FFFFFF"
        font_color = note_data.get("font_color") or "#000000"
        self.setStyleSheet(f"""
            #TaskNoteFloat {{
                background: {color};
                border: 1px solid #ccc;
                border-radius: 6px;
            }}
        """)
        self._title_lbl.setStyleSheet(f"color: {font_color}; background: transparent;")
        # 重建勾选框
        self._build_checkboxes(font_color)
        self._items_layout.addStretch()
