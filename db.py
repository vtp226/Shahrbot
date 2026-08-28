import os
import datetime as dt
import aiosqlite

DB_PATH = os.environ.get("DB_PATH", "bot.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS chats (
    chat_id     INTEGER PRIMARY KEY,
    title       TEXT,
    type        TEXT,
    owner_id    INTEGER,
    active      INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS windows (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id         INTEGER NOT NULL,
    start_time      TEXT NOT NULL,   -- "HH:MM"
    end_time        TEXT NOT NULL,   -- "HH:MM" or "24:00"
    interval_hours  REAL NOT NULL,
    FOREIGN KEY (chat_id) REFERENCES chats (chat_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS posts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id         INTEGER NOT NULL,
    owner_id        INTEGER,
    content_type    TEXT NOT NULL,   -- text / photo / video
    text            TEXT,
    file_id         TEXT,
    status          TEXT DEFAULT 'pending',  -- pending/scheduled/sent/cancelled/failed
    scheduled_time  TEXT,
    created_at      TEXT,
    sent_at         TEXT,
    FOREIGN KEY (chat_id) REFERENCES chats (chat_id) ON DELETE CASCADE
);
"""


async def init_db(app=None):
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute("PRAGMA foreign_keys = ON;")
        await conn.execute("PRAGMA journal_mode = WAL;")
        await conn.executescript(SCHEMA)
        await conn.commit()


def _now_iso():
    return dt.datetime.now(dt.timezone.utc).isoformat()


# ---------- chats ----------

async def upsert_chat(chat_id: int, title: str, chat_type: str, owner_id: int):
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute("PRAGMA foreign_keys = ON;")
        await conn.execute(
            """INSERT INTO chats (chat_id, title, type, owner_id, active)
               VALUES (?, ?, ?, ?, 1)
               ON CONFLICT(chat_id) DO UPDATE SET
                    title=excluded.title,
                    type=excluded.type,
                    owner_id=excluded.owner_id,
                    active=1""",
            (chat_id, title, chat_type, owner_id),
        )
        await conn.commit()


async def deactivate_chat(chat_id: int):
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute("UPDATE chats SET active=0 WHERE chat_id=?", (chat_id,))
        await conn.commit()


async def get_owner_chats(owner_id: int):
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            "SELECT * FROM chats WHERE owner_id=? AND active=1 ORDER BY title", (owner_id,)
        )
        rows = await cur.fetchall()
        return [dict(r) for r in rows]


async def get_chat(chat_id: int):
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute("SELECT * FROM chats WHERE chat_id=?", (chat_id,))
        row = await cur.fetchone()
        return dict(row) if row else None


async def get_active_chat_ids():
    async with aiosqlite.connect(DB_PATH) as conn:
        cur = await conn.execute("SELECT chat_id FROM chats WHERE active=1")
        rows = await cur.fetchall()
        return [r[0] for r in rows]


# ---------- windows ----------

async def add_window(chat_id: int, start_time: str, end_time: str, interval_hours: float):
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute("PRAGMA foreign_keys = ON;")
        await conn.execute(
            "INSERT INTO windows (chat_id, start_time, end_time, interval_hours) VALUES (?, ?, ?, ?)",
            (chat_id, start_time, end_time, interval_hours),
        )
        await conn.commit()


async def get_windows(chat_id: int):
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            "SELECT * FROM windows WHERE chat_id=? ORDER BY start_time", (chat_id,)
        )
        rows = await cur.fetchall()
        return [dict(r) for r in rows]


async def delete_window(window_id: int):
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute("DELETE FROM windows WHERE id=?", (window_id,))
        await conn.commit()


# ---------- posts ----------

async def add_post(chat_id: int, owner_id: int, content_type: str, text: str, file_id: str):
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute("PRAGMA foreign_keys = ON;")
        cur = await conn.execute(
            """INSERT INTO posts (chat_id, owner_id, content_type, text, file_id, status, created_at)
               VALUES (?, ?, ?, ?, ?, 'pending', ?)""",
            (chat_id, owner_id, content_type, text, file_id, _now_iso()),
        )
        await conn.commit()
        return cur.lastrowid


async def get_queue(chat_id: int):
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            """SELECT * FROM posts WHERE chat_id=? AND status IN ('pending','scheduled')
               ORDER BY COALESCE(scheduled_time, '9999'), id""",
            (chat_id,),
        )
        rows = await cur.fetchall()
        return [dict(r) for r in rows]


async def get_pending_posts(chat_id: int):
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            "SELECT * FROM posts WHERE chat_id=? AND status='pending' ORDER BY id", (chat_id,)
        )
        rows = await cur.fetchall()
        return [dict(r) for r in rows]


async def get_scheduled_times(chat_id: int):
    async with aiosqlite.connect(DB_PATH) as conn:
        cur = await conn.execute(
            "SELECT scheduled_time FROM posts WHERE chat_id=? AND status='scheduled'", (chat_id,)
        )
        rows = await cur.fetchall()
        return {r[0] for r in rows}


async def assign_schedule(post_id: int, scheduled_time_iso: str):
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            "UPDATE posts SET status='scheduled', scheduled_time=? WHERE id=?",
            (scheduled_time_iso, post_id),
        )
        await conn.commit()


async def get_due_posts(now_iso: str):
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            "SELECT * FROM posts WHERE status='scheduled' AND scheduled_time<=? ORDER BY scheduled_time",
            (now_iso,),
        )
        rows = await cur.fetchall()
        return [dict(r) for r in rows]


async def mark_sent(post_id: int):
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            "UPDATE posts SET status='sent', sent_at=? WHERE id=?", (_now_iso(), post_id)
        )
        await conn.commit()


async def mark_failed(post_id: int):
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute("UPDATE posts SET status='failed' WHERE id=?", (post_id,))
        await conn.commit()


async def cancel_post(post_id: int):
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            "UPDATE posts SET status='cancelled' WHERE id=? AND status IN ('pending','scheduled')",
            (post_id,),
        )
        await conn.commit()


async def get_post(post_id: int):
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute("SELECT * FROM posts WHERE id=?", (post_id,))
        row = await cur.fetchone()
        return dict(row) if row else None
