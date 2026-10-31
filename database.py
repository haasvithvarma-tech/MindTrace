import sqlite3
from pathlib import Path

# Resolve the database path relative to this file, regardless of
# where the application is launched from.
DB_PATH = Path(__file__).parent / "mindtrace.db"


def get_db():
    """Return a sqlite3 connection to mindtrace.db."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # Allows column access by name
    return conn


def init_db():
    """Create the users table if it does not already exist."""
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT    NOT NULL UNIQUE,
            password TEXT    NOT NULL,
            role     TEXT    NOT NULL CHECK(role IN ('teacher', 'student'))
        )
    """)
    conn.commit()
    conn.close()
