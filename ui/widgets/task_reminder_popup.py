"""定时提醒弹窗 - TaskReminderPopup。

无边框、居中置顶、显示任务名和说明。
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont


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

        self.setObjectName("ReminderPopup")
        self.setFixedSize(380, 200)
        self._init_ui(task)
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

        # 顶部图标 + 标题栏
        header = QHBoxLayout()
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

        # 任务名
        name_lbl = QLabel(task.get("name", "未命名"))
        name_font = QFont()
        name_font.setPointSize(16)
        name_font.setBold(True)
        name_lbl.setFont(name_font)
        name_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        name_lbl.setStyleSheet("color: #333;")
        layout.addWidget(name_lbl)

        # 描述
        desc = task.get("description", "")
        if desc:
            desc_lbl = QLabel(desc)
            desc_lbl.setWordWrap(True)
            desc_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            desc_lbl.setStyleSheet("color: #666; font-size: 12px;")
            desc_lbl.setMaximumHeight(40)
            layout.addWidget(desc_lbl)

        layout.addStretch()

        # 按钮
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        if self._confirm_script:
            cancel_btn = QPushButton("取消")
            cancel_btn.clicked.connect(self._on_close)
            btn_layout.addWidget(cancel_btn)
            confirm_btn = QPushButton("执行脚本")
            confirm_btn.setStyleSheet(
                "QPushButton { background: #1a73e8; color: #fff; border-radius: 6px;"
                " padding: 6px 20px; font-weight: bold; }"
                "QPushButton:hover { background: #1557b0; }"
            )
            confirm_btn.clicked.connect(self._on_confirm)
            btn_layout.addWidget(confirm_btn)
        else:
            close_btn = QPushButton("知道了")
            close_btn.setStyleSheet(
                "QPushButton { background: #1a73e8; color: #fff; border-radius: 6px;"
                " padding: 6px 20px; font-weight: bold; }"
                "QPushButton:hover { background: #1557b0; }"
            )
            close_btn.clicked.connect(self._on_close)
            btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)

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
