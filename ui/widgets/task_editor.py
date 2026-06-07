"""任务编辑对话框 - TaskEditor。

下拉框规则选择，多选动作（各有独立文件选择），可选提示音。
"""

import os
import sys
import shutil
import ctypes
import os as _os_module
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLineEdit, QTextEdit,
    QPushButton, QLabel, QComboBox, QMessageBox, QDateTimeEdit,
    QCheckBox, QFileDialog, QFrame, QWidget,
)
from PySide6.QtCore import Qt, Signal, QDateTime

from core.task_manager import TaskStore
from config import AppConfig

# 辅助：判断内容是否为 HTML
def _is_html(content: str) -> bool:
    return bool(content) and (
        content.strip().startswith("<!DOCTYPE")
        or content.strip().startswith("<html")
        or "<img" in content
        or "<p" in content
        or "<div" in content
    )


def _is_admin() -> bool:
    """检查当前进程是否有管理员权限。"""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


def _restart_as_admin():
    """以管理员权限重启当前应用。"""
    ctypes.windll.shell32.ShellExecuteW(
        None, "runas", sys.executable, " ".join(sys.argv), None, 1
    )


class TaskEditor(QDialog):
    """任务编辑对话框。"""

    saved = Signal(int)

    RULE_TYPES = ["一次性", "每天", "每周", "每月", "每隔N天"]

    # (key, label, file_filter, hint)
    ACTION_DEFS = [
        ("popup", "弹窗提醒", None, None),
        ("open_app", "打开软件", "可执行文件 (*.exe);;所有文件 (*.*)", "⚠ 打开软件可能需要管理员权限"),
        ("open_file", "打开文件", "所有文件 (*.*)", None),
        ("open_folder", "打开文件夹", None, None),  # 用 QFileDialog.getExistingDirectory
        ("run_script", "运行脚本", "脚本文件 (*.bat *.cmd *.ps1 *.py *.sh);;所有文件 (*.*)", None),
    ]

    def __init__(self, task_store: TaskStore, task_data: dict = None, parent=None):
        super().__init__(parent)
        self._store = task_store
        self._task_data = task_data
        self._is_new = task_data is None

        config = AppConfig.instance()
        self._sound_dir = config.sounds_dir

        self.setWindowTitle("新建任务" if self._is_new else "编辑任务")
        self.setMinimumSize(500, 600)
        self.resize(520, 650)
        self._init_ui()
        self._load_data()

    # ═══════════════════════════════════════════
    # UI
    # ═══════════════════════════════════════════

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(6)

        # ── 任务名 ──
        layout.addWidget(QLabel("任务名 *"))
        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("输入任务名称...")
        layout.addWidget(self._name_edit)

        # ── 描述 ──
        layout.addWidget(QLabel("描述（选填）"))
        self._desc_edit = QTextEdit()
        self._desc_edit.setPlaceholderText("任务说明...")
        self._desc_edit.setMaximumHeight(50)
        layout.addWidget(self._desc_edit)

        # ── 时间规则 ──
        layout.addWidget(QLabel("时间规则"))
        self._rule_type = QComboBox()
        self._rule_type.addItems(self.RULE_TYPES)
        self._rule_type.setMinimumWidth(90)
        self._rule_type.currentIndexChanged.connect(self._on_rule_changed)
        layout.addWidget(self._rule_type)

        # 规则 UI 容器
        self._rule_once = self._build_once_ui()
        self._rule_daily = self._build_time_ui()
        self._rule_weekly = self._build_weekly_ui()
        self._rule_monthly = self._build_monthly_ui()
        self._rule_interval = self._build_interval_ui()
        self._rule_container = QVBoxLayout()
        layout.addLayout(self._rule_container)

        # ── 日期范围（可选） ──
        date_layout = QHBoxLayout()
        self._use_start = QCheckBox("开始日期")
        self._start_date = QDateTimeEdit()
        self._start_date.setCalendarPopup(True)
        self._start_date.setDateTime(QDateTime.currentDateTime())
        self._start_date.setVisible(False)
        self._use_start.toggled.connect(self._start_date.setVisible)
        date_layout.addWidget(self._use_start)
        date_layout.addWidget(self._start_date, 1)
        self._use_end = QCheckBox("结束日期")
        self._end_date = QDateTimeEdit()
        self._end_date.setCalendarPopup(True)
        self._end_date.setDateTime(QDateTime.currentDateTime().addMonths(1))
        self._end_date.setVisible(False)
        self._use_end.toggled.connect(self._end_date.setVisible)
        date_layout.addWidget(self._use_end)
        date_layout.addWidget(self._end_date, 1)
        layout.addLayout(date_layout)

        # ── 动作（多选，各有独立路径） ──
        layout.addWidget(QLabel("触发动作（可多选，勾选后选择路径）"))
        self._action_rows: dict[str, dict] = {}
        for key, label, file_filter, hint in self.ACTION_DEFS:
            row = self._build_action_row(key, label, file_filter, hint)
            layout.addWidget(row)

        # ── 提示音 ──
        self._sound_enabled = QCheckBox("触发时播放提示音")
        self._sound_enabled.toggled.connect(self._on_sound_toggled)
        layout.addWidget(self._sound_enabled)

        self._sound_combo = QComboBox()
        self._sound_combo.setMinimumWidth(160)
        self._refresh_sound_list()
        self._sound_combo.setVisible(False)
        layout.addWidget(self._sound_combo)

        self._sound_browse_btn = QPushButton("选择音频文件...")
        self._sound_browse_btn.clicked.connect(self._on_browse_sound)
        self._sound_browse_btn.setVisible(False)
        layout.addWidget(self._sound_browse_btn)

        self._sound_hint = QLabel(
            f"自定义提示音将复制到: {self._sound_dir}"
        )
        self._sound_hint.setStyleSheet("color: #999; font-size: 10px;")
        self._sound_hint.setVisible(False)
        layout.addWidget(self._sound_hint)

        # ── 按钮 ──
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

        # 初始化显示默认规则（一次性）的 UI
        self._on_rule_changed()

    # ═══════════════════════════════════════════
    # 规则 UI 构建
    # ═══════════════════════════════════════════

    def _make_combo(self, items: list[str], width: int = 65) -> QComboBox:
        cb = QComboBox()
        cb.addItems(items)
        cb.setMinimumWidth(width)
        return cb

    def _build_once_ui(self):
        w = QFrame()
        ly = QHBoxLayout(w); ly.setContentsMargins(0, 0, 0, 0)
        self._once_dt = QDateTimeEdit(QDateTime.currentDateTime().addSecs(60))
        self._once_dt.setCalendarPopup(True)
        self._once_dt.setDisplayFormat("yyyy-MM-dd HH:mm")
        ly.addWidget(QLabel("触发时间："))
        ly.addWidget(self._once_dt, 1)
        return w

    def _build_time_ui(self):
        w = QFrame()
        ly = QHBoxLayout(w); ly.setContentsMargins(0, 0, 0, 0)
        self._hour_combo = self._make_combo([f"{h:02d}" for h in range(24)])
        self._min_combo = self._make_combo([f"{m:02d}" for m in range(0, 60, 5)])
        ly.addWidget(QLabel("时")); ly.addWidget(self._hour_combo)
        ly.addWidget(QLabel("分")); ly.addWidget(self._min_combo)
        ly.addStretch()
        return w

    def _build_weekly_ui(self):
        w = QFrame()
        ly = QVBoxLayout(w); ly.setContentsMargins(0, 0, 0, 0); ly.setSpacing(4)
        day_ly = QHBoxLayout(); day_ly.setSpacing(4)
        self._weekday_checks: dict[int, QCheckBox] = {}
        for i, dn in enumerate(["一", "二", "三", "四", "五", "六", "日"]):
            cb = QCheckBox(dn); self._weekday_checks[i + 1] = cb; day_ly.addWidget(cb)
        day_ly.addStretch(); ly.addLayout(day_ly)
        time_ly = QHBoxLayout()
        self._w_hour = self._make_combo([f"{h:02d}" for h in range(24)])
        self._w_min = self._make_combo([f"{m:02d}" for m in range(0, 60, 5)])
        time_ly.addWidget(QLabel("时")); time_ly.addWidget(self._w_hour)
        time_ly.addWidget(QLabel("分")); time_ly.addWidget(self._w_min)
        time_ly.addStretch(); ly.addLayout(time_ly)
        return w

    def _build_monthly_ui(self):
        w = QFrame()
        ly = QHBoxLayout(w); ly.setContentsMargins(0, 0, 0, 0); ly.setSpacing(6)
        self._day_combo = self._make_combo([f"{d}号" for d in range(1, 32)] + ["最后一天"], width=80)
        self._m_hour = self._make_combo([f"{h:02d}" for h in range(24)])
        self._m_min = self._make_combo([f"{m:02d}" for m in range(0, 60, 5)])
        ly.addWidget(QLabel("每月")); ly.addWidget(self._day_combo)
        ly.addWidget(QLabel("时")); ly.addWidget(self._m_hour)
        ly.addWidget(QLabel("分")); ly.addWidget(self._m_min)
        ly.addStretch()
        return w

    def _build_interval_ui(self):
        w = QFrame()
        ly = QHBoxLayout(w); ly.setContentsMargins(0, 0, 0, 0); ly.setSpacing(6)
        self._interval_spin = self._make_combo([str(d) for d in range(1, 31)])
        self._interval_spin.setEditable(True)
        self._i_hour = self._make_combo([f"{h:02d}" for h in range(24)])
        self._i_min = self._make_combo([f"{m:02d}" for m in range(0, 60, 5)])
        ly.addWidget(QLabel("每隔")); ly.addWidget(self._interval_spin)
        ly.addWidget(QLabel("天")); ly.addWidget(QLabel("时"))
        ly.addWidget(self._i_hour); ly.addWidget(QLabel("分"))
        ly.addWidget(self._i_min); ly.addStretch()
        return w

    def _on_rule_changed(self):
        while self._rule_container.count():
            item = self._rule_container.takeAt(0)
            if item.widget():
                item.widget().setParent(None)
        mapping = {0: self._rule_once, 1: self._rule_daily, 2: self._rule_weekly,
                   3: self._rule_monthly, 4: self._rule_interval}
        w = mapping.get(self._rule_type.currentIndex())
        if w:
            self._rule_container.addWidget(w)
        if self._rule_type.currentIndex() == 3:
            hint = QLabel("（30/31号及最后一天需对应月份才触发）")
            hint.setStyleSheet("color: #999; font-size: 10px;")
            self._rule_container.addWidget(hint)

    # ═══════════════════════════════════════════
    # 动作行（每个动作独立文件选择）
    # ═══════════════════════════════════════════

    def _build_action_row(self, key: str, label: str, file_filter: str | None, hint: str | None) -> QWidget:
        """构建一个动作行：勾选框 + 弹出内容 / 路径选择 + 浏览按钮 + 可选提示。"""
        row = QWidget()
        rly = QVBoxLayout(row)
        rly.setContentsMargins(0, 0, 0, 0)
        rly.setSpacing(2)

        top = QHBoxLayout(); top.setSpacing(6)
        cb = QCheckBox(label)
        cb.toggled.connect(lambda checked, k=key: self._on_action_toggled(k, checked))
        top.addWidget(cb)

        if key == "popup":
            # 弹窗提醒：文本编辑 + 图片插入
            popup_edit = QTextEdit()
            popup_edit.setPlaceholderText("弹窗提醒内容（支持插入图片）...")
            popup_edit.setMaximumHeight(80)
            popup_edit.setAcceptRichText(True)
            popup_edit.hide()
            top.addWidget(popup_edit, 1)

            img_btn = QPushButton("插入图片")
            img_btn.setFixedWidth(90)
            img_btn.setStyleSheet("font-size: 12px; padding: 2px 4px;")
            img_btn.hide()
            img_btn.clicked.connect(lambda: self._on_insert_popup_image(popup_edit))
            top.addWidget(img_btn)

            self._action_rows[key] = {
                "cb": cb, "popup_edit": popup_edit, "img_btn": img_btn,
                "browse": None, "path": None, "hint": None, "filter": None,
            }
        else:
            path_edit = QLineEdit()
            path_edit.setReadOnly(True)
            path_edit.setPlaceholderText("未选择")
            path_edit.setStyleSheet("background: #f5f5f5; color: #555; font-size: 11px;")
            path_edit.hide()
            top.addWidget(path_edit, 1)

            browse_btn = QPushButton("浏览...")
            browse_btn.setFixedWidth(72)
            browse_btn.hide()
            browse_btn.clicked.connect(lambda checked, k=key, f=file_filter: self._on_browse_action(k, f))
            top.addWidget(browse_btn)

            hint_lbl = None
            if hint:
                hint_lbl = QLabel(hint)
                hint_lbl.setStyleSheet("color: #e67e22; font-size: 10px;")
                hint_lbl.hide()
                rly.addWidget(hint_lbl)

            self._action_rows[key] = {
                "cb": cb, "path": path_edit, "browse": browse_btn, "hint": hint_lbl,
                "filter": file_filter, "popup_edit": None, "img_btn": None,
            }

        rly.addLayout(top)
        return row

    def _on_action_toggled(self, key: str, checked: bool):
        row = self._action_rows[key]
        if key == "popup":
            row["popup_edit"].setVisible(checked)
            row["img_btn"].setVisible(checked)
        else:
            row["path"].setVisible(checked)
            row["browse"].setVisible(checked)
            if row["hint"]:
                row["hint"].setVisible(checked)

    def _on_browse_action(self, key: str, file_filter: str | None):
        row = self._action_rows[key]
        if key == "open_folder":
            path = QFileDialog.getExistingDirectory(self, "选择文件夹")
        else:
            flt = file_filter if file_filter else "所有文件 (*.*)"
            path, _ = QFileDialog.getOpenFileName(self, f"选择{row['cb'].text()}", "", flt)
        if path:
            row["path"].setText(path)

    def _on_insert_popup_image(self, editor: QTextEdit):
        """在弹窗编辑器中插入图片。"""
        path, _ = QFileDialog.getOpenFileName(
            self, "选择图片", "",
            "图片文件 (*.png *.jpg *.jpeg *.gif *.bmp *.webp);;所有文件 (*.*)"
        )
        if not path:
            return
        import uuid
        config = AppConfig.instance()
        img_dir = _os_module.path.join(config.DATA_DIR, "images")
        _os_module.makedirs(img_dir, exist_ok=True)

        ext = _os_module.path.splitext(path)[1] or ".png"
        dest = _os_module.path.join(img_dir, f"task_img_{uuid.uuid4().hex[:8]}{ext}")
        shutil.copy2(path, dest)

        img_path = dest.replace("\\", "/")
        editor.textCursor().insertHtml(f'<img src="file:///{img_path}" style="max-width:100%;">')

    # ═══════════════════════════════════════════
    # 声音
    # ═══════════════════════════════════════════

    def _on_sound_toggled(self):
        v = self._sound_enabled.isChecked()
        self._sound_combo.setVisible(v)
        self._sound_browse_btn.setVisible(v)
        self._sound_hint.setVisible(v)

    def _refresh_sound_list(self):
        self._sound_combo.clear()
        self._sound_combo.addItem("系统提示音（默认）", "")
        for fname in sorted(os.listdir(self._sound_dir)):
            if fname.lower().endswith(('.wav', '.mp3', '.flac', '.ogg')):
                self._sound_combo.addItem(fname, os.path.join(self._sound_dir, fname))
        self._sound_combo.addItem("选择其他文件...", "__browse__")

    def _on_browse_sound(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择音频文件", "",
            "音频文件 (*.wav *.mp3 *.flac *.ogg);;所有文件 (*.*)"
        )
        if not path:
            return
        # 复制到 sounds 目录
        fname = os.path.basename(path)
        dest = os.path.join(self._sound_dir, fname)
        if not os.path.exists(dest):
            shutil.copy2(path, dest)
        self._refresh_sound_list()
        # 选中新添加的文件
        for i in range(self._sound_combo.count()):
            if self._sound_combo.itemData(i) == dest:
                self._sound_combo.setCurrentIndex(i)
                break

    # ═══════════════════════════════════════════
    # 加载数据
    # ═══════════════════════════════════════════

    def _load_data(self):
        if self._task_data:
            d = self._task_data
            self._name_edit.setText(d.get("name", ""))
            self._desc_edit.setPlainText(d.get("description", ""))

            # 规则
            rt = d.get("rule_type", "daily")
            rv = d.get("rule_value", "09:00")
            rt_idx = {"once": 0, "daily": 1, "weekly": 2, "monthly": 3, "interval": 4}
            self._rule_type.setCurrentIndex(rt_idx.get(rt, 1))
            self._on_rule_changed()

            if rt == "once":
                try:
                    dt = QDateTime.fromString(rv, "yyyy-MM-dd HH:mm")
                    if dt.isValid():
                        self._once_dt.setDateTime(dt)
                except Exception:
                    pass
            elif rt in ("daily", "weekly", "monthly", "interval"):
                try:
                    time_part = rv.split("@")[-1]
                    h, m = map(int, time_part.split(":"))
                    if rt == "daily":
                        self._hour_combo.setCurrentIndex(h)
                        self._min_combo.setCurrentIndex(m // 5)
                    elif rt == "weekly":
                        for dn in rv.split("@")[0].split(","):
                            dn = dn.strip()
                            if dn.isdigit() and int(dn) in self._weekday_checks:
                                self._weekday_checks[int(dn)].setChecked(True)
                        self._w_hour.setCurrentIndex(h)
                        self._w_min.setCurrentIndex(m // 5)
                    elif rt == "monthly":
                        day_part = rv.split("@")[0]
                        if day_part == "last":
                            self._day_combo.setCurrentIndex(31)
                        elif day_part.isdigit():
                            self._day_combo.setCurrentIndex(int(day_part) - 1)
                        self._m_hour.setCurrentIndex(h)
                        self._m_min.setCurrentIndex(m // 5)
                    elif rt == "interval":
                        days_part = rv.split("@")[0]
                        idx = self._interval_spin.findText(days_part)
                        if idx >= 0:
                            self._interval_spin.setCurrentIndex(idx)
                        else:
                            self._interval_spin.setEditText(days_part)
                        self._i_hour.setCurrentIndex(h)
                        self._i_min.setCurrentIndex(m // 5)
                except Exception:
                    pass

            # 日期
            if d.get("start_date"):
                self._use_start.setChecked(True)
                self._start_date.setDateTime(QDateTime.fromSecsSinceEpoch(d["start_date"]))
            if d.get("end_date"):
                self._use_end.setChecked(True)
                self._end_date.setDateTime(QDateTime.fromSecsSinceEpoch(d["end_date"]))

            # 动作多选 + 路径/弹窗内容
            actions = [a.strip() for a in d.get("action_type", "").split(",") if a.strip()]
            # action_value 格式：key1|path1;;key2|path2（弹窗为 key|HTML）
            av = d.get("action_value", "")
            action_data = {}
            if av:
                for part in av.split(";;"):
                    part = part.strip()
                    if "|" in part:
                        k, p = part.split("|", 1)
                        action_data[k.strip()] = p.strip()

            for key in self._action_rows:
                row = self._action_rows[key]
                if key in actions:
                    row["cb"].setChecked(True)
                if key in action_data:
                    if key == "popup":
                        content = action_data[key]
                        if content and _is_html(content):
                            row["popup_edit"].setHtml(content)
                        elif content:
                            row["popup_edit"].setPlainText(content)
                    elif row.get("path"):
                        row["path"].setText(action_data[key])

            # 声音
            sp = d.get("sound_path", "")
            if d.get("sound_enabled"):
                self._sound_enabled.setChecked(True)
                if sp and os.path.exists(sp):
                    found = False
                    for i in range(self._sound_combo.count()):
                        if self._sound_combo.itemData(i) == sp:
                            self._sound_combo.setCurrentIndex(i)
                            found = True
                            break
                    if not found:
                        self._sound_combo.setCurrentIndex(0)
                else:
                    self._sound_combo.setCurrentIndex(0)
            self._on_sound_toggled()

    # ═══════════════════════════════════════════
    # 保存
    # ═══════════════════════════════════════════

    def _on_save(self):
        name = self._name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "提示", "任务名不能为空")
            return

        rule_type, rule_value = self._collect_rule()
        if not rule_value:
            QMessageBox.warning(self, "提示", "请完整设置时间规则")
            return

        actions = [k for k, row in self._action_rows.items() if row["cb"].isChecked()]
        if not actions:
            QMessageBox.warning(self, "提示", "请至少选择一个触发动作")
            return

        # 动作值：key1|path1;;key2|path2（弹窗存储 HTML）
        action_parts = []
        for k in actions:
            if k == "popup":
                html = self._action_rows[k]["popup_edit"].toHtml()
                action_parts.append(f"{k}|{html}")
            else:
                p = self._action_rows[k]["path"].text()
                action_parts.append(f"{k}|{p}")
        action_value = "\n;;\n".join(action_parts)

        sd = int(self._start_date.dateTime().toSecsSinceEpoch()) if self._use_start.isChecked() else None
        ed = int(self._end_date.dateTime().toSecsSinceEpoch()) if self._use_end.isChecked() else None

        # 声音
        sound_enabled = 1 if self._sound_enabled.isChecked() else 0
        sound_path = ""
        if sound_enabled:
            data = self._sound_combo.currentData()
            if data and data != "__browse__":
                sound_path = data

        kwargs = dict(
            name=name, description=self._desc_edit.toPlainText().strip(),
            rule_type=rule_type, rule_value=rule_value,
            action_type=",".join(actions), action_value=action_value,
            start_date=sd, end_date=ed,
            sound_path=sound_path, sound_enabled=sound_enabled,
        )

        if self._is_new:
            tid = self._store.create(**kwargs)
        else:
            tid = self._task_data["id"]
            self._store.update(tid, **kwargs)

        # 如果选择了"打开软件"且当前无管理员权限，提示并重启获取权限
        if "open_app" in actions and not _is_admin():
            self.saved.emit(tid)
            self.accept()
            reply = QMessageBox.question(
                self.parent(), "需要管理员权限",
                "此任务包含\"打开软件\"动作，需要管理员权限才能确保软件正常启动。\n\n"
                "是否现在以管理员权限重启 InfoVault？\n"
                "（任务已保存，重启后自动生效）",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.Yes:
                _restart_as_admin()
                from PySide6.QtWidgets import QApplication
                QApplication.quit()
            return

        self.saved.emit(tid)
        self.accept()

    def _collect_rule(self):
        idx = self._rule_type.currentIndex()
        if idx == 0:
            return "once", self._once_dt.dateTime().toString("yyyy-MM-dd HH:mm")
        elif idx == 1:
            h, m = self._hour_combo.currentIndex(), self._min_combo.currentIndex() * 5
            return "daily", f"{h:02d}:{m:02d}"
        elif idx == 2:
            days = [str(k) for k, cb in self._weekday_checks.items() if cb.isChecked()]
            if not days:
                return "weekly", ""
            h, m = self._w_hour.currentIndex(), self._w_min.currentIndex() * 5
            return "weekly", f"{','.join(days)}@{h:02d}:{m:02d}"
        elif idx == 3:
            day_str = self._day_combo.currentText()
            day = "last" if day_str == "最后一天" else str(int(day_str.replace("号", "")))
            h, m = self._m_hour.currentIndex(), self._m_min.currentIndex() * 5
            return "monthly", f"{day}@{h:02d}:{m:02d}"
        elif idx == 4:
            interval = self._interval_spin.currentText().strip()
            if not interval.isdigit():
                return "interval", ""
            h, m = self._i_hour.currentIndex(), self._i_min.currentIndex() * 5
            return "interval", f"{interval}@{h:02d}:{m:02d}"
        return "", ""
