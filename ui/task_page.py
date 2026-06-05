"""定时助手页面 - TaskPage。

显示任务列表，支持创建/编辑/删除/启用禁用，响应提醒弹窗。
"""

import logging
import datetime
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QComboBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor

from core.task_manager import TaskStore
from core.task_scheduler import TaskScheduler
from ui.widgets.task_editor import TaskEditor
from ui.widgets.task_reminder_popup import TaskReminderPopup

log = logging.getLogger("InfoVault.task")


class TaskPage(QWidget):
    """定时助手管理页面。"""

    def __init__(self, task_store: TaskStore, scheduler: TaskScheduler):
        super().__init__()
        self._store = task_store
        self._scheduler = scheduler
        self._popups: dict[int, TaskReminderPopup] = {}
        self._init_ui()
        self._refresh()

        # 连接调度器信号
        scheduler.remind_requested.connect(self._on_remind)
        scheduler.start()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        # 工具栏
        toolbar = QHBoxLayout()
        toolbar.setSpacing(6)

        new_btn = QPushButton("+ 新建任务")
        new_btn.setFixedHeight(30)
        new_btn.setMinimumWidth(90)
        new_btn.clicked.connect(self._on_new)
        toolbar.addWidget(new_btn)

        toolbar.addStretch()

        self._filter_combo = QComboBox()
        self._filter_combo.addItems(["全部", "进行中", "已过期", "已停用"])
        self._filter_combo.currentIndexChanged.connect(self._on_filter_changed)
        toolbar.addWidget(self._filter_combo)

        layout.addLayout(toolbar)

        # 任务列表
        self._table = QTableWidget()
        self._table.setColumnCount(7)
        self._table.setHorizontalHeaderLabels(["状态", "任务名", "时间规则", "动作", "操作", "日志", "删除"])
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        self._table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)
        self._table.horizontalHeader().setSectionResizeMode(6, QHeaderView.ResizeMode.Fixed)
        self._table.setColumnWidth(0, 50)
        self._table.setColumnWidth(2, 140)
        self._table.setColumnWidth(3, 100)
        self._table.setColumnWidth(4, 80)
        self._table.setColumnWidth(5, 80)
        self._table.setColumnWidth(6, 80)
        self._table.verticalHeader().setVisible(False)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.doubleClicked.connect(self._on_edit_row)
        self._table.setStyleSheet(
            "QTableWidget { border: none; gridline-color: #eee; }"
            "QTableWidget::item { padding: 6px 8px; }"
        )
        layout.addWidget(self._table, 1)

    def _refresh(self):
        self._table.setRowCount(0)
        filter_map = {"全部": "all", "进行中": "active", "已过期": "expired", "已停用": "disabled"}
        status = filter_map.get(self._filter_combo.currentText(), "all")
        tasks = self._store.get_all(status_filter=status)
        now = int(datetime.datetime.now().timestamp())

        for task in tasks:
            row = self._table.rowCount()
            self._table.insertRow(row)

            # 状态圆点
            enabled = task.get("enabled", 1)
            end_date = task.get("end_date")
            if not enabled:
                status_text = "⏸"
                status_tip = "已停用"
            elif end_date and end_date <= now:
                status_text = "⏹"
                status_tip = "已过期"
            else:
                status_text = "▶"
                status_tip = "运行中"

            status_item = QTableWidgetItem(status_text)
            status_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            status_item.setToolTip(status_tip)
            self._table.setItem(row, 0, status_item)

            # 任务名
            self._table.setItem(row, 1, QTableWidgetItem(task.get("name", "")))

            # 时间规则摘要
            rule_type = task.get("rule_type", "")
            rule_value = task.get("rule_value", "")
            rule_map = {
                "once": "一次性", "daily": "每天", "weekly": "每周",
                "monthly": "每月", "interval": "每隔N天",
            }
            rule_label = rule_map.get(rule_type, rule_type)
            # 美化间隔显示
            if rule_type == "interval":
                parts = rule_value.split("@")
                rule_label = f"每隔{parts[0]}天"
                rule_value = parts[1] if len(parts) > 1 else ""
            self._table.setItem(row, 2, QTableWidgetItem(f"{rule_label} {rule_value}"))

            # 动作（多选用逗号分隔）
            action_map = {
                "popup": "🔔", "open_app": "💻", "open_file": "📄",
                "open_folder": "📁", "run_script": "⚙",
            }
            actions = [a.strip() for a in task.get("action_type", "").split(",") if a.strip()]
            action_text = " ".join(action_map.get(a, "?") for a in actions)
            sound_mark = " 🔊" if task.get("sound_enabled") else ""
            self._table.setItem(row, 3, QTableWidgetItem(action_text + sound_mark))

            # 操作按钮
            btn_text = "启用" if not enabled else "禁用"
            btn = QPushButton(btn_text)
            btn.setFixedHeight(24)
            btn.clicked.connect(lambda checked, tid=task["id"]: self._on_toggle(tid))
            self._table.setCellWidget(row, 4, btn)

            # 日志按钮
            log_btn = QPushButton("日志")
            log_btn.setFixedHeight(24)
            log_btn.clicked.connect(lambda checked, tid=task["id"]: self._on_show_logs(tid))
            self._table.setCellWidget(row, 5, log_btn)

            # 删除按钮
            del_btn = QPushButton("删除")
            del_btn.setFixedHeight(24)
            del_btn.setStyleSheet(
                "QPushButton { color: #d32f2f; }"
                "QPushButton:hover { background: rgba(211,47,47,0.1); }"
            )
            del_btn.clicked.connect(lambda checked, tid=task["id"]: self._on_delete(tid))
            self._table.setCellWidget(row, 6, del_btn)

            # 存储 task_id
            self._table.item(row, 0).setData(Qt.ItemDataRole.UserRole, task["id"])

    # ── 操作 ──

    def _on_new(self):
        dlg = TaskEditor(self._store, parent=self)
        dlg.saved.connect(self._on_saved)
        dlg.exec()

    def _on_edit_row(self, index):
        task_id = self._table.item(index.row(), 0).data(Qt.ItemDataRole.UserRole)
        task = self._store.get(task_id)
        if task:
            dlg = TaskEditor(self._store, task, self)
            dlg.saved.connect(self._on_saved)
            dlg.exec()

    def _on_saved(self, task_id: int):
        self._refresh()

    def _on_toggle(self, task_id: int):
        self._store.toggle_enabled(task_id)
        self._refresh()

    def _on_delete(self, task_id: int):
        task = self._store.get(task_id)
        name = task.get("name", "任务") if task else "任务"
        reply = QMessageBox.question(
            self, "确认删除",
            f"确定删除任务「{name}」吗？\n此操作不可撤销。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._store.delete(task_id)
            self._refresh()

    def _on_filter_changed(self):
        self._refresh()

    def _on_show_logs(self, task_id: int):
        task = self._store.get(task_id)
        name = task.get("name", "任务") if task else "任务"
        logs = self._store.get_logs(task_id, limit=30)
        if not logs:
            QMessageBox.information(self, f"日志 - {name}", "暂无执行记录。")
            return

        lines = []
        for log_entry in logs:
            ts = datetime.datetime.fromtimestamp(log_entry["triggered_at"])
            status_icon = "✓" if log_entry["status"] == "success" else "✗"
            lines.append(
                f"{status_icon} {ts.strftime('%m-%d %H:%M')}  {log_entry['status']}"
            )
            if log_entry.get("message"):
                for mline in log_entry["message"].split("\n")[:3]:
                    lines.append(f"   {mline}")

        QMessageBox.information(self, f"日志 - {name}", "\n".join(lines[-30:]))

    # ── 提醒弹窗 ──

    def _on_remind(self, task: dict):
        tid = task["id"]
        if tid in self._popups:
            self._popups[tid].close()
        popup = TaskReminderPopup(task)
        popup.closed.connect(self._on_popup_closed)
        popup.confirmed.connect(self._on_script_confirmed)
        popup.show()
        self._popups[tid] = popup

    def _on_popup_closed(self, task_id: int):
        if task_id in self._popups:
            del self._popups[task_id]

    def _on_script_confirmed(self, task_id: int):
        task = self._store.get(task_id)
        if task:
            self._scheduler.execute_confirmed_script(task)
        if task_id in self._popups:
            del self._popups[task_id]


def create_page(task_store: TaskStore, scheduler: TaskScheduler) -> QWidget:
    return TaskPage(task_store, scheduler)
