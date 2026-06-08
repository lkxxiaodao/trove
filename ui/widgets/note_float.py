"""悬浮笔记窗口 - NoteFloatWindow。

始终置顶、无边框、可拖拽移动、可自由调整大小。
"""

import os
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTextEdit,
    QPushButton, QSizeGrip, QApplication, QColorDialog, QMenu,
)
from PySide6.QtCore import Qt, Signal, QPoint, QRect, QEvent, QTimer
from PySide6.QtGui import QColor, QFont, QMouseEvent, QPalette, QPixmap

from config import AppConfig

# 资源路径
_ASSETS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "assets")


# 辅助：判断内容是否为 HTML
def _is_html(content: str) -> bool:
    return bool(content) and (
        content.strip().startswith("<!DOCTYPE")
        or content.strip().startswith("<html")
        or "<img" in content
        or "<p" in content
        or "<div" in content
    )


class NoteFloatWindow(QWidget):
    """悬浮笔记窗口。

    信号:
        unfloated(note_id): 用户关闭悬浮时发出
        edit_requested(note_id): 用户请求编辑时发出
    """

    unfloated = Signal(int)
    edit_requested = Signal(int)
    content_changed = Signal(int, str)  # note_id, new_content
    ghost_changed = Signal(int, bool)  # note_id, is_ghost

    @property
    def COLORS(self):
        config = AppConfig.instance()
        return {c["name"]: c["bg"] for c in config.NOTE_PRESET_COLORS}

    @property
    def FONT_COLORS(self):
        config = AppConfig.instance()
        return {c["name"]: c["font"] for c in config.NOTE_PRESET_COLORS}

    def __init__(self, note_data: dict, font_size: int = 14, parent=None):
        flags = Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
        super().__init__(parent, flags)
        self._note_id = note_data["id"]
        self._note_data = note_data
        self._font_size = font_size
        self._drag_pos = None
        self._is_resizing = False
        self._resize_edge = None
        self._resize_start_geo = None
        self._resize_start_pos = None
        self._is_locked = False
        self._is_ghost = False  # 幽灵模式（点击穿透）
        self._save_timer = QTimer()
        self._save_timer.setSingleShot(True)
        self._save_timer.timeout.connect(self._do_auto_save)

        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setMinimumSize(180, 120)
        self._init_ui()
        self._apply_data()
        self._show_smart()

    # ---- UI ----
    def _init_ui(self):
        self.setObjectName("NoteFloatWindow")
        self.setStyleSheet("""
            #NoteFloatWindow {
                background: #fff;
                border: 1px solid #ccc;
                border-radius: 6px;
            }
        """)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ---- 标题栏 ----
        title_bar = QWidget()
        title_bar.setFixedHeight(32)
        title_bar.setCursor(Qt.CursorShape.SizeAllCursor)
        title_bar.setStyleSheet("background: #eee; border-radius: 6px 6px 0 0;")
        title_bar.mousePressEvent = self._title_press
        title_bar.mouseMoveEvent = self._title_move
        title_bar.mouseReleaseEvent = self._title_release

        tb_layout = QHBoxLayout(title_bar)
        tb_layout.setContentsMargins(8, 0, 4, 0)
        tb_layout.setSpacing(4)

        self._color_dot = QLabel()
        self._color_dot.setFixedSize(10, 10)
        self._color_dot.setStyleSheet("border-radius: 5px; background: #aaa;")
        tb_layout.addWidget(self._color_dot)

        self._title_label = QLabel("笔记")
        self._title_label.setStyleSheet("font-weight: bold; background: transparent;")
        self._title_label.setCursor(Qt.CursorShape.SizeAllCursor)
        tb_layout.addWidget(self._title_label, 1)

        # 颜色切换按钮（前 5 个预设）
        colors = list(self.COLORS.items())
        for idx, (name, color) in enumerate(colors[:5]):
            btn = QPushButton()
            btn.setFixedSize(14, 14)
            font_c = self.FONT_COLORS.get(name, "#000000")
            btn.setStyleSheet(f"background: {color}; border: 1px solid #bbb; border-radius: 3px;")
            btn.setToolTip(f"{name} (字体: {font_c})")
            btn.clicked.connect(lambda checked, c=color, fc=font_c: self._set_color_with_font(c, fc))
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

        # 关闭按钮（QLabel 模拟，确保 ✕ 正常显示）
        close_btn = QLabel("✕")
        close_btn.setFixedSize(24, 24)
        close_btn.setAlignment(Qt.AlignmentFlag.AlignCenter)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setToolTip("关闭悬浮")
        close_btn.setStyleSheet("""
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
        close_btn.mousePressEvent = lambda e: self._on_unfloat()
        tb_layout.addWidget(close_btn)

        main_layout.addWidget(title_bar)

        # ---- 内容区 ----
        self._content_edit = QTextEdit()
        self._content_edit.setReadOnly(self._is_locked)  # 默认 False = 可编辑
        self._content_edit.setFrameShape(QTextEdit.Shape.NoFrame)
        self._content_edit.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._content_edit.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._content_edit.setStyleSheet("""
            background: transparent;
            padding: 6px 10px;
        """)
        # 图片自适应
        self._content_edit.document().setDefaultStyleSheet("img { max-width: 100%; height: auto; }")
        self._content_edit.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._content_edit.customContextMenuRequested.connect(self._on_context_menu)
        self._content_edit.textChanged.connect(self._on_content_changed)
        main_layout.addWidget(self._content_edit, 1)

        # ---- 底部：锁 + 标签 + 调整手柄 ----
        bottom_bar = QHBoxLayout()
        bottom_bar.setContentsMargins(8, 2, 4, 4)
        bottom_bar.setSpacing(4)

        # 锁 / 解锁按钮
        self._lock_btn = QLabel()
        self._lock_btn.setFixedSize(20, 20)
        self._lock_btn.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._lock_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._lock_btn.setToolTip("解锁状态 — 点击锁定（锁定后内容不可编辑）")
        self._lock_btn.mousePressEvent = self._on_lock_toggle
        bottom_bar.addWidget(self._lock_btn)

        self._tag_label = QLabel()
        self._tag_label.setMinimumWidth(40)
        self._tag_label.setStyleSheet(
            "color: #666; font-size: 10px;"
            "background: rgba(0,0,0,0.06); border-radius: 3px;"
            "padding: 2px 5px;"
        )
        self._tag_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        bottom_bar.addWidget(self._tag_label)
        bottom_bar.addStretch()

        grip = QSizeGrip(self)
        grip.setFixedSize(16, 16)
        grip.setStyleSheet("background: transparent;")
        bottom_bar.addWidget(grip)
        main_layout.addLayout(bottom_bar)

        # 刷新锁图标
        self._refresh_lock_icon()

    def _on_content_changed(self):
        """内容变化时启动防抖定时器，500ms 后自动保存。"""
        self._save_timer.start(500)

    def _do_auto_save(self):
        """将当前内容写回数据库。"""
        content = self._content_edit.toHtml() if _is_html(self._note_data.get("content", "")) else self._content_edit.toPlainText()
        self._note_data["content"] = content
        self.content_changed.emit(self._note_id, content)

    def _apply_data(self):
        self._title_label.setText(self._note_data.get("title", "未命名"))
        content = self._note_data.get("content", "")
        if content and _is_html(content):
            self._content_edit.setHtml(content)
        else:
            self._content_edit.setPlainText(content)
        color = self._note_data.get("color", "#FFFFFF")
        font_color = self._note_data.get("font_color", "#000000")
        self._apply_bg_color(color, font_color)

        # 标签（最多 1 个）
        tags = self._note_data.get("tags") or []
        if tags:
            self._tag_label.setText(tags[0]["name"][:5])
            self._tag_label.show()
        else:
            self._tag_label.hide()

    def _apply_bg_color(self, color: str, font_color: str = "#000000"):
        self._color_dot.setStyleSheet(f"border-radius: 5px; background: {color};")
        self.setStyleSheet(f"""
            #NoteFloatWindow {{
                background: {color};
                border: 1px solid #ccc;
                border-radius: 6px;
            }}
        """)
        self._content_edit.setStyleSheet(f"""
            background: transparent;
            padding: 6px 10px;
            color: {font_color};
        """)

    def _set_color(self, color: str):
        self._note_data["color"] = color
        self._apply_bg_color(color, self._note_data.get("font_color", "#000000"))

    def _set_color_with_font(self, bg: str, font: str):
        self._note_data["color"] = bg
        self._note_data["font_color"] = font
        self._apply_bg_color(bg, font)

    def _adjust_opacity(self, delta: int):
        """按步长调整窗口透明度（20%~100%）。"""
        current = round(self.windowOpacity() * 100)
        new_val = max(20, min(100, current + delta))
        self.setWindowOpacity(new_val / 100.0)
        self._opacity_label.setText(f"{new_val}%")

    def _on_custom_color(self):
        """打开取色器选择自定义背景色。"""
        current = QColor(self._note_data.get("color", "#FFFFFF"))
        color = QColorDialog.getColor(current, self, "选择背景颜色")
        if color.isValid():
            self._note_data["color"] = color.name()
            self._apply_bg_color(color.name(), self._note_data.get("font_color", "#000000"))

    def _show_smart(self):
        """在屏幕右侧中间区域显示。"""
        screen = QApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            self.resize(280, 220)
            self.move(geo.right() - 300, geo.top() + 100)
        self.show()

    # ---- 标题栏拖拽 ----
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

    # ---- 右键菜单 ----
    def _on_context_menu(self, pos):
        menu = QMenu(self)
        edit_action = menu.addAction("编辑")
        font_color_action = menu.addAction("更改字体颜色")
        ghost_action = menu.addAction("幽灵模式")
        ghost_action.setCheckable(True)
        ghost_action.setChecked(self._is_ghost)
        menu.addSeparator()
        unfollow_action = menu.addAction("取消悬浮")
        action = menu.exec(self._content_edit.mapToGlobal(pos))
        if action == edit_action:
            self.edit_requested.emit(self._note_id)
        elif action == font_color_action:
            current = QColor(self._note_data.get("font_color", "#000000"))
            color = QColorDialog.getColor(current, self, "选择字体颜色")
            if color.isValid():
                self._note_data["font_color"] = color.name()
                self._apply_bg_color(self._note_data.get("color", "#FFFFFF"), color.name())
        elif action == ghost_action:
            self._toggle_ghost()
        elif action == unfollow_action:
            self._on_unfloat()

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

    # ---- 操作 ----
    def _on_unfloat(self):
        self.unfloated.emit(self._note_id)

    # ---- 锁 / 解锁 ----
    def _refresh_lock_icon(self):
        """根据锁定状态刷新锁图标。"""
        icon_name = "锁定.png" if self._is_locked else "解锁.png"
        icon_path = os.path.join(_ASSETS_DIR, icon_name)
        if os.path.exists(icon_path):
            pixmap = QPixmap(icon_path).scaled(
                16, 16, Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            self._lock_btn.setPixmap(pixmap)
        else:
            # 备用：用文字显示
            self._lock_btn.setText("🔒" if self._is_locked else "🔓")

        self._lock_btn.setToolTip(
            "锁定状态 — 点击解锁（内容不可编辑）" if self._is_locked
            else "解锁状态 — 点击锁定（内容可编辑）"
        )

    def _on_lock_toggle(self, event: QMouseEvent):
        """切换锁定 / 解锁状态。"""
        if event.button() != Qt.MouseButton.LeftButton:
            return
        self._is_locked = not self._is_locked
        self._content_edit.setReadOnly(self._is_locked)
        self._refresh_lock_icon()

    def update_content(self, note_data: dict, font_size: int = None):
        """外部更新笔记内容。"""
        self._note_data = note_data
        self._font_size = font_size or self._font_size
        self._apply_data()
        self._set_font()

    def _set_font(self):
        font = QFont()
        font.setPointSize(self._font_size)
        self._content_edit.setFont(font)