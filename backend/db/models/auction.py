from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from bson import ObjectId

APP_TIMEZONE = ZoneInfo("America/Toronto")

AUCTION_STATUSES = {
    "PENDING",
    "ACTIVE",
    "CLOSED",
}

@dataclass
class AuctionDoc:
    id: str
    name: str
    status: str
    item_ids: list[str]
    created_at: datetime
    started_at: datetime | None
    ended_at: datetime | None

    @staticmethod
    def from_doc(doc: dict[str, Any]) -> "AuctionDoc":
        """builds an AuctionDoc from document returned by mongodb"""
        return AuctionDoc(
            id=str(doc["_id"]),
            name=doc["name"],
            status=doc.get("status", "PENDING"),
            item_ids=[str(oid) for oid in doc.get("item_ids", [])],
            created_at=doc.get("created_at", datetime.now(APP_TIMEZONE)),
            started_at=doc.get("started_at"),
            ended_at=doc.get("ended_at"),
        )

    @staticmethod
    def new_doc(name: str, item_ids: list[ObjectId] | None = None) -> dict[str, Any]:
        """returns a dict ready for insert_one()"""
        return {
            "name": name,
            "status": "PENDING",
            "item_ids": item_ids or [],
            "created_at": datetime.now(APP_TIMEZONE),
            "started_at": None,
            "ended_at": None,
        }
