"""
Async PostgreSQL database module for authentication, RBAC, and KB management.

Provides connection pool management and table initialization for:
- users
- reset_tokens
- kb_documents
- token_blacklist
- login_attempts
"""

import os

import asyncpg

# Database connection string from environment variable
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://aiopsadmin:AiOps2024Secure!@aiops-db.ctq62w4so4tn.ap-south-1.rds.amazonaws.com:5432/aiopsplatform"
)

# Connection pool
_pool = None


async def get_pool():
    """Get or create the connection pool."""
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(DATABASE_URL, min_size=2, max_size=10)
    return _pool


async def get_db():
    """Get a database connection from the pool.

    Returns an asyncpg connection pool. Use as:
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM users WHERE username = $1", username)
    """
    pool = await get_pool()
    return pool


async def init_db():
    """Initialize the database by creating all required tables if they don't exist."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('Admin', 'L1_User')),
                first_time_flag BOOLEAN NOT NULL DEFAULT TRUE,
                created_at TIMESTAMP NOT NULL DEFAULT NOW()
            )
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS reset_tokens (
                id SERIAL PRIMARY KEY,
                username TEXT NOT NULL REFERENCES users(username),
                token TEXT UNIQUE NOT NULL,
                expires_at TIMESTAMP NOT NULL,
                used BOOLEAN NOT NULL DEFAULT FALSE
            )
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS kb_documents (
                id SERIAL PRIMARY KEY,
                title TEXT NOT NULL,
                filename TEXT NOT NULL,
                file_path TEXT NOT NULL,
                content_type TEXT NOT NULL,
                file_size INTEGER NOT NULL,
                uploaded_by TEXT NOT NULL REFERENCES users(username),
                uploaded_at TIMESTAMP NOT NULL DEFAULT NOW()
            )
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS token_blacklist (
                id SERIAL PRIMARY KEY,
                jti TEXT UNIQUE NOT NULL,
                expires_at TIMESTAMP NOT NULL
            )
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS login_attempts (
                id SERIAL PRIMARY KEY,
                username TEXT NOT NULL,
                attempted_at TIMESTAMP NOT NULL DEFAULT NOW(),
                success BOOLEAN NOT NULL DEFAULT FALSE
            )
        """)

        # Seed default admin user if no users exist (first-time bootstrap)
        count = await conn.fetchval("SELECT COUNT(*) FROM users")
        if count == 0:
            from backend.security import hash_password

            admin_hash = hash_password("Admin@1234")
            await conn.execute(
                "INSERT INTO users (username, password_hash, role, first_time_flag) VALUES ($1, $2, $3, $4)",
                "admin", admin_hash, "Admin", True
            )
