"""悬浮笔记窗口 - NoteFloatWindow。

始终置顶、无边框、可拖拽移动、可自由调整大小。
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTextEdit,
    QPushButton, QSizeGrip, QApplication,
)
from PySide6.QtCore import Qt, Signal, QPoint, QRect
from PySide6.QtGui import QColor, QFont, QMouseEvent, QPalette


class NoteFloatWindow(QWidget):
    """悬浮笔记窗口。

    信号:
        unfloated(note_id): 用户关闭悬浮时发出
        edit_requested(note_id): 用户请求编辑时发出
    """

    unfloated = Signal(int)
    edit_requested = Signal(int)

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

        # 颜色切换按钮
        for name, color in list(self.COLORS.items())[:5]:
            btn = QPushButton()
            btn.setFixedSize(14, 14)
            btn.setStyleSheet(f"background: {color}; border: 1px solid #bbb; border-radius: 3px;")
            btn.setToolTip(name)
            btn.clicked.connect(lambda checked, c=color: self._set_color(c))
            tb_layout.addWidget(btn)

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(28, 28)
        close_btn.setStyleSheet(
            "QPushButton {"
            "  border: none;"
            "  font-size: 16px;"
            "  font-weight: bold;"
            "  color: #bbb;"
            "  background: transparent;"
            "  border-radius: 6px;"
            "}"
            "QPushButton:hover {"
            "  background: rgba(211, 47, 47, 0.15);"
            "  color: #d32f2f;"
            "}"
        )
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setToolTip("关闭悬浮")
        close_btn.clicked.connect(self._on_unfloat)
        tb_layout.addWidget(close_btn)

        main_layout.addWidget(title_bar)

        # ---- 内容区 ----
        self._content_edit = QTextEdit()
        self._content_edit.setReadOnly(True)
        self._content_edit.setFrameShape(QTextEdit.Shape.NoFrame)
        self._content_edit.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._content_edit.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._content_edit.setStyleSheet("background: transparent; padding: 6px 10px;")
        self._content_edit.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._content_edit.customContextMenuRequested.connect(self._on_context_menu)
        main_layout.addWidget(self._content_edit, 1)

        # ---- 底部：标签 + 调整手柄 ----
        bottom_bar = QHBoxLayout()
        bottom_bar.setContentsMargins(8, 2, 4, 4)
        bottom_bar.setSpacing(4)

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

    def _apply_data(self):
        self._title_label.setText(self._note_data.get("title", "未命名"))
        self._content_edit.setPlainText(self._note_data.get("content", ""))
        color = self._note_data.get("color", "#FFFFFF")
        self._apply_bg_color(color)

        # 标签（最多 1 个）
        tags = self._note_data.get("tags") or []
        if tags:
            self._tag_label.setText(tags[0]["name"][:5])
            self._tag_label.show()
        else:
            self._tag_label.hide()

    def _apply_bg_color(self, color: str):
        self._color_dot.setStyleSheet(f"border-radius: 5px; background: {color};")
        self.setStyleSheet(f"""
            #NoteFloatWindow {{
                background: {color};
                border: 1px solid #ccc;
                border-radius: 6px;
            }}
        """)
        self._content_edit.setStyleSheet(f"background: transparent; padding: 6px 10px;")

    def _set_color(self, color: str):
        self._note_data["color"] = color
        self._apply_bg_color(color)

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
        from PySide6.QtWidgets import QMenu
        menu = QMenu(self)
        edit_action = menu.addAction("编辑")
        menu.addSeparator()
        unfollow_action = menu.addAction("取消悬浮")
        action = menu.exec(self._content_edit.mapToGlobal(pos))
        if action == edit_action:
            self.edit_requested.emit(self._note_id)
        elif action == unfollow_action:
            self._on_unfloat()

    # ---- 操作 ----
    def _on_unfloat(self):
        self.unfloated.emit(self._note_id)

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