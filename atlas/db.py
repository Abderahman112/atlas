"""SQLite storage: chat history, tasks, mood log, and notification de-duplication."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY, chat_id INTEGER NOT NULL, role TEXT NOT NULL,
    content TEXT NOT NULL, ts TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY, title TEXT NOT NULL, due TEXT, notes TEXT,
    done INTEGER NOT NULL DEFAULT 0, created TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS moods (
    id INTEGER PRIMARY KEY, ts TEXT NOT NULL, energy INTEGER, mood TEXT, note TEXT
);
CREATE TABLE IF NOT EXISTS notified (key TEXT PRIMARY KEY, ts TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""


class DB:
    def __init__(self, path: Path | str):
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)

    @contextmanager
    def tx(self):
        with self.conn:
            yield self.conn

    # --- chat history -------------------------------------------------------
    def add_message(self, chat_id: int, role: str, content: str) -> None:
        with self.tx() as c:
            c.execute("INSERT INTO messages (chat_id, role, content, ts) VALUES (?,?,?,?)",
                      (chat_id, role, content, datetime.now().isoformat()))

    def history(self, chat_id: int, limit: int = 30) -> list[dict]:
        """Recent turns as API messages: same-role runs merged, always starting with a user turn."""
        rows = self.conn.execute(
            "SELECT role, content FROM messages WHERE chat_id=? ORDER BY id DESC LIMIT ?",
            (chat_id, limit)).fetchall()[::-1]
        merged: list[dict] = []
        for r in rows:
            if merged and merged[-1]["role"] == r["role"]:
                merged[-1]["content"] += "\n\n" + r["content"]
            else:
                merged.append({"role": r["role"], "content": r["content"]})
        if merged and merged[0]["role"] == "assistant":
            merged.insert(0, {"role": "user", "content": "(earlier conversation)"})
        return merged

    # --- tasks ---------------------------------------------------------------
    def add_task(self, title: str, due: str | None = None, notes: str | None = None) -> int:
        with self.tx() as c:
            cur = c.execute("INSERT INTO tasks (title, due, notes, created) VALUES (?,?,?,?)",
                            (title, due, notes, datetime.now().isoformat()))
            return cur.lastrowid

    def tasks(self, include_done: bool = False) -> list[dict]:
        q = "SELECT * FROM tasks" + ("" if include_done else " WHERE done=0") + \
            " ORDER BY due IS NULL, due"
        return [dict(r) for r in self.conn.execute(q)]

    def complete_task(self, task_id: int) -> bool:
        with self.tx() as c:
            return c.execute("UPDATE tasks SET done=1 WHERE id=?", (task_id,)).rowcount > 0

    # --- mood ------------------------------------------------------------------
    def log_mood(self, energy: int | None, mood: str | None, note: str | None) -> None:
        with self.tx() as c:
            c.execute("INSERT INTO moods (ts, energy, mood, note) VALUES (?,?,?,?)",
                      (datetime.now().isoformat(), energy, mood, note))

    def recent_moods(self, n: int = 7) -> list[dict]:
        return [dict(r) for r in self.conn.execute(
            "SELECT ts, energy, mood, note FROM moods ORDER BY id DESC LIMIT ?", (n,))]

    # --- notification de-dup ----------------------------------------------------
    def claim(self, key: str) -> bool:
        """True the first time a key is seen, so each reminder fires once."""
        with self.tx() as c:
            cur = c.execute("INSERT OR IGNORE INTO notified (key, ts) VALUES (?,?)",
                            (key, datetime.now().isoformat()))
            return cur.rowcount == 1

    def get(self, key: str, default: str | None = None) -> str | None:
        row = self.conn.execute("SELECT value FROM kv WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default

    def set(self, key: str, value: str) -> None:
        with self.tx() as c:
            c.execute("INSERT INTO kv (key, value) VALUES (?,?) "
                      "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))
