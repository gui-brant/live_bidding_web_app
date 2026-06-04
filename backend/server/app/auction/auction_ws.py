from __future__ import annotations

import asyncio
import os
from typing import Any

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect, status
from fastapi.encoders import jsonable_encoder
from bson import ObjectId

from app.auction.auction_service import AuctionService
from app.auth.auth_deps import get_current_user_from_websocket
from app.helper.timezone import now_in_app_timezone

router = APIRouter(prefix="/ws/auctions", tags=["auction-ws"])

# WS Event Contract:
# - auction.connected: {type, auction_id, user_id, server_time}
# - auction.started: {type, auction_id, state, server_time}
# - auction.ended: {type, auction_id, result, state, server_time}
# - auction.state_updated: {type, auction_id, state, server_time}
# - auction.timer_extended: {type, auction_id, reason, extension, state, server_time}
# - auction.invites_updated: {type, auction_id, action, invited_user_ids, server_time}
# - auction.participant_joined: {type, auction_id, user_id, reconnected, server_time}
# - auction.message: {type, auction_id, user_id, item_id?, message, server_time}
#   message.type may be OUTBID, WON, INACTIVITY_REMINDER, BID_LOCKED, GIFT_CARD_ACTION_REQUIRED, or GIFT_CARD_WON.
# - auction.chat_message: {type, auction_id, message, server_time}
# - bid.placed: {type, auction_id, item_id, bid_amount, server_time}
# - auction.snapshot: {type, auction_id, state, my_messages, chat_messages, server_time}
EVENT_AUCTION_CONNECTED = "auction.connected"
EVENT_AUCTION_STARTED = "auction.started"
EVENT_AUCTION_ENDED = "auction.ended"
EVENT_AUCTION_STATE_UPDATED = "auction.state_updated"
EVENT_AUCTION_TIMER_EXTENDED = "auction.timer_extended"
EVENT_AUCTION_INVITES_UPDATED = "auction.invites_updated"
EVENT_AUCTION_PARTICIPANT_JOINED = "auction.participant_joined"
EVENT_AUCTION_CHAT_MESSAGE = "auction.chat_message"
EVENT_BID_PLACED = "bid.placed"
EVENT_AUCTION_SNAPSHOT = "auction.snapshot"


def _utc_now_iso() -> str:
    # Keep one consistent server-side timestamp format for WS payloads.
    return now_in_app_timezone().isoformat()


def _extract_user_id(user: object) -> str:
    # Support dict/object user shapes returned by auth dependency.
    if isinstance(user, dict):
        value = user.get("id") or user.get("_id") or user.get("user_id")
    else:
        value = getattr(user, "id", None) or getattr(user, "_id", None) or getattr(user, "user_id", None)
    if value is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authenticated user.")
    return str(value)


def _extract_user_role(user: object) -> str:
    if isinstance(user, dict):
        value = user.get("role")
    else:
        value = getattr(user, "role", None)
    if value is None:
        return "rep"
    return str(value).lower()


def ws_event(event_type: str, *, auction_id: str, **payload: Any) -> dict[str, Any]:
    # Shared event envelope so backend emits one stable shape.
    return {"type": event_type, "auction_id": auction_id, "server_time": _utc_now_iso(), **payload}


class AuctionWsManager:
    # Keeps websocket clients grouped by auction_id.
    def __init__(self) -> None:
        self._rooms: dict[str, set[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, *, auction_id: str, websocket: WebSocket) -> None:
        # Accept first, then register into the room for this auction id.
        await websocket.accept()
        async with self._lock:
            self._rooms.setdefault(auction_id, set()).add(websocket)

    async def disconnect(self, *, auction_id: str, websocket: WebSocket) -> None:
        # Remove socket from room and clean empty rooms.
        async with self._lock:
            room = self._rooms.get(auction_id)
            if not room:
                return
            room.discard(websocket)
            if not room:
                self._rooms.pop(auction_id, None)

    async def broadcast(self, *, auction_id: str, payload: dict[str, Any]) -> None:
        # Fan-out one payload to all sockets in that auction room.
        async with self._lock:
            room = list(self._rooms.get(auction_id, set()))
        if not room:
            return
        safe_payload = jsonable_encoder(payload)

        stale: list[WebSocket] = []
        for socket in room:
            try:
                await socket.send_json(safe_payload)
            except Exception:
                stale.append(socket)

        for socket in stale:
            await self.disconnect(auction_id=auction_id, websocket=socket)


auction_ws_manager = AuctionWsManager()


def _auction_collection(websocket: WebSocket):
    # Resolve auctions collection from app state so this module stays dependency-light.
    db = getattr(websocket.app.state, "mongo_db", None)
    if db is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="MongoDB is not configured.")
    return db[os.getenv("AUCTIONS_COLLECTION_NAME", "auctions")]


async def _find_auction_doc(websocket: WebSocket, auction_id: str) -> dict[str, Any] | None:
    auctions = _auction_collection(websocket)
    normalized = str(auction_id).strip()
    if ObjectId.is_valid(normalized):
        doc = await auctions.find_one({"_id": ObjectId(normalized)})
        if doc:
            return doc
    return await auctions.find_one({"_id": normalized})


def _items_collection(websocket: WebSocket):
    db = getattr(websocket.app.state, "mongo_db", None)
    if db is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="MongoDB is not configured.")
    return db[os.getenv("ITEMS_COLLECTION_NAME", "items")]


def _users_collection(websocket: WebSocket):
    db = getattr(websocket.app.state, "mongo_db", None)
    if db is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="MongoDB is not configured.")
    return db[os.getenv("USERS_COLLECTION_NAME", "users")]


def _bids_collection(websocket: WebSocket):
    db = getattr(websocket.app.state, "mongo_db", None)
    if db is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="MongoDB is not configured.")
    return db[os.getenv("BIDS_COLLECTION_NAME", "bids")]


def _messages_collection(websocket: WebSocket):
    db = getattr(websocket.app.state, "mongo_db", None)
    if db is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="MongoDB is not configured.")
    return db[os.getenv("AUCTION_MESSAGES_COLLECTION_NAME", "auction_messages")]


def _chat_messages_collection(websocket: WebSocket):
    db = getattr(websocket.app.state, "mongo_db", None)
    if db is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="MongoDB is not configured.")
    return db[os.getenv("AUCTION_CHAT_MESSAGES_COLLECTION_NAME", "auction_chat_messages")]


def _auction_service(websocket: WebSocket) -> AuctionService:
    # Build a lightweight service instance from collections already stored on app state.
    return AuctionService(
        auction_collection=_auction_collection(websocket),
        items_collection=_items_collection(websocket),
        users_collection=_users_collection(websocket),
        bids_collection=_bids_collection(websocket),
        messages_collection=_messages_collection(websocket),
        chat_messages_collection=_chat_messages_collection(websocket),
    )


async def _check_ws_access(*, websocket: WebSocket, auction_id: str, user_id: str, user_role: str) -> tuple[bool, str]:
    # Reuse same business guard as HTTP flows: running auction + invited + joined.
    auction_doc = await _find_auction_doc(websocket, auction_id)
    if not auction_doc:
        return False, "Auction not found."

    if user_role == "admin":
        return True, ""

    if auction_doc.get("status") != "RUNNING":
        return False, "Auction is not running."

    invited_ids = {str(value) for value in auction_doc.get("invited_user_ids", [])}
    if user_id not in invited_ids:
        return False, "User is not invited to this auction."

    participant_ids = {str(value) for value in auction_doc.get("participants", [])}
    if user_id not in participant_ids:
        # Invitation alone is not enough; user must join first via HTTP endpoint.
        return False, "User must join auction before opening live channel."

    return True, ""


async def _build_initial_snapshot(
    *,
    websocket: WebSocket,
    auction_id: str,
    user_id: str,
    user_role: str,
) -> dict[str, Any]:
    # Missed personal notifications, including INACTIVITY_REMINDER/BID_LOCKED, are replayed from my_messages.
    service = _auction_service(websocket)
    state = await service.get_auction_state(auction_id=auction_id)
    messages_out = await service.list_messages_for_user(auction_id=auction_id, user_id=user_id, limit=20)
    chat_messages_out = await service.list_chat_messages(
        auction_id=auction_id,
        user_id=user_id,
        user_role=user_role,
        limit=50,
    )
    return jsonable_encoder(
        {
            # Convert the Pydantic model now so websocket payloads stay JSON-safe.
            "state": state.model_dump(mode="python", exclude_none=True),
            "my_messages": messages_out.get("messages", []),
            "chat_messages": chat_messages_out.get("chat_messages", []),
        }
    )


@router.websocket("/{auction_id}")
async def auction_live_socket(websocket: WebSocket, auction_id: str):
    # Step 1: authenticate socket using JWT from header/query/cookie.
    try:
        user = await get_current_user_from_websocket(websocket)
        user_id = _extract_user_id(user)
        user_role = _extract_user_role(user)
    except HTTPException as exc:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason=exc.detail)
        return

    allowed, reason = await _check_ws_access(
        websocket=websocket,
        auction_id=auction_id,
        user_id=user_id,
        user_role=user_role,
    )
    if not allowed:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason=reason)
        return

    # Step 2: attach to room and keep lightweight ping/pong alive.
    await auction_ws_manager.connect(auction_id=auction_id, websocket=websocket)
    try:
        await websocket.send_json(ws_event(EVENT_AUCTION_CONNECTED, auction_id=auction_id, user_id=user_id))
        snapshot = await _build_initial_snapshot(
            websocket=websocket,
            auction_id=auction_id,
            user_id=user_id,
            user_role=user_role,
        )
        await websocket.send_json(
            ws_event(
                EVENT_AUCTION_SNAPSHOT,
                auction_id=auction_id,
                state=snapshot["state"],
                my_messages=snapshot["my_messages"],
                chat_messages=snapshot["chat_messages"],
            )
        )
        while True:
            try:
                incoming = await websocket.receive_json()
            except ValueError:
                # Ignore non-JSON frames to keep connection alive.
                continue
            if not isinstance(incoming, dict):
                continue
            incoming_type = str(incoming.get("type", "")).lower()
            if incoming_type == "ping":
                # Minimal heartbeat so clients can detect a live socket.
                await websocket.send_json({"type": "pong", "server_time": _utc_now_iso()})
            elif incoming_type in {"sync.request", "auction.sync.request"}:
                # Let clients force a fresh state + message snapshot after reconnect/drift.
                snapshot = await _build_initial_snapshot(
                    websocket=websocket,
                    auction_id=auction_id,
                    user_id=user_id,
                    user_role=user_role,
                )
                await websocket.send_json(
                    ws_event(
                        EVENT_AUCTION_SNAPSHOT,
                        auction_id=auction_id,
                        state=snapshot["state"],
                        my_messages=snapshot["my_messages"],
                        chat_messages=snapshot["chat_messages"],
                    )
                )
    except WebSocketDisconnect:
        # Normal close path from client side.
        pass
    finally:
        # Always detach connection so stale sockets do not leak in room state.
        await auction_ws_manager.disconnect(auction_id=auction_id, websocket=websocket)
