"""定时任务调度引擎 - TaskScheduler。

后台轮询，解析五种时间规则，触发动作。
"""

import datetime
import re
import subprocess
import os
import logging
from PySide6.QtCore import QObject, QTimer, Signal

from core.task_manager import TaskStore

log = logging.getLogger("InfoVault.scheduler")


class RuleParser:
    """时间规则解析与匹配。"""

    # ── 公有 ──

    @staticmethod
    def should_trigger(task: dict) -> bool:
        now = datetime.datetime.now()
        rule_type = task.get("rule_type", "daily")
        rule_value = task.get("rule_value", "")

        # 检查时间范围
        start = task.get("start_date")
        end = task.get("end_date")
        ts = int(now.timestamp())
        if start and ts < start:
            return False
        if end and ts >= end:
            return False

        if rule_type == "once":
            return RuleParser._match_once(rule_value, now)
        elif rule_type == "daily":
            return RuleParser._match_daily(rule_value, now)
        elif rule_type == "weekly":
            return RuleParser._match_weekly(rule_value, now)
        elif rule_type == "monthly":
            return RuleParser._match_monthly(rule_value, now)
        elif rule_type == "interval":
            return RuleParser._match_interval(rule_value, now)
        return False

    # ── 各规则匹配 ──

    @staticmethod
    def _match_once(value: str, now: datetime.datetime) -> bool:
        """value = 'YYYY-MM-DD HH:MM'"""
        try:
            target = datetime.datetime.strptime(value.strip(), "%Y-%m-%d %H:%M")
            diff = abs((now - target).total_seconds())
            return diff < 60
        except Exception:
            return False

    @staticmethod
    def _match_daily(value: str, now: datetime.datetime) -> bool:
        """value = 'HH:MM'"""
        try:
            h, m = map(int, value.strip().split(":"))
            return now.hour == h and now.minute == m
        except Exception:
            return False

    @staticmethod
    def _match_weekly(value: str, now: datetime.datetime) -> bool:
        """value = '1,3,5@HH:MM'（周一到周日=1~7）"""
        try:
            days_str, time_str = value.strip().split("@")
            days = {int(d.strip()) for d in days_str.split(",")}
            h, m = map(int, time_str.split(":"))
            weekday = now.isoweekday()
            return weekday in days and now.hour == h and now.minute == m
        except Exception:
            return False

    @staticmethod
    def _match_monthly(value: str, now: datetime.datetime) -> bool:
        """value = '15@HH:MM' 或 'last@HH:MM'"""
        try:
            day_str, time_str = value.strip().split("@")
            h, m = map(int, time_str.split(":"))
            if not (now.hour == h and now.minute == m):
                return False
            if day_str == "last":
                import calendar
                last_day = calendar.monthrange(now.year, now.month)[1]
                return now.day == last_day
            target_day = int(day_str)
            return now.day == target_day
        except Exception:
            return False

    @staticmethod
    def _match_interval(value: str, now: datetime.datetime) -> bool:
        """value = '3@HH:MM'（每隔 N 天）"""
        try:
            days_str, time_str = value.strip().split("@")
            interval = int(days_str)
            h, m = map(int, time_str.split(":"))
            if not (now.hour == h and now.minute == m):
                return False
            # 以 epoch 为基准，每隔 interval 天触发
            epoch = datetime.datetime(2026, 1, 1)
            diff_days = (now.date() - epoch.date()).days
            return diff_days % interval == 0
        except Exception:
            return False


class TaskScheduler(QObject):
    """定时任务调度器。

    信号:
        remind_requested(dict): 需要弹窗提醒（任务数据）
        action_executed(int, str): task_id, 状态
    """

    remind_requested = Signal(dict)
    action_executed = Signal(int, str)

    def __init__(self, task_store: TaskStore):
        super().__init__()
        self._store = task_store
        self._timer: QTimer | None = None
        self._paused = False
        self._last_fired: dict[int, str] = {}  # task_id → 上次触发的分钟标识

    def start(self):
        if self._timer:
            return
        self._timer = QTimer()
        self._timer.timeout.connect(self._tick)
        self._timer.start(1000)  # 每秒检查一次
        log.info("TaskScheduler 已启动")

    def stop(self):
        if self._timer:
            self._timer.stop()
            self._timer = None
        log.info("TaskScheduler 已停止")

    def pause(self):
        self._paused = True
        log.info("TaskScheduler 已暂停（免打扰）")

    def resume(self):
        self._paused = False
        log.info("TaskScheduler 已恢复")

    def is_paused(self) -> bool:
        return self._paused

    # ── 内部 ──

    def _tick(self):
        if self._paused:
            return
        try:
            tasks = self._store.get_enabled()
            now = datetime.datetime.now()
            minute_key = now.strftime("%Y%m%d%H%M")
            for task in tasks:
                tid = task["id"]
                # 同一分钟内不重复触发
                if self._last_fired.get(tid) == minute_key:
                    continue
                if RuleParser.should_trigger(task):
                    self._last_fired[tid] = minute_key
                    self._execute(task)
        except Exception as e:
            log.error(f"调度异常: {e}", exc_info=True)

    def _execute(self, task: dict):
        tid = task["id"]
        action_type = task.get("action_type", "popup")
        action_value = task.get("action_value", "") or ""
        actions = [a.strip() for a in action_type.split(",") if a.strip()]

        # 解析 key|path;;key|path
        path_map: dict[str, str] = {}
        if action_value:
            for part in action_value.split(";;"):
                if "|" in part:
                    k, p = part.split("|", 1)
                    path_map[k.strip()] = p.strip()

        # 先播放提示音
        if task.get("sound_enabled"):
            self._play_sound(task.get("sound_path", ""))

        for act in actions:
            value = path_map.get(act, "")
            try:
                if act == "popup":
                    self.remind_requested.emit(task)
                    self._store.log(tid, "success", "弹窗提醒已触发")
                elif act == "open_file":
                    if value and os.path.exists(value):
                        os.startfile(value)
                        self._store.log(tid, "success", f"已打开文件: {value}")
                    else:
                        self._store.log(tid, "failure", f"文件不存在: {value}")
                elif act == "open_folder":
                    if value and os.path.exists(value):
                        os.startfile(value)
                        self._store.log(tid, "success", f"已打开文件夹: {value}")
                    else:
                        self._store.log(tid, "failure", f"文件夹不存在: {value}")
                elif act == "open_app":
                    if value and os.path.exists(value):
                        try:
                            self._run_as_admin(value)
                            self._store.log(tid, "success", f"已启动软件: {value}")
                        except Exception as e:
                            self._store.log(tid, "failure", f"启动失败: {e}")
                    else:
                        self._store.log(tid, "failure", f"软件路径不存在: {value}")
                elif act == "run_script":
                    if value:
                        self._run_script(task, value)
                        return  # 脚本需确认
                    else:
                        self._store.log(tid, "failure", "未指定脚本路径")
                else:
                    self._store.log(tid, "failure", f"未知动作: {act}")
            except Exception as e:
                self._store.log(tid, "failure", str(e))
                log.error(f"任务 {tid} 动作 {act} 失败: {e}")

    def _run_as_admin(self, path: str):
        """以管理员权限运行可执行文件（触发 UAC）。"""
        import ctypes
        # ShellExecuteW(hwnd, lpOperation, lpFile, lpParameters, lpDirectory, nShowCmd)
        SW_SHOWNORMAL = 1
        ret = ctypes.windll.shell32.ShellExecuteW(
            None, "runas", path, None, None, SW_SHOWNORMAL
        )
        if ret <= 32:
            # > 32 表示成功
            error_codes = {
                2: "文件不存在",
                3: "路径不存在",
                5: "访问被拒绝",
                8: "内存不足",
                32: "DLL 未找到",
            }
            msg = error_codes.get(ret, f"错误码 {ret}")
            raise OSError(f"以管理员权限启动失败: {msg}")

    def _play_sound(self, path: str):
        """播放系统提示音或指定音频文件。"""
        if path and os.path.exists(path):
            # 使用 winsound 播放 wav（Windows 原生，无需额外依赖）
            import winsound
            winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC)
        else:
            import winsound
            winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)

    def _run_script(self, task: dict, value: str):
        """执行脚本/命令（通知 UI 确认后才执行）。"""
        self.remind_requested.emit({
            **task,
            "_confirm_script": True,
            "_script_path": value,
        })

    def execute_confirmed_script(self, task: dict):
        """UI 确认后执行脚本。"""
        tid = task["id"]
        value = task.get("_script_path", task.get("action_value", ""))
        try:
            result = subprocess.run(
                value, shell=True,
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode == 0:
                self._store.log(tid, "success", f"脚本执行成功\n{result.stdout[:500]}")
            else:
                self._store.log(tid, "failure", f"脚本退出码: {result.returncode}\n{result.stderr[:500]}")
        except subprocess.TimeoutExpired:
            self._store.log(tid, "failure", "脚本执行超时（30 秒）")
        except Exception as e:
            self._store.log(tid, "failure", str(e))
