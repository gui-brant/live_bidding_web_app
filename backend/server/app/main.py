from __future__ import annotations

import os
import asyncio
import logging
from contextlib import asynccontextmanager
from dataclasses import replace
from typing import Any, Optional

from bson import ObjectId
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

from app.auction import auction_deps
from app.auction.auction_router import router as auction_router
from app.auction.auction_ws import auction_ws_manager, router as auction_ws_router
from app.auction.ws_outbox import WsOutboxDispatcher
from app.auction.auction_service import AuctionService
from app.auction.auction_ws import EVENT_AUCTION_ENDED, EVENT_AUCTION_STATE_UPDATED, ws_event
from app.helper.helpers import _utc_now
from app.auth import auth_deps
from app.auth.auth_router import router as auth_router
from app.compat_router import router as compat_router
from app.auth.interfaces import OtpChallenge
from app.auth import impls as auth_impls
from app.bids import bids_deps
from app.bids.bids_router import router as bids_router
from app.items import items_deps
from app.items.items_router import router as items_router
from app.users import users_deps
from app.users.users_router import router as users_router
from app.wishlist import wishlist_deps
from app.wishlist.wishlist_router import router as wishlist_router

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:
    # dotenv is optional. Env vars can still be injected by runtime.
    pass

logger = logging.getLogger(__name__)


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def _allowed_origins() -> list[str]:
    raw = os.getenv("CORS_ALLOW_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000")
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


def _dev_admin_emails() -> set[str]:
    raw = os.getenv("DEV_ADMIN_EMAILS", "")
    return {email.strip().lower() for email in raw.split(",") if email.strip()}


@asynccontextmanager
async def lifespan(app: FastAPI):
    mongo_uri = os.getenv("MONGODB_URI")
    db_name = os.getenv("MONGODB_DB_NAME", "auction_system")

    app.state.mongo_client = None
    app.state.mongo_db = None
    app.state.ws_outbox_dispatcher = None
    app.state.auction_auto_end_task = None
    app.state.auction_inactivity_task = None

    if mongo_uri:
        from motor.motor_asyncio import AsyncIOMotorClient

        client = AsyncIOMotorClient(mongo_uri)
        app.state.mongo_client = client
        app.state.mongo_db = client[db_name]

        ws_outbox_collection = app.state.mongo_db[os.getenv("WS_OUTBOX_COLLECTION_NAME", "ws_outbox")]
        dispatcher = WsOutboxDispatcher(
            ws_outbox_collection=ws_outbox_collection,
            broadcast_func=auction_ws_manager.broadcast,
            poll_interval_seconds=float(os.getenv("WS_OUTBOX_POLL_SECONDS", "0.25")),
            max_batch_size=int(os.getenv("WS_OUTBOX_BATCH_SIZE", "100")),
        )
        await dispatcher.start()
        app.state.ws_outbox_dispatcher = dispatcher
        poll_seconds = float(os.getenv("AUCTION_AUTO_END_POLL_SECONDS", "5"))
        app.state.auction_auto_end_task = asyncio.create_task(
            _auto_end_loop(app.state.mongo_db, poll_seconds),
            name="auction-auto-end-loop",
        )
        inactivity_poll_seconds = float(os.getenv("AUCTION_INACTIVITY_POLL_SECONDS", "15"))
        app.state.auction_inactivity_task = asyncio.create_task(
            _auction_inactivity_loop(app.state.mongo_db, inactivity_poll_seconds),
            name="auction-inactivity-loop",
        )

    yield

    dispatcher = getattr(app.state, "ws_outbox_dispatcher", None)
    if dispatcher is not None:
        await dispatcher.stop()

    auto_end_task = getattr(app.state, "auction_auto_end_task", None)
    if auto_end_task is not None:
        auto_end_task.cancel()
        try:
            await auto_end_task
        except asyncio.CancelledError:
            pass

    inactivity_task = getattr(app.state, "auction_inactivity_task", None)
    if inactivity_task is not None:
        inactivity_task.cancel()
        try:
            await inactivity_task
        except asyncio.CancelledError:
            pass

    client = getattr(app.state, "mongo_client", None)
    if client is not None:
        client.close()


app = FastAPI(
    title="KogBuck Auction Backend",
    version="0.2.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _require_db(request: Request):
    db = getattr(request.app.state, "mongo_db", None)
    if db is None:
        raise HTTPException(status_code=500, detail="MongoDB is not configured. Set MONGODB_URI.")
    return db


def _users_collection(request: Request):
    return _require_db(request)[os.getenv("USERS_COLLECTION_NAME", "users")]


def _items_collection(request: Request):
    return _require_db(request)[os.getenv("ITEMS_COLLECTION_NAME", "items")]


def _auctions_collection(request: Request):
    return _require_db(request)[os.getenv("AUCTIONS_COLLECTION_NAME", "auctions")]


def _bids_collection(request: Request):
    return _require_db(request)[os.getenv("BIDS_COLLECTION_NAME", "bids")]


def _auction_messages_collection(request: Request):
    return _require_db(request)[os.getenv("AUCTION_MESSAGES_COLLECTION_NAME", "auction_messages")]


def _auction_chat_messages_collection(request: Request):
    return _require_db(request)[os.getenv("AUCTION_CHAT_MESSAGES_COLLECTION_NAME", "auction_chat_messages")]


def _ws_outbox_collection(request: Request):
    return _require_db(request)[os.getenv("WS_OUTBOX_COLLECTION_NAME", "ws_outbox")]


def _wishlist_collection(request: Request):
    return _require_db(request)[os.getenv("WISHLIST_COLLECTION_NAME", "wishlist")]


async def _auto_end_expired_auctions(db) -> None:
    auctions = db[os.getenv("AUCTIONS_COLLECTION_NAME", "auctions")]
    items = db[os.getenv("ITEMS_COLLECTION_NAME", "items")]
    users = db[os.getenv("USERS_COLLECTION_NAME", "users")]
    bids = db[os.getenv("BIDS_COLLECTION_NAME", "bids")]
    messages = db[os.getenv("AUCTION_MESSAGES_COLLECTION_NAME", "auction_messages")]
    chat_messages = db[os.getenv("AUCTION_CHAT_MESSAGES_COLLECTION_NAME", "auction_chat_messages")]
    ws_outbox = db[os.getenv("WS_OUTBOX_COLLECTION_NAME", "ws_outbox")]

    service = AuctionService(
        auction_collection=auctions,
        items_collection=items,
        users_collection=users,
        bids_collection=bids,
        messages_collection=messages,
        ws_outbox_collection=ws_outbox,
        chat_messages_collection=chat_messages,
    )

    now = _utc_now()
    cursor = auctions.find(
        {
            "status": "RUNNING",
            "$or": [
                {"ends_at": {"$lte": now}},
                {"end_time": {"$lte": now}},
            ],
        }
    )
    async for doc in cursor:
        auction_id = str(doc.get("_id"))
        try:
            result = await service.close_auction_and_distribute(auction_id=auction_id)
            state = await service.get_auction_state(auction_id=auction_id)
            await service.queue_ws_events(
                auction_id=auction_id,
                events=[
                    ws_event(EVENT_AUCTION_ENDED, auction_id=auction_id, result=result, state=state),
                    ws_event(EVENT_AUCTION_STATE_UPDATED, auction_id=auction_id, state=state),
                ],
            )
        except Exception:
            logger.exception("Failed to auto-end auction %s.", auction_id)


async def _auto_end_loop(db, poll_seconds: float) -> None:
    interval = max(1.0, poll_seconds)
    while True:
        try:
            await _auto_end_expired_auctions(db)
        except Exception:
            logger.exception("Auto-end loop failed.")
        await asyncio.sleep(interval)


async def _dispatch_inactivity_notifications(db) -> None:
    auctions = db[os.getenv("AUCTIONS_COLLECTION_NAME", "auctions")]
    items = db[os.getenv("ITEMS_COLLECTION_NAME", "items")]
    users = db[os.getenv("USERS_COLLECTION_NAME", "users")]
    bids = db[os.getenv("BIDS_COLLECTION_NAME", "bids")]
    messages = db[os.getenv("AUCTION_MESSAGES_COLLECTION_NAME", "auction_messages")]
    chat_messages = db[os.getenv("AUCTION_CHAT_MESSAGES_COLLECTION_NAME", "auction_chat_messages")]
    ws_outbox = db[os.getenv("WS_OUTBOX_COLLECTION_NAME", "ws_outbox")]

    service = AuctionService(
        auction_collection=auctions,
        items_collection=items,
        users_collection=users,
        bids_collection=bids,
        messages_collection=messages,
        ws_outbox_collection=ws_outbox,
        chat_messages_collection=chat_messages,
    )

    await service.process_inactivity_notifications()


async def _auction_inactivity_loop(db, poll_seconds: float) -> None:
    interval = max(5.0, poll_seconds)
    while True:
        try:
            await _dispatch_inactivity_notifications(db)
        except Exception:
            logger.exception("Auction inactivity loop failed.")
        await asyncio.sleep(interval)


class _DevEmailService:
    # In dev mode we keep OTP in memory for easy manual testing.
    def __init__(self) -> None:
        self._codes: dict[str, str] = {}

    async def send_otp(self, email: str, code: str) -> None:
        self._codes[email] = code

    def get_code(self, email: str) -> Optional[str]:
        return self._codes.get(email)


class _DevOtpRepository:
    # In-memory OTP challenge store for local testing.
    def __init__(self) -> None:
        self._challenges: dict[str, OtpChallenge] = {}

    async def create_or_replace(self, email: str, challenge: OtpChallenge) -> None:
        self._challenges[email] = challenge

    async def get(self, email: str) -> Optional[OtpChallenge]:
        return self._challenges.get(email)

    async def decrement_attempts(self, email: str) -> int:
        challenge = self._challenges.get(email)
        if challenge is None:
            return 0
        updated = replace(challenge, attempts_left=max(0, challenge.attempts_left - 1))
        self._challenges[email] = updated
        return updated.attempts_left

    async def delete(self, email: str) -> None:
        self._challenges.pop(email, None)


class _MongoUserAuthRepository:
    # Dev-mode auth user repository backed by Mongo users collection.
    def __init__(self, users_collection) -> None:
        self._users = users_collection

    async def get_by_email(self, email: str):
        return await self._users.find_one({"email": email})

    async def get_by_id(self, user_id: str):
        candidates: list[Any] = [user_id]
        if ObjectId.is_valid(user_id):
            candidates.append(ObjectId(user_id))
        return await self._users.find_one({"_id": {"$in": candidates}})

    async def ensure_user(self, email: str, default_role: str = "rep"):
        role = default_role
        default_name = email.split("@", 1)[0]
        if email.lower() in _dev_admin_emails():
            role = "admin"
        await self._users.update_one(
            {"email": email},
            {
                "$setOnInsert": {
                    "email": email,
                    "name": default_name,
                    "role": role,
                    "balance_amount": int(os.getenv("DEV_DEFAULT_KOGBUCKS", "1000")),
                    "kogbucks": int(os.getenv("DEV_DEFAULT_KOGBUCKS", "1000")),
                    "bid_counter": 0,
                    "held_item_id": None,
                    "before_bid_amount": 0,
                    "balance_committed": False,
                    "has_bid": False,
                    "gift_card_winner": False,
                }
            },
            upsert=True,
        )
        return await self._users.find_one({"email": email})


_DEV_EMAIL_SERVICE = _DevEmailService()
_DEV_OTP_REPO = _DevOtpRepository()


def _dev_user_repo(request: Request):
    return _MongoUserAuthRepository(_users_collection(request))


def _dev_otp_repo():
    return _DEV_OTP_REPO


def _dev_email_service():
    return _DEV_EMAIL_SERVICE


# Items module dependencies
app.dependency_overrides[items_deps.get_items_collection] = _items_collection

# Auction module dependencies
app.dependency_overrides[auction_deps.get_auction_collection] = _auctions_collection
app.dependency_overrides[auction_deps.get_items_collection] = _items_collection
app.dependency_overrides[auction_deps.get_users_collection] = _users_collection
app.dependency_overrides[auction_deps.get_bids_collection] = _bids_collection
app.dependency_overrides[auction_deps.get_messages_collection] = _auction_messages_collection
app.dependency_overrides[auction_deps.get_chat_messages_collection] = _auction_chat_messages_collection
app.dependency_overrides[auction_deps.get_ws_outbox_collection] = _ws_outbox_collection

# Bids module dependencies
app.dependency_overrides[bids_deps.get_users_collection] = _users_collection
app.dependency_overrides[bids_deps.get_items_collection] = _items_collection
app.dependency_overrides[bids_deps.get_auction_collection] = _auctions_collection
app.dependency_overrides[bids_deps.get_bids_collection] = _bids_collection
app.dependency_overrides[bids_deps.get_messages_collection] = _auction_messages_collection
app.dependency_overrides[bids_deps.get_ws_outbox_collection] = _ws_outbox_collection

# users module dependencies
app.dependency_overrides[users_deps.get_users_collection] = _users_collection

# wishlist module dependencies
app.dependency_overrides[wishlist_deps.get_wishlist_collection] = _wishlist_collection
app.dependency_overrides[wishlist_deps.get_users_collection] = _users_collection


# Wire Mongo-backed OTP repo and SMTP email service when Mongo is configured.
def _mongo_otp_repo(request: Request):
    return auth_impls.MongoOtpRepository(_require_db(request)[os.getenv("OTPS_COLLECTION_NAME", "otps")])


def _smtp_email_service():
    return auth_impls.SmtpEmailService()


# Ensure user repo is available (backed by users collection) for non-dev mode as well.
app.dependency_overrides[auth_deps.get_user_repo] = _dev_user_repo
app.dependency_overrides[auth_deps.get_otp_repo] = _mongo_otp_repo
app.dependency_overrides[auth_deps.get_email_service] = _smtp_email_service

# Optional dev-mode auth wiring for local testing.
if _env_bool("AUTH_DEV_MODE", False):
    # Keep OTP visible via /dev/otp while using Mongo-backed auth repositories.
    app.dependency_overrides[auth_deps.get_email_service] = _dev_email_service


app.include_router(auth_router)
app.include_router(items_router)
app.include_router(auction_router)
app.include_router(auction_ws_router)
app.include_router(bids_router)
app.include_router(users_router)
app.include_router(wishlist_router)
app.include_router(compat_router)


@app.get("/health")
async def health():
    return {"ok": True}


@app.get("/dev/otp/{email}")
async def dev_get_otp(email: str):
    if not _env_bool("AUTH_DEV_MODE", False):
        raise HTTPException(status_code=404, detail="Not found.")
    code = _DEV_EMAIL_SERVICE.get_code(email)
    if not code:
        raise HTTPException(status_code=404, detail="OTP not found for this email.")
    return {"email": email, "code": code}
