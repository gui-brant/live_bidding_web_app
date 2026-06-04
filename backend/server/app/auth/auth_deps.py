from __future__ import annotations

import os
from datetime import datetime
from typing import Optional

from bson import ObjectId
from fastapi import Depends, HTTPException, Request, WebSocket, status
from fastapi.requests import HTTPConnection
from pymongo import ReturnDocument

from . import jwt as jwt_utils
from .interfaces import EmailService, OtpChallenge, OtpRepository, TokenBlocklistRepository, UserAuthRepository
from .auth_service import AuthService
from app.helper.timezone import now_in_app_timezone


def _candidate_id_values(user_id: str) -> list[object]:
    values: list[object] = [user_id]
    if ObjectId.is_valid(user_id):
        values.append(ObjectId(user_id))
    return values


def _require_db(conn: HTTPConnection):
    db = getattr(conn.app.state, "mongo_db", None)
    if db is None:
        raise HTTPException(status_code=500, detail="MongoDB is not configured. Set MONGODB_URI.")
    return db


def _users_collection(conn: HTTPConnection):
    return _require_db(conn)[os.getenv("USERS_COLLECTION_NAME", "users")]


def _otp_collection(conn: HTTPConnection):
    return _require_db(conn)[os.getenv("AUTH_OTP_COLLECTION_NAME", "auth_otp_challenges")]


def _token_blocklist_collection(conn: HTTPConnection):
    return _require_db(conn)[os.getenv("AUTH_BLOCKLIST_COLLECTION_NAME", "auth_token_blocklist")]


def _dev_admin_emails() -> set[str]:
    raw = os.getenv("DEV_ADMIN_EMAILS", "")
    return {email.strip().lower() for email in raw.split(",") if email.strip()}


class MongoUserAuthRepository:
    # Mongo implementation for auth user lookups + ensure_user.
    def __init__(self, users_collection) -> None:
        self._users = users_collection

    async def get_by_email(self, email: str):
        return await self._users.find_one({"email": email})

    async def get_by_id(self, user_id: str):
        return await self._users.find_one({"_id": {"$in": _candidate_id_values(user_id)}})

    async def ensure_user(self, email: str, default_role: str = "rep"):
        #This is the "just in time" user provisioning logic that creates a user record on first login if one doesn't already exist. 
        #It also ensures that certain fields are always present and sets defaults for them if they're missing. 
        #This is useful for keeping the authentication flow simple while still maintaining a consistent user data structure in MongoDB.
        #this function is called during the OTP verification/login process. If a user with the given email doesn't exist, it creates a new user with default values. 
        #If the user already exists, it checks for missing fields and updates them with defaults if necessary. 
        #This way, we can ensure that all user records have the required fields without needing a separate user registration step.
        role = default_role
        if email.lower() in _dev_admin_emails():
            role = "admin"
        now = now_in_app_timezone()
        default_kogbucks = int(os.getenv("DEV_DEFAULT_KOGBUCKS", "1000"))
        default_name = email.split("@", 1)[0]

        existing = await self._users.find_one({"email": email})
        if not existing:
            await self._users.insert_one(
                {
                    "email": email,
                    "name": default_name,
                    "role": role,
                    "balance_amount": default_kogbucks,
                    "kogbucks": default_kogbucks,
                    "bid_counter": 0,
                    "held_item_id": None,
                    "before_bid_amount": 0,
                    "balance_committed": False,
                    "has_bid": False,
                    "gift_card_winner": False,
                    "created_at": now,
                    "updated_at": now,
                }
            )
            return await self._users.find_one({"email": email})

        patch: dict[str, object] = {"updated_at": now}
        if not existing.get("name"):
            patch["name"] = default_name
        if not existing.get("role"):
            patch["role"] = role
        if "balance_amount" not in existing:
            patch["balance_amount"] = default_kogbucks
        if "kogbucks" not in existing:
            patch["kogbucks"] = default_kogbucks
        if "bid_counter" not in existing:
            patch["bid_counter"] = 0
        if "held_item_id" not in existing:
            patch["held_item_id"] = None
        if "before_bid_amount" not in existing:
            patch["before_bid_amount"] = 0
        if "balance_committed" not in existing:
            patch["balance_committed"] = False
        if "has_bid" not in existing:
            patch["has_bid"] = False
        if "gift_card_winner" not in existing:
            patch["gift_card_winner"] = False
        if "created_at" not in existing:
            patch["created_at"] = now

        if patch:
            await self._users.update_one({"_id": existing["_id"]}, {"$set": patch})
        return await self._users.find_one({"email": email})


class MongoOtpRepository:
    # Mongo implementation for hashed OTP challenge storage.
    def __init__(self, otp_collection) -> None:
        self._otp = otp_collection

    async def create_or_replace(self, email: str, challenge: OtpChallenge) -> None:
        await self._otp.replace_one(
            {"email": email},
            {
                "email": challenge.email,
                "code_hash": challenge.code_hash,
                "code_salt": challenge.code_salt,
                "expires_at": challenge.expires_at,
                "attempts_left": challenge.attempts_left,
                "next_send_allowed_at": challenge.next_send_allowed_at,
                "updated_at": now_in_app_timezone(),
            },
            upsert=True,
        )

    async def get(self, email: str) -> OtpChallenge | None:
        doc = await self._otp.find_one({"email": email})
        if not doc:
            return None
        return OtpChallenge(
            email=str(doc["email"]),
            code_hash=str(doc["code_hash"]),
            code_salt=str(doc["code_salt"]),
            expires_at=doc["expires_at"],
            attempts_left=int(doc["attempts_left"]),
            next_send_allowed_at=doc["next_send_allowed_at"],
        )

    async def decrement_attempts(self, email: str) -> int:
        updated = await self._otp.find_one_and_update(
            {"email": email, "attempts_left": {"$gt": 0}},
            {"$inc": {"attempts_left": -1}},
            return_document=ReturnDocument.AFTER,
        )
        if updated:
            return int(updated.get("attempts_left", 0))
        doc = await self._otp.find_one({"email": email}, {"attempts_left": 1})
        return int(doc.get("attempts_left", 0)) if doc else 0

    async def delete(self, email: str) -> None:
        await self._otp.delete_one({"email": email})


class MongoTokenBlocklistRepository:
    # Optional JWT jti blocklist persisted in Mongo.
    def __init__(self, blocklist_collection) -> None:
        self._blocklist = blocklist_collection

    async def block_jti(self, jti: str, expires_at: datetime) -> None:
        await self._blocklist.update_one(
            {"jti": jti},
            {"$set": {"jti": jti, "expires_at": expires_at, "updated_at": now_in_app_timezone()}},
            upsert=True,
        )

    async def is_blocked(self, jti: str) -> bool:
        now = now_in_app_timezone()
        doc = await self._blocklist.find_one({"jti": jti, "expires_at": {"$gt": now}})
        return doc is not None


class ConsoleEmailService:
    # Minimal fallback email service for local development.
    async def send_otp(self, email: str, code: str) -> None:
        print(f"[AUTH OTP] email={email} code={code}")


def get_user_repo(request: Request) -> UserAuthRepository:
    return MongoUserAuthRepository(_users_collection(request))


def get_otp_repo(request: Request) -> OtpRepository:
    return MongoOtpRepository(_otp_collection(request))


def get_email_service() -> EmailService:
    # Replace with your real email provider in integration env if available.
    return ConsoleEmailService()


def get_blocklist_repo(request: HTTPConnection) -> TokenBlocklistRepository | None:
    enabled = os.getenv("AUTH_ENABLE_BLOCKLIST", "false").strip().lower() in {"1", "true", "yes", "on"}
    if not enabled:
        return None
    return MongoTokenBlocklistRepository(_token_blocklist_collection(request))


def get_jwt_settings() -> jwt_utils.JwtSettings:
    # Pull JWT/cookie settings from env.
    return jwt_utils.load_jwt_settings()


def get_auth_service(
    user_repo: UserAuthRepository = Depends(get_user_repo),
    otp_repo: OtpRepository = Depends(get_otp_repo),
    email_service: EmailService = Depends(get_email_service),
    blocklist_repo: TokenBlocklistRepository | None = Depends(get_blocklist_repo),
    jwt_settings: jwt_utils.JwtSettings = Depends(get_jwt_settings),
) -> AuthService:
    # Build the AuthService with injected dependencies.
    return AuthService(
        user_repo=user_repo,
        otp_repo=otp_repo,
        email_service=email_service,
        blocklist_repo=blocklist_repo,
        jwt_settings=jwt_settings,
    )


def get_token_from_request(request: Request, *, settings: jwt_utils.JwtSettings) -> Optional[str]:
    # Accept token from Authorization header or HttpOnly cookie.
    auth_header = request.headers.get("Authorization")
    if auth_header:
        prefix = "bearer "
        if auth_header.lower().startswith(prefix):
            return auth_header[len(prefix):].strip()
    if settings.use_cookie:
        return request.cookies.get(settings.cookie_name)
    return None


def get_token_from_websocket(websocket: WebSocket, *, settings: jwt_utils.JwtSettings) -> Optional[str]:
    # Accept token from Authorization header, query params, or HttpOnly cookie.
    auth_header = websocket.headers.get("Authorization")
    if auth_header:
        prefix = "bearer "
        if auth_header.lower().startswith(prefix):
            return auth_header[len(prefix):].strip()

    token_from_query = websocket.query_params.get("token") or websocket.query_params.get("access_token")
    if token_from_query:
        return token_from_query.strip()

    if settings.use_cookie:
        return websocket.cookies.get(settings.cookie_name)
    return None


async def get_current_user(
    request: Request,
    user_repo: UserAuthRepository = Depends(get_user_repo),
    blocklist_repo: TokenBlocklistRepository | None = Depends(get_blocklist_repo),
    jwt_settings: jwt_utils.JwtSettings = Depends(get_jwt_settings),
):
    # Decode JWT, enforce revocation, fetch user by id.
    token = get_token_from_request(request, settings=jwt_settings)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing token.")

    try:
        payload = jwt_utils.decode_jwt(token, settings=jwt_settings, verify_exp=True)
    except jwt_utils.JwtExpired:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired.")
    except jwt_utils.JwtError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token.")

    jti = payload.get("jti")
    if jti and blocklist_repo:
        if await blocklist_repo.is_blocked(str(jti)):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token revoked.")

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token.")

    user = await user_repo.get_by_id(str(user_id))
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token.")
    return user


async def get_current_user_from_websocket(websocket: WebSocket):
    # WebSocket variant of auth guard so live channels can enforce JWT + blocklist.
    jwt_settings = get_jwt_settings()
    token = get_token_from_websocket(websocket, settings=jwt_settings)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing token.")

    try:
        payload = jwt_utils.decode_jwt(token, settings=jwt_settings, verify_exp=True)
    except jwt_utils.JwtExpired:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired.")
    except jwt_utils.JwtError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token.")

    jti = payload.get("jti")
    blocklist_repo = get_blocklist_repo(websocket)
    if jti and blocklist_repo:
        if await blocklist_repo.is_blocked(str(jti)):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token revoked.")

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token.")

    user_repo = MongoUserAuthRepository(_users_collection(websocket))
    user = await user_repo.get_by_id(str(user_id))
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token.")
    return user


def require_role(required_role: str):
    # Simple role guard for admin/rep endpoints.
    async def _require_role(user=Depends(get_current_user)):
        role = getattr(user, "role", None) if not isinstance(user, dict) else user.get("role")
        if role != required_role:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden.")
        return user

    return _require_role
