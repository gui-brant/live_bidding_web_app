from datetime import datetime, timedelta
from typing import Any, Awaitable, Callable, Dict, Optional
from fastapi import HTTPException, status
from bson import ObjectId
import asyncio
import random
import re
from app.helper.timezone import ensure_app_datetime, now_in_app_timezone

# default user settings for the settings feature
_DEFAULT_SETTINGS = {
    "enable_email": True,
    "enable_in_app": True,
    "enable_sms": False,
    "notify_outbid": True,
    "notify_auction_timeframe": True,
    "notify_auction_win": True,
}

async def _get_user_settings(user_id: str, users_collection, session=None) -> Dict[str, Any]:
    if not user_id:
        return {**_DEFAULT_SETTINGS}
    query = {"$expr": {"$eq": [{"$toString": "$_id"}, str(user_id)]}}
    doc = await users_collection.find_one(query, session=session)
    if not doc:
        return {**_DEFAULT_SETTINGS}

    raw_settings = {**(doc.get("notification_prefs") or {}), **(doc.get("settings") or {})}
    normalized: Dict[str, Any] = {}

    if "enable_in_app" in raw_settings:
        normalized["enable_in_app"] = bool(raw_settings.get("enable_in_app"))
    elif "in_app_enabled" in raw_settings:
        normalized["enable_in_app"] = bool(raw_settings.get("in_app_enabled"))

    if "enable_email" in raw_settings:
        normalized["enable_email"] = bool(raw_settings.get("enable_email"))
    elif "email_enabled" in raw_settings:
        normalized["enable_email"] = bool(raw_settings.get("email_enabled"))

    if "enable_sms" in raw_settings:
        normalized["enable_sms"] = bool(raw_settings.get("enable_sms"))
    elif "sms_enabled" in raw_settings:
        normalized["enable_sms"] = bool(raw_settings.get("sms_enabled"))

    for key in ("notify_outbid", "notify_auction_timeframe", "notify_auction_win"):
        if key in raw_settings and raw_settings.get(key) is not None:
            normalized[key] = bool(raw_settings.get(key))

    return {**_DEFAULT_SETTINGS, **normalized}
    

def _utc_now() -> datetime:
    """Backward-compatible name. Returns current app timezone timestamp."""
    return now_in_app_timezone()


def _as_str_id(value: Any) -> str:
    """Normalize any id-like value to string."""
    return str(value)


def _candidate_id_values(value: str) -> list[str]:
    """Return normalized user-id candidates as strings only."""
    if not isinstance(value, str) or not value.strip():
        return []
    return [value.strip()]


def _user_ids_query(user_ids: list[str]) -> Dict[str, Any]:
    normalized = [value for value in {str(user_id).strip() for user_id in user_ids} if value] #check if the user_ids list is empty or contains only empty/whitespace strings after normalization.
    #if there are no valid user ids in the list, then return a Mongo query indicating that zero document ids were matched. 
    if not normalized:
        return {"_id": {"$exists": False}} 
    #If there are valid user ids, then return a Mongo query whose key 
    return {"$expr": {"$in": [{"$toString": "$_id"}, normalized]}}
    # Check if string ids are in the normalized list


def _compute_user_metrics(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Compute kogbucks metrics used by participant and dashboard endpoints."""
    balance_amount = int(doc.get("balance_amount", 0))
    before_bid_amount = int(doc.get("before_bid_amount", 0))
    if "balance_amount" in doc or "before_bid_amount" in doc:
        total = balance_amount + before_bid_amount
    else:
        total = int(doc.get("kogbucks", 0))
    committed = bool(doc.get("balance_committed", False))
    held = before_bid_amount if committed else 0
    bidding_power = max(0, total - held)
    return {
        "user_id": str(doc["_id"]),
        "name": doc.get("name") or doc.get("email"),
        "kogbucks_total": total,
        "kogbucks_held": held,
        "bidding_power": bidding_power,
    }


async def _insert_user_message(
    messages_collection,
    *,
    auction_id: str,
    user_id: str,
    item_id: Optional[str],
    msg_type: str,
    message: str,
) -> None:
    await messages_collection.insert_one(
        {
            "auction_id": auction_id,
            "user_id": user_id,
            "item_id": item_id,
            "scope": "USER",
            "audience": "USER",
            "type": msg_type,
            "message": message,
            "created_at": _utc_now(),
        }
    )

def _is_transient_transaction_error(exc: BaseException) -> bool:
    """
    Mongo uses labels to indicate retryable transaction errors.
    Motor exceptions generally expose .has_error_label().
    """
    has_label = getattr(exc, "has_error_label", None)
    if callable(has_label):
        return bool(
            exc.has_error_label("TransientTransactionError")
            or exc.has_error_label("UnknownTransactionCommitResult")
        )
    # Fallback: be conservative
    return False


def _get_motor_client_from_collection(collection) -> Any:
    """
    Motor collection -> database -> client
    Works for AsyncIOMotorCollection.
    """
    return collection.database.client

NotificationCall = Callable[[], Awaitable[None]]

def _parse_object_id(value: str, *, field_name: str) -> ObjectId:
    if not ObjectId.is_valid(value):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid {field_name}.")
    return ObjectId(value)

def _extract_user_id(current_user: object) -> str:
    if isinstance(current_user, dict):
        value = current_user.get("id") or current_user.get("_id") or current_user.get("user_id")
    else:
        value = getattr(current_user, "id", None) or getattr(current_user, "_id", None) or getattr(current_user, "user_id", None)
    if value is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authenticated user.")
    return _as_str_id(value)

def _user_id_query(user_id: str) -> Dict[str, Any]:
    candidates = _candidate_id_values(user_id)
    if not candidates:
        return {"_id": None}
    normalized = candidates[0]
    return {"$expr": {"$eq": [{"$toString": "$_id"}, normalized]}}


def _normalize_user_id_text(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    # Tolerate stringified wrappers like ObjectId("...") from legacy paths.
    match = re.fullmatch(r"ObjectId\((['\"])([0-9a-fA-F]{24})\1\)", text)
    if match:
        return match.group(2)
    return text
