from __future__ import annotations

import asyncio
import random

from datetime import timedelta, datetime
from typing import Any, Awaitable, Callable, Dict, Optional, TypeVar

from bson import ObjectId
from fastapi import Depends, HTTPException, status
from app.helper.helpers import (
    _is_transient_transaction_error,
    _utc_now,
    _user_id_query,
    _compute_user_metrics,
    _user_ids_query,
    _get_user_settings,
)
from app.helper.timezone import ensure_app_datetime
from app.helper.emailer import send_notification_email
from app.auction.auction_schemas import AuctionStateOut
from app.auction.ws_outbox import enqueue_ws_event, enqueue_ws_events

T = TypeVar("T")
INACTIVITY_REMINDER_INTERVAL_SECONDS = 150
AUCTION_MESSAGE_TYPE_INACTIVITY_REMINDER = "INACTIVITY_REMINDER"
AUCTION_MESSAGE_TYPE_BID_LOCKED = "BID_LOCKED"
AUCTION_MESSAGE_TYPE_GIFT_CARD_ACTION_REQUIRED = "GIFT_CARD_ACTION_REQUIRED"
AUCTION_MESSAGE_TYPE_GIFT_CARD_WON = "GIFT_CARD_WON"


async def _run_txn_with_retries(
    client,
    txn_coro_factory: Callable[[Any], Awaitable[T]],
    *,
    max_retries: int = 5,
    base_backoff: float = 0.05,
    max_backoff: float = 0.8,
) -> T:
    last_exc: Optional[BaseException] = None
    for attempt in range(max_retries):
        try:
            async with await client.start_session() as session:
                async with session.start_transaction():
                    return await txn_coro_factory(session)
        except Exception as exc:
            last_exc = exc
            if not _is_transient_transaction_error(exc):
                raise
            backoff = min(max_backoff, base_backoff * (2**attempt))
            backoff *= 0.5 + random.random()
            await asyncio.sleep(backoff)
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Auction update could not be committed due to contention. Please retry.",
    ) from last_exc


class AuctionService:
    """Service layer for auction state, participants, timer, and post-auction summaries."""

    def __init__(
        self,
        *,
        auction_collection,
        items_collection,
        users_collection,
        bids_collection,
        messages_collection,
        ws_outbox_collection=None,
        chat_messages_collection=None,
    ) -> None:
        self._auction = auction_collection
        self._items = items_collection
        self._users = users_collection
        self._bids = bids_collection
        self._messages = messages_collection
        self._ws_outbox = ws_outbox_collection
        self._chat_messages = chat_messages_collection

    def _state_out(self, doc: Dict[str, Any]) -> AuctionStateOut:
        return AuctionStateOut.model_validate(doc)

    def _auction_id_query(self, auction_id: str) -> Dict[str, Any]:
        normalized = str(auction_id).strip()
        if ObjectId.is_valid(normalized):
            return {"_id": {"$in": [normalized, ObjectId(normalized)]}}
        return {"_id": normalized}

    def _auction_insert_id(self, auction_id: str) -> Any:
        normalized = str(auction_id).strip()
        if ObjectId.is_valid(normalized):
            return ObjectId(normalized)
        return normalized

    async def _find_auction_doc(self, auction_id: str, *, session=None) -> Optional[Dict[str, Any]]:
        normalized = str(auction_id).strip()
        if ObjectId.is_valid(normalized):
            doc = await self._auction.find_one({"_id": ObjectId(normalized)}, session=session)
            if doc:
                return doc
        return await self._auction.find_one({"_id": normalized}, session=session)

    def _chat_collection(self):#Helper method to access the chat messages collection, 
        #raises an HTTP 500 error if the collection is not configured, ensuring that the rest of the auction service can safely assume its existence when handling chat-related functionality.
        if self._chat_messages is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Auction chat collection is not configured.",
            )
        return self._chat_messages

    def _read_user_role(self, user: object) -> str:
        if isinstance(user, dict):
            value = user.get("role") or user.get("type")
        else:
            value = getattr(user, "role", None) or getattr(user, "type", None)
        if value is None:
            return "rep"
        return str(value).lower()

    def _read_user_name(self, user_doc: Dict[str, Any]) -> str:
        return str(user_doc.get("name") or user_doc.get("email") or user_doc.get("_id"))

    async def _admin_user_ids(self, *, session=None) -> list[str]:
        admin_ids: list[str] = []
        async for doc in self._users.find({"role": "admin"}, {"_id": 1}, session=session):
            admin_ids.append(str(doc["_id"]))
        return admin_ids

    def _build_personal_message_event(
        self,
        *,
        auction_id: str,
        user_id: str,
        message_type: str,
        content: str,
        item_id: Optional[str] = None,
        **extra_message_fields: Any,
    ) -> Dict[str, Any]:
        from app.auction.auction_ws import ws_event

        message_payload: Dict[str, Any] = {
            "type": message_type,
            "content": content,
            **extra_message_fields,
        }
        return ws_event(
            "auction.message",
            auction_id=auction_id,
            user_id=user_id,
            item_id=item_id,
            message=message_payload,
        )

    async def _queue_user_notification_once(
        self,
        *,
        auction_id: str,
        user_id: str,
        message_type: str,
        content: str,
        dedupe_fields: Optional[Dict[str, Any]] = None,
        item_id: Optional[str] = None,
        extra_doc_fields: Optional[Dict[str, Any]] = None,
        extra_ws_fields: Optional[Dict[str, Any]] = None,
        require_running_auction: bool = False,
        skip_if_user_has_bid: bool = False,
        allow_duplicates: bool = False,
    ) -> bool:
        client = self._messages.database.client
        dedupe_query = {
            "auction_id": auction_id,
            "user_id": user_id,
            "type": message_type,
            **(dedupe_fields or {}),
        }

        async def _txn_body(session) -> bool:
            settings = await _get_user_settings(user_id=user_id, users_collection=self._users, session=session)
            if not settings.get("enable_in_app", True):
                return False
            if message_type == "OUTBID" and not settings.get("notify_outbid", True):
                return False
            if message_type == "WON" and not settings.get("notify_auction_win", True):
                return False
            if message_type in {AUCTION_MESSAGE_TYPE_INACTIVITY_REMINDER, AUCTION_MESSAGE_TYPE_BID_LOCKED}:
                if not settings.get("notify_auction_timeframe", True):
                    return False

            if require_running_auction:
                current_auction = await self._find_auction_doc(auction_id, session=session)
                if not current_auction or current_auction.get("status") != "RUNNING":
                    return False

            if skip_if_user_has_bid:
                current_user = await self._users.find_one(
                    _user_id_query(user_id),
                    projection={"_id": 1, "bid_counter": 1, "has_bid": 1},
                    session=session,
                )
                if not current_user:
                    return False
                current_bid_counter = int(current_user.get("bid_counter", 0) or 0)
                current_has_bid = bool(current_user.get("has_bid", False)) or current_bid_counter > 0
                if current_has_bid:
                    return False

            if not allow_duplicates:
                existing = await self._messages.find_one(dedupe_query, projection={"_id": 1}, session=session)
                if existing:
                    return False

            now = _utc_now()
            doc = {
                "auction_id": auction_id,
                "user_id": user_id,
                "item_id": item_id,
                "scope": "USER",
                "audience": "USER",
                "type": message_type,
                "message": content,
                "created_at": now,
                **(extra_doc_fields or {}),
            }
            await self._messages.insert_one(doc, session=session)

            if self._ws_outbox is not None:
                await self.queue_ws_event(
                    auction_id=auction_id,
                    event=self._build_personal_message_event(
                        auction_id=auction_id,
                        user_id=user_id,
                        message_type=message_type,
                        content=content,
                        item_id=item_id,
                        **(extra_ws_fields or {}),
                    ),
                    session=session,
                )
            return True

        inserted = await _run_txn_with_retries(client, _txn_body)
        if inserted:
            await self._send_email_notification(
                user_id=user_id,
                message_type=message_type,
                content=content,
                item_id=item_id,
            )
        return inserted

    async def _send_email_notification(
        self,
        *,
        user_id: str,
        message_type: str,
        content: str,
        item_id: Optional[str] = None,
    ) -> None:
        settings = await _get_user_settings(user_id=user_id, users_collection=self._users)
        if not settings.get("enable_email", True):
            return
        if message_type == "OUTBID" and not settings.get("notify_outbid", True):
            return
        if message_type == "WON" and not settings.get("notify_auction_win", True):
            return
        if message_type in {AUCTION_MESSAGE_TYPE_INACTIVITY_REMINDER, AUCTION_MESSAGE_TYPE_BID_LOCKED}:
            if not settings.get("notify_auction_timeframe", True):
                return

        user_doc = await self._users.find_one(_user_id_query(user_id), projection={"email": 1, "name": 1})
        if not user_doc:
            return
        to_email = user_doc.get("email")
        if not to_email:
            return
        subject = f"Auction notification: {message_type}"
        await send_notification_email(str(to_email), subject, content)

    def _serialize_chat_message(self, doc: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "id": str(doc["_id"]),
            "sender_user_id": str(doc.get("sender_user_id")),
            "sender_name": str(doc.get("sender_name") or doc.get("sender_user_id") or ""),
            "sender_role": str(doc.get("sender_role") or "rep"),
            "content": str(doc.get("content") or ""),
            "created_at": doc.get("created_at"),
        }

    def _ensure_chat_participant_access(self, *, auction_doc: Dict[str, Any], user_id: str) -> None:# we probably have this function already
        invited_ids = {str(value) for value in auction_doc.get("invited_user_ids", [])}
        if user_id not in invited_ids:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You are not invited to this auction.")

        participant_ids = {str(value) for value in auction_doc.get("participants", [])}
        if user_id not in participant_ids:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You must join the auction before using auction chat.",
            )

    def _ensure_chat_running(self, *, auction_doc: Dict[str, Any]) -> None:
        if auction_doc.get("status") != "RUNNING":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Auction chat is only available while the auction is running.",
            )

    async def queue_ws_event(self, *, auction_id: str, event: dict[str, Any], session=None) -> None:
        if self._ws_outbox is None:
            return
        await enqueue_ws_event(self._ws_outbox, auction_id=auction_id, event=event, session=session)

    async def queue_ws_events(self, *, auction_id: str, events: list[dict[str, Any]], session=None) -> None:
        if self._ws_outbox is None:
            return
        await enqueue_ws_events(self._ws_outbox, auction_id=auction_id, events=events, session=session)

    async def start_auction(self, *, auction_id: str = "current") -> AuctionStateOut:
        auction_id = str(auction_id).strip()
        if not auction_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid auction_id.")

        client = self._auction.database.client

        async def _txn_body(session) -> AuctionStateOut:
            running = await self._auction.find_one({"status": "RUNNING"}, session=session)
            if running and running.get("status") == "RUNNING":
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Auction is already running.")

            auction_doc = await self._find_auction_doc(auction_id, session=session)
            if not auction_doc:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Auction not found.")

            auction_db_id = auction_doc["_id"]
            normalized_auction_id = str(auction_db_id)

            selected_docs = await self._items.find(
                {
                    "status": "AVAILABLE",
                    "$and": [
                        {
                            "$or": [
                                {"auction_id": normalized_auction_id},
                                {
                                    "$and": [
                                        {"selected_for_auction": True},
                                        {"$or": [{"auction_id": None}, {"auction_id": {"$exists": False}}]},
                                    ]
                                },
                            ]
                        },
                        {
                            "$or": [
                                {"active_auction_id": None},
                                {"active_auction_id": {"$exists": False}},
                            ]
                        },
                    ],
                },
                session=session,
            ).to_list(length=None)

            selected_object_ids = [doc["_id"] for doc in selected_docs]
            selected = [str(item_id) for item_id in selected_object_ids]
            if not selected:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="No selected items available for this auction.",
                )

            now = _utc_now()
            starts_at = now
            join_deadline = starts_at + timedelta(minutes=30)
            ends_at = starts_at + timedelta(minutes=60)

            existing_invites = [str(value) for value in auction_doc.get("invited_user_ids", [])]
            previous_participants = [str(value) for value in auction_doc.get("participants", [])]

            doc = {
                "_id": auction_db_id,
                "status": "RUNNING",
                "starts_at": starts_at,
                "ends_at": ends_at,
                "scheduled_ends_at": ends_at,
                "join_deadline": join_deadline,
                "overtime_count": 0,
                "selected_item_ids": selected,
                "gift_card_candidate_user_ids": [],
                "participants": [],
                "invited_user_ids": existing_invites,
                "extensions": [],
                "highest_bid": 0,
                "highest_bidder_name": None,
                "highest_bidder_id": None,
                "users_table": [],
                "updated_at": now,
            }

            lock_res = await self._items.update_many(
                {
                    "_id": {"$in": selected_object_ids},
                    "status": "AVAILABLE",
                    "$or": [
                        {"active_auction_id": None},
                        {"active_auction_id": {"$exists": False}},
                    ],
                },
                {
                    "$set": {
                        "auction_id": normalized_auction_id,
                        "active_auction_id": normalized_auction_id,
                        "selected_for_auction": True,
                        "updated_at": now,
                    }
                },
                session=session,
            )
            if lock_res.modified_count != len(selected_object_ids):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Selected items changed while starting auction. Please retry.",
                )

            if previous_participants:
                await self._reset_user_bid_state(now=now, user_ids=previous_participants, session=session)

            await self._users.update_many(
                {"gift_card_winner": True},
                {"$set": {"gift_card_winner": False, "updated_at": now}},
                session=session,
            )

            await self._auction.replace_one({"_id": auction_db_id}, doc, upsert=False, session=session)
            return self._state_out(doc)

        return await _run_txn_with_retries(client, _txn_body)

    async def create_auction(
        self,
        *,
        auction_id: Optional[str] = None,
        scheduled_starts_at: Optional[datetime] = None,
    ) -> AuctionStateOut:
        if scheduled_starts_at is not None:
            now = _utc_now()
            doc: Dict[str, Any] = {
                "status": "IDLE",
                "starts_at": None,
                "ends_at": None,
                "scheduled_starts_at": scheduled_starts_at,
                "scheduled_ends_at": None,
                "join_deadline": None,
                "participants": [],
                "invited_user_ids": [],
                "extensions": [],
                "overtime_count": 0,
                "highest_bid": 0,
                "highest_bidder_name": None,
                "highest_bidder_id": None,
                "users_table": [],
                "updated_at": now,
            }
            result = await self._auction.insert_one(doc)
            created = await self._auction.find_one({"_id": result.inserted_id})
            return AuctionStateOut.model_validate(created or {**doc, "_id": result.inserted_id})

        normalized_id = str(auction_id or "current").strip()
        if not normalized_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid auction_id.")

        now = _utc_now()
        state = AuctionStateOut.model_validate({"_id": normalized_id, "status": "IDLE"})
        doc = state.model_dump(by_alias=True)
        doc["updated_at"] = now
        doc["_id"] = self._auction_insert_id(normalized_id)

        result = await self._auction.update_one(
            self._auction_id_query(normalized_id),
            {"$setOnInsert": doc},
            upsert=True,
        )

        if result.upserted_id is None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Auction already exists.")

        created = await self._auction.find_one({"_id": result.upserted_id})
        return self._state_out(created or doc)

    async def delete_auction(self, *, auction_id: str) -> bool:
        normalized_id = str(auction_id).strip()
        if not normalized_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid auction_id.")

        existing = await self._find_auction_doc(normalized_id)
        if not existing:
            return False
        if existing.get("status") == "RUNNING":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Cannot delete a running auction.",
            )
        result = await self._auction.delete_one({"_id": existing["_id"]})
        return result.deleted_count > 0

    async def get_auction_state(self, *, auction_id: str = "current") -> AuctionStateOut:
        doc = await self._find_auction_doc(auction_id)
        if not doc:
            return self._state_out({"_id": auction_id, "status": "IDLE"})
        return self._state_out(doc)

    async def close_auction_and_distribute(self, *, auction_id: str = "current") -> Dict[str, Any]:
        current = await self._find_auction_doc(auction_id)
        if not current or current.get("status") != "RUNNING":
            now = _utc_now()
            return {"success": True, "status": "ENDED", "ended_at": now}

        auction_db_id = current["_id"]
        normalized_auction_id = str(auction_db_id)
        client = self._auction.database.client

        async def _txn_body(session) -> tuple[Dict[str, Any], list[str], list[str], list[str], Dict[str, Any]]:
            locked = await self._auction.find_one({"_id": auction_db_id, "status": "RUNNING"}, session=session)
            if not locked:
                now = _utc_now()
                return {"success": True, "status": "ENDED", "ended_at": now}, [], [], [], {"ws": [], "email": []}

            now = _utc_now()
            selected_item_ids = [str(value) for value in locked.get("selected_item_ids", [])]
            participant_ids = [str(value) for value in locked.get("participants", [])]
            gift_card_candidate_user_ids: list[str] = []
            for participant_id in participant_ids:
                user_doc = await self._users.find_one(_user_id_query(participant_id), session=session)
                if not user_doc or self._read_user_role(user_doc) != "rep":
                    continue
                if int(user_doc.get("bid_counter", 0) or 0) == 0:
                    gift_card_candidate_user_ids.append(str(user_doc["_id"]))

            winner_payload = await self._distribute_items(
                selected_item_ids=selected_item_ids,
                participant_ids=participant_ids,
                now=now,
                auction_id=normalized_auction_id,
                session=session,
            )

            await self._reset_user_bid_state(now=now, user_ids=participant_ids, session=session)

            await self._auction.update_one(
                {"_id": auction_db_id},
                {
                    "$set": {
                        "status": "ENDED",
                        "ended_at": now,
                        "updated_at": now,
                        "gift_card_candidate_user_ids": gift_card_candidate_user_ids,
                    }
                },
                session=session,
            )

            await self._items.update_many(
                {
                    "$or": [
                        {"auction_id": normalized_auction_id},
                        {
                            "_id": {
                                "$in": [ObjectId(item_id) for item_id in selected_item_ids if ObjectId.is_valid(item_id)]
                            }
                        },
                    ]
                },
                {
                    "$set": {
                        "selected_for_auction": False,
                        "active_auction_id": None,
                        "updated_at": now,
                    }
                },
                session=session,
            )

            if self._ws_outbox is not None and winner_payload["ws"]:
                from app.auction.auction_ws import ws_event

                await self.queue_ws_events(
                    auction_id=normalized_auction_id,
                    events=[
                        ws_event(
                            "auction.message",
                            auction_id=normalized_auction_id,
                            user_id=winner_notice["user_id"],
                            item_id=winner_notice["item_id"],
                            message={
                                "type": "WON",
                                "content": winner_notice["content"],
                                "final_bid": winner_notice["final_bid"],
                            },
                        )
                        for winner_notice in winner_payload["ws"]
                    ],
                    session=session,
                )

            admin_user_ids = await self._admin_user_ids(session=session)
            return {"success": True, "status": "ENDED", "ended_at": now}, admin_user_ids, gift_card_candidate_user_ids, participant_ids, winner_payload

        result, admin_user_ids, gift_card_candidate_user_ids, participant_ids, winner_payload = await _run_txn_with_retries(client, _txn_body)

        # --- Send item-won email notifications ---
        for notice in winner_payload.get("email", []):
            await self._send_email_notification(
                user_id=notice["user_id"],
                message_type="WON",
                content=notice["content"],
                item_id=notice.get("item_id"),
            )

        # --- Automatic $25 gift card raffle ---
        # Collect all rep participants who joined the auction
        rep_participant_ids: list[str] = []
        for pid in participant_ids:
            user_doc = await self._users.find_one(_user_id_query(pid), projection={"_id": 1, "role": 1, "type": 1})
            if user_doc and self._read_user_role(user_doc) == "rep":
                rep_participant_ids.append(str(user_doc["_id"]))

        if rep_participant_ids:
            # Randomly select one rep from all who joined
            giftcard_winner_id = rep_participant_ids[random.randint(0, len(rep_participant_ids) - 1)]

            # Look up winner details for notification text
            winner_doc = await self._users.find_one(_user_id_query(giftcard_winner_id), projection={"_id": 1, "email": 1, "name": 1})
            winner_name = self._read_user_name(winner_doc) if winner_doc else giftcard_winner_id
            winner_email = winner_doc.get("email", "") if winner_doc else ""

            # Mark the winner in the database
            now_gc = _utc_now()
            await self._users.update_many(
                {"gift_card_winner": True},
                {"$set": {"gift_card_winner": False, "updated_at": now_gc}},
            )
            await self._users.update_one(
                _user_id_query(giftcard_winner_id),
                {"$set": {"gift_card_winner": True, "updated_at": now_gc}},
            )
            await self._auction.update_one(
                {"_id": auction_db_id},
                {"$set": {"gift_card_winner_user_id": giftcard_winner_id, "updated_at": now_gc}},
            )

            # In-app + email notification to the winning rep
            winner_message = (
                f"Congratulations! You have been randomly selected to win a $25 gift card "
                f"from the auction. You will receive it shortly."
            )
            await self._queue_user_notification_once(
                auction_id=normalized_auction_id,
                user_id=giftcard_winner_id,
                message_type=AUCTION_MESSAGE_TYPE_GIFT_CARD_WON,
                content=winner_message,
                allow_duplicates=True,
            )

            # In-app + email notification to all admins
            admin_message = (
                f"Auction ended. {winner_name} ({winner_email}) has been automatically "
                f"selected to receive a $25 gift card."
            )
            for admin_user_id in admin_user_ids:
                await self._queue_user_notification_once(
                    auction_id=normalized_auction_id,
                    user_id=admin_user_id,
                    message_type=AUCTION_MESSAGE_TYPE_GIFT_CARD_ACTION_REQUIRED,
                    content=admin_message,
                    allow_duplicates=True,
                )

        return result

    async def join_auction(self, *, auction_id: str, user_id: str) -> Dict[str, Any]:
        client = self._auction.database.client

        async def _txn_body(session) -> Dict[str, Any]:
            auction = await self._find_auction_doc(auction_id, session=session)
            if not auction:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Auction not found.")
            if auction.get("status") != "RUNNING":
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Auction is not running.")

            auction_db_id = auction["_id"]
            normalized_auction_id = str(auction_db_id)

            invited = {str(value) for value in auction.get("invited_user_ids", [])}
            if user_id not in invited:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You are not invited to this auction.",
                )

            participants = {str(value) for value in auction.get("participants", [])}
            if user_id in participants:
                return {
                    "success": True,
                    "joined": True,
                    "reconnected": True,
                    "message": "Reconnected to auction.",
                    "auction_id": normalized_auction_id,
                }

            now = _utc_now()
            join_deadline = ensure_app_datetime(auction.get("join_deadline"))
            if join_deadline and now > join_deadline:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Join window is closed. First-time joins are only allowed in the first 30 minutes.",
                )

            await self._auction.update_one(
                {"_id": auction_db_id},
                {"$addToSet": {"participants": user_id}},
                session=session,
            )

            return {
                "success": True,
                "joined": True,
                "reconnected": False,
                "message": "Joined auction successfully.",
                "auction_id": normalized_auction_id,
            }

        return await _run_txn_with_retries(client, _txn_body)

    async def add_invites(self, *, auction_id: str, user_ids: list[str]) -> Dict[str, Any]:
        auction_doc = await self._find_auction_doc(auction_id)
        if not auction_doc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Auction not found.")

        cleaned = sorted({user_id.strip() for user_id in user_ids if user_id and user_id.strip()})
        await self._auction.update_many(
            self._auction_id_query(auction_id),
            {"$addToSet": {"invited_user_ids": {"$each": cleaned}}},
        )
        return await self.get_invites(auction_id=auction_id)

    async def remove_invites(self, *, auction_id: str, user_ids: list[str]) -> Dict[str, Any]:
        auction_doc = await self._find_auction_doc(auction_id)
        if not auction_doc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Auction not found.")

        cleaned = sorted({user_id.strip() for user_id in user_ids if user_id and user_id.strip()})
        await self._auction.update_many(
            self._auction_id_query(auction_id),
            {"$pull": {"invited_user_ids": {"$in": cleaned}}},
        )
        return await self.get_invites(auction_id=auction_id)

    async def get_invites(self, *, auction_id: str) -> Dict[str, Any]:
        doc = await self._find_auction_doc(auction_id)
        if not doc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Auction not found.")
        return {"auction_id": str(doc.get("_id", auction_id)), "invited_user_ids": [str(v) for v in doc.get("invited_user_ids", [])]}

    async def extend_timer(
        self,
        *,
        auction_id: str,
        delta_seconds: int,
        by_user_id: Optional[str],
        reason: str,
        bid_id: Optional[str] = None,
        session=None,
        defer_notifications: bool = False,
    ) -> AuctionStateOut:
        current = await self._find_auction_doc(auction_id, session=session)
        if not current:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Auction not found.")
        if current.get("status") != "RUNNING":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Auction is not running.")

        auction_db_id = current["_id"]
        normalized_auction_id = str(auction_db_id)

        ends_at = ensure_app_datetime(current.get("ends_at", current.get("end_time")))
        if not ends_at:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Auction has no end time.")

        now = _utc_now()

        scheduled_ends_at = ensure_app_datetime(current.get("scheduled_ends_at"))
        if scheduled_ends_at is None:
            scheduled_ends_at = ends_at

        effective_delta_seconds = int(delta_seconds)
        current_overtime_count = int(current.get("overtime_count", 0) or 0)
        if reason == "late_bid":
            # Auto late-bid extensions are capped to 5 occurrences total.
            if current_overtime_count >= 5:
                return self._state_out(current)
            max_ends_at = scheduled_ends_at + timedelta(seconds=900)
            desired_ends_at = ends_at + timedelta(seconds=delta_seconds)
            capped_ends_at = min(desired_ends_at, max_ends_at)
            if capped_ends_at <= ends_at:
                if "scheduled_ends_at" not in current:
                    await self._auction.update_one(
                        {"_id": auction_db_id},
                        {"$set": {"scheduled_ends_at": scheduled_ends_at}},
                        session=session,
                    )
                    current["scheduled_ends_at"] = scheduled_ends_at
                return self._state_out(current)
            effective_delta_seconds = int((capped_ends_at - ends_at).total_seconds())

        if effective_delta_seconds <= 0:
            return self._state_out(current)

        new_ends_at = ends_at + timedelta(seconds=effective_delta_seconds)
        extension = {
            "at": now,
            "by_user_id": by_user_id,
            "reason": reason,
            "delta_seconds": effective_delta_seconds,
            "bid_id": bid_id,
        }
        update_doc: Dict[str, Any] = {
            "$set": {
                "ends_at": new_ends_at,
                "scheduled_ends_at": scheduled_ends_at,
                "end_time": new_ends_at,
                "deadlines.hard_end": new_ends_at,
                "updated_at": now,
            },
            "$push": {"extensions": extension},
        }
        if reason == "late_bid":
            update_doc["$inc"] = {"overtime_count": 1}
        await self._auction.update_one(
            {"_id": auction_db_id},
            update_doc,
            session=session,
        )
        updated = await self._auction.find_one({"_id": auction_db_id}, session=session)
        state = self._state_out(updated or current)

        if not defer_notifications:
            from app.auction.auction_ws import EVENT_AUCTION_STATE_UPDATED, EVENT_AUCTION_TIMER_EXTENDED, ws_event

            await self.queue_ws_events(
                auction_id=normalized_auction_id,
                events=[
                    ws_event(
                        EVENT_AUCTION_TIMER_EXTENDED,
                        auction_id=normalized_auction_id,
                        reason=reason,
                        extension=extension,
                        state=state,
                    ),
                    ws_event(EVENT_AUCTION_STATE_UPDATED, auction_id=normalized_auction_id, state=state),
                ],
                session=session,
            )

        return state

    async def maybe_extend_for_late_bid(
        self,
        *,
        auction_id: str,
        by_user_id: str,
        bid_id: Optional[str],
    ) -> Optional[AuctionStateOut]:
        current = await self._find_auction_doc(auction_id)
        if not current or current.get("status") != "RUNNING":
            return None

        normalized_auction_id = str(current["_id"])
        now = _utc_now()
        ends_at = ensure_app_datetime(current.get("ends_at", current.get("end_time")))
        if not ends_at:
            return None

        if (ends_at - now) <= timedelta(minutes=10):
            return await self.extend_timer(
                auction_id=normalized_auction_id,
                delta_seconds=180,
                by_user_id=by_user_id,
                reason="late_bid",
                bid_id=bid_id,
            )
        return None

    async def get_sorted_participants(
        self,
        *,
        auction_id: str,
        order: str = "desc",
        include_invited: bool = False,
        include_bid_info: bool = False,
    ) -> Dict[str, Any]:
        auction = await self._find_auction_doc(auction_id)
        if not auction:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Auction not found.")

        participant_ids = [str(value) for value in auction.get("participants", [])]
        invited_ids = [str(value) for value in auction.get("invited_user_ids", [])]
        base_ids = invited_ids if include_invited else participant_ids
        seen_ids: set[str] = set()
        user_ids = [user_id for user_id in base_ids if user_id and not (user_id in seen_ids or seen_ids.add(user_id))]

        participants = await self._load_participants(participant_ids=user_ids)
        reverse = order.lower() != "asc"
        participants.sort(key=lambda entry: entry["bidding_power"], reverse=reverse)

        if include_invited:
            participant_set = {str(value) for value in participant_ids}
            for entry in participants:
                entry["joined"] = entry.get("user_id") in participant_set

        if include_bid_info and user_ids:
            normalized_auction_id = str(auction["_id"])
            bid_details: dict[str, dict[str, Any]] = {}
            cursor = (
                self._bids.find(
                    {"auction_id": normalized_auction_id, "bidder_id": {"$in": user_ids}},
                )
                .sort("timestamp", -1)
            )
            async for bid_doc in cursor:
                bidder_id = str(bid_doc.get("bidder_id") or "")
                if not bidder_id or bidder_id in bid_details:
                    continue
                item_id = str(bid_doc.get("item_id") or "")
                bid_details[bidder_id] = {
                    "item_id": item_id or None,
                    "amount": int(bid_doc.get("amount", 0) or 0),
                }
                if len(bid_details) >= len(user_ids):
                    break

            item_ids = {
                info["item_id"]
                for info in bid_details.values()
                if info.get("item_id") and ObjectId.is_valid(str(info.get("item_id")))
            }
            item_title_map: dict[str, str] = {}
            if item_ids:
                object_ids = [ObjectId(item_id) for item_id in item_ids if ObjectId.is_valid(item_id)]
                cursor = self._items.find({"_id": {"$in": object_ids}})
                async for item_doc in cursor:
                    item_title_map[str(item_doc["_id"])] = (
                        item_doc.get("name") or item_doc.get("title") or str(item_doc["_id"])
                    )

            for entry in participants:
                info = bid_details.get(entry.get("user_id"))
                if not info:
                    entry["last_bid_item_id"] = None
                    entry["last_bid_item_title"] = None
                    entry["last_bid_amount"] = None
                    continue
                item_id = info.get("item_id")
                entry["last_bid_item_id"] = item_id
                entry["last_bid_item_title"] = item_title_map.get(item_id) or item_id
                entry["last_bid_amount"] = info.get("amount")

        return {"participants": participants}

    async def get_dashboard_kbs(self, *, auction_id: str, top_n: int = 5) -> Dict[str, Any]:
        auction = await self._find_auction_doc(auction_id)
        if not auction:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Auction not found.")

        invited = [str(value) for value in auction.get("invited_user_ids", [])]
        participant_ids = [str(value) for value in auction.get("participants", [])]
        participants = await self._load_participants(participant_ids=participant_ids)
        participants_sorted = sorted(participants, key=lambda entry: entry["bidding_power"], reverse=True)

        if auction.get("status") == "ENDED" and "gift_card_candidate_user_ids" in auction:
            not_bid_yet_user_ids = [str(value) for value in auction.get("gift_card_candidate_user_ids", [])]
            not_bid_yet_count = len(not_bid_yet_user_ids)
        else:
            not_bid_yet_count = 0
            not_bid_yet_user_ids: list[str] = []
            for participant_id in participant_ids:
                user_doc = await self._users.find_one(_user_id_query(participant_id))
                if user_doc and int(user_doc.get("bid_counter", 0)) == 0:
                    not_bid_yet_count += 1
                    not_bid_yet_user_ids.append(str(user_doc.get("_id")))

        return {
            "invited_count": len(invited),
            "joined_count": len(participant_ids),
            "not_bid_yet_count": not_bid_yet_count,
            "not_bid_yet_user_ids": not_bid_yet_user_ids,
            "top_by_bidding_power": participants_sorted[:top_n],
        }

    async def get_my_dashboard_kbs(self, *, auction_id: str, user_id: str) -> Dict[str, Any]:
        auction = await self._find_auction_doc(auction_id)
        if not auction:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Auction not found.")

        user_doc = await self._users.find_one(_user_id_query(user_id))
        if not user_doc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

        metrics = _compute_user_metrics(user_doc)
        invited = user_id in {str(value) for value in auction.get("invited_user_ids", [])}
        joined = user_id in {str(value) for value in auction.get("participants", [])}
        return {
            "auction_id": str(auction["_id"]),
            "user_id": metrics["user_id"],
            "name": metrics["name"],
            "kogbucks_total": metrics["kogbucks_total"],
            "kogbucks_held": metrics["kogbucks_held"],
            "bidding_power": metrics["bidding_power"],
            "invited": invited,
            "joined": joined,
            "bid_counter": int(user_doc.get("bid_counter", 0)),
        }

    async def mark_gift_card_winner(self, *, auction_id: str, user_id: str) -> Dict[str, Any]:
        auction = await self._find_auction_doc(auction_id)
        if not auction:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Auction not found.")
        if auction.get("status") != "ENDED":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Gift card winner can only be selected after auction ends.")

        candidate_ids = {str(value) for value in auction.get("gift_card_candidate_user_ids", [])}
        if user_id not in candidate_ids:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Selected user is not eligible for the gift card.")

        client = self._users.database.client
        normalized_auction_id = str(auction["_id"])

        async def _txn_body(session) -> Dict[str, Any]:
            user_doc = await self._users.find_one(_user_id_query(user_id), session=session)
            if not user_doc:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
            if self._read_user_role(user_doc) != "rep":
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Gift card winner must be a rep.")

            now = _utc_now()
            await self._users.update_many(
                {"gift_card_winner": True},
                {"$set": {"gift_card_winner": False, "updated_at": now}},
                session=session,
            )
            await self._users.update_one(
                {"_id": user_doc["_id"]},
                {"$set": {"gift_card_winner": True, "updated_at": now}},
                session=session,
            )
            return {
                "auction_id": normalized_auction_id,
                "user_id": str(user_doc["_id"]),
                "gift_card_winner": True,
            }

        result = await _run_txn_with_retries(client, _txn_body)
        await self._queue_user_notification_once(
            auction_id=normalized_auction_id,
            user_id=result["user_id"],
            message_type=AUCTION_MESSAGE_TYPE_GIFT_CARD_WON,
            content="You have been selected as the gift card winner.",
            allow_duplicates=True,
        )
        return result

    async def confirm_gift_card_sent(self, *, auction_id: str, user_id: str) -> Dict[str, Any]:
        auction = await self._find_auction_doc(auction_id)
        if not auction:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Auction not found.")
        if auction.get("status") != "ENDED":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Gift card can only be confirmed after auction ends.")

        candidate_ids = {str(value) for value in auction.get("gift_card_candidate_user_ids", [])}
        if user_id not in candidate_ids:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Selected user is not eligible for the gift card.")

        client = self._users.database.client
        normalized_auction_id = str(auction["_id"])

        async def _txn_body(session) -> Dict[str, Any]:
            user_doc = await self._users.find_one(_user_id_query(user_id), session=session)
            if not user_doc:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
            if self._read_user_role(user_doc) != "rep":
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Gift card winner must be a rep.")

            now = _utc_now()
            await self._users.update_one(
                {"_id": user_doc["_id"]},
                {"$set": {"gift_card_winner": False, "updated_at": now}},
                session=session,
            )
            return {
                "auction_id": normalized_auction_id,
                "user_id": str(user_doc["_id"]),
                "gift_card_winner": False,
            }

        return await _run_txn_with_retries(client, _txn_body)

    async def process_inactivity_notifications(self, *, now: Optional[datetime] = None) -> int:
        sent_count = 0
        current_time = ensure_app_datetime(now) or _utc_now()
        cursor = self._auction.find({"status": "RUNNING"})

        async for auction_doc in cursor:
            sent_count += await self._process_auction_inactivity_notifications(
                auction_doc=auction_doc,
                now=current_time,
            )

        return sent_count

    async def _process_auction_inactivity_notifications(
        self,
        *,
        auction_doc: Dict[str, Any],
        now: datetime,
    ) -> int:
        starts_at = ensure_app_datetime(auction_doc.get("starts_at"))
        join_deadline = ensure_app_datetime(auction_doc.get("join_deadline"))
        if not starts_at or not join_deadline:
            return 0

        auction_id = str(auction_doc.get("_id"))
        invited_ids = {str(value) for value in auction_doc.get("invited_user_ids", [])}
        participant_ids = [str(value) for value in auction_doc.get("participants", []) if str(value).strip()]
        if not participant_ids:
            return 0

        sent_count = 0
        user_docs = [
            doc
            async for doc in self._users.find(_user_ids_query(participant_ids))
        ]
        for user_doc in user_docs:
            user_id = str(user_doc["_id"])
            if user_id not in invited_ids:
                continue
            if self._read_user_role(user_doc) != "rep":
                continue

            bid_counter = int(user_doc.get("bid_counter", 0) or 0)
            has_bid = bool(user_doc.get("has_bid", False)) or bid_counter > 0
            if has_bid:
                continue

            if now > join_deadline:
                sent = await self._queue_user_notification_once(
                    auction_id=auction_id,
                    user_id=user_id,
                    message_type=AUCTION_MESSAGE_TYPE_BID_LOCKED,
                    content="You may no longer bid",
                    require_running_auction=True,
                    skip_if_user_has_bid=True,
                )
                sent_count += int(sent)
                continue

            elapsed_seconds = int((now - starts_at).total_seconds())
            if elapsed_seconds < INACTIVITY_REMINDER_INTERVAL_SECONDS:
                continue

            reminder_slot = elapsed_seconds // INACTIVITY_REMINDER_INTERVAL_SECONDS
            if reminder_slot <= 0:
                continue

            sent = await self._queue_user_notification_once(
                auction_id=auction_id,
                user_id=user_id,
                message_type=AUCTION_MESSAGE_TYPE_INACTIVITY_REMINDER,
                content="You have not placed a bid yet.",
                dedupe_fields={"reminder_slot": reminder_slot},
                extra_doc_fields={
                    "reminder_slot": reminder_slot,
                    "reminder_interval_seconds": INACTIVITY_REMINDER_INTERVAL_SECONDS,
                },
                extra_ws_fields={
                    "reminder_slot": reminder_slot,
                    "reminder_interval_seconds": INACTIVITY_REMINDER_INTERVAL_SECONDS,
                },
                require_running_auction=True,
                skip_if_user_has_bid=True,
            )
            sent_count += int(sent)

        return sent_count

    async def list_messages_for_user(self, *, auction_id: str, user_id: str, limit: int = 20) -> Dict[str, Any]:
        cursor = self._messages.find(
            {"auction_id": auction_id, "user_id": user_id},
        ).sort("created_at", -1).limit(limit)
        messages: list[Dict[str, Any]] = []
        async for doc in cursor:
            messages.append(
                {
                    "id": str(doc["_id"]),
                    "auction_id": doc.get("auction_id", auction_id),
                    "user_id": doc.get("user_id", user_id),
                    "item_id": doc.get("item_id"),
                    "type": doc.get("type", "LEADING"),
                    "message": doc.get("message", ""),
                    "created_at": doc.get("created_at"),
                }
            )
        return {"messages": messages}

    async def list_chat_messages(
        self,
        *,
        auction_id: str,
        user_id: str,
        user_role: str,
        limit: int = 50,
    ) -> Dict[str, Any]:#retrieve chat messages for a specific auction, ensuring that the requesting user has the permissions to access the chat 
        auction_doc = await self._find_auction_doc(auction_id)
        if not auction_doc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Auction not found.")

        if str(user_role).lower() != "admin":#Admins can view chat messages without restrictions, while non-admin users must be both invited to and participants in the auction to access the chat.
            self._ensure_chat_running(auction_doc=auction_doc)
            self._ensure_chat_participant_access(auction_doc=auction_doc, user_id=user_id)

        normalized_auction_id = str(auction_doc["_id"])
        bounded_limit = max(1, min(int(limit), 100))
        docs = await self._chat_collection().find(
            {"auction_id": normalized_auction_id},
        ).sort("created_at", -1).limit(bounded_limit).to_list(length=bounded_limit)
        docs.reverse()

        return {
            "auction_id": normalized_auction_id,
            "chat_messages": [self._serialize_chat_message(doc) for doc in docs],
        }

    async def post_chat_message(
        self,
        *,
        auction_id: str,
        user_id: str,
        user_role: str,
        content: str,
    ) -> Dict[str, Any]:#post a new chat message to auction chat room. 
        #The method first validates the input,
        # then performs a transaction to ensure data consistency。
        # Within the transaction, it checks if the auction exists and is running, verifies the user access, and then inserts the new chat message into the database.
        # it also queues a WebSocket event to notify other clients of the new message.
        cleaned_content = str(content or "").strip()
        if not cleaned_content:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Chat message content is required.")

        client = self._chat_collection().database.client

        async def _txn_body(session) -> Dict[str, Any]:
            auction_doc = await self._find_auction_doc(auction_id, session=session)
            if not auction_doc:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Auction not found.")

            self._ensure_chat_running(auction_doc=auction_doc)
            if str(user_role).lower() != "admin":
                self._ensure_chat_participant_access(auction_doc=auction_doc, user_id=user_id)

            user_doc = await self._users.find_one(_user_id_query(user_id), session=session)
            if not user_doc:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

            normalized_auction_id = str(auction_doc["_id"])
            sender_role = self._read_user_role(user_doc)
            now = _utc_now()
            chat_doc = {
                "auction_id": normalized_auction_id,
                "sender_user_id": str(user_doc["_id"]),
                "sender_name": self._read_user_name(user_doc),
                "sender_role": sender_role,
                "content": cleaned_content,
                "created_at": now,
                "updated_at": now,
            }
            result = await self._chat_collection().insert_one(chat_doc, session=session)
            saved_doc = {**chat_doc, "_id": result.inserted_id}

            if self._ws_outbox is not None:
                from app.auction.auction_ws import EVENT_AUCTION_CHAT_MESSAGE, ws_event

                await self.queue_ws_event(
                    auction_id=normalized_auction_id,
                    event=ws_event(
                        EVENT_AUCTION_CHAT_MESSAGE,
                        auction_id=normalized_auction_id,
                        message=self._serialize_chat_message(saved_doc),
                    ),
                    session=session,
                )

            return self._serialize_chat_message(saved_doc)

        return await _run_txn_with_retries(client, _txn_body)

    async def get_my_results(self, *, auction_id: str, user_id: str) -> Dict[str, Any]:
        auction = await self._find_auction_doc(auction_id)
        if not auction:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Auction not found.")

        normalized_auction_id = str(auction["_id"])
        selected_item_ids = [str(value) for value in auction.get("selected_item_ids", [])]
        selected_object_ids = [ObjectId(value) for value in selected_item_ids if ObjectId.is_valid(value)]

        won: list[Dict[str, Any]] = []
        won_item_ids: set[str] = set()
        won_query: Dict[str, Any] = {
            "$expr": {"$eq": [{"$toString": "$winner_user_id"}, user_id]},
            "auction_id": normalized_auction_id,
        }
        if selected_object_ids:
            won_query = {
                "$expr": {"$eq": [{"$toString": "$winner_user_id"}, user_id]},
                "$or": [
                    {"auction_id": normalized_auction_id},
                    {"_id": {"$in": selected_object_ids}},
                ],
            }

        async for doc in self._items.find(won_query):
            item_id = str(doc["_id"])
            won_item_ids.add(item_id)
            won.append(
                {
                    "item_id": item_id,
                    "title": doc.get("name"),
                    "final_bid": int(doc.get("highest_bid", 0) or 0),
                }
            )

        bid_cursor = self._bids.find({"auction_id": normalized_auction_id, "bidder_id": user_id})
        bid_item_ids: set[str] = set()
        async for doc in bid_cursor:
            bid_item_ids.add(str(doc.get("item_id")))

        lost_item_ids = sorted(bid_item_ids - won_item_ids)
        lost_object_ids = [ObjectId(item_id) for item_id in lost_item_ids if ObjectId.is_valid(item_id)]
        lost_docs_by_id: dict[str, Dict[str, Any]] = {}
        if lost_object_ids:
            async for doc in self._items.find({"_id": {"$in": lost_object_ids}}):
                lost_docs_by_id[str(doc["_id"])] = doc

        lost: list[Dict[str, Any]] = []
        for item_id in lost_item_ids:
            doc = lost_docs_by_id.get(item_id)
            if not doc:
                continue
            lost.append(
                {
                    "item_id": item_id,
                    "title": doc.get("name"),
                    "final_bid": int(doc.get("highest_bid", 0) or 0),
                }
            )

        return {"won": won, "lost": lost}

    async def _load_participants(self, *, participant_ids: list[str]) -> list[Dict[str, Any]]:
        participants: list[Dict[str, Any]] = []
        for participant_id in participant_ids:
            user_doc = await self._users.find_one(_user_id_query(participant_id))
            if not user_doc:
                continue
            participants.append(_compute_user_metrics(user_doc))
        return participants

    def _user_table_row_from_docs(
        self,
        *,
        user_doc: Dict[str, Any],
        item_doc: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        held_item_id = user_doc.get("held_item_id")
        held_item_name = item_doc.get("name") if item_doc else None
        item_status = "NOT_BID"

        if held_item_id and item_doc:
            if str(item_doc.get("highest_bidder_id", item_doc.get("temp_owner"))) == str(user_doc["_id"]):
                item_status = "LEADING"
            else:
                item_status = "OUTBID"
        elif bool(user_doc.get("has_bid", False)):
            item_status = "OUTBID"

        return {
            "user_id": str(user_doc["_id"]),
            "user_name": user_doc.get("name") or user_doc.get("email"),
            "kogbucks": int(user_doc.get("balance_amount", 0)),
            "has_bid": bool(user_doc.get("has_bid", False)),
            "item_on_hold": held_item_name or held_item_id,
            "item_status": item_status,
        }

    async def build_user_table_row(self, *, user_id: str, session=None) -> Optional[Dict[str, Any]]:
        user_doc = await self._users.find_one(_user_id_query(user_id), session=session)
        if not user_doc:
            return None

        held_item_id = user_doc.get("held_item_id")
        item_doc = None

        if held_item_id and ObjectId.is_valid(str(held_item_id)):
            item_doc = await self._items.find_one({"_id": ObjectId(str(held_item_id))}, session=session)

        return self._user_table_row_from_docs(user_doc=user_doc, item_doc=item_doc)

    async def build_users_table(self, *, auction_doc: Dict[str, Any], session=None) -> list[Dict[str, Any]]:
        participant_ids = [str(value) for value in auction_doc.get("participants", [])]
        if not participant_ids:
            return []

        user_docs = [
            doc
            async for doc in self._users.find(_user_ids_query(participant_ids), session=session)
        ]

        held_item_object_ids = [
            ObjectId(str(user_doc["held_item_id"]))
            for user_doc in user_docs
            if user_doc.get("held_item_id") and ObjectId.is_valid(str(user_doc["held_item_id"]))
        ]
        items_by_id: dict[str, Dict[str, Any]] = {}
        if held_item_object_ids:
            async for item_doc in self._items.find({"_id": {"$in": held_item_object_ids}}, session=session):
                items_by_id[str(item_doc["_id"])] = item_doc

        rows = [
            self._user_table_row_from_docs(
                user_doc=user_doc,
                item_doc=items_by_id.get(str(user_doc.get("held_item_id"))),
            )
            for user_doc in user_docs
        ]

        rows.sort(key=lambda row: (row.get("user_name") or "").lower())
        return rows

    async def select_items_for_auction(
        self,
        *,
        item_ids: list[ObjectId],
        auction_id: str = "current",
    ) -> Dict[str, Any]:
        normalized_auction_id = str(auction_id).strip()
        if not normalized_auction_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid auction_id.")

        auction_doc = await self._find_auction_doc(normalized_auction_id)
        if auction_doc and auction_doc.get("status") == "RUNNING":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Cannot change selected items while auction is running.",
            )

        requested_ids = list(dict.fromkeys(item_ids))
        if not requested_ids:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No item ids were provided.")

        requested_docs = await self._items.find(
            {"_id": {"$in": requested_ids}},
            projection={"_id": 1, "auction_id": 1, "status": 1, "active_auction_id": 1},
        ).to_list(length=None)
        docs_by_id = {doc["_id"]: doc for doc in requested_docs}

        missing_ids = [str(item_id) for item_id in requested_ids if item_id not in docs_by_id]
        if missing_ids:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Some item IDs do not exist: {', '.join(missing_ids)}",
            )

        already_selected_ids: list[str] = []
        for item_id in requested_ids:
            doc = docs_by_id[item_id]
            selected_value = doc.get("auction_id")
            if selected_value not in (None, "", False) and str(selected_value) != normalized_auction_id:
                already_selected_ids.append(str(item_id))

        if already_selected_ids:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Some items are already selected for another auction: {', '.join(already_selected_ids)}",
            )

        available_docs = await self._items.find(
            {
                "_id": {"$in": requested_ids},
                "status": "AVAILABLE",
                "$or": [{"active_auction_id": None}, {"active_auction_id": {"$exists": False}}],
            },
            projection={"_id": 1},
        ).to_list(length=None)
        available_ids = {doc["_id"] for doc in available_docs}
        unavailable_ids = [str(item_id) for item_id in requested_ids if item_id not in available_ids]
        if unavailable_ids:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Some items are not available for selection: {', '.join(unavailable_ids)}",
            )

        now = _utc_now()
        await self._items.update_many(
            {"_id": {"$in": requested_ids}},
            {
                "$set": {
                    "auction_id": normalized_auction_id,
                    "selected_for_auction": True,
                    "active_auction_id": None,
                    "updated_at": now,
                }
            },
        )

        return {
            "auction_id": normalized_auction_id,
            "selected_count": len(requested_ids),
            "selected_item_ids": [str(item_id) for item_id in requested_ids],
        }

    async def _ensure_auction_exists(self, *, auction_id: str) -> None:
        now = _utc_now()
        base_state = AuctionStateOut.model_validate({"_id": auction_id, "status": "IDLE"})
        insert_doc = base_state.model_dump(by_alias=True)
        insert_doc["_id"] = self._auction_insert_id(auction_id)
        insert_doc["updated_at"] = now
        await self._auction.update_one(
            self._auction_id_query(auction_id),
            {"$setOnInsert": insert_doc},
            upsert=True,
        )

    async def _distribute_items(
        self,
        *,
        selected_item_ids: Optional[list[str]],
        participant_ids: Optional[list[str]],
        now: datetime,
        auction_id: str,
        session=None,
    ) -> Dict[str, list[Dict[str, Any]]]:
        object_ids = [ObjectId(item_id) for item_id in (selected_item_ids or []) if ObjectId.is_valid(item_id)]
        filters: list[Dict[str, Any]] = [{"auction_id": auction_id}]
        if object_ids:
            filters.append({"_id": {"$in": object_ids}})
        query: Dict[str, Any] = {"$or": filters}

        auction_items = await self._items.find(query, session=session).to_list(length=None)

        ws_notifications: list[Dict[str, Any]] = []
        email_notifications: list[Dict[str, Any]] = []
        winning_user_ids: set[str] = set()
        available_items: list[Dict[str, Any]] = []

        # First pass: finalize bid-based winners and collect still-available items.
        for item_doc in auction_items:
            item_status = str(item_doc.get("status", "AVAILABLE"))
            highest_bidder_id = item_doc.get("highest_bidder_id")
            if highest_bidder_id:
                winner_user_id = str(highest_bidder_id)
                winning_user_ids.add(winner_user_id)

                await self._items.update_one(
                    {"_id": item_doc["_id"]},
                    {
                        "$set": {
                            "winner_user_id": highest_bidder_id,
                            "status": "SOLD",
                            "auction_id": auction_id,
                            "updated_at": now,
                        },
                        "$unset": {"temp_owner": ""},
                    },
                    session=session,
                )

                # check to see if the user has "notify_auction_win" enabled
                winner_settings = await _get_user_settings(
                    user_id=winner_user_id,
                    users_collection=self._users,
                    session=session,
                )
                winner_notice = {
                    "user_id": winner_user_id,
                    "item_id": str(item_doc["_id"]),
                    "content": f"You won item {item_doc.get('name') or str(item_doc['_id'])}.",
                    "final_bid": int(item_doc.get("highest_bid", 0) or 0),
                }
                if winner_settings.get("enable_in_app", True) and winner_settings.get("notify_auction_win", True):
                    existing = await self._messages.find_one(
                        {
                            "auction_id": auction_id,
                            "user_id": winner_user_id,
                            "type": "WON",
                            "item_id": str(item_doc["_id"]),
                        },
                        projection={"_id": 1},
                        session=session,
                    )
                    if not existing:
                        await self._messages.insert_one(
                            {
                                "auction_id": auction_id,
                                "user_id": winner_user_id,
                                "item_id": str(item_doc["_id"]),
                                "scope": "USER",
                                "audience": "USER",
                                "type": "WON",
                                "message": winner_notice["content"],
                                "final_bid": winner_notice["final_bid"],
                                "created_at": now,
                            },
                            session=session,
                        )
                    ws_notifications.append(winner_notice)
                if winner_settings.get("enable_email", True) and winner_settings.get("notify_auction_win", True):
                    email_notifications.append(winner_notice)
                continue

            if item_status == "AVAILABLE":
                available_items.append(item_doc)
                continue

            # Non-available items without a highest bidder are still closed out.
            item_name = str(item_doc.get("name") or str(item_doc["_id"]))
            #print(f"The {item_name} was faulty and is being recycled for use in a later auction.")

            await self._items.update_one(
                {"_id": item_doc["_id"]},
                {
                    "$set": {
                        "winner_user_id": None,
                        "highest_bid": 0,
                        "highest_bidder_id": None,
                        "status": "AVAILABLE",
                        "auction_id": None,
                        "active_auction_id": None,
                        "selected_for_auction": False,
                        "updated_at": now,
                    },
                    "$unset": {"temp_owner": ""},
                },
                session=session,
)

        # Rank participants by total budget (highest first) and keep only users without won items.
        ranked_candidates: list[Dict[str, Any]] = []
        for participant_id in (participant_ids or []):
            participant_str = str(participant_id).strip()
            if not participant_str or participant_str in winning_user_ids:
                continue
            user_doc = await self._users.find_one(_user_id_query(participant_str), session=session)
            if not user_doc:
                continue
            score = int(user_doc.get("balance_amount", 0)) + int(user_doc.get("before_bid_amount", 0))
            ranked_candidates.append({"user_id": str(user_doc["_id"]), "score": score})

        ranked_candidates.sort(key=lambda row: (-row["score"], row["user_id"]))

        # Randomly assign available items in strongest-rank-first order.
        random.shuffle(available_items)
        while available_items and ranked_candidates:
            item_doc = available_items.pop()
            assignee = ranked_candidates.pop(0)
            assignee_id = assignee["user_id"]
            await self._items.update_one(
                {"_id": item_doc["_id"]},
                {
                    "$set": {
                        "winner_user_id": assignee_id,
                        "status": "SOLD",
                        "auction_id": auction_id,
                        "active_auction_id": None,
                        "updated_at": now,
                    },
                    "$unset": {"temp_owner": ""},
                },
                session=session,
            )
            assignee_settings = await _get_user_settings(user_id=assignee_id, users_collection=self._users, session=session)
            assignee_notice = {
                "user_id": assignee_id,
                "item_id": str(item_doc["_id"]),
                "content": f"You won item {item_doc.get('name') or str(item_doc['_id'])}.",
                "final_bid": int(item_doc.get("highest_bid", 0) or 0),
            }
            if assignee_settings.get("enable_in_app", True) and assignee_settings.get("notify_auction_win", True):
                existing = await self._messages.find_one(
                    {
                        "auction_id": auction_id,
                        "user_id": assignee_id,
                        "type": "WON",
                        "item_id": str(item_doc["_id"]),
                    },
                    projection={"_id": 1},
                    session=session,
                )
                if not existing:
                    await self._messages.insert_one(
                        {
                            "auction_id": auction_id,
                            "user_id": assignee_id,
                            "item_id": str(item_doc["_id"]),
                            "scope": "USER",
                            "audience": "USER",
                            "type": "WON",
                            "message": assignee_notice["content"],
                            "final_bid": assignee_notice["final_bid"],
                            "created_at": now,
                        },
                        session=session,
                    )
                ws_notifications.append(assignee_notice)
            if assignee_settings.get("enable_email", True) and assignee_settings.get("notify_auction_win", True):
                email_notifications.append(assignee_notice)

        # Remaining available items become outstanding sold inventory.
        if available_items:
            outstanding_names = [str(item.get("name") or str(item.get("_id"))) for item in available_items]
            #print(f"{', '.join(outstanding_names)} are outstanding. The can no longer be used to bid with.")
            outstanding_ids = [item["_id"] for item in available_items]
            await self._items.update_many(
                {"_id": {"$in": outstanding_ids}},
                {
                    "$set": {
                        "winner_user_id": None,
                        "status": "SOLD",
                        "auction_id": auction_id,
                        "active_auction_id": None,
                        "updated_at": now,
                    },
                    "$unset": {"temp_owner": ""},
                },
                session=session,
            )

        return {"ws": ws_notifications, "email": email_notifications}

    async def _reset_user_bid_state(self, *, now: datetime, user_ids: list[str], session=None) -> None:
        query = _user_ids_query(user_ids)
        if query.get("_id", {}).get("$exists") is False:
            return

        await self._users.update_many(
            query,
            {
                "$set": {
                    "bid_counter": 0,
                    "balance_committed": False,
                    "held_item_id": None,
                    "committed_item_id": None,
                    "before_bid_amount": 0,
                    "has_bid": False,
                    "updated_at": now,
                }
            },
            session=session,
        )
