"""
Async SQLite database module for authentication, RBAC, and KB management.

Provides connection management and table initialization for:
- users
- reset_tokens
- kb_documents
- token_blacklist
- login_attempts
"""

import os
from contextlib import asynccontextmanager

import aiosqlite

# Database file path - stored alongside the existing email_reports.db
DATABASE_PATH = os.path.join(os.path.dirname(__file__), "aiops.db")


@asynccontextmanager
async def get_db():
    """Async context manager that yields an aiosqlite connection.

    Usage:
        async with get_db() as db:
            await db.execute(...)
    """
    db = await aiosqlite.connect(DATABASE_PATH)
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA journal_mode=WAL")
    await db.execute("PRAGMA foreign_keys=ON")
    try:
        yield db
    finally:
        await db.close()


async def init_db():
    """Initialize the database by creating all required tables if they don't exist."""
    async with get_db() as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('Admin', 'L1_User')),
                first_time_flag BOOLEAN NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS reset_tokens (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                token TEXT UNIQUE NOT NULL,
                expires_at TEXT NOT NULL,
                used BOOLEAN NOT NULL DEFAULT 0,
                FOREIGN KEY (username) REFERENCES users(username)
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS kb_documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                filename TEXT NOT NULL,
                file_path TEXT NOT NULL,
                content_type TEXT NOT NULL,
                file_size INTEGER NOT NULL,
                uploaded_by TEXT NOT NULL,
                uploaded_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (uploaded_by) REFERENCES users(username)
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS token_blacklist (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                jti TEXT UNIQUE NOT NULL,
                expires_at TEXT NOT NULL
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS login_attempts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                attempted_at TEXT NOT NULL DEFAULT (datetime('now')),
                success BOOLEAN NOT NULL DEFAULT 0
            )
        """)

        await db.commit()

        # Seed default admin user if no users exist (first-time bootstrap)
        cursor = await db.execute("SELECT COUNT(*) FROM users")
        row = await cursor.fetchone()
        user_count = row[0] if row else 0

        if user_count == 0:
            from backend.security import hash_password

            admin_password_hash = hash_password("Admin@1234")
            await db.execute(
                """
                INSERT INTO users (username, password_hash, role, first_time_flag)
                VALUES ('admin', ?, 'Admin', 1)
                """,
                (admin_password_hash,),
            )
            await db.commit()
