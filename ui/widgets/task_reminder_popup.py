"""定时提醒弹窗 - TaskReminderPopup。

无边框、居中置顶、显示任务名和弹窗内容（文字+图片）。
支持拖拽移动和自由缩放，图片自动适配窗口大小。
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTextEdit, QSizeGrip,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QMouseEvent


class TaskReminderPopup(QWidget):
    """提醒弹窗。

    信号:
        closed(task_id): 用户关闭弹窗
        confirmed(task_id): 用户确认执行脚本
    """

    closed = Signal(int)
    confirmed = Signal(int)

    def __init__(self, task: dict, parent=None):
        flags = (
            Qt.WindowType.Window |
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint
        )
        super().__init__(parent, flags)
        self._task_id = task["id"]
        self._confirm_script = task.get("_confirm_script", False)
        self._task = task
        self._drag_pos = None

        self.setObjectName("ReminderPopup")
        self.setMinimumSize(280, 200)
        self._init_ui(task)
        self._fit_to_content(task)
        self._center()

    def _init_ui(self, task: dict):
        self.setStyleSheet("""
            #ReminderPopup {
                background: #ffffff;
                border: 2px solid #1a73e8;
                border-radius: 14px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)

        # —— 顶部标题栏（拖拽手柄） ——
        header = QHBoxLayout()
        header.setSpacing(6)

        icon = QLabel("⏰")
        icon.setStyleSheet("font-size: 20px;")
        header.addWidget(icon)

        title_lbl = QLabel("定时提醒")
        title_font = QFont()
        title_font.setPointSize(13)
        title_font.setBold(True)
        title_lbl.setFont(title_font)
        title_lbl.setStyleSheet("color: #1a73e8;")
        header.addWidget(title_lbl, 1)
        header.addStretch()

        layout.addLayout(header)

        # —— 任务名 ——
        name_lbl = QLabel(task.get("name", "未命名"))
        name_font = QFont()
        name_font.setPointSize(16)
        name_font.setBold(True)
        name_lbl.setFont(name_font)
        name_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        name_lbl.setStyleSheet("color: #333;")
        layout.addWidget(name_lbl)

        # 标题栏整体作为拖拽区域
        name_lbl.setCursor(Qt.CursorShape.SizeAllCursor)
        name_lbl.mousePressEvent = self._title_press
        name_lbl.mouseMoveEvent = self._title_move
        name_lbl.mouseReleaseEvent = self._title_release

        # —— 弹窗专属内容（HTML 或纯文本） ——
        popup_html = task.get("_popup_html", "")
        if popup_html:
            self._content_edit = QTextEdit()
            self._content_edit.setReadOnly(True)
            self._content_edit.setFrameShape(QTextEdit.Shape.NoFrame)
            self._content_edit.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
            self._content_edit.setStyleSheet("background: transparent; padding: 4px 0;")
            if popup_html.strip().startswith("<!DOCTYPE") or "<img" in popup_html or "<p" in popup_html:
                self._content_edit.setHtml(popup_html)
            else:
                self._content_edit.setPlainText(popup_html)
            # 图片自适应 + 内容宽高适配
            self._content_edit.document().setDefaultStyleSheet(
                "img { max-width: 100%; height: auto; }"
            )
            layout.addWidget(self._content_edit, 1)
        else:
            self._content_edit = None
            desc = task.get("description", "")
            if desc:
                desc_lbl = QLabel(desc)
                desc_lbl.setWordWrap(True)
                desc_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                desc_lbl.setStyleSheet("color: #666; font-size: 12px;")
                desc_lbl.setMaximumHeight(40)
                layout.addWidget(desc_lbl)

        layout.addStretch()

        # —— 底部：按钮 + 调整手柄 ——
        bottom = QHBoxLayout()
        bottom.setSpacing(6)

        # 调整大小手柄
        grip = QSizeGrip(self)
        grip.setFixedSize(16, 16)
        grip.setStyleSheet("background: transparent;")
        bottom.addWidget(grip)
        bottom.addStretch()

        if self._confirm_script:
            cancel_btn = QPushButton("取消")
            cancel_btn.clicked.connect(self._on_close)
            bottom.addWidget(cancel_btn)
            confirm_btn = QPushButton("执行脚本")
            confirm_btn.setStyleSheet(
                "QPushButton { background: #1a73e8; color: #fff; border-radius: 6px;"
                " padding: 6px 20px; font-weight: bold; }"
                "QPushButton:hover { background: #1557b0; }"
            )
            confirm_btn.clicked.connect(self._on_confirm)
            bottom.addWidget(confirm_btn)
        else:
            close_btn = QPushButton("知道了")
            close_btn.setStyleSheet(
                "QPushButton { background: #1a73e8; color: #fff; border-radius: 6px;"
                " padding: 6px 20px; font-weight: bold; }"
                "QPushButton:hover { background: #1557b0; }"
            )
            close_btn.clicked.connect(self._on_close)
            bottom.addWidget(close_btn)
        layout.addLayout(bottom)

    def _fit_to_content(self, task: dict):
        """根据弹窗内容（图片）自动调整初始窗口大小，保持图片宽高比。"""
        popup_html = task.get("_popup_html", "")
        if not popup_html or not self._content_edit:
            self.resize(420, 260)
            return

        # 获取最大图片尺寸
        import re
        max_w, max_h = 0, 0
        from PySide6.QtGui import QPixmap

        for m in re.finditer(r'<img\s+src="file:///([^"]+)"', popup_html):
            path = m.group(1)
            pix = QPixmap(path)
            if not pix.isNull():
                pw, ph = pix.width(), pix.height()
                max_w = max(max_w, pw)
                max_h = max(max_h, ph)

        if max_w <= 0:
            self.resize(420, 260)
            return

        from PySide6.QtWidgets import QApplication
        screen = QApplication.primaryScreen()
        if screen:
            screen_w = screen.availableGeometry().width()
            screen_h = screen.availableGeometry().height()
        else:
            screen_w, screen_h = 1920, 1080

        # 预留空间：左右内边距 ~60px，标题栏+按钮 ~160px
        pad_x, pad_y = 60, 160
        # 按宽高比缩放，确保完整显示且不超过屏幕 75%/70%
        avail_img_w = int(screen_w * 0.75) - pad_x
        avail_img_h = int(screen_h * 0.70) - pad_y

        if avail_img_w > 0 and avail_img_h > 0:
            scale = min(avail_img_w / max_w, avail_img_h / max_h, 1.0)
        else:
            scale = 1.0

        win_w = int(max_w * scale + pad_x)
        win_h = int(max_h * scale + pad_y)
        self.resize(max(win_w, self.minimumWidth()), max(win_h, self.minimumHeight()))

    # —— 拖拽移动 ——
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

    def _center(self):
        """居中显示。"""
        from PySide6.QtWidgets import QApplication
        screen = QApplication.primaryScreen()
        if screen:
            c = screen.availableGeometry().center()
            self.move(c.x() - self.width() // 2, c.y() - self.height() // 2)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self._on_close()
        super().keyPressEvent(event)

    def _on_close(self):
        self.closed.emit(self._task_id)
        self.close()

    def _on_confirm(self):
        self.confirmed.emit(self._task_id)
        self.close()
