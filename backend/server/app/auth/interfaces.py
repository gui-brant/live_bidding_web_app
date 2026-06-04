from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Protocol, runtime_checkable


@runtime_checkable
class AuthUser(Protocol):
    """Minimal user shape required by auth layer."""

    # Keep these fields available for auth only.
    id: str
    email: str
    role: str


@dataclass(frozen=True)
class OtpChallenge:
    """Stored OTP challenge, with hash only (never plaintext)."""

    # Stored challenge fields in DB.
    email: str
    code_hash: str
    code_salt: str
    expires_at: datetime
    attempts_left: int
    next_send_allowed_at: datetime


class UserAuthRepository(Protocol):
    # DB repo for auth user records.
    async def get_by_email(self, email: str) -> Optional[AuthUser]:
        ...

    async def get_by_id(self, user_id: str) -> Optional[AuthUser]:
        ...

    async def ensure_user(self, email: str, default_role: str = "rep") -> AuthUser:
        ...


class OtpRepository(Protocol):
    # DB repo for OTP challenges.
    async def create_or_replace(self, email: str, challenge: OtpChallenge) -> None:
        ...

    async def get(self, email: str) -> Optional[OtpChallenge]:
        ...

    async def decrement_attempts(self, email: str) -> int:
        ...

    async def delete(self, email: str) -> None:
        ...


class EmailService(Protocol):
    # Email sender service (implemented elsewhere).
    async def send_otp(self, email: str, code: str) -> None:
        ...


class TokenBlocklistRepository(Protocol):
    # Optional token revocation store.
    async def block_jti(self, jti: str, expires_at: datetime) -> None:
        ...

    async def is_blocked(self, jti: str) -> bool:
        ...
