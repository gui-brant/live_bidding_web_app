from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional, Any

from . import jwt as jwt_utils
from . import otp as otp_utils
from .interfaces import EmailService, OtpChallenge, OtpRepository, TokenBlocklistRepository, UserAuthRepository
from ..helper.timezone import APP_TIMEZONE, ensure_app_datetime, now_in_app_timezone


class AuthError(Exception):
    # Custom error so router can map to ErrorResponse.
    def __init__(self, *, status_code: int, detail: str, code: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail
        self.code = code


@dataclass(frozen=True)
class AuthSettings:
    # Auth knobs (OTP TTL, attempts, cooldown).
    otp_ttl_seconds: int = int(os.getenv("AUTH_OTP_TTL_SECONDS", "600"))
    otp_attempts: int = int(os.getenv("AUTH_OTP_ATTEMPTS", "5"))
    otp_send_cooldown_seconds: int = int(os.getenv("AUTH_OTP_SEND_COOLDOWN_SECONDS", "0"))


@dataclass(frozen=True)
class AuthResult:
    # Pack what router needs after verify.
    access_token: str
    expires_in: int
    user: object
    jti: Optional[str]


def _get_attr(obj: object, name: str):
    # Works for dicts or objects.
    if isinstance(obj, dict):
        return obj.get(name)
    return getattr(obj, name, None)

class AuthService:
    # Core auth logic; DB and email implementations are injected.
    def __init__(
        self,
        *,
        user_repo: UserAuthRepository,
        otp_repo: OtpRepository,
        email_service: EmailService,
        blocklist_repo: TokenBlocklistRepository | None = None,
        auth_settings: AuthSettings | None = None,
        jwt_settings: jwt_utils.JwtSettings | None = None,
    ) -> None:
        self._user_repo = user_repo
        self._otp_repo = otp_repo
        self._email_service = email_service
        self._blocklist_repo = blocklist_repo
        self._auth_settings = auth_settings or AuthSettings()
        self._jwt_settings = jwt_settings or jwt_utils.load_jwt_settings()

    @property
    def jwt_settings(self) -> jwt_utils.JwtSettings:
        return self._jwt_settings

    async def request_otp(self, email: str) -> None:
        # Generate + hash OTP, store challenge, email the code.
        code = otp_utils.generate_otp()
        code_hash, code_salt = otp_utils.hash_otp(code)
        now = now_in_app_timezone()
        challenge = OtpChallenge(
            email=email,
            code_hash=code_hash,
            code_salt=code_salt,
            expires_at=now + timedelta(seconds=self._auth_settings.otp_ttl_seconds),
            attempts_left=self._auth_settings.otp_attempts,
            next_send_allowed_at=now + timedelta(seconds=self._auth_settings.otp_send_cooldown_seconds),
        )
        print("OTP:" + code)
        await self._otp_repo.create_or_replace(email, challenge)
        await self._email_service.send_otp(email, code)

    async def verify_otp(self, *, email: str, code: str) -> AuthResult:
        # Validate OTP challenge then issue JWT.
        challenge = await self._otp_repo.get(email)
        if not challenge:
            raise AuthError(status_code=401, detail="Invalid or expired code.", code="OTP_INVALID")

        now = now_in_app_timezone()
        expires_at = ensure_app_datetime(_get_attr(challenge, "expires_at"))
        attempts_left = _get_attr(challenge, "attempts_left")
        code_hash = _get_attr(challenge, "code_hash")
        code_salt = _get_attr(challenge, "code_salt")

        if not code_hash or not code_salt:
            raise AuthError(status_code=500, detail="OTP challenge missing required fields.", code="OTP_INVALID_STATE")

        if expires_at and now >= expires_at:
            await self._otp_repo.delete(email)
            raise AuthError(status_code=401, detail="Invalid or expired code.", code="OTP_EXPIRED")

        if attempts_left is not None and attempts_left <= 0:
            raise AuthError(status_code=401, detail="Invalid or expired code.", code="OTP_INVALID")

        if not otp_utils.verify_otp(code, code_hash, salt=code_salt):
            await self._otp_repo.decrement_attempts(email)
            raise AuthError(status_code=401, detail="Invalid or expired code.", code="OTP_INVALID")

        await self._otp_repo.delete(email)
        user = await self._user_repo.ensure_user(email, default_role="rep")

        user_id = _get_attr(user, "id") or _get_attr(user, "user_id") or _get_attr(user, "_id")
        role = _get_attr(user, "role")
        if not user_id or not role:
            raise AuthError(status_code=500, detail="User record missing required fields.", code="USER_INVALID")

        token, expires_in, payload = jwt_utils.create_access_token(
            subject=str(user_id),
            role=str(role),
            settings=self._jwt_settings,
        )
        print(f"[AUTH TOKEN] token={token}")
        return AuthResult(
            access_token=token,
            expires_in=expires_in,
            user=user,
            jti=payload.get("jti"),
        )

    async def logout(self, token: str | None) -> None:
        # Optional: blocklist the token's jti so it can't be reused.
        if not token or not self._blocklist_repo:
            return
        try:
            payload = jwt_utils.decode_jwt(token, settings=self._jwt_settings, verify_exp=False)
        except jwt_utils.JwtError:
            return
        jti = payload.get("jti")
        exp = payload.get("exp")
        if not jti or not exp:
            return
        expires_at = datetime.fromtimestamp(int(exp), tz=APP_TIMEZONE)
        await self._blocklist_repo.block_jti(str(jti), expires_at)
