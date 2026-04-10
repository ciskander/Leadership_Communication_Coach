"""
auth/password.py — Password hashing and verification using bcrypt.
"""
from __future__ import annotations

import re

import bcrypt


def hash_password(plain: str) -> str:
    """Hash a plaintext password with bcrypt."""
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """Verify a plaintext password against a bcrypt hash."""
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


# Minimum 8 chars, at least 1 letter and 1 digit
_PASSWORD_RE = re.compile(r"^(?=.*[A-Za-z])(?=.*\d).{8,}$")


def validate_password_strength(password: str) -> str | None:
    """Return an error message if password is too weak, else None."""
    if len(password) < 8:
        return "Password must be at least 8 characters."
    if not _PASSWORD_RE.match(password):
        return "Password must contain at least one letter and one number."
    return None
