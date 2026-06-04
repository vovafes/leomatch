import aiosqlite
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "bot.db"


async def init_db():
    DB_PATH.parent.mkdir(exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS chats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_chat_id INTEGER UNIQUE,
                username TEXT,
                name TEXT,
                status TEXT DEFAULT 'active',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER,
                sender TEXT,
                text TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (chat_id) REFERENCES chats(id)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        await db.commit()


async def get_or_create_chat(telegram_chat_id: int, username: str, name: str | None = None) -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM chats WHERE telegram_chat_id = ?", (telegram_chat_id,)
        )
        row = await cur.fetchone()
        if row:
            return dict(row)
        await db.execute(
            "INSERT INTO chats (telegram_chat_id, username, name) VALUES (?, ?, ?)",
            (telegram_chat_id, username, name),
        )
        await db.commit()
        cur = await db.execute(
            "SELECT * FROM chats WHERE telegram_chat_id = ?", (telegram_chat_id,)
        )
        return dict(await cur.fetchone())


async def save_message(chat_id: int, sender: str, text: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO messages (chat_id, sender, text) VALUES (?, ?, ?)",
            (chat_id, sender, text),
        )
        await db.commit()


async def get_context(chat_id: int, limit: int = 20) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT sender, text FROM messages WHERE chat_id = ? ORDER BY timestamp DESC LIMIT ?",
            (chat_id, limit),
        )
        rows = await cur.fetchall()
        return [dict(r) for r in reversed(rows)]


async def set_chat_status(telegram_chat_id: int, status: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE chats SET status = ? WHERE telegram_chat_id = ?",
            (status, telegram_chat_id),
        )
        await db.commit()


async def get_all_chats() -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("""
            SELECT c.*,
                   m.text      AS last_message,
                   m.sender    AS last_sender,
                   m.timestamp AS last_message_time
            FROM chats c
            LEFT JOIN messages m ON m.id = (
                SELECT id FROM messages WHERE chat_id = c.id
                ORDER BY timestamp DESC LIMIT 1
            )
            ORDER BY COALESCE(m.timestamp, c.created_at) DESC
        """)
        rows = await cur.fetchall()
        return [dict(r) for r in rows]


async def get_messages_for_chat(chat_id: int, limit: int = 50) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM messages WHERE chat_id = ? ORDER BY timestamp ASC LIMIT ?",
            (chat_id, limit),
        )
        rows = await cur.fetchall()
        return [dict(r) for r in rows]


async def get_stats() -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT COUNT(*) as n FROM chats")
        total = (await cur.fetchone())["n"]
        cur = await db.execute("SELECT COUNT(*) as n FROM chats WHERE status = 'active'")
        active = (await cur.fetchone())["n"]
        cur = await db.execute(
            "SELECT COUNT(*) as n FROM messages WHERE sender='me' AND date(timestamp)=date('now')"
        )
        sent_today = (await cur.fetchone())["n"]
        cur = await db.execute(
            "SELECT COUNT(*) as n FROM chats WHERE date(created_at) = date('now')"
        )
        matches_today = (await cur.fetchone())["n"]
        return {
            "total": total,
            "active": active,
            "paused": total - active,
            "sent_today": sent_today,
            "matches_today": matches_today,
        }


async def get_activity_stats(days: int = 14) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("""
            SELECT date(timestamp) as day,
                   SUM(CASE WHEN sender='me'  THEN 1 ELSE 0 END) as sent,
                   SUM(CASE WHEN sender='her' THEN 1 ELSE 0 END) as received
            FROM messages
            WHERE timestamp >= datetime('now', ? )
            GROUP BY date(timestamp)
            ORDER BY day ASC
        """, (f"-{days} days",))
        rows = await cur.fetchall()
        return [{"day": r[0], "sent": r[1], "received": r[2]} for r in rows]


async def get_setting(key: str, default: str = "") -> str:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT value FROM settings WHERE key = ?", (key,))
        row = await cur.fetchone()
        return row["value"] if row else default


async def set_setting(key: str, value: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?)"
            " ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        await db.commit()
