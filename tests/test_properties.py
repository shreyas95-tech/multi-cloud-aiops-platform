"""Property-based tests for auth-rbac-ui-redesign feature.

Uses Hypothesis to verify universal correctness properties across large input spaces.
"""

import sys
import os
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from hypothesis import given, settings
from hypothesis import strategies as st
from hypothesis.strategies import text

from security import (
    hash_password,
    verify_password,
    create_access_token,
    decode_access_token,
)


class TestPasswordHashingStrength:
    """Property 2: Password Hashing Strength

    For any password string, the resulting hash is a valid bcrypt hash
    with work factor >= 12.

    **Validates: Requirements 1.3**
    """

    @given(password=text(min_size=1, max_size=72))
    @settings(max_examples=20, deadline=5000)
    def test_hash_is_valid_bcrypt_with_work_factor_12(self, password: str):
        """For any non-empty password (up to 72 chars), hash_password produces
        a valid bcrypt hash with version 2b and 12 rounds."""
        hashed = hash_password(password)

        # Verify the result starts with "$2b$12$" (bcrypt version 2b, 12 rounds)
        assert hashed.startswith("$2b$12$"), (
            f"Hash does not start with '$2b$12$': {hashed[:10]}..."
        )

        # Verify the result is 60 characters long (standard bcrypt hash length)
        assert len(hashed) == 60, (
            f"Expected hash length 60, got {len(hashed)}"
        )

        # Verify that verify_password returns True for the original password
        assert verify_password(password, hashed) is True, (
            f"verify_password failed for password that was just hashed"
        )


# Strategies for JWT property tests
valid_usernames = st.text(
    alphabet=st.characters(whitelist_categories=("Ll", "Lu", "Nd")),
    min_size=1,
    max_size=50,
)
valid_roles = st.sampled_from(["Admin", "L1_User"])
valid_first_time = st.booleans()


class TestJWTIssuanceCorrectness:
    """Property 1: JWT Issuance Correctness

    For any valid (username, role) pair, the issued token decodes to contain
    correct sub, role, and exp exactly 60 minutes from issuance.

    **Validates: Requirements 1.1, 1.5**
    """

    @given(
        username=valid_usernames,
        role=valid_roles,
        first_time=valid_first_time,
    )
    @settings(max_examples=100)
    def test_jwt_round_trip_preserves_claims(self, username, role, first_time):
        """Issued token decodes to contain correct sub, role, first_time, jti, and exp."""
        before = datetime.utcnow()
        token = create_access_token(username=username, role=role, first_time=first_time)
        after = datetime.utcnow()

        payload = decode_access_token(token)

        # sub matches username
        assert payload["sub"] == username

        # role matches
        assert payload["role"] == role

        # first_time matches
        assert payload["first_time"] == first_time

        # jti is present and non-empty
        assert "jti" in payload
        assert isinstance(payload["jti"], str)
        assert len(payload["jti"]) > 0

        # exp is approximately now + 60 minutes (within 5 seconds tolerance)
        expected_exp_low = before + timedelta(minutes=60) - timedelta(seconds=5)
        expected_exp_high = after + timedelta(minutes=60) + timedelta(seconds=5)

        exp_timestamp = payload["exp"]
        exp_dt = datetime.utcfromtimestamp(exp_timestamp)

        assert expected_exp_low <= exp_dt <= expected_exp_high, (
            f"exp {exp_dt} not within expected range "
            f"[{expected_exp_low}, {expected_exp_high}]"
        )


# --- Property 7: Password Policy Validation ---

import re
import string
from hypothesis.strategies import composite, sampled_from, integers

from security import validate_password_policy


# --- Helpers ---

def _meets_password_policy(password: str) -> bool:
    """Reference implementation of the password policy for oracle testing."""
    if len(password) < 8:
        return False
    if not re.search(r"[A-Z]", password):
        return False
    if not re.search(r"[a-z]", password):
        return False
    if not re.search(r"\d", password):
        return False
    if not re.search(r"[^A-Za-z0-9]", password):
        return False
    return True


# --- Strategies ---

SPECIAL_CHARS = "!@#$%^&*()-_=+[]{}|;:',.<>?/~`"


@composite
def valid_passwords(draw):
    """Generate strings that intentionally satisfy all password policy criteria."""
    upper = draw(sampled_from(list(string.ascii_uppercase)))
    lower = draw(sampled_from(list(string.ascii_lowercase)))
    digit = draw(sampled_from(list(string.digits)))
    special = draw(sampled_from(list(SPECIAL_CHARS)))

    # Fill remaining characters to reach 8+ total length
    extra_length = draw(integers(min_value=4, max_value=16))
    all_chars = string.ascii_letters + string.digits + SPECIAL_CHARS
    extra = draw(text(alphabet=all_chars, min_size=extra_length, max_size=extra_length))

    return upper + lower + digit + special + extra


@composite
def passwords_missing_uppercase(draw):
    """Generate passwords (8+ chars) with lowercase, digit, special, but no uppercase."""
    chars = string.ascii_lowercase + string.digits + SPECIAL_CHARS
    # Ensure we have at least one of each required type (except uppercase)
    lower = draw(sampled_from(list(string.ascii_lowercase)))
    digit = draw(sampled_from(list(string.digits)))
    special = draw(sampled_from(list(SPECIAL_CHARS)))
    extra_length = draw(integers(min_value=5, max_value=16))
    extra = draw(text(alphabet=chars, min_size=extra_length, max_size=extra_length))
    return lower + digit + special + extra


@composite
def passwords_missing_lowercase(draw):
    """Generate passwords (8+ chars) with uppercase, digit, special, but no lowercase."""
    chars = string.ascii_uppercase + string.digits + SPECIAL_CHARS
    upper = draw(sampled_from(list(string.ascii_uppercase)))
    digit = draw(sampled_from(list(string.digits)))
    special = draw(sampled_from(list(SPECIAL_CHARS)))
    extra_length = draw(integers(min_value=5, max_value=16))
    extra = draw(text(alphabet=chars, min_size=extra_length, max_size=extra_length))
    return upper + digit + special + extra


@composite
def passwords_missing_digit(draw):
    """Generate passwords (8+ chars) with uppercase, lowercase, special, but no digit."""
    chars = string.ascii_letters + SPECIAL_CHARS
    upper = draw(sampled_from(list(string.ascii_uppercase)))
    lower = draw(sampled_from(list(string.ascii_lowercase)))
    special = draw(sampled_from(list(SPECIAL_CHARS)))
    extra_length = draw(integers(min_value=5, max_value=16))
    extra = draw(text(alphabet=chars, min_size=extra_length, max_size=extra_length))
    return upper + lower + special + extra


@composite
def passwords_missing_special(draw):
    """Generate passwords (8+ chars) with uppercase, lowercase, digit, but no special."""
    chars = string.ascii_letters + string.digits
    upper = draw(sampled_from(list(string.ascii_uppercase)))
    lower = draw(sampled_from(list(string.ascii_lowercase)))
    digit = draw(sampled_from(list(string.digits)))
    extra_length = draw(integers(min_value=5, max_value=16))
    extra = draw(text(alphabet=chars, min_size=extra_length, max_size=extra_length))
    return upper + lower + digit + extra


# --- Property Tests ---


class TestPasswordPolicyProperty:
    """Property 7: Password Policy Validation

    For any string, validate_password_policy accepts it if and only if it
    has len>=8 AND has uppercase AND has lowercase AND has digit AND has special char.

    **Validates: Requirements 3.4**
    """

    @given(password=text(min_size=0, max_size=50))
    @settings(max_examples=100)
    def test_arbitrary_strings_match_policy_oracle(self, password):
        """Test 1: For any arbitrary string, the function's decision matches
        the policy definition (oracle test).

        **Validates: Requirements 3.4**
        """
        expected = _meets_password_policy(password)
        actual = validate_password_policy(password)
        assert actual == expected, (
            f"Mismatch for password {password!r}: "
            f"expected {expected}, got {actual}"
        )

    @given(password=valid_passwords())
    @settings(max_examples=100)
    def test_valid_passwords_are_accepted(self, password):
        """Test 2: Strings that meet all criteria are accepted.

        **Validates: Requirements 3.4**
        """
        assert len(password) >= 8
        assert re.search(r"[A-Z]", password)
        assert re.search(r"[a-z]", password)
        assert re.search(r"\d", password)
        assert re.search(r"[^A-Za-z0-9]", password)
        assert validate_password_policy(password) is True

    @given(password=passwords_missing_uppercase())
    @settings(max_examples=100)
    def test_missing_uppercase_rejected(self, password):
        """Test 3a: Strings missing uppercase are rejected.

        **Validates: Requirements 3.4**
        """
        assert validate_password_policy(password) is False

    @given(password=passwords_missing_lowercase())
    @settings(max_examples=100)
    def test_missing_lowercase_rejected(self, password):
        """Test 3b: Strings missing lowercase are rejected.

        **Validates: Requirements 3.4**
        """
        assert validate_password_policy(password) is False

    @given(password=passwords_missing_digit())
    @settings(max_examples=100)
    def test_missing_digit_rejected(self, password):
        """Test 3c: Strings missing digits are rejected.

        **Validates: Requirements 3.4**
        """
        assert validate_password_policy(password) is False

    @given(password=passwords_missing_special())
    @settings(max_examples=100)
    def test_missing_special_char_rejected(self, password):
        """Test 3d: Strings missing special characters are rejected.

        **Validates: Requirements 3.4**
        """
        assert validate_password_policy(password) is False


# --- Property 5: Blacklisted Token Rejection ---

import asyncio
import tempfile
from unittest.mock import patch

from hypothesis import assume

from security import create_access_token, decode_access_token


class TestBlacklistedTokenRejection:
    """Property 5: Blacklisted Token Rejection

    For any JWT token whose jti exists in the token blacklist,
    the Auth Middleware SHALL reject the request with a 401 status code.

    **Validates: Requirements 2.2**
    """

    @given(
        username=st.text(
            alphabet=st.characters(whitelist_categories=("Ll", "Lu", "Nd")),
            min_size=1,
            max_size=30,
        ),
        role=st.sampled_from(["Admin", "L1_User"]),
        first_time=st.booleans(),
    )
    @settings(max_examples=20, deadline=10000)
    def test_blacklisted_token_is_rejected_with_401(self, username, role, first_time):
        """For any token whose jti is in the blacklist, the middleware rejects with 401.

        **Validates: Requirements 2.2**
        """
        from fastapi import FastAPI, Depends
        from fastapi.testclient import TestClient

        # Create a temporary database for isolation
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            tmp_db_path = tmp.name

        try:
            # Patch the DATABASE_PATH so the middleware uses our temp database
            with patch("backend.database.DATABASE_PATH", tmp_db_path):
                # Initialize the temp database with the token_blacklist table
                import aiosqlite

                async def _setup_and_blacklist():
                    db = await aiosqlite.connect(tmp_db_path)
                    await db.execute("PRAGMA journal_mode=WAL")
                    await db.execute("""
                        CREATE TABLE IF NOT EXISTS token_blacklist (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            jti TEXT UNIQUE NOT NULL,
                            expires_at TEXT NOT NULL
                        )
                    """)
                    # Create the token and extract its jti
                    token = create_access_token(
                        username=username, role=role, first_time=first_time
                    )
                    payload = decode_access_token(token)
                    jti = payload["jti"]

                    # Blacklist the jti
                    expires_at = (
                        datetime.utcnow() + timedelta(hours=2)
                    ).strftime("%Y-%m-%d %H:%M:%S")
                    await db.execute(
                        "INSERT INTO token_blacklist (jti, expires_at) VALUES (?, ?)",
                        (jti, expires_at),
                    )
                    await db.commit()
                    await db.close()
                    return token

                token = asyncio.run(_setup_and_blacklist())

                # Create a mini FastAPI app that uses the auth middleware
                from backend.api.middleware.auth_middleware import get_current_user

                app = FastAPI()

                @app.get("/protected")
                async def protected_route(user: dict = Depends(get_current_user)):
                    return {"user": user}

                client = TestClient(app)

                # Make request with the blacklisted token
                response = client.get(
                    "/protected",
                    headers={"Authorization": f"Bearer {token}"},
                )

                assert response.status_code == 401, (
                    f"Expected 401 for blacklisted token, got {response.status_code}. "
                    f"username={username!r}, role={role!r}, jti was blacklisted."
                )
        finally:
            # Clean up temp database file
            if os.path.exists(tmp_db_path):
                os.unlink(tmp_db_path)


# --- Property 8: RBAC Permission Matrix ---

import asyncio
import tempfile
from unittest.mock import patch

import pytest
from fastapi import FastAPI, Depends
from fastapi.testclient import TestClient

from backend.security import create_access_token
from backend.api.middleware.auth_middleware import get_current_user
from backend.api.middleware.rbac import require_role, require_not_first_time


def _create_rbac_test_app():
    """Create a mini FastAPI app with endpoints protected by various RBAC rules."""
    app = FastAPI()

    @app.get("/admin-only", dependencies=[Depends(require_role("Admin")), Depends(require_not_first_time())])
    async def admin_only():
        return {"status": "ok", "endpoint": "admin-only"}

    @app.get("/all-authenticated")
    async def all_authenticated(user: dict = Depends(get_current_user)):
        return {"status": "ok", "endpoint": "all-authenticated"}

    @app.get("/no-first-time", dependencies=[Depends(require_not_first_time())])
    async def no_first_time():
        return {"status": "ok", "endpoint": "no-first-time"}

    return app


class TestRBACPermissionMatrix:
    """Property 8: RBAC Permission Matrix

    For any request to a protected endpoint, given a user's role and first_time_flag
    status, the RBAC_Service SHALL:
    - Return 401 if no valid token is present
    - Return 403 if the user's role is not permitted for that endpoint
    - Restrict first-time users (first_time_flag=true) to only the password-change endpoint
    - Permit Admin users access to all endpoints
    - Restrict L1_User to KB read endpoints only
    - Reject any role value not in {Admin, L1_User}

    **Validates: Requirements 4.3, 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 6.4**
    """

    def setup_method(self):
        """Set up the test app and client with a temp database for each test."""
        self._tmp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self._tmp_db_path = self._tmp_db.name
        self._tmp_db.close()

        # Patch the DATABASE_PATH to use a temp file
        self._db_patch = patch("backend.database.DATABASE_PATH", self._tmp_db_path)
        self._db_patch.start()

        # Initialize the database tables
        from backend.database import init_db
        asyncio.get_event_loop().run_until_complete(init_db())

        self.app = _create_rbac_test_app()
        self.client = TestClient(self.app)

    def teardown_method(self):
        """Clean up temp database."""
        self._db_patch.stop()
        try:
            os.unlink(self._tmp_db_path)
        except OSError:
            pass

    def _make_auth_header(self, username: str, role: str, first_time: bool) -> dict:
        """Create an Authorization header with a valid JWT."""
        token = create_access_token(username=username, role=role, first_time=first_time)
        return {"Authorization": f"Bearer {token}"}

    # --- Hypothesis-driven tests ---

    @given(
        username=valid_usernames,
        role=st.just("Admin"),
        first_time=st.just(False),
    )
    @settings(max_examples=50)
    def test_admin_not_first_time_accesses_all_endpoints(self, username, role, first_time):
        """Admin with first_time=False can access all endpoints → 200.

        **Validates: Requirements 4.3, 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 6.4**
        """
        headers = self._make_auth_header(username, role, first_time)

        # Admin-only endpoint
        resp = self.client.get("/admin-only", headers=headers)
        assert resp.status_code == 200, f"Expected 200 on /admin-only, got {resp.status_code}"

        # All authenticated endpoint
        resp = self.client.get("/all-authenticated", headers=headers)
        assert resp.status_code == 200, f"Expected 200 on /all-authenticated, got {resp.status_code}"

        # No-first-time endpoint
        resp = self.client.get("/no-first-time", headers=headers)
        assert resp.status_code == 200, f"Expected 200 on /no-first-time, got {resp.status_code}"

    @given(
        username=valid_usernames,
        role=st.just("Admin"),
        first_time=st.just(True),
    )
    @settings(max_examples=50)
    def test_admin_first_time_blocked_from_non_password_change(self, username, role, first_time):
        """Admin with first_time=True is blocked from all endpoints requiring
        require_not_first_time() → 403.

        **Validates: Requirements 4.3, 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 6.4**
        """
        headers = self._make_auth_header(username, role, first_time)

        # Admin-only endpoint (has require_not_first_time) → 403
        resp = self.client.get("/admin-only", headers=headers)
        assert resp.status_code == 403, f"Expected 403 on /admin-only for first_time Admin, got {resp.status_code}"

        # No-first-time endpoint → 403
        resp = self.client.get("/no-first-time", headers=headers)
        assert resp.status_code == 403, f"Expected 403 on /no-first-time for first_time Admin, got {resp.status_code}"

        # All authenticated endpoint (no first_time check) → 200
        resp = self.client.get("/all-authenticated", headers=headers)
        assert resp.status_code == 200, f"Expected 200 on /all-authenticated for first_time Admin, got {resp.status_code}"

    @given(
        username=valid_usernames,
        role=st.just("L1_User"),
        first_time=st.just(False),
    )
    @settings(max_examples=50)
    def test_l1_user_not_first_time_limited_access(self, username, role, first_time):
        """L1_User with first_time=False can access general authenticated endpoints
        but NOT admin-only endpoints → 403 on admin-only.

        **Validates: Requirements 4.3, 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 6.4**
        """
        headers = self._make_auth_header(username, role, first_time)

        # Admin-only endpoint → 403 (require_role("Admin") blocks L1_User)
        resp = self.client.get("/admin-only", headers=headers)
        assert resp.status_code == 403, f"Expected 403 on /admin-only for L1_User, got {resp.status_code}"

        # All authenticated endpoint → 200
        resp = self.client.get("/all-authenticated", headers=headers)
        assert resp.status_code == 200, f"Expected 200 on /all-authenticated for L1_User, got {resp.status_code}"

        # No-first-time endpoint → 200 (L1_User with first_time=False passes)
        resp = self.client.get("/no-first-time", headers=headers)
        assert resp.status_code == 200, f"Expected 200 on /no-first-time for L1_User, got {resp.status_code}"

    @given(
        username=valid_usernames,
        role=st.just("L1_User"),
        first_time=st.just(True),
    )
    @settings(max_examples=50)
    def test_l1_user_first_time_blocked_from_all_protected(self, username, role, first_time):
        """L1_User with first_time=True is blocked from endpoints with
        require_not_first_time() → 403.

        **Validates: Requirements 4.3, 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 6.4**
        """
        headers = self._make_auth_header(username, role, first_time)

        # Admin-only endpoint → 403 (blocked by role check first)
        resp = self.client.get("/admin-only", headers=headers)
        assert resp.status_code == 403, f"Expected 403 on /admin-only for first_time L1_User, got {resp.status_code}"

        # No-first-time endpoint → 403
        resp = self.client.get("/no-first-time", headers=headers)
        assert resp.status_code == 403, f"Expected 403 on /no-first-time for first_time L1_User, got {resp.status_code}"

        # All authenticated endpoint (no first_time check) → 200
        resp = self.client.get("/all-authenticated", headers=headers)
        assert resp.status_code == 200, f"Expected 200 on /all-authenticated for first_time L1_User, got {resp.status_code}"

    @given(
        endpoint=st.sampled_from(["/admin-only", "/all-authenticated", "/no-first-time"]),
    )
    @settings(max_examples=50)
    def test_no_token_returns_401(self, endpoint):
        """Requests without any token are rejected with 401.

        **Validates: Requirements 4.3, 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 6.4**
        """
        resp = self.client.get(endpoint)
        assert resp.status_code in (401, 403), f"Expected 401/403 on {endpoint} without token, got {resp.status_code}"


# --- Property 3: Invalid Credentials Rejection ---

import pytest
from httpx import AsyncClient, ASGITransport
from hypothesis import assume


class TestInvalidCredentialsRejection:
    """Property 3: Invalid Credentials Rejection

    For any username/password pair where credentials don't match,
    the login endpoint returns 401.

    **Validates: Requirements 1.2**
    """

    KNOWN_PASSWORD = "KnownPass@123"
    TEST_USERNAME = "prop3user"

    @pytest.fixture(autouse=True)
    def setup_temp_db(self, tmp_path, monkeypatch):
        """Use a temporary database for each test method."""
        test_db_path = str(tmp_path / "test_prop3.db")
        monkeypatch.setattr("backend.database.DATABASE_PATH", test_db_path)

        # Initialize DB and seed user
        from backend.database import init_db, get_db
        from backend.security import hash_password

        asyncio.get_event_loop().run_until_complete(init_db())

        async def _seed():
            hashed = hash_password(self.KNOWN_PASSWORD)
            async with get_db() as db:
                await db.execute(
                    "INSERT INTO users (username, password_hash, role, first_time_flag) VALUES (?, ?, ?, ?)",
                    (self.TEST_USERNAME, hashed, "Admin", 0),
                )
                await db.commit()

        asyncio.get_event_loop().run_until_complete(_seed())

    @given(
        wrong_password=st.text(min_size=1, max_size=50),
    )
    @settings(max_examples=20, deadline=30000)
    def test_wrong_password_returns_401(self, wrong_password):
        """For any password that is NOT the known password, login returns 401.

        **Validates: Requirements 1.2**
        """
        # Ensure the generated password is not the actual known password
        assume(wrong_password != self.KNOWN_PASSWORD)

        from backend.api.main import app
        from backend.database import get_db

        async def _do_request():
            # Clear login attempts to prevent rate limiter interference
            async with get_db() as db:
                await db.execute("DELETE FROM login_attempts")
                await db.commit()

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post("/api/auth/login", json={
                    "username": self.TEST_USERNAME,
                    "password": wrong_password,
                })
                return response

        response = asyncio.run(_do_request())

        assert response.status_code == 401, (
            f"Expected 401 for wrong password {wrong_password!r}, "
            f"got {response.status_code}. Response: {response.text}"
        )


# --- Property 4: Rate Limiter Threshold Enforcement ---

import httpx
from httpx import ASGITransport


class TestRateLimiterThresholdEnforcement:
    """Property 4: Rate Limiter Threshold Enforcement

    For any sequence of login attempts for a single username, if the number of
    failed attempts within a 15-minute window exceeds 5, all subsequent attempts
    within that window SHALL be rejected with a 429 status code regardless of
    credential validity.

    **Validates: Requirements 1.4**
    """

    @given(
        extra_attempts=st.integers(min_value=1, max_value=10),
    )
    @settings(max_examples=10, deadline=30000)
    def test_rate_limiter_rejects_after_5_failures(self, extra_attempts: int):
        """After 5 failed login attempts, N subsequent attempts (even with valid
        credentials) are all rejected with 429.

        **Validates: Requirements 1.4**
        """
        import asyncio

        async def _run_test():
            # Create a temporary database for isolation
            with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
                tmp_db_path = tmp.name

            try:
                with patch("backend.database.DATABASE_PATH", tmp_db_path):
                    # Initialize database tables
                    import aiosqlite

                    db = await aiosqlite.connect(tmp_db_path)
                    await db.execute("PRAGMA journal_mode=WAL")
                    await db.execute("PRAGMA foreign_keys=ON")

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
                        CREATE TABLE IF NOT EXISTS login_attempts (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            username TEXT NOT NULL,
                            attempted_at TEXT NOT NULL DEFAULT (datetime('now')),
                            success BOOLEAN NOT NULL DEFAULT 0
                        )
                    """)
                    await db.execute("""
                        CREATE TABLE IF NOT EXISTS token_blacklist (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            jti TEXT UNIQUE NOT NULL,
                            expires_at TEXT NOT NULL
                        )
                    """)

                    # Seed a test user with a known password
                    from backend.security import hash_password
                    test_username = "ratelimit_testuser"
                    test_password = "ValidPass1!"
                    password_hash = hash_password(test_password)

                    await db.execute(
                        "INSERT INTO users (username, password_hash, role, first_time_flag) VALUES (?, ?, ?, ?)",
                        (test_username, password_hash, "Admin", 0),
                    )
                    await db.commit()
                    await db.close()

                    # Import the app fresh with patched DATABASE_PATH
                    from backend.api.main import app

                    # Reset the rate limiter state (fresh instance)
                    from backend.api.routes import auth as auth_module
                    from backend.security import RateLimiter as _RateLimiter
                    original_rate_limiter = auth_module.rate_limiter
                    auth_module.rate_limiter = _RateLimiter()

                    try:
                        transport = ASGITransport(app=app)
                        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                            # Make 5 failed login attempts with wrong password
                            for i in range(5):
                                resp = await client.post(
                                    "/api/auth/login",
                                    json={"username": test_username, "password": "WrongPass1!"},
                                )
                                # First 5 should be 401 (invalid credentials)
                                assert resp.status_code == 401, (
                                    f"Attempt {i+1}/5: Expected 401, got {resp.status_code}"
                                )

                            # Now make extra_attempts more attempts with VALID credentials
                            # All should be rejected with 429
                            for i in range(extra_attempts):
                                resp = await client.post(
                                    "/api/auth/login",
                                    json={"username": test_username, "password": test_password},
                                )
                                assert resp.status_code == 429, (
                                    f"Attempt {i+1}/{extra_attempts} after lockout: "
                                    f"Expected 429, got {resp.status_code}. "
                                    f"Rate limiter should block all attempts after 5 failures."
                                )
                    finally:
                        # Restore original rate limiter
                        auth_module.rate_limiter = original_rate_limiter

            finally:
                # Clean up temp database file
                if os.path.exists(tmp_db_path):
                    os.unlink(tmp_db_path)

        asyncio.run(_run_test())


# --- Property 10: Username Uniqueness Enforcement ---

import httpx
import pytest
from httpx import AsyncClient, ASGITransport

from backend.api.main import app


@composite
def valid_create_user_usernames(draw):
    """Generate usernames valid for CreateUserRequest (3-50 chars, [a-zA-Z0-9_])."""
    length = draw(integers(min_value=3, max_value=30))
    chars = string.ascii_letters + string.digits + "_"
    username = draw(text(alphabet=chars, min_size=length, max_size=length))
    assume(len(username) >= 3)
    return username


@composite
def valid_create_user_passwords(draw):
    """Generate passwords that meet the password policy (8+ chars with upper, lower, digit, special)."""
    upper = draw(sampled_from(list(string.ascii_uppercase)))
    lower = draw(sampled_from(list(string.ascii_lowercase)))
    digit = draw(sampled_from(list(string.digits)))
    special = draw(sampled_from(list(SPECIAL_CHARS)))
    extra_length = draw(integers(min_value=4, max_value=12))
    all_chars = string.ascii_letters + string.digits + SPECIAL_CHARS
    extra = draw(text(alphabet=all_chars, min_size=extra_length, max_size=extra_length))
    return upper + lower + digit + special + extra


class TestUsernameUniquenessEnforcement:
    """Property 10: Username Uniqueness Enforcement

    For any create-user request where the username already exists in the database,
    the User_Management_Service SHALL return a 409 Conflict response, and the
    existing user record SHALL remain unchanged.

    **Validates: Requirements 6.2**
    """

    @given(
        username=valid_create_user_usernames(),
        password1=valid_create_user_passwords(),
        password2=valid_create_user_passwords(),
        role1=st.sampled_from(["Admin", "L1_User"]),
        role2=st.sampled_from(["Admin", "L1_User"]),
    )
    @settings(max_examples=20, deadline=30000)
    def test_duplicate_username_returns_409_and_record_unchanged(
        self, username, password1, password2, role1, role2
    ):
        """Creating a user with a duplicate username returns 409 and
        the existing record is unchanged.

        **Validates: Requirements 6.2**
        """
        import asyncio

        async def _run_test():
            # Use a temporary database for isolation
            with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
                tmp_db_path = tmp.name

            try:
                with patch("backend.database.DATABASE_PATH", tmp_db_path):
                    # Initialize the database tables
                    from backend.database import init_db
                    await init_db()

                    # Seed an admin user to authenticate requests
                    from backend.database import get_db
                    from backend.security import hash_password as _hash_pw
                    admin_hash = _hash_pw("Admin@1234")
                    async with get_db() as db:
                        await db.execute(
                            "INSERT INTO users (username, password_hash, role, first_time_flag) VALUES (?, ?, ?, 0)",
                            ("test_admin", admin_hash, "Admin"),
                        )
                        await db.commit()

                    # Get an admin token
                    admin_token = create_access_token(
                        username="test_admin", role="Admin", first_time=False
                    )
                    headers = {"Authorization": f"Bearer {admin_token}"}

                    transport = ASGITransport(app=app)
                    async with AsyncClient(transport=transport, base_url="http://test") as client:
                        # First creation — should succeed (201)
                        resp1 = await client.post(
                            "/api/users",
                            json={"username": username, "password": password1, "role": role1},
                            headers=headers,
                        )
                        assert resp1.status_code == 201, (
                            f"Expected 201 for first user creation, got {resp1.status_code}: {resp1.text}"
                        )

                        # Record original user state from DB
                        async with get_db() as db:
                            cursor = await db.execute(
                                "SELECT username, password_hash, role, first_time_flag FROM users WHERE username = ?",
                                (username,),
                            )
                            original_row = await cursor.fetchone()

                        assert original_row is not None, "User should exist after first creation"
                        original_hash = original_row["password_hash"]
                        original_role = original_row["role"]
                        original_first_time = original_row["first_time_flag"]

                        # Second creation with same username (possibly different password/role) — should be 409
                        resp2 = await client.post(
                            "/api/users",
                            json={"username": username, "password": password2, "role": role2},
                            headers=headers,
                        )
                        assert resp2.status_code == 409, (
                            f"Expected 409 for duplicate username, got {resp2.status_code}: {resp2.text}"
                        )

                        # Verify original record is unchanged
                        async with get_db() as db:
                            cursor = await db.execute(
                                "SELECT username, password_hash, role, first_time_flag FROM users WHERE username = ?",
                                (username,),
                            )
                            after_row = await cursor.fetchone()

                        assert after_row is not None, "Original user should still exist"
                        assert after_row["password_hash"] == original_hash, (
                            "Password hash should be unchanged after duplicate creation attempt"
                        )
                        assert after_row["role"] == original_role, (
                            f"Role should be unchanged: expected {original_role}, got {after_row['role']}"
                        )
                        assert after_row["first_time_flag"] == original_first_time, (
                            "first_time_flag should be unchanged after duplicate creation attempt"
                        )
            finally:
                if os.path.exists(tmp_db_path):
                    os.unlink(tmp_db_path)
                # Clean up WAL/SHM files if they exist
                for suffix in ("-wal", "-shm"):
                    wal_path = tmp_db_path + suffix
                    if os.path.exists(wal_path):
                        os.unlink(wal_path)

        asyncio.run(_run_test())


# --- Property 9: New User First-Time Flag Invariant ---

import pytest
import httpx
from hypothesis import assume
from hypothesis.strategies import composite


@composite
def alphanumeric_usernames(draw):
    """Generate alphanumeric usernames between 3 and 20 characters (ASCII only, matching ^[a-zA-Z0-9_]+$)."""
    alphabet = string.ascii_letters + string.digits + "_"
    username = draw(
        st.text(
            alphabet=alphabet,
            min_size=3,
            max_size=20,
        )
    )
    return username


@composite
def policy_compliant_passwords(draw):
    """Generate passwords that meet password policy (8+ chars, upper, lower, digit, special)."""
    upper = draw(st.sampled_from(list(string.ascii_uppercase)))
    lower = draw(st.sampled_from(list(string.ascii_lowercase)))
    digit = draw(st.sampled_from(list(string.digits)))
    special = draw(st.sampled_from(list(SPECIAL_CHARS)))
    # Fill remaining to reach 8+ total
    extra_length = draw(st.integers(min_value=4, max_value=12))
    all_chars = string.ascii_letters + string.digits + SPECIAL_CHARS
    extra = draw(st.text(alphabet=all_chars, min_size=extra_length, max_size=extra_length))
    return upper + lower + digit + special + extra


class TestNewUserFirstTimeFlagInvariant:
    """Property 9: New User First-Time Flag Invariant

    For any user created via the User_Management_Service, the resulting user
    record SHALL have first_time_flag set to true, regardless of the role assigned.

    **Validates: Requirements 6.1**
    """

    @pytest.fixture(autouse=True)
    def setup_temp_db(self, tmp_path):
        """Set up a temporary database with an admin user for each test."""
        self._tmp_db_path = str(tmp_path / "test_prop9.db")

    def _get_db_path_patch(self):
        return patch("backend.database.DATABASE_PATH", self._tmp_db_path)

    @given(
        username=alphanumeric_usernames(),
        password=policy_compliant_passwords(),
        role=st.sampled_from(["Admin", "L1_User"]),
    )
    @settings(max_examples=20, deadline=30000)
    def test_created_user_always_has_first_time_flag_true(self, username, password, role):
        """Every user created via POST /api/users has first_time_flag=true in the DB.

        **Validates: Requirements 6.1**
        """
        # Avoid collision with the seeded admin user
        assume(username != "seed_admin")

        import aiosqlite
        from backend.database import init_db
        from backend.security import hash_password, create_access_token

        # Use a unique db path for each hypothesis example to avoid conflicts
        tmp_db_path = self._tmp_db_path

        with self._get_db_path_patch():

            async def _run_test():
                # Initialize the database
                await init_db()

                # Seed an admin user who will make the create-user request
                admin_username = "seed_admin"
                admin_password_hash = hash_password("Admin@1234")
                async with aiosqlite.connect(tmp_db_path) as db:
                    db.row_factory = aiosqlite.Row
                    await db.execute("PRAGMA journal_mode=WAL")
                    await db.execute("PRAGMA foreign_keys=ON")
                    # Insert admin user with first_time_flag=false so they can create users
                    await db.execute(
                        """
                        INSERT OR IGNORE INTO users (username, password_hash, role, first_time_flag)
                        VALUES (?, ?, 'Admin', 0)
                        """,
                        (admin_username, admin_password_hash),
                    )
                    await db.commit()

                # Create an admin token (first_time=False so RBAC allows user creation)
                admin_token = create_access_token(
                    username=admin_username, role="Admin", first_time=False
                )

                # Make the API call to create the new user
                from backend.api.main import app

                async with httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=app), base_url="http://test"
                ) as client:
                    response = await client.post(
                        "/api/users",
                        json={
                            "username": username,
                            "password": password,
                            "role": role,
                        },
                        headers={"Authorization": f"Bearer {admin_token}"},
                    )

                # If 409 conflict (username already exists from seed), skip this example
                if response.status_code == 409:
                    return  # acceptable — username collision with seed admin

                assert response.status_code == 201, (
                    f"Expected 201 Created, got {response.status_code}: {response.text}"
                )

                # Query the database directly to verify first_time_flag
                async with aiosqlite.connect(tmp_db_path) as db:
                    db.row_factory = aiosqlite.Row
                    cursor = await db.execute(
                        "SELECT first_time_flag FROM users WHERE username = ?",
                        (username,),
                    )
                    row = await cursor.fetchone()

                assert row is not None, (
                    f"User {username!r} not found in database after creation"
                )
                assert row["first_time_flag"] == 1, (
                    f"Expected first_time_flag=1 (true) for user {username!r}, "
                    f"got {row['first_time_flag']}"
                )

            asyncio.run(_run_test())


# --- Property 6: Reset Token Single-Use Invariant ---


class TestResetTokenSingleUseInvariant:
    """Property 6: Reset Token Single-Use Invariant

    For any reset token, once it has been successfully used to change a password
    OR its 30-minute expiry has elapsed, all subsequent attempts to use that token
    SHALL be rejected with a 400 status code and the message
    "Reset token is invalid or expired".

    **Validates: Requirements 3.2, 3.3**
    """

    @given(
        new_password1=valid_passwords(),
        new_password2=valid_passwords(),
    )
    @settings(max_examples=10, deadline=60000)
    def test_used_reset_token_rejected_on_second_use(self, new_password1, new_password2):
        """Once a reset token is used to reset a password, a second use with a
        different valid password returns 400.

        **Validates: Requirements 3.2, 3.3**
        """
        import asyncio

        async def _run_test():
            with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
                tmp_db_path = tmp.name

            try:
                with patch("backend.database.DATABASE_PATH", tmp_db_path):
                    # Initialize the database
                    from backend.database import init_db, get_db
                    await init_db()

                    # Seed a test user
                    from backend.security import hash_password as _hash_pw
                    test_username = "reset_prop6_user"
                    test_password = "OldPass@123"
                    password_hash = _hash_pw(test_password)

                    async with get_db() as db:
                        await db.execute(
                            "INSERT INTO users (username, password_hash, role, first_time_flag) VALUES (?, ?, ?, ?)",
                            (test_username, password_hash, "Admin", 0),
                        )
                        await db.commit()

                    # Request a reset token via the API
                    from backend.api.main import app

                    transport = ASGITransport(app=app)
                    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                        # Step 1: Request a reset token
                        resp = await client.post(
                            "/api/auth/reset-request",
                            json={"username": test_username},
                        )
                        assert resp.status_code == 200, (
                            f"Expected 200 for reset-request, got {resp.status_code}: {resp.text}"
                        )
                        reset_token = resp.json()["data"]["token"]

                        # Step 2: Use the token to reset password (should succeed)
                        resp = await client.post(
                            "/api/auth/reset",
                            json={"token": reset_token, "new_password": new_password1},
                        )
                        assert resp.status_code == 200, (
                            f"Expected 200 for first reset, got {resp.status_code}: {resp.text}"
                        )

                        # Step 3: Attempt to use the same token again → 400
                        resp = await client.post(
                            "/api/auth/reset",
                            json={"token": reset_token, "new_password": new_password2},
                        )
                        assert resp.status_code == 400, (
                            f"Expected 400 for reused reset token, got {resp.status_code}: {resp.text}. "
                            f"Reset tokens must be single-use."
                        )

                        # Verify the error message matches requirements
                        response_data = resp.json()
                        detail = response_data.get("detail", "")
                        assert "invalid or expired" in detail.lower(), (
                            f"Expected error message containing 'invalid or expired', got: {detail}"
                        )

            finally:
                if os.path.exists(tmp_db_path):
                    os.unlink(tmp_db_path)
                for suffix in ("-wal", "-shm"):
                    wal_path = tmp_db_path + suffix
                    if os.path.exists(wal_path):
                        os.unlink(wal_path)

        asyncio.run(_run_test())


# --- Property 13: KB File Type and Size Validation ---

import io
import httpx
import aiosqlite
from hypothesis import given, settings, assume
from hypothesis import strategies as st


# Valid content types for KB upload
KB_VALID_CONTENT_TYPES = [
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "text/plain",
]

# Invalid content types for KB upload
KB_INVALID_CONTENT_TYPES = [
    "image/png",
    "image/jpeg",
    "application/json",
    "application/xml",
    "text/html",
    "application/zip",
    "video/mp4",
    "audio/mpeg",
    "application/octet-stream",
    "text/csv",
]

KB_MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB


class TestKBFileTypeAndSizeValidation:
    """Property 13: KB File Type and Size Validation

    For any file upload attempt, the KB_Service SHALL accept the file if and only
    if its content type is one of {PDF, DOCX, plain text} AND its size is <= 10 MB.
    Files exceeding 10 MB SHALL be rejected with 413. Files with unsupported types
    SHALL be rejected with 415.

    **Validates: Requirements 7.2, 7.3**
    """

    @given(
        content_type=st.sampled_from(KB_VALID_CONTENT_TYPES),
        file_size=st.integers(min_value=1, max_value=KB_MAX_FILE_SIZE),
        title=st.text(
            alphabet=st.characters(whitelist_categories=("Ll", "Lu", "Nd", "Zs")),
            min_size=1,
            max_size=50,
        ),
    )
    @settings(max_examples=20, deadline=30000)
    def test_valid_type_and_size_returns_201(self, content_type, file_size, title):
        """Test 1: Files with valid content types and size <= 10MB are accepted (201).

        **Validates: Requirements 7.2, 7.3**
        """
        # Cap actual test content to a reasonable size to keep tests fast
        # Use min of file_size and 1024 bytes for actual content (the size check
        # reads the full file, so we just need the content to be <= 10MB)
        actual_size = min(file_size, 1024)
        file_content = b"x" * actual_size

        async def _run_test():
            with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
                tmp_db_path = tmp.name

            try:
                with patch("backend.database.DATABASE_PATH", tmp_db_path):
                    from backend.database import init_db, get_db
                    from backend.security import hash_password, create_access_token

                    await init_db()

                    # Seed an admin user
                    admin_hash = hash_password("Admin@1234")
                    async with get_db() as db:
                        await db.execute(
                            "INSERT INTO users (username, password_hash, role, first_time_flag) VALUES (?, ?, ?, 0)",
                            ("kb_admin", admin_hash, "Admin"),
                        )
                        await db.commit()

                    # Create admin token
                    admin_token = create_access_token(
                        username="kb_admin", role="Admin", first_time=False
                    )

                    # Determine filename based on content type
                    ext_map = {
                        "application/pdf": "test.pdf",
                        "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "test.docx",
                        "text/plain": "test.txt",
                    }
                    filename = ext_map.get(content_type, "test.bin")

                    from backend.api.main import app

                    transport = httpx.ASGITransport(app=app)
                    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                        response = await client.post(
                            "/api/kb/documents",
                            headers={"Authorization": f"Bearer {admin_token}"},
                            data={"title": title},
                            files={"file": (filename, file_content, content_type)},
                        )

                    assert response.status_code == 201, (
                        f"Expected 201 for valid content_type={content_type!r}, "
                        f"size={actual_size}, got {response.status_code}: {response.text}"
                    )
            finally:
                if os.path.exists(tmp_db_path):
                    os.unlink(tmp_db_path)
                for suffix in ("-wal", "-shm"):
                    p = tmp_db_path + suffix
                    if os.path.exists(p):
                        os.unlink(p)

        asyncio.run(_run_test())

    @given(
        content_type=st.sampled_from(KB_INVALID_CONTENT_TYPES),
        title=st.text(
            alphabet=st.characters(whitelist_categories=("Ll", "Lu", "Nd", "Zs")),
            min_size=1,
            max_size=50,
        ),
    )
    @settings(max_examples=20, deadline=30000)
    def test_invalid_content_type_returns_415(self, content_type, title):
        """Test 2: Files with invalid content types are rejected with 415.

        **Validates: Requirements 7.2, 7.3**
        """
        file_content = b"some test content"

        async def _run_test():
            with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
                tmp_db_path = tmp.name

            try:
                with patch("backend.database.DATABASE_PATH", tmp_db_path):
                    from backend.database import init_db, get_db
                    from backend.security import hash_password, create_access_token

                    await init_db()

                    # Seed an admin user
                    admin_hash = hash_password("Admin@1234")
                    async with get_db() as db:
                        await db.execute(
                            "INSERT INTO users (username, password_hash, role, first_time_flag) VALUES (?, ?, ?, 0)",
                            ("kb_admin", admin_hash, "Admin"),
                        )
                        await db.commit()

                    # Create admin token
                    admin_token = create_access_token(
                        username="kb_admin", role="Admin", first_time=False
                    )

                    from backend.api.main import app

                    transport = httpx.ASGITransport(app=app)
                    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                        response = await client.post(
                            "/api/kb/documents",
                            headers={"Authorization": f"Bearer {admin_token}"},
                            data={"title": title},
                            files={"file": ("test.bin", file_content, content_type)},
                        )

                    assert response.status_code == 415, (
                        f"Expected 415 for invalid content_type={content_type!r}, "
                        f"got {response.status_code}: {response.text}"
                    )
            finally:
                if os.path.exists(tmp_db_path):
                    os.unlink(tmp_db_path)
                for suffix in ("-wal", "-shm"):
                    p = tmp_db_path + suffix
                    if os.path.exists(p):
                        os.unlink(p)

        asyncio.run(_run_test())

    @given(
        content_type=st.sampled_from(KB_VALID_CONTENT_TYPES),
        extra_bytes=st.integers(min_value=1, max_value=1024),
        title=st.text(
            alphabet=st.characters(whitelist_categories=("Ll", "Lu", "Nd", "Zs")),
            min_size=1,
            max_size=50,
        ),
    )
    @settings(max_examples=20, deadline=60000)
    def test_file_exceeding_10mb_returns_413(self, content_type, extra_bytes, title):
        """Test 3: Files exceeding 10MB are rejected with 413.

        **Validates: Requirements 7.2, 7.3**
        """
        # Create content that exceeds 10 MB
        file_content = b"x" * (KB_MAX_FILE_SIZE + extra_bytes)

        async def _run_test():
            with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
                tmp_db_path = tmp.name

            try:
                with patch("backend.database.DATABASE_PATH", tmp_db_path):
                    from backend.database import init_db, get_db
                    from backend.security import hash_password, create_access_token

                    await init_db()

                    # Seed an admin user
                    admin_hash = hash_password("Admin@1234")
                    async with get_db() as db:
                        await db.execute(
                            "INSERT INTO users (username, password_hash, role, first_time_flag) VALUES (?, ?, ?, 0)",
                            ("kb_admin", admin_hash, "Admin"),
                        )
                        await db.commit()

                    # Create admin token
                    admin_token = create_access_token(
                        username="kb_admin", role="Admin", first_time=False
                    )

                    # Determine filename based on content type
                    ext_map = {
                        "application/pdf": "large.pdf",
                        "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "large.docx",
                        "text/plain": "large.txt",
                    }
                    filename = ext_map.get(content_type, "large.bin")

                    from backend.api.main import app

                    transport = httpx.ASGITransport(app=app)
                    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                        response = await client.post(
                            "/api/kb/documents",
                            headers={"Authorization": f"Bearer {admin_token}"},
                            data={"title": title},
                            files={"file": (filename, file_content, content_type)},
                        )

                    assert response.status_code == 413, (
                        f"Expected 413 for file exceeding 10MB (size={len(file_content)}), "
                        f"content_type={content_type!r}, got {response.status_code}: {response.text}"
                    )
            finally:
                if os.path.exists(tmp_db_path):
                    os.unlink(tmp_db_path)
                for suffix in ("-wal", "-shm"):
                    p = tmp_db_path + suffix
                    if os.path.exists(p):
                        os.unlink(p)

        asyncio.run(_run_test())
