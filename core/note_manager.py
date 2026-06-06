"""微笔记数据管理 - NoteStore。

封装 notes、notes_fts、tags、note_tags 四表的 CRUD，
支持 FTS5 全文搜索和标签多对多关联。
"""

import time
from data.db import Database


class NoteStore:
    """笔记数据操作。"""

    def __init__(self, db: Database):
        self._db = db

    # ================================================================
    # 笔记 CRUD
    # ================================================================

    def create(self, title: str, content: str = "") -> int:
        """创建笔记，返回 note_id。"""
        now = int(time.time())
        cursor = self._db.execute(
            "INSERT INTO notes (title, content, sort_order, created, modified) VALUES (?, ?, ?, ?, ?)",
            (title, content, now, now, now),
        )
        note_id = cursor.lastrowid
        # 同步 FTS（外部内容表只插入 rowid，内容从 notes 表读取）
        self._db.execute(
            "INSERT INTO notes_fts (rowid, title, content) VALUES (?, '', '')",
            (note_id,),
        )
        return note_id

    def update(self, note_id: int, **fields):
        """更新笔记字段。"""
        allowed = {"title", "content", "color", "font_color", "sort_order"}
        updates = {k: v for k, v in fields.items() if k in allowed}
        if not updates:
            return
        updates["modified"] = int(time.time())

        set_clause = ", ".join(f"{k} = ?" for k in updates)
        params = list(updates.values()) + [note_id]
        self._db.execute(f"UPDATE notes SET {set_clause} WHERE id = ?", params)

        # 同步 FTS（外部内容表：先删后插）
        if "title" in updates or "content" in updates:
            self._db.execute(
                "INSERT INTO notes_fts(notes_fts, rowid) VALUES('delete', ?)",
                (note_id,),
            )
            self._db.execute(
                "INSERT INTO notes_fts (rowid, title, content) VALUES (?, '', '')",
                (note_id,),
            )

    def delete(self, note_id: int):
        self._db.execute("DELETE FROM notes WHERE id = ?", (note_id,))
        # 外部内容表删除语法
        self._db.execute(
            "INSERT INTO notes_fts(notes_fts, rowid) VALUES('delete', ?)",
            (note_id,),
        )
        self._db.execute("DELETE FROM note_tags WHERE note_id = ?", (note_id,))

    def delete_many(self, note_ids: list[int]):
        """批量删除笔记。"""
        if not note_ids:
            return
        placeholders = ",".join("?" * len(note_ids))
        self._db.execute(f"DELETE FROM notes WHERE id IN ({placeholders})", note_ids)
        for nid in note_ids:
            self._db.execute(
                "INSERT INTO notes_fts(notes_fts, rowid) VALUES('delete', ?)",
                (nid,),
            )
        self._db.execute(f"DELETE FROM note_tags WHERE note_id IN ({placeholders})", note_ids)

    def get(self, note_id: int) -> dict | None:
        note = self._db.fetchone("SELECT * FROM notes WHERE id = ?", (note_id,))
        if not note:
            return None
        note = dict(note)
        note["tags"] = self.get_note_tags(note_id)
        return note

    def get_all(self, tag_ids: list[int] = None,
                sort_by: str = "sort_order", color: str = None) -> list[dict]:
        """获取所有笔记，可选标签筛选和颜色筛选。"""
        conditions = []
        params = []

        if tag_ids:
            placeholders = ",".join("?" * len(tag_ids))
            conditions.append(f"n.id IN (SELECT DISTINCT nt.note_id FROM note_tags nt WHERE nt.tag_id IN ({placeholders}))")
            params.extend(tag_ids)

        if color:
            conditions.append("n.color = ?")
            params.append(color)

        if conditions:
            where_clause = " AND ".join(conditions)
            sql = f"SELECT * FROM notes n WHERE {where_clause} ORDER BY n.{sort_by} DESC"
        else:
            sql = f"SELECT * FROM notes ORDER BY {sort_by} DESC"

        rows = self._db.fetchall(sql, tuple(params))
        result = []
        for row in rows:
            d = dict(row)
            d["tags"] = self.get_note_tags(d["id"])
            result.append(d)
        return result

    def search(self, keyword: str, tag_ids: list[int] = None,
               limit: int = 50, offset: int = 0) -> list[dict]:
        """搜索笔记标题和内容（LIKE 模糊匹配）。"""
        like = f"%{keyword}%"
        if tag_ids:
            placeholders = ",".join("?" * len(tag_ids))
            sql = f"""SELECT DISTINCT n.* FROM notes n
                JOIN note_tags nt ON n.id = nt.note_id
                WHERE (n.title LIKE ? OR n.content LIKE ?)
                AND nt.tag_id IN ({placeholders})
                ORDER BY n.modified DESC
                LIMIT ? OFFSET ?"""
            rows = self._db.fetchall(sql, (like, like, *tag_ids, limit, offset))
        else:
            sql = """SELECT * FROM notes
                WHERE title LIKE ? OR content LIKE ?
                ORDER BY modified DESC
                LIMIT ? OFFSET ?"""
            rows = self._db.fetchall(sql, (like, like, limit, offset))
        result = []
        for row in rows:
            d = dict(row)
            d["tags"] = self.get_note_tags(d["id"])
            result.append(d)
        return result

    def reorder(self, note_ids: list[int]):
        """批量更新 sort_order。"""
        for i, nid in enumerate(note_ids):
            self._db.execute(
                "UPDATE notes SET sort_order = ? WHERE id = ?", (i, nid)
            )

    # ================================================================
    # 标签操作
    # ================================================================

    def add_tag(self, name: str) -> int:
        """添加标签，返回 tag_id。名称最多 5 个字符。已存在则返回已有 ID。"""
        name = name.strip()[:5]
        if not name:
            return -1
        # 先查是否存在，避免 INSERT OR IGNORE 的 lastrowid 不可靠
        row = self._db.fetchone("SELECT id FROM tags WHERE name = ?", (name,))
        if row:
            return row["id"]
        cursor = self._db.execute(
            "INSERT INTO tags (name) VALUES (?)", (name,)
        )
        return cursor.lastrowid if cursor.lastrowid else -1

    def get_all_tags(self) -> list[dict]:
        """返回所有被至少一条笔记使用的标签（过滤掉废弃标签）。"""
        return self._db.fetchall(
            """SELECT DISTINCT t.* FROM tags t
               JOIN note_tags nt ON t.id = nt.tag_id
               ORDER BY t.name"""
        )

    def set_note_tags(self, note_id: int, tag_ids: list[int]):
        self._db.execute("DELETE FROM note_tags WHERE note_id = ?", (note_id,))
        for tid in tag_ids:
            self._db.execute(
                "INSERT OR IGNORE INTO note_tags (note_id, tag_id) VALUES (?, ?)",
                (note_id, tid),
            )

    def get_note_tags(self, note_id: int) -> list[dict]:
        return self._db.fetchall(
            """SELECT t.* FROM tags t
               JOIN note_tags nt ON t.id = nt.tag_id
               WHERE nt.note_id = ?""",
            (note_id,),
        )

    # ================================================================
    # 浮动
    # ================================================================

    def set_floating(self, note_id: int, floating: bool):
        self._db.execute(
            "UPDATE notes SET is_floating = ? WHERE id = ?",
            (1 if floating else 0, note_id),
        )

    def get_floating(self) -> list[dict]:
        rows = self._db.fetchall("SELECT * FROM notes WHERE is_floating = 1")
        result = []
        for row in rows:
            d = dict(row)
            d["tags"] = self.get_note_tags(d["id"])
            result.append(d)
        return result