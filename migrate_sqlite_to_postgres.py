"""One-off migration from the old SQLite database to PostgreSQL.

Usage (with the Compose database running):

    python migrate_sqlite_to_postgres.py

Source:  data/weai.db  (override with SQLITE_DB_PATH)
Target:  DATABASE_URL from .env / the environment
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import sqlite3
from pathlib import Path

from dotenv import load_dotenv
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from db_schema import SCHEMA_STATEMENTS

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
SQLITE_PATH = Path(os.getenv("SQLITE_DB_PATH", BASE_DIR / "data" / "weai.db"))
DATABASE_URL = (os.getenv("DATABASE_URL") or "").strip()
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = "postgresql://" + DATABASE_URL[len("postgres://") :]


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


async def insert_many(connection, statement: str, rows: list[tuple]) -> None:
    """psycopg exposes executemany on cursors, not on connections."""
    async with connection.cursor() as cursor:
        await cursor.executemany(statement, rows)


def read_source() -> dict[str, list[tuple]]:
    if not SQLITE_PATH.exists():
        raise SystemExit(f"SQLite database not found: {SQLITE_PATH}")

    source = sqlite3.connect(SQLITE_PATH)
    source.row_factory = sqlite3.Row
    try:
        tables = {
            name: [tuple(row) for row in source.execute(f"SELECT * FROM {name}")]
            for name in ("users", "app_sessions", "conversations", "messages", "files")
            if source.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
                (name,),
            ).fetchone()
        }
    finally:
        source.close()
    return tables


async def migrate() -> None:
    if not DATABASE_URL:
        raise SystemExit("DATABASE_URL is not configured.")

    tables = read_source()
    pool = AsyncConnectionPool(
        conninfo=DATABASE_URL,
        kwargs={"row_factory": dict_row},
        min_size=1,
        max_size=2,
        open=False,
    )

    async with pool:
        async with pool.connection() as connection:
            for statement in SCHEMA_STATEMENTS:
                await connection.execute(statement)

            if tables.get("users"):
                await insert_many(connection, 
                    """
                    INSERT INTO users (sub, email, name, picture, created_at, last_login)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (sub) DO UPDATE SET
                        email = EXCLUDED.email,
                        name = EXCLUDED.name,
                        picture = EXCLUDED.picture,
                        last_login = EXCLUDED.last_login
                    """,
                    tables["users"],
                )

            if tables.get("app_sessions"):
                await insert_many(connection, 
                    """
                    INSERT INTO app_sessions (token, user_sub, expires_at, created_at)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (token) DO NOTHING
                    """,
                    [
                        (token_hash(row[0]), row[1], row[2], row[3])
                        for row in tables["app_sessions"]
                    ],
                )

            if tables.get("conversations"):
                await insert_many(connection, 
                    """
                    INSERT INTO conversations (id, user_sub, title, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (id) DO NOTHING
                    """,
                    tables["conversations"],
                )

            if tables.get("messages"):
                await insert_many(connection, 
                    """
                    INSERT INTO messages
                        (id, conversation_id, role, content, attachments, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (id) DO NOTHING
                    """,
                    tables["messages"],
                )
                await connection.execute(
                    """
                    SELECT setval(
                        pg_get_serial_sequence('messages', 'id'),
                        GREATEST(COALESCE((SELECT MAX(id) FROM messages), 1), 1),
                        EXISTS (SELECT 1 FROM messages)
                    )
                    """
                )

            if tables.get("files"):
                file_rows = []
                for row in tables["files"]:
                    # Old SQLite rows stored a filesystem path; embed those bytes.
                    old_path = Path(row[5])
                    if not old_path.is_absolute():
                        old_path = BASE_DIR / old_path
                    try:
                        blob = old_path.read_bytes() if old_path.exists() else b""
                    except OSError:
                        blob = b""
                    file_rows.append((row[0], row[1], row[2], row[3], row[4], blob, row[6], row[7]))

                await insert_many(connection, 
                    """
                    INSERT INTO files
                        (id, user_sub, name, mime_type, size, data, extracted_text, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (id) DO NOTHING
                    """,
                    file_rows,
                )

    for name, rows in tables.items():
        print(f"{name}: {len(rows)} row(s) migrated")
    print("Migration complete.")


if __name__ == "__main__":
    asyncio.run(migrate())
