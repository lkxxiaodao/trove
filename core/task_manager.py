"""定时任务数据管理 - TaskStore。

封装 tasks、task_logs 表的 CRUD，支持状态筛选和搜索。
"""

import time
from data.db import Database


class TaskStore:
    """定时任务数据操作。"""

    def __init__(self, db: Database):
        self._db = db

    # ================================================================
    # 任务 CRUD
    # ================================================================

    def create(self, name: str, description: str = "",
               rule_type: str = "daily", rule_value: str = "09:00",
               action_type: str = "popup", action_value: str = "",
               start_date: int = None, end_date: int = None,
               sound_path: str = "", sound_enabled: int = 0) -> int:
        """创建任务，返回 task_id。"""
        now = int(time.time())
        cursor = self._db.execute(
            """INSERT INTO tasks
               (name, description, rule_type, rule_value, start_date, end_date,
                action_type, action_value, enabled, created, modified,
                sound_path, sound_enabled)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?)""",
            (name, description, rule_type, rule_value,
             start_date, end_date, action_type, action_value, now, now,
             sound_path, sound_enabled),
        )
        return cursor.lastrowid

    def update(self, task_id: int, **fields):
        """更新任务字段。"""
        allowed = {"name", "description", "rule_type", "rule_value",
                   "start_date", "end_date", "action_type", "action_value",
                   "enabled", "sound_path", "sound_enabled"}
        updates = {k: v for k, v in fields.items() if k in allowed}
        if not updates:
            return
        updates["modified"] = int(time.time())
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        params = list(updates.values()) + [task_id]
        self._db.execute(f"UPDATE tasks SET {set_clause} WHERE id = ?", params)

    def delete(self, task_id: int):
        self._db.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        self._db.execute("DELETE FROM task_logs WHERE task_id = ?", (task_id,))

    def get(self, task_id: int) -> dict | None:
        row = self._db.fetchone("SELECT * FROM tasks WHERE id = ?", (task_id,))
        return dict(row) if row else None

    def get_all(self, status_filter: str = "all") -> list[dict]:
        """获取任务列表，支持状态筛选。"""
        now = int(time.time())
        if status_filter == "active":
            sql = """SELECT * FROM tasks
                     WHERE enabled = 1 AND (end_date IS NULL OR end_date > ?)
                     ORDER BY modified DESC"""
            rows = self._db.fetchall(sql, (now,))
        elif status_filter == "expired":
            sql = """SELECT * FROM tasks
                     WHERE end_date IS NOT NULL AND end_date <= ?
                     ORDER BY modified DESC"""
            rows = self._db.fetchall(sql, (now,))
        elif status_filter == "disabled":
            rows = self._db.fetchall(
                "SELECT * FROM tasks WHERE enabled = 0 ORDER BY modified DESC"
            )
        else:
            rows = self._db.fetchall("SELECT * FROM tasks ORDER BY modified DESC")
        return [dict(r) for r in rows]

    def get_enabled(self) -> list[dict]:
        """仅返回已启用的任务（供调度器使用）。"""
        rows = self._db.fetchall(
            "SELECT * FROM tasks WHERE enabled = 1"
        )
        return [dict(r) for r in rows]

    def toggle_enabled(self, task_id: int) -> bool:
        """切换启用状态，返回新状态。"""
        row = self._db.fetchone(
            "SELECT enabled FROM tasks WHERE id = ?", (task_id,)
        )
        if not row:
            return False
        new_val = 0 if row["enabled"] else 1
        self._db.execute(
            "UPDATE tasks SET enabled = ?, modified = ? WHERE id = ?",
            (new_val, int(time.time()), task_id),
        )
        return bool(new_val)

    def search(self, keyword: str) -> list[dict]:
        """搜索任务名和描述。"""
        like = f"%{keyword}%"
        rows = self._db.fetchall(
            "SELECT * FROM tasks WHERE name LIKE ? OR description LIKE ? ORDER BY modified DESC",
            (like, like),
        )
        return [dict(r) for r in rows]

    # ================================================================
    # 执行日志
    # ================================================================

    def log(self, task_id: int, status: str, message: str = ""):
        """记录一次触发日志。"""
        self._db.execute(
            "INSERT INTO task_logs (task_id, triggered_at, status, message) VALUES (?, ?, ?, ?)",
            (task_id, int(time.time()), status, message),
        )

    def get_logs(self, task_id: int, limit: int = 50) -> list[dict]:
        rows = self._db.fetchall(
            "SELECT * FROM task_logs WHERE task_id = ? ORDER BY triggered_at DESC LIMIT ?",
            (task_id, limit),
        )
        return [dict(r) for r in rows]

    def clear_logs(self, task_id: int = None):
        """清除日志。task_id=None 清除所有。"""
        if task_id is not None:
            self._db.execute("DELETE FROM task_logs WHERE task_id = ?", (task_id,))
        else:
            self._db.execute("DELETE FROM task_logs")
