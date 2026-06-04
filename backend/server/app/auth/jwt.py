from __future__ import annotations

import os
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

import jwt as pyjwt
from app.helper.timezone import now_in_app_timezone


class JwtError(Exception):
    # Generic JWT error.
    pass


class JwtExpired(JwtError):
    # Token is valid but expired.
    pass


def _env_bool(name: str, default: bool) -> bool:
    # Small helper to parse bool env vars.
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


@dataclass(frozen=True)
class JwtSettings:
    # Auth-related config pulled from env.
    secret_key: str
    algorithm: str
    access_ttl_seconds: int
    issuer: Optional[str]
    audience: Optional[str]
    use_cookie: bool
    cookie_name: str
    cookie_secure: bool
    cookie_samesite: str
    cookie_path: str
    cookie_domain: Optional[str]
    jti_enabled: bool


def load_jwt_settings() -> JwtSettings:
    # Central place to read JWT/cookie settings.
    secret = os.getenv("AUTH_JWT_SECRET", "change-me")
    return JwtSettings(
        secret_key=secret,
        algorithm=os.getenv("AUTH_JWT_ALGORITHM", "HS256"),
        access_ttl_seconds=int(os.getenv("AUTH_ACCESS_TTL_SECONDS", "900")),
        issuer=os.getenv("AUTH_JWT_ISSUER"),
        audience=os.getenv("AUTH_JWT_AUDIENCE"),
        use_cookie=_env_bool("AUTH_USE_HTTPONLY_COOKIE", True),
        cookie_name=os.getenv("AUTH_COOKIE_NAME", "access_token"),
        cookie_secure=_env_bool("AUTH_COOKIE_SECURE", True),
        cookie_samesite=os.getenv("AUTH_COOKIE_SAMESITE", "lax"),
        cookie_path=os.getenv("AUTH_COOKIE_PATH", "/"),
        cookie_domain=os.getenv("AUTH_COOKIE_DOMAIN"),
        jti_enabled=_env_bool("AUTH_JWT_JTI_ENABLED", False),
    )


def encode_jwt(payload: Dict[str, Any], *, settings: JwtSettings) -> str:
    # Use PyJWT for signing/encoding.
    try:
        token = pyjwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)
    except pyjwt.PyJWTError as exc:
        raise JwtError("Failed to encode token.") from exc
    if isinstance(token, bytes):
        return token.decode("utf-8")
    return token


def decode_jwt(token: str, *, settings: JwtSettings, verify_exp: bool = True) -> Dict[str, Any]:
    # Use PyJWT for signature and claims validation.
    options = {
        "verify_exp": verify_exp,
        "verify_aud": bool(settings.audience),
        "verify_iss": bool(settings.issuer),
    }
    try:
        return pyjwt.decode(
            token,
            settings.secret_key,
            algorithms=[settings.algorithm],
            issuer=settings.issuer if settings.issuer else None,
            audience=settings.audience if settings.audience else None,
            options=options,
        )
    except pyjwt.ExpiredSignatureError as exc:
        raise JwtExpired("Token expired.") from exc
    except pyjwt.InvalidTokenError as exc:
        raise JwtError("Invalid token.") from exc


def create_access_token(*, subject: str, role: str, settings: JwtSettings) -> tuple[str, int, Dict[str, Any]]:
    # Create access token payload + signed token.
    now = now_in_app_timezone()
    expires_at = now + timedelta(seconds=settings.access_ttl_seconds)
    payload: Dict[str, Any] = {
        "sub": subject,
        "role": role,
        "exp": int(expires_at.timestamp()),
        "iat": int(now.timestamp()),
    }
    if settings.issuer:
        payload["iss"] = settings.issuer
    if settings.audience:
        payload["aud"] = settings.audience
    if settings.jti_enabled:
        payload["jti"] = secrets.token_urlsafe(16)

    token = encode_jwt(payload, settings=settings)
    return token, settings.access_ttl_seconds, payload
