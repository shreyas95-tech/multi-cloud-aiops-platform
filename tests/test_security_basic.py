"""Basic tests for backend/security.py module."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from security import (
    hash_password,
    verify_password,
    create_access_token,
    decode_access_token,
    validate_password_policy,
    generate_reset_token,
    JWT_SECRET_KEY,
    JWT_ALGORITHM,
)
from datetime import datetime, timedelta
from jose import jwt as jose_jwt, JWTError
import pytest


class TestHashPassword:
    def test_produces_bcrypt_hash_with_work_factor_12(self):
        hashed = hash_password("TestPass@123")
        assert hashed.startswith("$2b$12$")

    def test_different_passwords_produce_different_hashes(self):
        h1 = hash_password("Password1!")
        h2 = hash_password("Password2!")
        assert h1 != h2

    def test_same_password_produces_different_hashes(self):
        # bcrypt uses random salt, so same input gives different output
        h1 = hash_password("SamePass@1")
        h2 = hash_password("SamePass@1")
        assert h1 != h2


class TestVerifyPassword:
    def test_correct_password_returns_true(self):
        hashed = hash_password("MySecret@1")
        assert verify_password("MySecret@1", hashed) is True

    def test_wrong_password_returns_false(self):
        hashed = hash_password("MySecret@1")
        assert verify_password("WrongPass@1", hashed) is False

    def test_empty_password_returns_false(self):
        hashed = hash_password("MySecret@1")
        assert verify_password("", hashed) is False


class TestCreateAccessToken:
    def test_token_contains_correct_claims(self):
        token = create_access_token("alice", "Admin", False)
        payload = decode_access_token(token)
        assert payload["sub"] == "alice"
        assert payload["role"] == "Admin"
        assert payload["first_time"] is False

    def test_token_contains_jti(self):
        token = create_access_token("bob", "L1_User", True)
        payload = decode_access_token(token)
        assert "jti" in payload
        assert len(payload["jti"]) == 36  # UUID format

    def test_token_contains_exp(self):
        token = create_access_token("charlie", "Admin", False)
        payload = decode_access_token(token)
        assert "exp" in payload

    def test_each_token_has_unique_jti(self):
        t1 = create_access_token("user", "Admin", False)
        t2 = create_access_token("user", "Admin", False)
        p1 = decode_access_token(t1)
        p2 = decode_access_token(t2)
        assert p1["jti"] != p2["jti"]

    def test_first_time_flag_true(self):
        token = create_access_token("newuser", "L1_User", True)
        payload = decode_access_token(token)
        assert payload["first_time"] is True

    def test_first_time_flag_false(self):
        token = create_access_token("existing", "Admin", False)
        payload = decode_access_token(token)
        assert payload["first_time"] is False


class TestDecodeAccessToken:
    def test_rejects_expired_token(self):
        expired_payload = {
            "sub": "user",
            "role": "Admin",
            "first_time": False,
            "jti": "test-jti",
            "exp": datetime.utcnow() - timedelta(minutes=1),
        }
        expired_token = jose_jwt.encode(
            expired_payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM
        )
        with pytest.raises(Exception):
            decode_access_token(expired_token)

    def test_rejects_invalid_token(self):
        with pytest.raises(Exception):
            decode_access_token("not-a-valid-token")

    def test_rejects_token_with_wrong_secret(self):
        payload = {
            "sub": "user",
            "role": "Admin",
            "first_time": False,
            "jti": "test-jti",
            "exp": datetime.utcnow() + timedelta(minutes=60),
        }
        token = jose_jwt.encode(payload, "wrong-secret", algorithm=JWT_ALGORITHM)
        with pytest.raises(Exception):
            decode_access_token(token)


class TestValidatePasswordPolicy:
    def test_accepts_valid_password(self):
        assert validate_password_policy("Admin@1234") is True

    def test_accepts_boundary_length(self):
        assert validate_password_policy("Aa1!aaaa") is True  # exactly 8 chars

    def test_rejects_too_short(self):
        assert validate_password_policy("Aa1!aaa") is False  # 7 chars

    def test_rejects_no_uppercase(self):
        assert validate_password_policy("nouppercase1!") is False

    def test_rejects_no_lowercase(self):
        assert validate_password_policy("NOLOWERCASE1!") is False

    def test_rejects_no_digit(self):
        assert validate_password_policy("NoDigits!!ab") is False

    def test_rejects_no_special_char(self):
        assert validate_password_policy("NoSpecial1ab") is False

    def test_rejects_empty_string(self):
        assert validate_password_policy("") is False

    def test_accepts_complex_password(self):
        assert validate_password_policy("C0mpl3x!Pass#2024") is True


class TestGenerateResetToken:
    def test_returns_uuid_format(self):
        token = generate_reset_token()
        assert len(token) == 36
        parts = token.split("-")
        assert len(parts) == 5

    def test_generates_unique_tokens(self):
        tokens = {generate_reset_token() for _ in range(100)}
        assert len(tokens) == 100  # all unique
