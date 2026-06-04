from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
import string
from typing import Tuple

DEFAULT_OTP_LENGTH = 6
DEFAULT_HASH_ITERATIONS = int(os.getenv("AUTH_OTP_HASH_ITERATIONS", "100000"))


def generate_otp(length: int = DEFAULT_OTP_LENGTH) -> str:
    # Simple numeric OTP generator (6 digits by default).
    if length <= 0:
        raise ValueError("OTP length must be positive.")
    return "".join(secrets.choice(string.digits) for _ in range(length))


def _derive_key(code: str, *, salt: str, iterations: int) -> bytes:
    # Hash helper so we never store the raw OTP.
    return hashlib.pbkdf2_hmac(
        "sha256",
        code.encode("utf-8"),
        salt.encode("utf-8"),
        iterations,
    )


def hash_otp(code: str, *, salt: str | None = None, iterations: int = DEFAULT_HASH_ITERATIONS) -> Tuple[str, str]:
    # Returns (hash, salt). Store these, never the OTP itself.
    if salt is None:
        salt = secrets.token_urlsafe(16)
    digest = _derive_key(code, salt=salt, iterations=iterations)
    encoded = base64.urlsafe_b64encode(digest).decode("utf-8").rstrip("=")
    return encoded, salt


def verify_otp(
    code: str,
    code_hash: str,
    *,
    salt: str,
    iterations: int = DEFAULT_HASH_ITERATIONS,
) -> bool:
    # Constant-time compare to avoid timing leaks.
    computed, _ = hash_otp(code, salt=salt, iterations=iterations)
    return hmac.compare_digest(computed, code_hash)
