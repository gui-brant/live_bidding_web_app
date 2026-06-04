from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, EmailStr, Field, ConfigDict


# ----------------------------
# Requests

class OtpRequestIn(BaseModel):
    """Client requests an OTP to be sent to email."""
    model_config = ConfigDict(extra="ignore")

    # Email used to send OTP.
    email: EmailStr = Field(..., description="User email to receive the one-time code.")


class OtpVerifyIn(BaseModel):
    """Client submits the OTP code to exchange for an auth session (JWT)."""
    model_config = ConfigDict(extra="ignore")

    # Must match the email that requested the OTP.
    email: EmailStr = Field(..., description="Email used to request the OTP.")
    # 6-digit numeric OTP only.
    code: str = Field(
        ...,
        min_length=6,
        max_length=6,
        pattern=r"^\d{6}$",
        description="6-digit numeric code sent via email.",
        examples=["123456"],
    )


class LogoutIn(BaseModel):
    """
    Optional body for logout. Many teams use POST /auth/logout with no body.
    Keep this if you later add device/session targeting.
    """
    model_config = ConfigDict(extra="forbid")

    # Only used if you send refresh tokens in body.
    refresh_token: Optional[str] = Field(
        default=None,
        description="Optional: if you use refresh tokens in body instead of HttpOnly cookie.",
    )


# ----------------------------
# Responses

class SafeProfile(BaseModel):
    """Minimal safe profile returned to frontend after auth."""
    model_config = ConfigDict(extra="forbid")

    # Keep it minimal for safety.
    user_id: str = Field(..., description="Authenticated user id (string).")
    email: EmailStr = Field(..., description="Authenticated user email.")
    role: Literal["rep", "admin"] = Field(..., description="Authorization role.")


class TokenResponse(BaseModel):
    """
    Returned after successful OTP verify.
    If you store tokens in HttpOnly cookies, you can still return a small JSON response
    to help frontend know who is logged in.
    """
    model_config = ConfigDict(extra="forbid")

    # Standard bearer token response.
    token_type: Literal["bearer"] = Field(default="bearer")
    access_token: Optional[str] = Field(
        default=None,
        description="JWT access token. Optional if you prefer HttpOnly cookie-only auth.",
    )
    expires_in: int = Field(
        ...,
        ge=1,
        description="Access token lifetime in seconds.",
        examples=[900],
    )
    # Safe profile used by frontend to show who is logged in.
    profile: SafeProfile = Field(..., description="Minimal safe profile for the frontend.")


class MeResponse(SafeProfile):
    """Safe minimal identity for /auth/me if you add it later."""


# ----------------------------
# Error shape (optional but helps frontend)

class ErrorResponse(BaseModel):
    """
    Optional standard error payload. FastAPI also has default error shapes.
    Use this only if your team wants consistent errors across frontend/backend.
    """
    model_config = ConfigDict(extra="forbid")

    # Frontend-friendly error info.
    detail: str = Field(..., examples=["Invalid or expired code."])
    code: Optional[str] = Field(
        default=None,
        description="Machine-readable error code (e.g., OTP_INVALID, OTP_EXPIRED, RATE_LIMITED).",
    )
