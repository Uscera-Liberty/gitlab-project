import os
import sqlite3
from collections.abc import Iterator
from pathlib import Path

SEED_USERS = [
    ("Alice Admin", "alice@example.com", "admin"),
    ("Bob Builder", "bob@example.com", "user"),
    ("Carol Coder", "carol@example.com", "user"),
    ("Dave DevOps", "dave@example.com", "user"),
]

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL,
    email      TEXT NOT NULL UNIQUE,
    role       TEXT NOT NULL DEFAULT 'user',
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
)
"""


def db_path() -> str:
    return os.getenv("DB_PATH", "./data/users.db")


def connect() -> sqlite3.Connection:
    # isolation_level=None — autocommit: каждый запрос фиксируется сразу
    conn = sqlite3.connect(db_path(), isolation_level=None)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Создаёт таблицу и добавляет стартовых пользователей, если таблица пустая."""
    Path(db_path()).parent.mkdir(parents=True, exist_ok=True)
    conn = connect()
    try:
        conn.execute(SCHEMA)
        (count,) = conn.execute("SELECT COUNT(*) FROM users").fetchone()
        if count == 0:
            conn.executemany("INSERT INTO users (name, email, role) VALUES (?, ?, ?)", SEED_USERS)
    finally:
        conn.close()


def get_conn() -> Iterator[sqlite3.Connection]:
    """FastAPI-зависимость: отдельное соединение на каждый запрос."""
    conn = connect()
    try:
        yield conn
    finally:
        conn.close()
