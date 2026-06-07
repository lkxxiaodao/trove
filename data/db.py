"""SQLite 数据库管理层。

特性：
- WAL 模式开启，提升并发读写性能
- 线程安全写入队列（生产者-消费者）
- 版本化数据库迁移（migrate）
"""

import sqlite3
import threading
import logging
from queue import Queue, Empty

log = logging.getLogger("trove.db")


# ============================================================
# 数据库迁移脚本（版本号 → SQL 清单）
# ============================================================

ClipboardMigrations = {
    1: [
        """
        CREATE TABLE IF NOT EXISTS history (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            content   TEXT    NOT NULL,
            timestamp INTEGER NOT NULL,
            starred   INTEGER DEFAULT 0
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_history_timestamp ON history(timestamp)",
    ],
    2: [
        "ALTER TABLE history ADD COLUMN clip_type TEXT DEFAULT 'text'",
        "ALTER TABLE history ADD COLUMN file_paths TEXT",
        "ALTER TABLE history ADD COLUMN image_data BLOB",
        "ALTER TABLE history ADD COLUMN content_hash TEXT",
    ],
}

NotesMigrations = {
    1: [
        """
        CREATE TABLE IF NOT EXISTS notes (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            title      TEXT,
            content    TEXT    DEFAULT '',
            color      TEXT    DEFAULT '#FFFFFF',
            sort_order INTEGER DEFAULT 0,
            created    INTEGER,
            modified   INTEGER
        )
        """,
        """
        CREATE VIRTUAL TABLE IF NOT EXISTS notes_fts
        USING fts5(title, content, content=notes, content_rowid=id)
        """,
        """
        CREATE TABLE IF NOT EXISTS tags (
            id   INTEGER PRIMARY KEY,
            name TEXT UNIQUE
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS note_tags (
            note_id INTEGER,
            tag_id  INTEGER,
            PRIMARY KEY (note_id, tag_id)
        )
        """,
    ],
    2: [
        # 重建 FTS 索引，确保已有数据被索引
        "INSERT INTO notes_fts(notes_fts) VALUES('rebuild')",
    ],
    3: [
        "ALTER TABLE notes ADD COLUMN is_floating INTEGER DEFAULT 0",
    ],
    4: [
        "ALTER TABLE notes ADD COLUMN font_color TEXT DEFAULT '#000000'",
    ],
    5: [
        "ALTER TABLE notes ADD COLUMN is_deleted INTEGER DEFAULT 0",
        "ALTER TABLE notes ADD COLUMN note_type TEXT DEFAULT 'normal'",
        "ALTER TABLE notes ADD COLUMN task_schedule TEXT DEFAULT ''",
        "ALTER TABLE notes ADD COLUMN auto_startup INTEGER DEFAULT 0",
    ],
}

TaskMigrations = {
    1: [
        """
        CREATE TABLE IF NOT EXISTS tasks (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            name         TEXT NOT NULL,
            description  TEXT DEFAULT '',
            rule_type    TEXT NOT NULL,
            rule_value   TEXT NOT NULL,
            start_date   INTEGER,
            end_date     INTEGER,
            action_type  TEXT NOT NULL,
            action_value TEXT DEFAULT '',
            enabled      INTEGER DEFAULT 1,
            created      INTEGER,
            modified     INTEGER
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS task_logs (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id      INTEGER NOT NULL,
            triggered_at INTEGER NOT NULL,
            status       TEXT NOT NULL,
            message      TEXT DEFAULT '',
            FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_task_logs_task ON task_logs(task_id)",
        "CREATE INDEX IF NOT EXISTS idx_task_logs_time ON task_logs(triggered_at)",
    ],
    2: [
        "ALTER TABLE tasks ADD COLUMN sound_path TEXT DEFAULT ''",
        "ALTER TABLE tasks ADD COLUMN sound_enabled INTEGER DEFAULT 0",
    ],
}


# ============================================================
# 数据库写入线程
# ============================================================

class _DbWriteWorker(threading.Thread):
    """后台线程，从队列中取写入任务并串行执行，避免 SQLite 并发冲突。"""

    def __init__(self, db_path: str):
        super().__init__(daemon=True)
        self._db_path = db_path
        self._queue = Queue()
        self._stop_event = threading.Event()

    def enqueue(self, sql: str, params=()):
        self._queue.put((sql, params))

    def run(self):
        conn = sqlite3.connect(self._db_path, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        try:
            while not self._stop_event.is_set():
                try:
                    sql, params = self._queue.get(timeout=0.5)
                except Empty:
                    continue
                try:
                    conn.execute(sql, params)
                    conn.commit()
                except sqlite3.Error as e:
                    log.error(f"写入队列执行失败: {e}\n  SQL: {sql}\n  params: {params}")
        finally:
            conn.close()

    def stop(self):
        self._stop_event.set()


# ============================================================
# Database 主类
# ============================================================

class Database:
    """SQLite 数据库封装。

    用法:
        db = Database("path/to/data.db")
        db.migrate(MyMigrations)
        db.execute("INSERT INTO ...", ...)
        rows = db.fetchall("SELECT ...")
        db.close()
    """

    def __init__(self, db_path: str):
        self._db_path = db_path
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._enable_wal()
        self._writer = _DbWriteWorker(db_path)
        self._writer.start()

    def _enable_wal(self):
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")

    # ---- 同步操作（读为主） ----
    def execute(self, sql: str, params=()) -> sqlite3.Cursor:
        """执行 SQL 并返回 cursor。用于读操作和需要立即返回结果的操作。"""
        cursor = self._conn.execute(sql, params)
        self._conn.commit()
        return cursor

    def fetchone(self, sql: str, params=()) -> dict | None:
        """返回单行字典，无结果返回 None。"""
        cursor = self._conn.execute(sql, params)
        row = cursor.fetchone()
        return dict(row) if row else None

    def fetchall(self, sql: str, params=()) -> list[dict]:
        """返回字典列表。"""
        cursor = self._conn.execute(sql, params)
        return [dict(row) for row in cursor.fetchall()]

    # ---- 异步写入（队列） ----
    def enqueue_write(self, sql: str, params=()):
        """将写入操作放入后台队列，不阻塞调用线程。"""
        self._writer.enqueue(sql, params)

    # ---- 迁移 ----
    def migrate(self, migrations: dict[int, list[str]]):
        """按版本号顺序执行迁移脚本。

        Args:
            migrations: {版本号: [SQL语句列表]}
        """
        # 确保版本表存在
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS _schema_version (version INTEGER PRIMARY KEY)"
        )
        self._conn.commit()

        current = self.fetchone("SELECT MAX(version) as v FROM _schema_version")
        current_version = current["v"] if current and current["v"] is not None else 0

        for version in sorted(migrations.keys()):
            if version <= current_version:
                continue
            log.info(f"执行迁移: {self._db_path} -> v{version}")
            for sql in migrations[version]:
                self._conn.execute(sql)
            self._conn.execute(
                "INSERT OR REPLACE INTO _schema_version (version) VALUES (?)",
                (version,),
            )
            self._conn.commit()

    # ---- 关闭 ----
    def close(self):
        self._writer.stop()
        self._writer.join(timeout=2)
        self._conn.close()