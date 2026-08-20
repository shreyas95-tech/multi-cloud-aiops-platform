"""Tests for the RateLimiter class in backend/security.py."""

import sys
import os

# Add project root to path so backend package is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
import asyncio
from datetime import datetime, timedelta

import aiosqlite

from backend.security import RateLimiter, RATE_LIMIT_MAX_ATTEMPTS, RATE_LIMIT_WINDOW_MINUTES
from backend.database import DATABASE_PATH, get_db, init_db


@pytest.fixture(autouse=True)
def use_temp_db(tmp_path, monkeypatch):
    """Use a temporary database for each test."""
    test_db_path = str(tmp_path / "test_aiops.db")
    monkeypatch.setattr("backend.database.DATABASE_PATH", test_db_path)
    # Run init_db to create tables
    asyncio.get_event_loop().run_until_complete(init_db())
    yield test_db_path


@pytest.fixture
def rate_limiter():
    return RateLimiter()


class TestRateLimiterIsLocked:
    @pytest.mark.asyncio
    async def test_not_locked_with_no_attempts(self, rate_limiter):
        """User with no failed attempts should not be locked."""
        result = await rate_limiter.is_locked("testuser")
        assert result is False

    @pytest.mark.asyncio
    async def test_not_locked_with_fewer_than_5_failures(self, rate_limiter):
        """User with less than 5 failed attempts should not be locked."""
        for _ in range(4):
            await rate_limiter.record_attempt("testuser", success=False)
        result = await rate_limiter.is_locked("testuser")
        assert result is False

    @pytest.mark.asyncio
    async def test_locked_after_5_failures(self, rate_limiter):
        """User should be locked after exactly 5 failed attempts."""
        for _ in range(5):
            await rate_limiter.record_attempt("testuser", success=False)
        result = await rate_limiter.is_locked("testuser")
        assert result is True

    @pytest.mark.asyncio
    async def test_locked_after_more_than_5_failures(self, rate_limiter):
        """User should remain locked with more than 5 failures."""
        for _ in range(7):
            await rate_limiter.record_attempt("testuser", success=False)
        result = await rate_limiter.is_locked("testuser")
        assert result is True

    @pytest.mark.asyncio
    async def test_different_users_tracked_independently(self, rate_limiter):
        """Failures for one user shouldn't affect another."""
        for _ in range(5):
            await rate_limiter.record_attempt("user_a", success=False)
        result_a = await rate_limiter.is_locked("user_a")
        result_b = await rate_limiter.is_locked("user_b")
        assert result_a is True
        assert result_b is False

    @pytest.mark.asyncio
    async def test_successful_attempts_not_counted(self, rate_limiter):
        """Successful login attempts should not count toward the lockout."""
        for _ in range(5):
            await rate_limiter.record_attempt("testuser", success=True)
        result = await rate_limiter.is_locked("testuser")
        assert result is False


class TestRateLimiterRecordAttempt:
    @pytest.mark.asyncio
    async def test_records_failed_attempt(self, rate_limiter):
        """Should record a failed attempt in the database."""
        await rate_limiter.record_attempt("testuser", success=False)
        async with get_db() as db:
            cursor = await db.execute(
                "SELECT COUNT(*) FROM login_attempts WHERE username = ? AND success = 0",
                ("testuser",),
            )
            row = await cursor.fetchone()
            assert row[0] == 1

    @pytest.mark.asyncio
    async def test_records_successful_attempt(self, rate_limiter):
        """Should record a successful attempt in the database."""
        await rate_limiter.record_attempt("testuser", success=True)
        async with get_db() as db:
            cursor = await db.execute(
                "SELECT COUNT(*) FROM login_attempts WHERE username = ? AND success = 1",
                ("testuser",),
            )
            row = await cursor.fetchone()
            assert row[0] == 1


class TestRateLimiterReset:
    @pytest.mark.asyncio
    async def test_reset_clears_failed_attempts(self, rate_limiter):
        """Reset should clear all failed attempts for a user."""
        for _ in range(5):
            await rate_limiter.record_attempt("testuser", success=False)
        assert await rate_limiter.is_locked("testuser") is True

        await rate_limiter.reset("testuser")
        assert await rate_limiter.is_locked("testuser") is False

    @pytest.mark.asyncio
    async def test_reset_does_not_affect_other_users(self, rate_limiter):
        """Reset for one user should not affect other users."""
        for _ in range(5):
            await rate_limiter.record_attempt("user_a", success=False)
            await rate_limiter.record_attempt("user_b", success=False)

        await rate_limiter.reset("user_a")
        assert await rate_limiter.is_locked("user_a") is False
        assert await rate_limiter.is_locked("user_b") is True

    @pytest.mark.asyncio
    async def test_reset_preserves_successful_attempts(self, rate_limiter):
        """Reset should only clear failed attempts, not successful ones."""
        await rate_limiter.record_attempt("testuser", success=True)
        await rate_limiter.record_attempt("testuser", success=False)
        await rate_limiter.reset("testuser")

        async with get_db() as db:
            cursor = await db.execute(
                "SELECT COUNT(*) FROM login_attempts WHERE username = ? AND success = 1",
                ("testuser",),
            )
            row = await cursor.fetchone()
            assert row[0] == 1
