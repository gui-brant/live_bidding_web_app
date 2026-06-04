from __future__ import annotations

from typing import Any, Dict, Optional, Callable, Awaitable, Tuple

from bson import ObjectId
from fastapi import HTTPException, status

from app.auction.auction_service import AuctionService
from app.auction.auction_ws import EVENT_AUCTION_STATE_UPDATED, EVENT_AUCTION_TIMER_EXTENDED, EVENT_BID_PLACED, ws_event
from app.auction.ws_outbox import enqueue_ws_events

from app.auction.auction_schemas import AuctionStateOut
from app.items.items_schemas import ItemOut
from app.users.user_schemas import UserOut

from datetime import timedelta
import asyncio
import random

from app.helper.helpers import _is_transient_transaction_error, _utc_now, _user_id_query, _normalize_user_id_text,_get_motor_client_from_collection, _extract_user_id, _insert_user_message, _get_user_settings, NotificationCall
from app.helper.timezone import ensure_app_datetime as _ensure_utc
from app.helper.emailer import send_notification_email


async def _run_txn_with_retries(
    client,
    txn_coro_factory: Callable[[Any], Awaitable[Tuple[Any, list[NotificationCall]]]],
    *,
    max_retries: int = 5,
    base_backoff: float = 0.05,
    max_backoff: float = 0.8,
) -> Tuple[Any, list[NotificationCall]]:
    """
    Runs a transaction coroutine factory with retry on transient transaction errors.
    The factory receives `session` and returns (result, deferred_notifications).
    """
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

            # Exponential backoff + jitter
            backoff = min(max_backoff, base_backoff * (2 ** attempt))
            backoff = backoff * (0.5 + random.random())  # jitter in [0.5, 1.5)
            await asyncio.sleep(backoff)

    # If we exhausted retries
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Bid could not be committed due to high contention. Please retry.",
    ) from last_exc

class BidsService:
    def __init__(
        self,
        *,
        users_collection,
        items_collection,
        auction_collection,
        bids_collection,
        messages_collection,
        ws_outbox_collection=None,
    ) -> None:
        self._users = users_collection
        self._items = items_collection
        self._auction = auction_collection
        self._bids = bids_collection
        self._messages = messages_collection
        self._ws_outbox = ws_outbox_collection
        self._auction_service = AuctionService(
            auction_collection=auction_collection,
            items_collection=items_collection,
            users_collection=users_collection,
            bids_collection=bids_collection,
            messages_collection=messages_collection,
            ws_outbox_collection=ws_outbox_collection,
        )

    async def _should_send_user_message(
        self,
        *,
        user_id: str,
        message_type: str,
        session=None,
    ) -> bool:
        settings = await _get_user_settings(user_id=user_id, users_collection=self._users, session=session)
        if not settings.get("enable_in_app", True):
            return False
        if message_type == "OUTBID":
            return bool(settings.get("notify_outbid", True))
        if message_type == "WON":
            return bool(settings.get("notify_auction_win", True))
        if message_type in {"INACTIVITY_REMINDER", "BID_LOCKED"}:
            return bool(settings.get("notify_auction_timeframe", True))
        return True

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
        if message_type in {"INACTIVITY_REMINDER", "BID_LOCKED"}:
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

    def _read_user_role(self, user_doc: Dict[str, Any]) -> Optional[str]:
        return user_doc.get("role") or user_doc.get("type")

    def _current_highest_bidder_id(self, item_doc: Dict[str, Any]) -> Optional[str]:
        # Canonical field is highest_bidder_id; keep temp_owner fallback for legacy records.
        return item_doc.get("highest_bidder_id") or item_doc.get("temp_owner")

    def _auction_id_query(self, auction_id: str) -> Dict[str, Any]:
        normalized = str(auction_id).strip()
        if ObjectId.is_valid(normalized):
            return {"_id": {"$in": [normalized, ObjectId(normalized)]}}
        return {"_id": normalized}

    def _total_kogbucks(self, user_doc: Dict[str, Any]) -> int:
        return int(user_doc.get("balance_amount", 0)) + int(user_doc.get("before_bid_amount", 0))

    async def _ranked_participants(
        self,
        *,
        auction_state: Dict[str, Any],
        session=None,
    ) -> list[Dict[str, Any]]:
        participant_ids = {str(value) for value in auction_state.get("participants", []) if str(value).strip()}
        invited_ids = {str(value) for value in auction_state.get("invited_user_ids", []) if str(value).strip()}
        user_ids = sorted(participant_ids | invited_ids)
        if not user_ids:
            return []

        ranked: list[Dict[str, Any]] = []
        for user_id in user_ids:
            user_doc = await self._users.find_one(_user_id_query(user_id), session=session)
            if not user_doc:
                continue
            ranked.append(
                {
                    "user_id": str(user_doc["_id"]),
                    "score": self._total_kogbucks(user_doc),
                    "user_doc": user_doc,
                }
            )

        # Higher score is better rank. Tie-break by user id for deterministic order.
        ranked.sort(key=lambda row: (-row["score"], row["user_id"]))
        for idx, row in enumerate(ranked, start=1):
            row["rank"] = idx
        return ranked

    def _rank_index(self, ranked_participants: list[Dict[str, Any]]) -> Dict[str, int]:
        return {row["user_id"]: int(row["rank"]) for row in ranked_participants}

    def _can_still_bid_now(
        self,
        *,
        user_doc: Dict[str, Any],
        join_deadline,
        now,
        current_highest_bid: int,
    ) -> bool:
        if bool(user_doc.get("balance_committed", False)):
            return False
        if int(user_doc.get("balance_amount", 0)) <= int(current_highest_bid):
            return False
        if join_deadline and now > join_deadline and not bool(user_doc.get("has_bid", False)):
            return False
        return True

    async def _derive_item_status_after_bid(
        self,
        *,
        auction_state: Dict[str, Any],
        new_bidder_id: str,
        current_highest_bid: int,
        session=None,
    ) -> str:
        ranked = await self._ranked_participants(auction_state=auction_state, session=session)
        if not ranked:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Auction rank state is inconsistent: no ranked participants found for an active bid."
            )


        rank_index = self._rank_index(ranked)
        current_bidder_rank = rank_index.get(new_bidder_id)
        if current_bidder_rank is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Auction rank state is inconsistent: leader {new_bidder_id} is not present in ranked participants."
        )


        bidder_entry = next((entry for entry in ranked if entry["user_id"] == new_bidder_id), None)
        if not bidder_entry:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Auction rank state is inconsistent: leader {new_bidder_id} is missing from ranked participants."
            )

        bidder_score = int(bidder_entry.get("score", 0))
        # PRE-SOLD only when the bidding rep has the highest Kogbucks in the auction.
        # Ties are allowed because no other rep is strictly higher.
        has_higher = any(int(entry.get("score", 0)) > bidder_score for entry in ranked if entry["user_id"] != new_bidder_id)
        return "TEMPORARILY-OWNED" if has_higher else "PRE-SOLD"

    async def _load_auction_users(self, *, auction_doc: Dict[str, Any], session=None) -> list[Dict[str, Any]]:
        # Load all user docs for participants + invited users of this auction.
        participant_ids = {str(v) for v in auction_doc.get("participants", [])}
        invited_ids = {str(v) for v in auction_doc.get("invited_user_ids", [])}
        user_ids = sorted(participant_ids | invited_ids)

        users: list[Dict[str, Any]] = []
        for user_id in user_ids:
            user_doc = await self._users.find_one(_user_id_query(user_id), session=session)
            if user_doc:
                users.append(user_doc)
        return users

#Notification methods below are not for live notifications, but rather to insert messages into the database that can be fetched by clients for inbox or history messages.
    async def _notify_users(
        self,
        *,
        auction_id: str,
        user_ids: set[str],
        message: str,
        item_id: Optional[str],
        audience: str,
    ) -> int:
        if not user_ids:
            return 0
        allowed_ids: list[str] = []
        for user_id in sorted(user_ids):
            settings = await _get_user_settings(user_id=user_id, users_collection=self._users)
            if settings.get("enable_in_app", True):
                allowed_ids.append(user_id)

        if not allowed_ids:
            return 0

        now = _utc_now()
        docs = [
            {
                "auction_id": auction_id,
                "user_id": user_id,
                "item_id": item_id,
                "type": "SYSTEM",
                "audience": audience,
                "message": message,
                "created_at": now,
            }
            for user_id in allowed_ids
        ]
        await self._messages.insert_many(docs)
        return len(docs)

    async def NotifyAdmin(
        self,
        *,
        auction_doc: Dict[str, Any],
        message: str,
        item_id: Optional[str] = None,
    ) -> int:
        users = await self._load_auction_users(auction_doc=auction_doc)
        admin_ids = {str(doc["_id"]) for doc in users if self._read_user_role(doc) == "admin"}
        if not admin_ids:
            async for doc in self._users.find({"role": "admin"}, {"_id": 1}):
                admin_ids.add(str(doc["_id"]))
        return await self._notify_users(
            auction_id=str(auction_doc["_id"]),
            user_ids=admin_ids,
            message=message,
            item_id=item_id,
            audience="ADMINS",
        )

    async def NotifyReps(
        self,
        *,
        auction_doc: Dict[str, Any],
        message: str,
        item_id: Optional[str] = None,
    ) -> int:
        users = await self._load_auction_users(auction_doc=auction_doc)
        rep_ids = {str(doc["_id"]) for doc in users if self._read_user_role(doc) == "rep"}
        return await self._notify_users(
            auction_id=str(auction_doc["_id"]),
            user_ids=rep_ids,
            message=message,
            item_id=item_id,
            audience="REPS",
        )

    async def NotifyAll(# currently unused, but this is 
        self,
        *,
        auction_doc: Dict[str, Any],
        message: str,
        item_id: Optional[str] = None,
    ) -> int:
        users = await self._load_auction_users(auction_doc=auction_doc)
        all_user_ids = {str(doc["_id"]) for doc in users}
        return await self._notify_users(
            auction_id=str(auction_doc["_id"]),
            user_ids=all_user_ids,
            message=message,
            item_id=item_id,
            audience="ALL",
        )

    async def _update_users_table(# keeps users_table synced with current participants
        self,
        *,
        auction_doc: Dict[str, Any],
        changed_user_ids: set[str],
        session=None,
    ) -> list[Dict[str, Any]]:
        participant_ids = {_normalize_user_id_text(v) for v in auction_doc.get("participants", [])}
        participant_ids.discard("")
        if not participant_ids:
            return []

        current_table = list(auction_doc.get("users_table", []))
        if not current_table:
            return await self._auction_service.build_users_table(auction_doc=auction_doc, session=session)

        rows_by_user_id: Dict[str, Dict[str, Any]] = {}
        for row in current_table:
            row_user_id = _normalize_user_id_text(row.get("user_id", ""))
            if row_user_id:
                rows_by_user_id[row_user_id] = row

        normalized_changed = {_normalize_user_id_text(uid) for uid in changed_user_ids}
        normalized_changed.discard("")
        target_ids = {uid for uid in normalized_changed if uid in participant_ids}
        for target_id in target_ids:
            row = await self._auction_service.build_user_table_row(user_id=target_id, session=session)
            if row:
                rows_by_user_id[target_id] = row
            else:
                rows_by_user_id.pop(target_id, None)

        # Keep table aligned to all current participants; backfill missing rows.
        missing_ids = [uid for uid in participant_ids if uid not in rows_by_user_id]
        for missing_id in missing_ids:
            row = await self._auction_service.build_user_table_row(user_id=missing_id, session=session)
            if row:
                rows_by_user_id[missing_id] = row

        normalized_rows = [rows_by_user_id[uid] for uid in participant_ids if uid in rows_by_user_id]
        normalized_rows.sort(key=lambda row: (row.get("user_name") or "").lower())
        return normalized_rows

    async def can_bid(
        self,
        *,
        user: Dict[str, Any],
        item: Dict[str, Any],
        auction_state: Dict[str, Any],
        user_id: str,
        item_id: str,
        session=None,
    ) -> tuple[bool, str]:
        if auction_state.get("status") != "RUNNING":
            return False, "Auction is not running."

        invited = {str(v) for v in auction_state.get("invited_user_ids", [])}
        participants = {str(v) for v in auction_state.get("participants", [])}
        if user_id not in invited:
            return False, "User is not invited to this auction."
        if user_id not in participants:
            return False, "User must join the auction before bidding."

        auction_id = str(auction_state.get("_id"))
        item_doc = item
        if not item_doc:
            item_doc = await self._items.find_one({"_id": ObjectId(item_id)}, session=session)
        if not item_doc:
            return False, "Item not found."
        if item_doc.get("auction_id") != auction_id:
            return False, "Item is not assigned to this auction."
        item_auction_id = item_doc.get("auction_id")
        # Item binding now lives on the item document itself; do not rely on auction.selected_item_ids here.
        if item_auction_id in (None, "", False):
            return False, "Item is not assigned to this auction."
        if str(item_auction_id) != str(auction_state.get("_id", auction_state.get("auction_id", ""))):
            return False, "Item is locked by another running auction."
        item_status = str(item_doc.get("status", "AVAILABLE"))
        if item_status == "SOLD":
            return False, "Item is not available."
        if item_status == "PRE-SOLD" and str(self._current_highest_bidder_id(item_doc) or "") != str(user_id):
            return False, "Item is pre-sold and cannot be outbid."
        if item_status not in {"AVAILABLE", "TEMPORARILY-OWNED", "PRE-SOLD"}:
            return False, "Item is not available."

        now = _utc_now()

        join_deadline = _ensure_utc(auction_state.get("join_deadline", auction_state.get("initial_bid_deadline")))

        if join_deadline and now > join_deadline:
            # Past the initial 30-minute window: only users who already placed a bid may continue bidding.
            # (They "participated" on time.)
            if not bool(user.get("has_bid", False)):
                return False, "Initial bid window has closed (first 30 minutes). You can no longer place your first bid."
        item_highest_bid = int(item_doc.get("highest_bid", 0))
        if int(user.get("balance_amount", 0)) <= item_highest_bid:
            return False, "User balance must be strictly greater than current highest bid."

        if bool(user.get("balance_committed", False)):
            return False, "User already has committed balance on another active bid."

        current_highest_bidder_id = str(self._current_highest_bidder_id(item_doc) or "").strip()
        if current_highest_bidder_id and current_highest_bidder_id != str(user_id):
            ranked = await self._ranked_participants(auction_state=auction_state, session=session)
            rank_index = self._rank_index(ranked)
            bidder_rank = rank_index.get(str(user_id))
            highest_bidder_rank = rank_index.get(current_highest_bidder_id)
            if bidder_rank is None:
                return False, "User is not ranked for this auction."
            if highest_bidder_rank is None:
                return False, "Current leader rank is unavailable."
            if bidder_rank >= highest_bidder_rank:
                return False, "Only higher-ranked participants can outbid the current leader."

        return True, "Eligible to bid."

    async def place_bid(self, *, current_user: object, auction_id: str, item_id: str) -> Dict[str, Any]:
        if not ObjectId.is_valid(item_id):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid item_id.")
        auction_id = str(auction_id).strip()
        if not auction_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid auction_id.")

        client = _get_motor_client_from_collection(self._users)
        auth_user_id = _extract_user_id(current_user)

        async def _txn_body(session) -> Tuple[Dict[str, Any], list[NotificationCall]]:
            deferred: list[NotificationCall] = []

            # 1) Load docs inside txn
            user_doc = await self._users.find_one(
                _user_id_query(auth_user_id),
                session=session,
            )
            if not user_doc:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
            user_id_str = str(user_doc["_id"])

            auction_doc = await self._auction.find_one(
                {**self._auction_id_query(auction_id), "status": "RUNNING"},
                session=session,
            )
            if not auction_doc:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Auction is not running.")

            item_object_id = ObjectId(item_id)
            item_doc = await self._items.find_one({"_id": item_object_id}, session=session)
            if not item_doc:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found.")

            ok, reason = await self.can_bid(
                user=user_doc,
                item=item_doc,
                auction_state=auction_doc,
                user_id=user_id_str,
                item_id=item_id,
                session=session,
            )
            if not ok:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=reason)

            now = _utc_now()
            previous_bidder_id = self._current_highest_bidder_id(item_doc)
            bid_value = int(user_doc.get("balance_amount", 0))
            item_name = item_doc.get("name") or item_id

            # 2) Item CAS update (prevents lost updates)
            item_highest_bid = int(item_doc.get("highest_bid", item_doc.get("highest_bid", 0)))
            if bid_value <= item_highest_bid:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Bid no longer exceeds current highest bid.",
                )

            prev_highest_bid = item_highest_bid
            prev_owner_id = self._current_highest_bidder_id(item_doc)

            item_update_res = await self._items.update_one(# CAS update to ensure item is still available and no higher bid has been placed since we read it
                {
                    "_id": item_object_id,
                    "status": {"$in": ["AVAILABLE", "TEMPORARILY-OWNED"]},
                    "$and": [
                        {
                            "$or": [
                                {"auction_id": auction_id},
                                {"$and": [{"auction_id": None}, {"active_auction_id": auction_id}]},#just in case there's still old active_auction_id not been migrated.
                                {"$and": [{"auction_id": {"$exists": False}}, {"active_auction_id": auction_id}]},
                            ]
                        },
                        {
                            "$or": [
                                {"highest_bid": {"$lt": bid_value}},
                                {"highest_bid": {"$exists": False}},
                            ]
                        },
                    ],
                },
                {
                    "$set": {
                        "highest_bid": bid_value,
                        "highest_bidder_id": user_id_str,
                        "status": "TEMPORARILY-OWNED",
                        "updated_at": now,
                    },
                    "$unset": {"temp_owner": ""},
                },
                session=session,
            )
            if item_update_res.matched_count == 0:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Bid conflict: item changed. Retry.",
                )

            # 3) Lock current bidder (same as you had)
            await self._users.update_one(
                {"_id": user_doc["_id"]},
                {
                    "$set": {
                        "held_item_id": item_id,
                        "before_bid_amount": bid_value,
                        "balance_amount": 0,
                        "balance_committed": True,
                        "committed_item_id": item_id,
                        "has_bid": True,
                        "updated_at": now,
                    },
                    "$inc": {"bid_counter": 1},
                },
                session=session,
            )

            # 4) Refund previous bidder (use captured prev_owner_id + guard prev_highest_bid > 0)
            if prev_owner_id and str(prev_owner_id) != user_id_str and prev_highest_bid > 0:
                #if there's a previous bidder, refund them by unlocking their balance and setting it back to the previous highest bid (which is what they were effectively paying before this new bid outbid them). Also clear their held/committed item since they're no longer winning that item. 
                previous_user = await self._users.find_one(
                    _user_id_query(str(prev_owner_id)),
                    session=session,
                )
                if previous_user:
                    await self._users.update_one(
                        {"_id": previous_user["_id"]},
                        {
                            "$set": {
                                "balance_amount": int(prev_highest_bid),
                                "balance_committed": False,
                                "before_bid_amount": 0,
                                "held_item_id": None,
                                "committed_item_id": None,
                                "updated_at": now,
                            }
                        },
                        session=session,
                    )

            # 4.5) Resolve provisional ownership status using rank-based outbid eligibility.
            derived_item_status = await self._derive_item_status_after_bid(
                auction_state=auction_doc,
                new_bidder_id=user_id_str,
                current_highest_bid=bid_value,
                session=session,
            )
            await self._items.update_one(
                {"_id": item_object_id},
                {"$set": {"status": derived_item_status, "updated_at": now}},
                session=session,
            )

            # 5) Insert bid record
            bid_doc = {"auction_id": auction_id, "item_id": item_id, "bidder_id": user_id_str, "amount": bid_value, "timestamp": now}
            bid_result = await self._bids.insert_one(bid_doc, session=session)
            bid_id = str(bid_result.inserted_id)

            # 6) Update auction global-highest
            auction_highest_bid = int(auction_doc.get("highest_bid", 0))
            if bid_value > auction_highest_bid:
                await self._auction.update_one(
                    {"_id": auction_doc["_id"]},
                    {
                        "$set": {
                            "highest_bid": bid_value,
                            "highest_bidder_name": user_doc.get("name") or user_doc.get("email"),
                            "highest_bidder_id": user_id_str,
                            "updated_at": now,
                        }
                    },
                    session=session,
                )

            # 7) Timer extension must be in txn (pass session!)
            ends_at = _ensure_utc(auction_doc.get("ends_at", auction_doc.get("end_time")))
            if ends_at and (ends_at - now) <= timedelta(minutes=10):
                await self._auction_service.extend_timer(
                    auction_id=auction_id,
                    delta_seconds=180,
                    by_user_id=user_id_str,
                    reason="late_bid",
                    bid_id=bid_id,
                    session=session,  # <-- MUST be session, not None
                    defer_notifications=True,  # <-- see next section
                )

            # 8) users_table update + store
            refreshed_auction_doc = await self._auction.find_one({"_id": auction_doc["_id"]}, session=session) or auction_doc
            changed_user_ids = {user_id_str}
            if prev_owner_id:
                changed_user_ids.add(str(prev_owner_id))
            users_table = await self._update_users_table(
                auction_doc=refreshed_auction_doc,
                changed_user_ids=changed_user_ids,
                session=session,
            )

            await self._auction.update_one(
                {"_id": auction_doc["_id"]},
                {"$set": {"users_table": users_table, "updated_at": now}},
                session=session,
            )

            # Reload for response (still inside txn snapshot)
            updated_item = await self._items.find_one({"_id": item_object_id}, session=session)
            updated_user = await self._users.find_one({"_id": user_doc["_id"]}, session=session)
            updated_auction = await self._auction.find_one({"_id": auction_doc["_id"]}, session=session)

            # 9) Defer notifications until AFTER commit (no session)
            deferred.append(
                lambda auction_doc=auction_doc, item_name=item_name, user_id_str=user_id_str: self.NotifyAdmin(
                    auction_doc=auction_doc,
                    message=f"{user_doc.get('name') or user_doc.get('email') or user_id_str} bid on {item_name}",
                    item_id=item_id,
                )
            )

            should_send_leading = await self._should_send_user_message(
                user_id=user_id_str,
                message_type="LEADING",
                session=session,
            )
            if should_send_leading:
                deferred.append(
                    lambda auction_id=auction_id, user_id_str=user_id_str, item_id=item_id, item_name=item_name: _insert_user_message(
                        messages_collection=self._messages,
                        auction_id=auction_id,
                        user_id=user_id_str,
                        item_id=item_id,
                        msg_type="LEADING",
                        message=f"You are leading on item {item_name}.",
                    )
                )
            # Store a user-targeted outbid WS payload so it can be enqueued with the rest of the room events.
            outbid_ws_event: Optional[dict[str, Any]] = None

            # If there was a previous bidder who is now outbid, notify them as well
            if previous_bidder_id and str(previous_bidder_id) != user_id_str:
                prev_id_str = str(previous_bidder_id)
                should_send_outbid = await self._should_send_user_message(
                    user_id=prev_id_str,
                    message_type="OUTBID",
                    session=session,
                )
                if should_send_outbid:
                    deferred.append(
                        lambda auction_id=auction_id, prev_id_str=prev_id_str, item_id=item_id, item_name=item_name: _insert_user_message(
                            messages_collection=self._messages,
                            auction_id=auction_id,
                            user_id=prev_id_str,
                            item_id=item_id,
                            msg_type="OUTBID",
                            message=f"You were outbid on item {item_name}.",
                        )
                    )
                    # The room still broadcasts this to everyone in the auction, but frontend can ignore it unless user_id matches.
                    outbid_ws_event = ws_event(
                        "auction.message",
                        auction_id=auction_id,
                        user_id=prev_id_str,#we include outbid user's id so that frontend can choose to show this event only to the specific user.
                        item_id=item_id,
                        message={
                            "type": "OUTBID",
                            "content": f"You were outbid on item {item_name}.",
                        },
                    )
                deferred.append(
                    lambda auction_id=auction_id, prev_id_str=prev_id_str, item_id=item_id, item_name=item_name: self._send_email_notification(
                        user_id=prev_id_str,
                        message_type="OUTBID",
                        content=f"You were outbid on item {item_name}.",
                        item_id=item_id,
                    )
                )

            result_payload = {
                "success": True,
                "updated_item": ItemOut.model_validate(updated_item or item_doc),
                "updated_user": UserOut.model_validate(updated_user or user_doc),
                "auction_state": AuctionStateOut.model_validate(updated_auction or auction_doc),
                "users_table": users_table,
                "message": "Bid accepted.",
                "bid_amount": bid_value,
                "previous_highest_bid": prev_highest_bid,
                "bid_time": now,
            }

            state_payload = result_payload["auction_state"].model_dump(mode="json")#prepare auction state payload for websocket event (convert to JSON-serializable dict)
            if self._ws_outbox is not None:
                events = []
                if len(updated_auction.get("extensions", [])) > len(auction_doc.get("extensions", [])):
                    latest_extension = updated_auction.get("extensions", [])[-1]
                    events.append(
                        ws_event(
                            EVENT_AUCTION_TIMER_EXTENDED,
                            auction_id=auction_id,
                            reason="late_bid",
                            extension=latest_extension,
                            state=state_payload,
                        )
                    )
                events.extend(
                    [
                        ws_event(EVENT_AUCTION_STATE_UPDATED, auction_id=auction_id, state=state_payload),
                        ws_event(
                            EVENT_BID_PLACED,
                            auction_id=auction_id,
                            item_id=item_id,
                            bid_amount=bid_value,
                        ),
                    ]
                )
                # Push the outbid notice through the same outbox dispatcher used for the other live auction updates.
                if outbid_ws_event is not None:
                    events.append(outbid_ws_event)
                await enqueue_ws_events(
                    self._ws_outbox,
                    auction_id=auction_id,
                    events=events,
                    session=session,
                )
            return result_payload, deferred

        # Run txn with retries
        payload, deferred_notifications = await _run_txn_with_retries(client, _txn_body, max_retries=5)

        # After commit: run notifications
        for notify in deferred_notifications:
            try:
                await notify()
            except Exception:
                # log this (don't fail the request)
                pass

        return payload

    async def get_eligibility(self, *, current_user: object, auction_id: str, item_id: str) -> Dict[str, Any]:
        if not ObjectId.is_valid(item_id):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid item_id.")
        auction_id = str(auction_id).strip()
        if not auction_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid auction_id.")

        user_id_str = _extract_user_id(current_user)
        user_doc = await self._users.find_one(_user_id_query(user_id_str))
        item_doc = await self._items.find_one({"_id": ObjectId(item_id)})
        auction_doc = await self._auction.find_one(
            {**self._auction_id_query(auction_id), "status": "RUNNING"}
        )

        if not user_doc or not item_doc or not auction_doc:
            return {"eligible": False, "reason": "Missing user, item, or auction state."}

        eligible, reason = await self.can_bid(
            user=user_doc,
            item=item_doc,
            auction_state=auction_doc,
            user_id=str(user_doc["_id"]),
            item_id=item_id,
        )
        return {"eligible": eligible, "reason": reason}
