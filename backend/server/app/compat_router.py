from __future__ import annotations

from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, unquote, urlparse
from typing import Any, Literal, Optional

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field

from app.auth.auth_deps import get_current_user, require_role
from app.auction.auction_deps import get_auction_service
from app.auction.auction_service import AuctionService
from app.bids.bids_deps import get_bids_service
from app.bids.bids_service import BidsService
from app.helper.helpers import _user_ids_query, _user_id_query, _get_user_settings
from app.helper.timezone import ensure_app_datetime, now_in_app_timezone
from app.helper.emailer import send_notification_email
from app.items.items_schemas import DEFAULT_ITEM_IMAGE_URL

router = APIRouter(tags=["compat"])


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _to_non_negative_int(value: Any, default: int = 0) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(0, parsed)


def _to_datetime(value: Any) -> Optional[datetime]:
    return ensure_app_datetime(value) #normalize to datetime or return None if input is invalid.


def _to_iso(value: Any) -> Optional[str]:
    parsed = _to_datetime(value)
    if parsed is None:
        return None
    return parsed.isoformat()


def _get_attr(obj: object, name: str):
    if isinstance(obj, dict):
        return obj.get(name)
    return getattr(obj, name, None)


def _extract_user_id(user: object) -> str:
    value = _get_attr(user, "id") or _get_attr(user, "_id") or _get_attr(user, "user_id")
    if value is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authenticated user.")
    return str(value)


def _extract_user_role(user: object) -> str:
    value = _get_attr(user, "role")
    if value is None:
        return "rep"
    return str(value).lower()


def _candidate_id_values(user_id: str) -> list[Any]:
    values: list[Any] = [user_id]
    if ObjectId.is_valid(user_id):
        values.append(ObjectId(user_id))
    return values


def _auction_id_query(auction_id: str) -> dict[str, Any]:
    if ObjectId.is_valid(auction_id):
        return {"_id": {"$in": [auction_id, ObjectId(auction_id)]}}
    return {"_id": auction_id}


def _normalize_string_list(values: list[Any]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for raw in values:
        text = str(raw).strip()
        if not text or text in seen:
            continue
        normalized.append(text)
        seen.add(text)
    return normalized


def _status_to_backend(status_value: str | None) -> str:
    status_text = (status_value or "UPCOMING").upper()
    if status_text == "LIVE":
        return "RUNNING"
    if status_text == "ENDED":
        return "ENDED"
    return "IDLE"


def _status_to_frontend(status_value: str | None) -> Literal["UPCOMING", "LIVE", "ENDED"]:
    status_text = (status_value or "IDLE").upper()
    if status_text == "RUNNING":
        return "LIVE"
    if status_text == "ENDED":
        return "ENDED"
    return "UPCOMING"


def _room_status_from_doc(doc: dict[str, Any]) -> Literal["IDLE", "RUNNING", "PAUSED", "ENDED"]:
    compat_status = str(doc.get("compat_room_status") or "").upper()
    if compat_status in {"IDLE", "RUNNING", "PAUSED", "ENDED"}:
        return compat_status  # type: ignore[return-value]
    base_status = str(doc.get("status") or "IDLE").upper()
    if base_status == "RUNNING":
        return "RUNNING"
    if base_status == "ENDED":
        return "ENDED"
    return "IDLE"


def _require_db(request: Request):
    db = getattr(request.app.state, "mongo_db", None)
    if db is None:
        raise HTTPException(status_code=500, detail="MongoDB is not configured. Set MONGODB_URI.")
    return db


def _users_collection(request: Request):
    return _require_db(request)["users"]


def _items_collection(request: Request):
    return _require_db(request)["items"]


def _auctions_collection(request: Request):
    return _require_db(request)["auctions"]


def _bids_collection(request: Request):
    return _require_db(request)["bids"]


def _parse_item_ids(raw_item_ids: list[Any]) -> list[str]:
    ids = _normalize_string_list(raw_item_ids)
    return [item_id for item_id in ids if ObjectId.is_valid(item_id)]


async def _ensure_items_selectable(items_collection, item_ids: list[str]) -> None:
    if not item_ids:
        return
    object_ids = [ObjectId(item_id) for item_id in item_ids]
    docs = [doc async for doc in items_collection.find({"_id": {"$in": object_ids}})]
    by_id = {str(doc.get("_id")): doc for doc in docs}
    invalid: list[str] = []
    missing: list[str] = []
    for item_id in item_ids:
        doc = by_id.get(item_id)
        if not doc:
            missing.append(item_id)
            continue
        status = str(doc.get("status") or "").upper()
        compat_status = str(doc.get("compat_item_status") or "").upper()
        if status in {"SOLD", "ENDED"} or compat_status == "ENDED" or doc.get("winner_user_id"):
            invalid.append(item_id)
    if missing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Some selected items were not found.")
    if invalid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Selected items that are SOLD or ENDED cannot be added to an auction.",
        )


async def _find_user_doc_by_id(users_collection, user_id: str) -> Optional[dict[str, Any]]:
    return await users_collection.find_one({"_id": {"$in": _candidate_id_values(user_id)}})


def _map_admin_user(doc: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(doc.get("_id")),
        "email": doc.get("email"),
        "role": (doc.get("role") or "rep").lower(),
        "display_name": doc.get("name"),
        "balance_amount": _to_non_negative_int(doc.get("balance_amount", 0)),
        "balance_committed": bool(doc.get("balance_committed", False)),
        "before_bid_amount": _to_non_negative_int(doc.get("before_bid_amount", 0)),
        "held_item_id": str(doc.get("held_item_id")) if doc.get("held_item_id") else None,
    }


def _map_admin_item(doc: dict[str, Any]) -> dict[str, Any]:
    image_url = _normalize_image_url(doc.get("image_url"))
    return {
        "id": str(doc.get("_id")),
        "name": doc.get("name") or doc.get("title") or "Untitled Item",
        "title": doc.get("name") or doc.get("title") or "Untitled Item",
        "category": doc.get("category") or "General",
        "description": doc.get("description"),
        "image_url": image_url,
        "status": doc.get("status"),
        "compat_item_status": doc.get("compat_item_status"),
        "winner_user_id": str(doc.get("winner_user_id")) if doc.get("winner_user_id") else None,
    }


def _auction_start_end(doc: dict[str, Any]) -> tuple[datetime, datetime]:
    now = _utc_now()
    starts_at = _to_datetime(doc.get("starts_at") or doc.get("startAt") or doc.get("start_time")) or now
    ends_at = _to_datetime(doc.get("ends_at") or doc.get("endAt") or doc.get("end_time")) or (starts_at + timedelta(hours=1))
    return starts_at, ends_at


async def _load_items_by_ids(items_collection, item_ids: list[str]) -> list[dict[str, Any]]:
    object_ids = [ObjectId(item_id) for item_id in item_ids if ObjectId.is_valid(item_id)]
    if not object_ids:
        return []
    docs = [doc async for doc in items_collection.find({"_id": {"$in": object_ids}})]
    by_id = {str(doc.get("_id")): doc for doc in docs}
    return [by_id[item_id] for item_id in item_ids if item_id in by_id]


def _map_auction_item_status(
    auction_doc: dict[str, Any],
    item_doc: dict[str, Any],
) -> Literal["UPCOMING", "LIVE", "SOLD", "ENDED", "TEMPORARILY-OWNED", "PRE-SOLD"]:
    compat_status = str(item_doc.get("compat_item_status") or "").upper()
    if compat_status == "ENDED":
        return "ENDED"

    item_status = str(item_doc.get("status") or "AVAILABLE").upper()
    if item_status in {"TEMPORARILY-OWNED", "PRE-SOLD"}:
        return item_status
    if item_status == "SOLD" or item_doc.get("winner_user_id"):
        return "SOLD"

    auction_status = _status_to_frontend(str(auction_doc.get("status") or "IDLE"))
    if auction_status == "LIVE":
        return "LIVE"

    if auction_status == "ENDED":
        return "ENDED"

    return "UPCOMING"


def _normalize_image_url(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return DEFAULT_ITEM_IMAGE_URL
    try:
        parsed = urlparse(text)
        params = parse_qs(parsed.query)
        for key in ("mediaurl", "imgurl"):
            if key in params and params[key]:
                candidate = unquote(params[key][0])
                if candidate:
                    return candidate
    except Exception:
        pass
    lowered = text.lower()
    if lowered.startswith(("http://", "https://", "data:", "blob:", "//")):
        return text
    return f"https://{text}"


def _map_auction_item(auction_doc: dict[str, Any], item_doc: dict[str, Any]) -> dict[str, Any]:
    item_id = str(item_doc.get("_id"))
    image_url = _normalize_image_url(item_doc.get("image_url"))
    winner_id = str(item_doc.get("winner_user_id")) if item_doc.get("winner_user_id") else None
    return {
        "itemId": item_id,
        "title": item_doc.get("name") or item_doc.get("title") or "Untitled Item",
        "description": item_doc.get("description"),
        "image_url": image_url,
        "status": _map_auction_item_status(auction_doc, item_doc),
        "highestBid": _to_non_negative_int(item_doc.get("highest_bid", 0)),
        "increment": _to_non_negative_int(item_doc.get("increment", 0)),
        "tempOwner": str(item_doc.get("highest_bidder_id")) if item_doc.get("highest_bidder_id") else None,
        "winnerUserId": str(item_doc.get("winner_user_id")) if item_doc.get("winner_user_id") else None,
        "updatedAt": _to_iso(item_doc.get("updated_at")),
    }


def _map_admin_auction(auction_doc: dict[str, Any]) -> dict[str, Any]:
    starts_at, ends_at = _auction_start_end(auction_doc)
    auction_id = str(auction_doc.get("_id"))
    item_ids = _normalize_string_list(auction_doc.get("selected_item_ids", []))

    return {
        "id": auction_id,
        "title": auction_doc.get("title") or f"Auction {auction_id}",
        "category": auction_doc.get("category") or "General",
        "status": _status_to_frontend(str(auction_doc.get("status") or "IDLE")),
        "startAt": starts_at.isoformat(),
        "endAt": ends_at.isoformat(),
        "currentHighestBid": _to_non_negative_int(auction_doc.get("highest_bid", 0)),
        "description": auction_doc.get("description"),
        "itemIds": item_ids,
        "invitedParticipantIds": _normalize_string_list(auction_doc.get("invited_user_ids", [])),
    }


async def _map_public_auction(auction_doc: dict[str, Any], items_collection) -> dict[str, Any]:
    starts_at, ends_at = _auction_start_end(auction_doc)
    auction_id = str(auction_doc.get("_id"))
    item_ids = _normalize_string_list(auction_doc.get("selected_item_ids", []))
    item_docs = await _load_items_by_ids(items_collection, item_ids)
    current_item_index = auction_doc.get("current_item_index")

    payload: dict[str, Any] = {
        "id": auction_id,
        "title": auction_doc.get("title") or f"Auction {auction_id}",
        "status": _status_to_frontend(str(auction_doc.get("status") or "IDLE")),
        "startAt": starts_at.isoformat(),
        "endAt": ends_at.isoformat(),
        "item_ids": item_ids,
        "auctionItems": [_map_auction_item(auction_doc, item_doc) for item_doc in item_docs],
        "invitedParticipantIds": _normalize_string_list(auction_doc.get("invited_user_ids", [])),
        "auctionStartTime": _to_iso(auction_doc.get("starts_at")),
        "initialBidDeadline": _to_iso(auction_doc.get("join_deadline")),
        "auctionEndTime": _to_iso(auction_doc.get("ends_at")),
        "overtimeCount": _to_non_negative_int(auction_doc.get("overtime_count", 0)),
        "current_item_index": _to_non_negative_int(current_item_index, 0) if current_item_index is not None else None,
        "current_item_id": str(auction_doc.get("current_item_id")) if auction_doc.get("current_item_id") else None,
    }
    return payload


def _room_state_payload(auction_doc: dict[str, Any]) -> dict[str, Any]:
    now = _utc_now()
    ends_at = _to_datetime(auction_doc.get("ends_at") or auction_doc.get("end_time"))
    room_status = _room_status_from_doc(auction_doc)

    remaining_seconds = 0
    if ends_at and room_status in {"RUNNING", "PAUSED"}:
        remaining_seconds = max(0, int((ends_at - now).total_seconds()))

    active_users = _normalize_string_list(auction_doc.get("participants", []))

    return {
        "auction_id": str(auction_doc.get("_id")),
        "status": room_status,
        "remainingSeconds": remaining_seconds,
        "active_count": len(active_users),
        "active_users": active_users,
    }


class NotificationPrefsIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    in_app_enabled: bool
    email_enabled: bool
    sms_enabled: bool
    notify_outbid: bool = True
    notify_auction_timeframe: bool = True
    notify_auction_win: bool = True


class AdminUpdateUserIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str = Field(..., min_length=1)


class AdminSetKogbucksIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kogbucks: int = Field(..., ge=0)


class AuctionItemCreateIn(BaseModel):
    model_config = ConfigDict(extra="ignore")

    title: Optional[str] = None
    name: Optional[str] = None
    category: Literal["physical item", "gift card"]
    description: Optional[str] = None
    image_url: Optional[str] = None


class AuctionItemUpdateIn(BaseModel):
    model_config = ConfigDict(extra="ignore")

    title: Optional[str] = None
    name: Optional[str] = None
    category: Optional[Literal["physical item", "gift card"]] = None
    description: Optional[str] = None
    image_url: Optional[str] = None


class AdminAuctionCreateIn(BaseModel):
    model_config = ConfigDict(extra="ignore")

    title: str = Field(..., min_length=1)
    category: Optional[str] = None
    status: Literal["UPCOMING", "LIVE", "ENDED"] = "UPCOMING"
    startAt: Optional[str] = None
    endAt: Optional[str] = None
    description: Optional[str] = None
    itemIds: list[str] = Field(default_factory=list)


class AdminAuctionUpdateIn(BaseModel):
    model_config = ConfigDict(extra="ignore")

    title: Optional[str] = None
    category: Optional[str] = None
    status: Optional[Literal["UPCOMING", "LIVE", "ENDED"]] = None
    startAt: Optional[str] = None
    endAt: Optional[str] = None
    description: Optional[str] = None
    itemIds: Optional[list[str]] = None


class AdminAuctionStatusIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["UPCOMING", "LIVE", "ENDED"]


class AdminInviteIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    userIds: list[str] = Field(default_factory=list)


class AdminAuctionTimeframeIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    startAt: str
    endAt: str


class AdminIncrementIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    itemId: str
    increment: int = Field(..., ge=0)


class AdminCustomNotificationIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(..., min_length=1, max_length=1000)
    audience: Literal["ADMINS", "REPS", "ALL"] = "REPS"
    itemId: Optional[str] = None


class AuctionBidIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_id: str


@router.get("/me")
async def get_me(current_user=Depends(get_current_user)):
    return {
        "user_id": _extract_user_id(current_user),
        "email": _get_attr(current_user, "email"),
        "role": (_get_attr(current_user, "role") or "rep").lower(),
        "display_name": _get_attr(current_user, "name"),
    }


@router.get("/kogbucks")
async def get_kogbucks(current_user=Depends(get_current_user)):
    available_balance = _to_non_negative_int(_get_attr(current_user, "balance_amount"), 0)
    held_balance = _to_non_negative_int(_get_attr(current_user, "before_bid_amount"), 0) if bool(_get_attr(current_user, "balance_committed")) else 0
    return {
        "available_balance": available_balance,
        "held_balance": held_balance,
        "is_on_hold": held_balance > 0,
        "hold_context": {"reason": "Active bid hold"} if held_balance > 0 else None,
    }


@router.get("/prefs")
async def get_notification_prefs(request: Request, current_user=Depends(get_current_user)):
    user_id = _extract_user_id(current_user)
    user_doc = await _find_user_doc_by_id(_users_collection(request), user_id)
    if not user_doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    prefs = user_doc.get("notification_prefs") or {}
    return {
        "in_app_enabled": bool(prefs.get("in_app_enabled", True)),
        "email_enabled": bool(prefs.get("email_enabled", True)),
        "sms_enabled": bool(prefs.get("sms_enabled", False)),
        "notify_outbid": bool(prefs.get("notify_outbid", True)),
        "notify_auction_timeframe": bool(prefs.get("notify_auction_timeframe", True)),
        "notify_auction_win": bool(prefs.get("notify_auction_win", True)),
    }


@router.put("/prefs")
async def update_notification_prefs(
    payload: NotificationPrefsIn,
    request: Request,
    current_user=Depends(get_current_user),
):
    user_id = _extract_user_id(current_user)
    users = _users_collection(request)
    user_doc = await _find_user_doc_by_id(users, user_id)
    if not user_doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

    prefs_doc = payload.model_dump()
    await users.update_one(
        {"_id": user_doc["_id"]},
        {
            "$set": {
                "notification_prefs": prefs_doc,
                "updated_at": _utc_now(),
            }
        },
    )
    return prefs_doc


@router.get("/admin/users", dependencies=[Depends(require_role("admin"))])
async def admin_list_users(request: Request):
    users = [_map_admin_user(doc) async for doc in _users_collection(request).find({})]
    users.sort(key=lambda entry: (entry.get("email") or "", entry["id"]))
    return users


@router.patch("/admin/users/{user_id}", dependencies=[Depends(require_role("admin"))])
async def admin_update_user_name(user_id: str, payload: AdminUpdateUserIn, request: Request):
    users = _users_collection(request)
    user_doc = await _find_user_doc_by_id(users, user_id)
    if not user_doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

    await users.update_one(
        {"_id": user_doc["_id"]},
        {
            "$set": {
                "name": payload.display_name.strip(),
                "updated_at": _utc_now(),
            }
        },
    )
    updated = await users.find_one({"_id": user_doc["_id"]})
    return _map_admin_user(updated or user_doc)


@router.post("/admin/users/{user_id}/kogbucks", dependencies=[Depends(require_role("admin"))])
async def admin_set_user_kogbucks(user_id: str, payload: AdminSetKogbucksIn, request: Request):
    users = _users_collection(request)
    user_doc = await _find_user_doc_by_id(users, user_id)
    if not user_doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

    now = _utc_now()
    await users.update_one(
        {"_id": user_doc["_id"]},
        {
            "$set": {
                "balance_amount": int(payload.kogbucks),
                "kogbucks": int(payload.kogbucks),
                "balance_committed": False,
                "before_bid_amount": 0,
                "held_item_id": None,
                "committed_item_id": None,
                "updated_at": now,
            }
        },
    )
    return {"ok": True}


@router.get("/auctions/items", dependencies=[Depends(get_current_user)])
async def list_auction_items(request: Request):
    items = [_map_admin_item(doc) async for doc in _items_collection(request).find({}).sort("updated_at", -1)]
    return items


@router.post("/auctions/items", dependencies=[Depends(require_role("admin"))])
async def create_auction_item(payload: AuctionItemCreateIn, request: Request):
    title = (payload.title or payload.name or "").strip()
    if not title:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Item title is required.")

    now = _utc_now()
    image_url = _normalize_image_url(payload.image_url)
    doc = {
        "name": title,
        "category": payload.category,
        "description": payload.description,
        "image_url": image_url,
        "status": "AVAILABLE",
        "highest_bid": 0,
        "highest_bidder_id": None,
        "winner_user_id": None,
        "active_auction_id": None,
        "selected_for_auction": False,
        "increment": 0,
        "created_at": now,
        "updated_at": now,
    }
    result = await _items_collection(request).insert_one(doc)
    created = await _items_collection(request).find_one({"_id": result.inserted_id})
    return _map_admin_item(created or {**doc, "_id": result.inserted_id})


@router.patch("/auctions/items/{item_id}", dependencies=[Depends(require_role("admin"))])
async def update_auction_item(item_id: str, payload: AuctionItemUpdateIn, request: Request):
    if not ObjectId.is_valid(item_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid item_id.")

    items = _items_collection(request)
    existing = await items.find_one({"_id": ObjectId(item_id)})
    if not existing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found.")

    updates: dict[str, Any] = {}
    if payload.title is not None or payload.name is not None:
        next_name = (payload.title if payload.title is not None else payload.name or "").strip()
        if not next_name:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Item title is required.")
        updates["name"] = next_name
    if payload.category is not None:
        updates["category"] = payload.category.strip() or "General"
    if payload.description is not None:
        updates["description"] = payload.description
    if payload.image_url is not None:
        updates["image_url"] = _normalize_image_url(payload.image_url)

    if updates:
        updates["updated_at"] = _utc_now()
        await items.update_one({"_id": existing["_id"]}, {"$set": updates})

    updated = await items.find_one({"_id": existing["_id"]})
    return _map_admin_item(updated or existing)


@router.delete("/auctions/items/{item_id}", dependencies=[Depends(require_role("admin"))])
async def delete_auction_item(item_id: str, request: Request):
    if not ObjectId.is_valid(item_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid item_id.")
    result = await _items_collection(request).delete_one({"_id": ObjectId(item_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found.")
    return {"ok": True}


@router.get("/admin/auctions", dependencies=[Depends(require_role("admin"))])
async def admin_list_auctions(request: Request):
    auctions = [_map_admin_auction(doc) async for doc in _auctions_collection(request).find({}).sort("updated_at", -1)]
    return auctions


@router.post("/admin/auctions", dependencies=[Depends(require_role("admin"))])
async def admin_create_auction(payload: AdminAuctionCreateIn, request: Request):
    now = _utc_now()
    starts_at = _to_datetime(payload.startAt) or now
    ends_at = _to_datetime(payload.endAt) or (starts_at + timedelta(hours=1))
    selected_item_ids = _parse_item_ids(payload.itemIds)
    await _ensure_items_selectable(_items_collection(request), selected_item_ids)
    auction_id_obj = ObjectId()
    auction_id = str(auction_id_obj)
    backend_status = _status_to_backend(payload.status)

    doc = {
        "_id": auction_id_obj,
        "title": payload.title.strip(),
        "category": (payload.category or "General").strip() or "General",
        "description": payload.description,
        "status": backend_status,
        "starts_at": starts_at,
        "ends_at": ends_at,
        "scheduled_ends_at": ends_at,
        "join_deadline": starts_at + timedelta(minutes=30),
        "selected_item_ids": selected_item_ids,
        "invited_user_ids": [],
        "participants": [],
        "extensions": [],
        "highest_bid": 0,
        "highest_bidder_name": None,
        "highest_bidder_id": None,
        "users_table": [],
        "current_item_index": 0 if selected_item_ids else None,
        "current_item_id": selected_item_ids[0] if selected_item_ids else None,
        "compat_room_status": "RUNNING" if backend_status == "RUNNING" else "IDLE",
        "created_at": now,
        "updated_at": now,
    }

    await _auctions_collection(request).insert_one(doc)

    item_object_ids = [ObjectId(item_id) for item_id in selected_item_ids]
    if item_object_ids:
        await _items_collection(request).update_many(
            {"_id": {"$in": item_object_ids}},
            {
                "$set": {
                    "selected_for_auction": True,
                    "updated_at": now,
                }
            },
        )
        if backend_status == "RUNNING":
            await _items_collection(request).update_many(
                {"_id": {"$in": item_object_ids}},
                {
                    "$set": {
                        "auction_id": auction_id,
                        "active_auction_id": auction_id,
                        "compat_item_status": None,
                        "updated_at": now,
                    }
                },
            )

    created = await _auctions_collection(request).find_one(_auction_id_query(auction_id))
    return _map_admin_auction(created or doc)


@router.patch("/admin/auctions/{auction_id}", dependencies=[Depends(require_role("admin"))])
async def admin_update_auction(auction_id: str, payload: AdminAuctionUpdateIn, request: Request):
    auctions = _auctions_collection(request)
    existing = await auctions.find_one(_auction_id_query(auction_id))
    if not existing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Auction not found.")

    updates: dict[str, Any] = {}
    if payload.title is not None:
        updates["title"] = payload.title.strip() or existing.get("title") or f"Auction {auction_id}"
    if payload.category is not None:
        updates["category"] = payload.category.strip() or "General"
    if payload.description is not None:
        updates["description"] = payload.description
    if payload.startAt is not None:
        starts_at = _to_datetime(payload.startAt)
        if not starts_at:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid startAt.")
        updates["starts_at"] = starts_at
        updates["join_deadline"] = starts_at + timedelta(minutes=30)
    if payload.endAt is not None:
        ends_at = _to_datetime(payload.endAt)
        if not ends_at:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid endAt.")
        updates["ends_at"] = ends_at
        updates["scheduled_ends_at"] = ends_at
    if payload.status is not None:
        backend_status = _status_to_backend(payload.status)
        updates["status"] = backend_status
        updates["compat_room_status"] = "RUNNING" if backend_status == "RUNNING" else backend_status
        if backend_status == "RUNNING":
            starts_at = _utc_now()
            ends_at = starts_at + timedelta(hours=1)
            updates["starts_at"] = starts_at
            updates["ends_at"] = ends_at
            updates["scheduled_ends_at"] = ends_at
            updates["join_deadline"] = starts_at + timedelta(minutes=30)
    if payload.itemIds is not None:
        selected_item_ids = _parse_item_ids(payload.itemIds)
        await _ensure_items_selectable(_items_collection(request), selected_item_ids)
        updates["selected_item_ids"] = selected_item_ids
        updates["current_item_id"] = selected_item_ids[0] if selected_item_ids else None
        updates["current_item_index"] = 0 if selected_item_ids else None

        item_object_ids = [ObjectId(item_id) for item_id in selected_item_ids]
        if item_object_ids:
            await _items_collection(request).update_many(
                {"_id": {"$in": item_object_ids}},
                {
                    "$set": {
                        "selected_for_auction": True,
                        "updated_at": _utc_now(),
                    }
                },
            )

    if updates:
        updates["updated_at"] = _utc_now()
        await auctions.update_one(_auction_id_query(auction_id), {"$set": updates})

    updated = await auctions.find_one(_auction_id_query(auction_id))
    return _map_admin_auction(updated or existing)


@router.patch("/admin/auctions/{auction_id}/status", dependencies=[Depends(require_role("admin"))])
async def admin_update_auction_status(
    auction_id: str,
    payload: AdminAuctionStatusIn,
    request: Request,
    auction_service: AuctionService = Depends(get_auction_service),
):
    auctions = _auctions_collection(request)
    existing = await auctions.find_one(_auction_id_query(auction_id))
    if not existing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Auction not found.")

    backend_status = _status_to_backend(payload.status)
    now = _utc_now()

    if backend_status == "ENDED":
        await auction_service.close_auction_and_distribute(auction_id=auction_id)
        await auctions.update_one(
            _auction_id_query(auction_id),
            {
                "$set": {
                    "status": "ENDED",
                    "compat_room_status": "ENDED",
                    "updated_at": now,
                }
            },
        )
    else:
        starts_at = now if backend_status == "RUNNING" else (_to_datetime(existing.get("starts_at")) or now)
        ends_at = starts_at + timedelta(hours=1) if backend_status == "RUNNING" else (_to_datetime(existing.get("ends_at")) or (starts_at + timedelta(hours=1)))
        updates = {
            "status": backend_status,
            "compat_room_status": "RUNNING" if backend_status == "RUNNING" else backend_status,
            "starts_at": starts_at,
            "ends_at": ends_at,
            "scheduled_ends_at": ends_at,
            "join_deadline": starts_at + timedelta(minutes=30),
            "updated_at": now,
        }
        await auctions.update_one(_auction_id_query(auction_id), {"$set": updates})

        if backend_status == "RUNNING":
            selected_item_ids = _normalize_string_list(existing.get("selected_item_ids", []))
            object_ids = [ObjectId(item_id) for item_id in selected_item_ids if ObjectId.is_valid(item_id)]
            if object_ids:
                await _items_collection(request).update_many(
                    {"_id": {"$in": object_ids}},
                    {
                        "$set": {
                            "auction_id": auction_id,
                            "active_auction_id": auction_id,
                            "selected_for_auction": True,
                            "compat_item_status": None,
                            "updated_at": now,
                        }
                    },
                )

    updated = await auctions.find_one(_auction_id_query(auction_id))
    return _map_admin_auction(updated or existing)


@router.post("/admin/auctions/{auction_id}/start", dependencies=[Depends(require_role("admin"))])
async def admin_start_auction_room(auction_id: str, request: Request):
    auctions = _auctions_collection(request)
    now = _utc_now()
    existing = await auctions.find_one(_auction_id_query(auction_id))
    if not existing:
        starts_at = now
        ends_at = starts_at + timedelta(hours=1)
        await auctions.insert_one(
            {
                "_id": auction_id,
                "title": f"Auction {auction_id}",
                "category": "General",
                "status": "RUNNING",
                "starts_at": starts_at,
                "ends_at": ends_at,
                "scheduled_ends_at": ends_at,
                "join_deadline": starts_at + timedelta(minutes=30),
                "selected_item_ids": [],
                "invited_user_ids": [],
                "participants": [],
                "extensions": [],
                "compat_room_status": "RUNNING",
                "updated_at": now,
                "created_at": now,
            }
        )
    else:
        starts_at = now
        ends_at = starts_at + timedelta(hours=1)
        await auctions.update_one(
            _auction_id_query(auction_id),
            {
                "$set": {
                    "status": "RUNNING",
                    "compat_room_status": "RUNNING",
                    "starts_at": starts_at,
                    "ends_at": ends_at,
                    "scheduled_ends_at": ends_at,
                    "join_deadline": starts_at + timedelta(minutes=30),
                    "updated_at": now,
                }
            },
        )

    updated = await auctions.find_one(_auction_id_query(auction_id))
    selected_item_ids = _normalize_string_list((updated or existing or {}).get("selected_item_ids", []))
    object_ids = [ObjectId(item_id) for item_id in selected_item_ids if ObjectId.is_valid(item_id)]
    if object_ids:
        await _items_collection(request).update_many(
            {"_id": {"$in": object_ids}},
            {
                "$set": {
                    "auction_id": auction_id,
                    "active_auction_id": auction_id,
                    "selected_for_auction": True,
                    "compat_item_status": None,
                    "updated_at": now,
                }
            },
        )
    return _room_state_payload(updated or {"_id": auction_id, "status": "RUNNING", "participants": []})


@router.post("/admin/auctions/{auction_id}/pause", dependencies=[Depends(require_role("admin"))])
async def admin_pause_auction_room(auction_id: str, request: Request):
    auctions = _auctions_collection(request)
    existing = await auctions.find_one(_auction_id_query(auction_id))
    if not existing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Auction not found.")
    await auctions.update_one(
        _auction_id_query(auction_id),
        {"$set": {"compat_room_status": "PAUSED", "updated_at": _utc_now()}},
    )
    updated = await auctions.find_one(_auction_id_query(auction_id))
    return _room_state_payload(updated or existing)


@router.post("/admin/auctions/{auction_id}/resume", dependencies=[Depends(require_role("admin"))])
async def admin_resume_auction_room(auction_id: str, request: Request):
    auctions = _auctions_collection(request)
    existing = await auctions.find_one(_auction_id_query(auction_id))
    if not existing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Auction not found.")
    await auctions.update_one(
        _auction_id_query(auction_id),
        {"$set": {"compat_room_status": "RUNNING", "updated_at": _utc_now()}},
    )
    updated = await auctions.find_one(_auction_id_query(auction_id))
    return _room_state_payload(updated or existing)


@router.post("/admin/auctions/{auction_id}/end", dependencies=[Depends(require_role("admin"))])
async def admin_end_auction_room(
    auction_id: str,
    request: Request,
    auction_service: AuctionService = Depends(get_auction_service),
):
    await auction_service.close_auction_and_distribute(auction_id=auction_id)
    await _auctions_collection(request).update_one(
        _auction_id_query(auction_id),
        {
            "$set": {
                "status": "ENDED",
                "compat_room_status": "ENDED",
                "updated_at": _utc_now(),
            }
        },
        upsert=True,
    )
    updated = await _auctions_collection(request).find_one(_auction_id_query(auction_id))
    return _room_state_payload(updated or {"_id": auction_id, "status": "ENDED", "participants": []})


@router.post("/admin/auctions/{auction_id}/invite", dependencies=[Depends(require_role("admin"))])
async def admin_invite_users(
    auction_id: str,
    payload: AdminInviteIn,
    request: Request,
    current_user=Depends(get_current_user),
):
    auctions = _auctions_collection(request)
    existing = await auctions.find_one(_auction_id_query(auction_id))
    if not existing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Auction not found.")

    user_ids = _normalize_string_list(payload.userIds)
    existing_invites = set(_normalize_string_list(existing.get("invited_user_ids", [])))
    new_invites = [user_id for user_id in user_ids if user_id not in existing_invites]
    await auctions.update_one(
        _auction_id_query(auction_id),
        {
            "$addToSet": {"invited_user_ids": {"$each": user_ids}},
            "$set": {"updated_at": _utc_now()},
        },
    )
    updated = await auctions.find_one(_auction_id_query(auction_id))

    if new_invites:
        start_at, end_at = _auction_start_end(updated or existing)
        items_collection = _items_collection(request)
        selected_ids = _normalize_string_list((updated or existing).get("selected_item_ids", []))
        selected_items = await _load_items_by_ids(items_collection, selected_ids)
        item_titles = [
            str(item.get("name") or item.get("title") or item.get("_id"))
            for item in selected_items
        ]
        items_block = "\n".join([f"- {title}" for title in item_titles]) or "- No items selected yet."

        admin_label = _get_attr(current_user, "name") or _get_attr(current_user, "email") or "Admin"
        admin_email = _get_attr(current_user, "email")
        admin_line = f"{admin_label} ({admin_email})" if admin_email and admin_email != admin_label else admin_label

        subject = f"You are invited to auction {(updated or existing).get('title') or auction_id}"
        body = (
            f"Hello,\n\n"
            f"You have been invited to an auction by {admin_line}.\n\n"
            f"Auction: {(updated or existing).get('title') or f'Auction {auction_id}'}\n"
            f"Start: {start_at.strftime('%Y-%m-%d %I:%M %p %Z')}\n"
            f"End: {end_at.strftime('%Y-%m-%d %I:%M %p %Z')}\n\n"
            f"Items:\n{items_block}\n"
        )

        users_collection = _users_collection(request)
        for user_id in new_invites:
            user_doc = await users_collection.find_one(_user_id_query(user_id), projection={"email": 1, "role": 1})
            if not user_doc:
                continue
            if str(user_doc.get("role") or "").lower() != "rep":
                continue
            settings = await _get_user_settings(user_id=user_id, users_collection=users_collection)
            if not settings.get("enable_email", True):
                continue
            if not settings.get("notify_auction_timeframe", True):
                continue
            to_email = user_doc.get("email")
            if not to_email:
                continue
            await send_notification_email(str(to_email), subject, body)

    return _map_admin_auction(updated or existing)


@router.delete("/admin/auctions/{auction_id}/invite", dependencies=[Depends(require_role("admin"))])
async def admin_revoke_users(auction_id: str, payload: AdminInviteIn, request: Request):
    auctions = _auctions_collection(request)
    existing = await auctions.find_one(_auction_id_query(auction_id))
    if not existing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Auction not found.")

    user_ids = _normalize_string_list(payload.userIds)
    await auctions.update_one(
        _auction_id_query(auction_id),
        {
            "$pull": {"invited_user_ids": {"$in": user_ids}},
            "$set": {"updated_at": _utc_now()},
        },
    )
    updated = await auctions.find_one(_auction_id_query(auction_id))
    return _map_admin_auction(updated or existing)


@router.post("/admin/auctions/{auction_id}/timeframe", dependencies=[Depends(require_role("admin"))])
async def admin_update_timeframe(auction_id: str, payload: AdminAuctionTimeframeIn, request: Request):
    starts_at = _to_datetime(payload.startAt)
    ends_at = _to_datetime(payload.endAt)
    if starts_at is None or ends_at is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid timeframe.")

    auctions = _auctions_collection(request)
    existing = await auctions.find_one(_auction_id_query(auction_id))
    if not existing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Auction not found.")

    await auctions.update_one(
        _auction_id_query(auction_id),
        {
            "$set": {
                "starts_at": starts_at,
                "ends_at": ends_at,
                "scheduled_ends_at": ends_at,
                "join_deadline": starts_at + timedelta(minutes=30),
                "updated_at": _utc_now(),
            }
        },
    )
    updated = await auctions.find_one(_auction_id_query(auction_id))
    return _map_admin_auction(updated or existing)


@router.post("/admin/auctions/{auction_id}/items/{item_id}/activate", dependencies=[Depends(require_role("admin"))])
async def admin_activate_item(auction_id: str, item_id: str, request: Request):
    if not ObjectId.is_valid(item_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid item_id.")

    auctions = _auctions_collection(request)
    items = _items_collection(request)
    auction_doc = await auctions.find_one(_auction_id_query(auction_id))
    if not auction_doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Auction not found.")
    item_doc = await items.find_one({"_id": ObjectId(item_id)})
    if not item_doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found.")
    item_status = str(item_doc.get("status") or "").upper()
    compat_status = str(item_doc.get("compat_item_status") or "").upper()
    if item_status in {"SOLD", "ENDED"} or compat_status == "ENDED" or item_doc.get("winner_user_id"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="SOLD or ENDED items cannot be added to an auction.",
        )

    selected_item_ids = _normalize_string_list(auction_doc.get("selected_item_ids", []))
    if item_id not in selected_item_ids:
        selected_item_ids.append(item_id)
    current_index = selected_item_ids.index(item_id)

    now = _utc_now()
    await auctions.update_one(
        _auction_id_query(auction_id),
        {
            "$set": {
                "selected_item_ids": selected_item_ids,
                "current_item_id": item_id,
                "current_item_index": current_index,
                "updated_at": now,
            }
        },
    )
    await items.update_one(
        {"_id": ObjectId(item_id)},
        {
            "$set": {
                "selected_for_auction": True,
                "active_auction_id": auction_id,
                "compat_item_status": None,
                "updated_at": now,
            }
        },
    )

    updated = await auctions.find_one(_auction_id_query(auction_id))
    return _map_admin_auction(updated or auction_doc)


@router.post("/admin/auctions/{auction_id}/items/{item_id}/end", dependencies=[Depends(require_role("admin"))])
async def admin_end_item(auction_id: str, item_id: str, request: Request):
    if not ObjectId.is_valid(item_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid item_id.")

    auctions = _auctions_collection(request)
    items = _items_collection(request)
    auction_doc = await auctions.find_one(_auction_id_query(auction_id))
    if not auction_doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Auction not found.")
    item_doc = await items.find_one({"_id": ObjectId(item_id)})
    if not item_doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found.")

    now = _utc_now()
    winner_user_id = item_doc.get("winner_user_id") or item_doc.get("highest_bidder_id")
    item_updates: dict[str, Any] = {
        "active_auction_id": None,
        "selected_for_auction": False,
        "updated_at": now,
    }
    if winner_user_id:
        item_updates["winner_user_id"] = str(winner_user_id)
        item_updates["status"] = "SOLD"
        item_updates["compat_item_status"] = None
    else:
        item_updates["compat_item_status"] = "ENDED"

    await items.update_one({"_id": ObjectId(item_id)}, {"$set": item_updates})

    selected_item_ids = _normalize_string_list(auction_doc.get("selected_item_ids", []))
    current_item_id = str(auction_doc.get("current_item_id")) if auction_doc.get("current_item_id") else None
    if current_item_id == item_id:
        next_item_id = None
        for candidate in selected_item_ids:
            if candidate != item_id:
                next_item_id = candidate
                break
        next_index = selected_item_ids.index(next_item_id) if next_item_id else None
        await auctions.update_one(
            _auction_id_query(auction_id),
            {
                "$set": {
                    "current_item_id": next_item_id,
                    "current_item_index": next_index,
                    "updated_at": now,
                }
            },
        )

    updated = await auctions.find_one(_auction_id_query(auction_id))
    return _map_admin_auction(updated or auction_doc)


@router.post("/admin/auctions/{auction_id}/bidding-increment", dependencies=[Depends(require_role("admin"))])
async def admin_update_increment(auction_id: str, payload: AdminIncrementIn, request: Request):
    if not ObjectId.is_valid(payload.itemId):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid itemId.")

    auctions = _auctions_collection(request)
    auction_doc = await auctions.find_one(_auction_id_query(auction_id))
    if not auction_doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Auction not found.")

    item_doc = await _items_collection(request).find_one({"_id": ObjectId(payload.itemId)})
    if not item_doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found.")

    await _items_collection(request).update_one(
        {"_id": item_doc["_id"]},
        {
            "$set": {
                "increment": int(payload.increment),
                "updated_at": _utc_now(),
            }
        },
    )

    updated = await auctions.find_one(_auction_id_query(auction_id))
    return _map_admin_auction(updated or auction_doc)


@router.post("/admin/auctions/{auction_id}/notifications", dependencies=[Depends(require_role("admin"))])
async def admin_send_custom_notification(
    auction_id: str,
    payload: AdminCustomNotificationIn,
    request: Request,
    bids_service: BidsService = Depends(get_bids_service),
):
    auctions = _auctions_collection(request)
    auction_doc = await auctions.find_one(_auction_id_query(auction_id))
    if not auction_doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Auction not found.")

    message = payload.message.strip()
    if not message:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Message cannot be blank.")

    item_id = payload.itemId.strip() if payload.itemId else None
    if item_id and not ObjectId.is_valid(item_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid itemId.")

    if payload.audience == "ADMINS":
        delivered = await bids_service.NotifyAdmin(auction_doc=auction_doc, message=message, item_id=item_id)
    elif payload.audience == "REPS":
        delivered = await bids_service.NotifyReps(auction_doc=auction_doc, message=message, item_id=item_id)
    else:
        delivered = await bids_service.NotifyAll(auction_doc=auction_doc, message=message, item_id=item_id)

    await auctions.update_one(
        {"_id": auction_doc["_id"]},
        {"$set": {"updated_at": _utc_now()}},
    )

    return {
        "ok": True,
        "auctionId": str(auction_doc.get("_id")),
        "audience": payload.audience,
        "itemId": item_id,
        "message": message,
        "deliveredCount": int(delivered),
    }


@router.get("/auctions")
async def list_public_auctions(request: Request, current_user=Depends(get_current_user)):
    _ = current_user
    items_collection = _items_collection(request)
    auctions = [doc async for doc in _auctions_collection(request).find({}).sort("updated_at", -1)]
    return [await _map_public_auction(doc, items_collection) for doc in auctions]


@router.get("/auctions/{auction_id}")
async def get_public_auction(auction_id: str, request: Request, current_user=Depends(get_current_user)):
    auctions = _auctions_collection(request)
    auction_doc = await auctions.find_one(_auction_id_query(auction_id))
    if not auction_doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Auction not found.")

    role = _extract_user_role(current_user)
    user_id = _extract_user_id(current_user)
    if role == "rep" and str(auction_doc.get("status") or "").upper() == "RUNNING":
        invited_ids = set(_normalize_string_list(auction_doc.get("invited_user_ids", [])))
        participant_ids = set(_normalize_string_list(auction_doc.get("participants", [])))
        join_deadline = _to_datetime(auction_doc.get("join_deadline"))
        if user_id in invited_ids and user_id not in participant_ids and (join_deadline is None or _utc_now() <= join_deadline):
            await auctions.update_one(
                _auction_id_query(auction_id),
                {
                    "$addToSet": {"participants": user_id},
                    "$set": {"updated_at": _utc_now()},
                },
            )
            auction_doc = await auctions.find_one(_auction_id_query(auction_id)) or auction_doc

    return await _map_public_auction(auction_doc, _items_collection(request))


@router.post("/auctions/{auction_id}/bid", dependencies=[Depends(require_role("rep"))])
async def place_public_bid(
    auction_id: str,
    payload: AuctionBidIn,
    current_user=Depends(get_current_user),
    bids_service: BidsService = Depends(get_bids_service),
):
    result = await bids_service.place_bid(
        current_user=current_user,
        auction_id=auction_id,
        item_id=payload.item_id,
    )

    bid_time = _to_iso(result.get("bid_time")) or _utc_now().isoformat()
    return {
        "success": bool(result.get("success", True)),
        "itemId": payload.item_id,
        "bidderId": _extract_user_id(current_user),
        "bidAmount": _to_non_negative_int(result.get("bid_amount", 0)),
        "timestamp": bid_time,
    }


@router.get("/auctions/{auction_id}/bid-history")
async def get_public_bid_history(
    auction_id: str,
    request: Request,
    item_id: Optional[str] = Query(default=None),
    current_user=Depends(get_current_user),
):
    _ = current_user
    filters: dict[str, Any] = {"auction_id": auction_id}
    if item_id:
        filters["item_id"] = item_id

    bids_cursor = _bids_collection(request).find(filters).sort("timestamp", -1)
    users = _users_collection(request)
    items = _items_collection(request)

    user_cache: dict[str, Optional[dict[str, Any]]] = {}
    item_cache: dict[str, Optional[dict[str, Any]]] = {}
    history: list[dict[str, Any]] = []

    async for bid_doc in bids_cursor:
        bidder_id = str(bid_doc.get("bidder_id") or "")
        bid_item_id = str(bid_doc.get("item_id") or "")

        if bidder_id not in user_cache:
            user_cache[bidder_id] = await _find_user_doc_by_id(users, bidder_id)
        if bid_item_id and bid_item_id not in item_cache:
            if ObjectId.is_valid(bid_item_id):
                item_cache[bid_item_id] = await items.find_one({"_id": ObjectId(bid_item_id)})
            else:
                item_cache[bid_item_id] = None

        bidder_doc = user_cache.get(bidder_id)
        item_doc = item_cache.get(bid_item_id)

        history.append(
            {
                "id": str(bid_doc.get("_id")),
                "auctionId": auction_id,
                "itemId": bid_item_id,
                "itemTitle": (item_doc or {}).get("name") if item_doc else bid_item_id,
                "bidderId": bidder_id,
                "bidderName": (bidder_doc or {}).get("name") or (bidder_doc or {}).get("email") or bidder_id,
                "bidAmount": _to_non_negative_int(bid_doc.get("amount", 0)),
                "createdAt": _to_iso(bid_doc.get("timestamp") or bid_doc.get("created_at")) or _utc_now().isoformat(),
            }
        )

    return history
