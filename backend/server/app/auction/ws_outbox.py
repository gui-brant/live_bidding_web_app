from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any, Awaitable, Callable, Optional
from fastapi.encoders import jsonable_encoder
from app.helper.timezone import now_in_app_timezone

logger = logging.getLogger(__name__)
STATUS_PENDING = "PENDING"
STATUS_PROCESSING = "PROCESSING"
STATUS_SENT = "SENT"

def _utc_now() -> datetime:
    return now_in_app_timezone()

def _next_retry_at(*, attempts: int, base_seconds: float, max_seconds: float) -> datetime:
    delay = min(max_seconds, base_seconds * (2 ** max(0, attempts - 1)))
    return _utc_now() + timedelta(seconds=delay)

async def enqueue_ws_events(#helper function to add multiple WebSocket events to the outbox collection for a given auction, 
    ws_outbox_collection,
    *,
    auction_id: str,
    events: list[dict[str, Any]],
    session=None,#with optional session for transactional context
) -> None:
    if not events:
        return
    now = _utc_now()
    docs = []
    for payload in events:
        docs.append(
            {
                "auction_id": auction_id,
                "payload": jsonable_encoder(payload),
                "status": STATUS_PENDING,
                "attempt_count": 0,
                "next_attempt_at": now,
                "created_at": now,
                "updated_at": now,
                "sent_at": None,
                "last_error": None,
            }
        )
    await ws_outbox_collection.insert_many(docs, session=session)


async def enqueue_ws_event(#add single WS event to queue
    ws_outbox_collection,
    *,
    auction_id: str,
    event: dict[str, Any],
    session=None,
) -> None:
    await enqueue_ws_events(
        ws_outbox_collection,
        auction_id=auction_id,
        events=[event],
        session=session,
    )


class WsOutboxDispatcher:
    # Background dispatcher that drains Mongo outbox and pushes to websocket rooms.
    def __init__(
        self,
        *,
        ws_outbox_collection,
        broadcast_func: Callable[..., Awaitable[None]],
        poll_interval_seconds: float = 0.25,
        max_batch_size: int = 100,
        retry_base_seconds: float = 0.5,
        retry_max_seconds: float = 10.0,
        processing_timeout_seconds: float = 30.0,
    ) -> None:
        self._outbox = ws_outbox_collection
        self._broadcast_func = broadcast_func
        self._poll_interval = max(0.05, float(poll_interval_seconds))
        self._max_batch_size = max(1, int(max_batch_size))
        self._retry_base_seconds = max(0.1, float(retry_base_seconds))
        self._retry_max_seconds = max(1.0, float(retry_max_seconds))
        self._processing_timeout_seconds = max(1.0, float(processing_timeout_seconds))
        self._task: Optional[asyncio.Task] = None
        self._running = False

    async def start(self) -> None:#start the background task that will continuously check the outbox collection for pending events 
        #and dispatch them to clients in real-time.
        if self._running:
            return
        self._running = True
        await self._ensure_indexes()
        self._task = asyncio.create_task(self._run(), name="ws-outbox-dispatcher")

    async def stop(self) -> None:# stop background dispatcher task, but ensuring that any in-progress dispatches are completed or cancelled properly.
        self._running = False
        task = self._task
        self._task = None
        if task is None:
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    async def _ensure_indexes(self) -> None:#ensure that the necessary indexes exist on the outbox collection 
        #for efficient querying of pending events and recovery of stuck events.
        try:
            await self._outbox.create_index([("status", 1), ("next_attempt_at", 1), ("created_at", 1)])
            await self._outbox.create_index([("status", 1), ("processing_started_at", 1)])
        except Exception:
            logger.exception("Failed to ensure ws_outbox indexes.")

    async def _run(self) -> None:#main loop that continuously runs while the dispatcher is active, 
        while self._running:
            try:
                await self.dispatch_once()#periodically calling dispatch_once to process pending events in batches,
            except Exception:
                logger.exception("Unhandled error while dispatching websocket outbox.")# and handling any exceptions that occur to prevent the loop from crashing.
            await asyncio.sleep(self._poll_interval)#sleeping for a configured interval between checks to balance responsiveness with resource usage.

    async def dispatch_once(self) -> int:#core method that performs a single pass of checking for pending events, claiming them for processing,
        #attempting to broadcast them to clients, and updating their status in the outbox collection    
        processed = 0
        now = _utc_now()
        reclaim_before = now - timedelta(seconds=self._processing_timeout_seconds)

        # Recover stuck items if a previous process crashed while PROCESSING.
        await self._outbox.update_many(
            {
                "status": STATUS_PROCESSING,
                "processing_started_at": {"$lt": reclaim_before},
            },
            {
                "$set": {
                    "status": STATUS_PENDING,
                    "next_attempt_at": now,
                    "updated_at": now,
                    "last_error": "Recovered stale PROCESSING job.",
                }
            },
        )

        cursor = self._outbox.find(
            {"status": STATUS_PENDING, "next_attempt_at": {"$lte": now}},
        ).sort("created_at", 1).limit(self._max_batch_size)
        docs = await cursor.to_list(length=self._max_batch_size)

        for doc in docs:
            claim = await self._outbox.update_one(
                {
                    "_id": doc["_id"],
                    "status": STATUS_PENDING,
                    "next_attempt_at": {"$lte": now},
                },
                {
                    "$set": {
                        "status": STATUS_PROCESSING,
                        "processing_started_at": now,
                        "updated_at": now,
                    }
                },
            )
            if claim.matched_count == 0:
                continue

            try:
                auction_id = str(doc.get("auction_id"))
                payload = doc.get("payload", {})
                await self._broadcast_func(auction_id=auction_id, payload=payload)
                await self._outbox.update_one(
                    {"_id": doc["_id"], "status": STATUS_PROCESSING},
                    {
                        "$set": {
                            "status": STATUS_SENT,
                            "sent_at": _utc_now(),
                            "updated_at": _utc_now(),
                            "last_error": None,
                        }
                    },
                )
                processed += 1
            except Exception as exc:
                attempts = int(doc.get("attempt_count", 0)) + 1
                await self._outbox.update_one(
                    {"_id": doc["_id"]},
                    {
                        "$set": {
                            "status": STATUS_PENDING,
                            "attempt_count": attempts,
                            "next_attempt_at": _next_retry_at(
                                attempts=attempts,
                                base_seconds=self._retry_base_seconds,
                                max_seconds=self._retry_max_seconds,
                            ),
                            "updated_at": _utc_now(),
                            "last_error": str(exc),
                        }
                    },
                )
                logger.exception("Failed to dispatch ws outbox event.")

        return processed
