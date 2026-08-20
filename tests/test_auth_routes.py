"""Tests for the auth router (login and logout endpoints)."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
import asyncio

from httpx import AsyncClient, ASGITransport

from backend.database import get_db, init_db
from backend.security import hash_password, decode_access_token
from backend.api.main import app


@pytest.fixture(autouse=True)
def use_temp_db(tmp_path, monkeypatch):
    """Use a temporary database for each test."""
    test_db_path = str(tmp_path / "test_aiops.db")
    monkeypatch.setattr("backend.database.DATABASE_PATH", test_db_path)
    asyncio.get_event_loop().run_until_complete(init_db())
    yield test_db_path


@pytest.fixture
def seed_user():
    """Seed a test user into the database."""

    async def _seed(username="testuser", password="Test@1234", role="Admin", first_time_flag=False):
        hashed = hash_password(password)
        async with get_db() as db:
            await db.execute(
                "INSERT INTO users (username, password_hash, role, first_time_flag) VALUES (?, ?, ?, ?)",
                (username, hashed, role, 1 if first_time_flag else 0),
            )
            await db.commit()

    return _seed


@pytest.fixture
def client():
    """Create an async test client."""
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


class TestLoginEndpoint:
    @pytest.mark.asyncio
    async def test_login_success(self, client, seed_user):
        """Successful login returns access_token, role, and requires_password_change."""
        await seed_user()
        async with client as c:
            response = await c.post("/api/auth/login", json={
                "username": "testuser",
                "password": "Test@1234",
            })
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "success"
        data = body["data"]
        assert "access_token" in data
        assert data["role"] == "Admin"
        assert data["requires_password_change"] is False

    @pytest.mark.asyncio
    async def test_login_first_time_flag(self, client, seed_user):
        """First-time user login returns requires_password_change=True."""
        await seed_user(first_time_flag=True)
        async with client as c:
            response = await c.post("/api/auth/login", json={
                "username": "testuser",
                "password": "Test@1234",
            })
        assert response.status_code == 200
        body = response.json()
        assert body["data"]["requires_password_change"] is True

    @pytest.mark.asyncio
    async def test_login_invalid_password(self, client, seed_user):
        """Wrong password returns 401."""
        await seed_user()
        async with client as c:
            response = await c.post("/api/auth/login", json={
                "username": "testuser",
                "password": "WrongPassword!1",
            })
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_login_nonexistent_user(self, client):
        """Nonexistent user returns 401."""
        async with client as c:
            response = await c.post("/api/auth/login", json={
                "username": "ghost",
                "password": "SomePass@1",
            })
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_login_rate_limited(self, client, seed_user):
        """After 5 failed attempts, returns 429."""
        await seed_user()
        async with client as c:
            for _ in range(5):
                await c.post("/api/auth/login", json={
                    "username": "testuser",
                    "password": "Wrong@1234",
                })
            # 6th attempt should be rate limited
            response = await c.post("/api/auth/login", json={
                "username": "testuser",
                "password": "Test@1234",  # correct password still rejected
            })
        assert response.status_code == 429


class TestLogoutEndpoint:
    @pytest.mark.asyncio
    async def test_logout_success(self, client, seed_user):
        """Authenticated user can logout and token jti is blacklisted."""
        await seed_user()
        async with client as c:
            # Login first
            login_resp = await c.post("/api/auth/login", json={
                "username": "testuser",
                "password": "Test@1234",
            })
            token = login_resp.json()["data"]["access_token"]

            # Logout
            response = await c.post(
                "/api/auth/logout",
                headers={"Authorization": f"Bearer {token}"},
            )
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "success"
        assert body["data"]["message"] == "Logged out successfully"

        # Verify jti is in blacklist
        payload = decode_access_token(token)
        async with get_db() as db:
            cursor = await db.execute(
                "SELECT 1 FROM token_blacklist WHERE jti = ?", (payload["jti"],)
            )
            row = await cursor.fetchone()
            assert row is not None

    @pytest.mark.asyncio
    async def test_logout_without_token(self, client):
        """Logout without auth token returns 401/403."""
        async with client as c:
            response = await c.post("/api/auth/logout")
        assert response.status_code in (401, 403)


class TestResetRequestEndpoint:
    @pytest.mark.asyncio
    async def test_reset_request_existing_user(self, client, seed_user):
        """Reset request for existing user returns success with token."""
        await seed_user()
        async with client as c:
            response = await c.post("/api/auth/reset-request", json={
                "username": "testuser",
            })
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "success"
        assert "token" in body["data"]
        assert body["data"]["message"] == "If the account exists, a reset token has been generated."

    @pytest.mark.asyncio
    async def test_reset_request_nonexistent_user(self, client):
        """Reset request for nonexistent user returns generic success (no enumeration)."""
        async with client as c:
            response = await c.post("/api/auth/reset-request", json={
                "username": "nonexistent",
            })
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "success"
        # No token field for nonexistent user
        assert "token" not in body["data"]


class TestResetEndpoint:
    @pytest.mark.asyncio
    async def test_reset_success(self, client, seed_user):
        """Valid reset token allows password change."""
        await seed_user()
        async with client as c:
            # Request a token
            req_resp = await c.post("/api/auth/reset-request", json={"username": "testuser"})
            token = req_resp.json()["data"]["token"]

            # Reset password
            response = await c.post("/api/auth/reset", json={
                "token": token,
                "new_password": "NewPass@123",
            })
            assert response.status_code == 200
            body = response.json()
            assert body["status"] == "success"
            assert body["data"]["message"] == "Password has been reset successfully."

            # Verify can login with new password
            login_resp = await c.post("/api/auth/login", json={
                "username": "testuser",
                "password": "NewPass@123",
            })
            assert login_resp.status_code == 200

    @pytest.mark.asyncio
    async def test_reset_invalid_token(self, client):
        """Invalid token returns 400."""
        async with client as c:
            response = await c.post("/api/auth/reset", json={
                "token": "invalid-token-xyz",
                "new_password": "NewPass@123",
            })
        assert response.status_code == 400
        assert "invalid or expired" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_reset_used_token(self, client, seed_user):
        """Used token returns 400 on second use."""
        await seed_user()
        async with client as c:
            # Request and use a token
            req_resp = await c.post("/api/auth/reset-request", json={"username": "testuser"})
            token = req_resp.json()["data"]["token"]
            await c.post("/api/auth/reset", json={
                "token": token,
                "new_password": "NewPass@123",
            })

            # Try to use same token again
            response = await c.post("/api/auth/reset", json={
                "token": token,
                "new_password": "Another@123",
            })
        assert response.status_code == 400
        assert "invalid or expired" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_reset_weak_password(self, client, seed_user):
        """Weak password on reset returns 400."""
        await seed_user()
        async with client as c:
            req_resp = await c.post("/api/auth/reset-request", json={"username": "testuser"})
            token = req_resp.json()["data"]["token"]

            response = await c.post("/api/auth/reset", json={
                "token": token,
                "new_password": "alllowercase",
            })
        assert response.status_code == 400
        assert "policy" in response.json()["detail"].lower()


class TestChangePasswordEndpoint:
    @pytest.mark.asyncio
    async def test_change_password_success(self, client, seed_user):
        """Authenticated user can change password and gets new JWT."""
        await seed_user(first_time_flag=True)
        async with client as c:
            # Login first
            login_resp = await c.post("/api/auth/login", json={
                "username": "testuser",
                "password": "Test@1234",
            })
            token = login_resp.json()["data"]["access_token"]

            # Change password
            response = await c.post(
                "/api/auth/change-password",
                json={
                    "current_password": "Test@1234",
                    "new_password": "NewSecure@1",
                },
                headers={"Authorization": f"Bearer {token}"},
            )
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "success"
        assert "access_token" in body["data"]
        assert body["data"]["role"] == "Admin"
        assert body["data"]["message"] == "Password changed successfully."

    @pytest.mark.asyncio
    async def test_change_password_wrong_current(self, client, seed_user):
        """Wrong current password returns 401."""
        await seed_user()
        async with client as c:
            login_resp = await c.post("/api/auth/login", json={
                "username": "testuser",
                "password": "Test@1234",
            })
            token = login_resp.json()["data"]["access_token"]

            response = await c.post(
                "/api/auth/change-password",
                json={
                    "current_password": "Wrong@1234",
                    "new_password": "NewSecure@1",
                },
                headers={"Authorization": f"Bearer {token}"},
            )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_change_password_weak_new(self, client, seed_user):
        """Weak new password returns 400."""
        await seed_user()
        async with client as c:
            login_resp = await c.post("/api/auth/login", json={
                "username": "testuser",
                "password": "Test@1234",
            })
            token = login_resp.json()["data"]["access_token"]

            response = await c.post(
                "/api/auth/change-password",
                json={
                    "current_password": "Test@1234",
                    "new_password": "alllowercase",
                },
                headers={"Authorization": f"Bearer {token}"},
            )
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_change_password_unauthenticated(self, client):
        """Unauthenticated change-password returns 401."""
        async with client as c:
            response = await c.post(
                "/api/auth/change-password",
                json={
                    "current_password": "Test@1234",
                    "new_password": "NewSecure@1",
                },
            )
        assert response.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_change_password_clears_first_time_flag(self, client, seed_user):
        """After password change, first_time_flag is cleared in database."""
        await seed_user(first_time_flag=True)
        async with client as c:
            login_resp = await c.post("/api/auth/login", json={
                "username": "testuser",
                "password": "Test@1234",
            })
            token = login_resp.json()["data"]["access_token"]

            await c.post(
                "/api/auth/change-password",
                json={
                    "current_password": "Test@1234",
                    "new_password": "NewSecure@1",
                },
                headers={"Authorization": f"Bearer {token}"},
            )

        # Verify the first_time_flag is cleared in the DB
        async with get_db() as db:
            cursor = await db.execute(
                "SELECT first_time_flag FROM users WHERE username = ?", ("testuser",)
            )
            row = await cursor.fetchone()
            assert row["first_time_flag"] == 0
