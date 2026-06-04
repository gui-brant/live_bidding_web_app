from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

APP_TIMEZONE = ZoneInfo("America/Toronto")

# define the valid account types. we replace anything that isn't in the set
ACCOUNT_TYPES = {
    "admin",
    "rep",
}

# representation of a user document
@dataclass
class UserDoc:
    id: str
    email: str
    name: str
    type: str
    balance: int
    balance_locked: bool
    active_bid_item_id: str | None
    created_at: datetime

    @staticmethod
    def from_doc(doc: dict[str, Any]) -> "UserDoc":
        """build a UserDoc from a document returned by mongodb."""
        return UserDoc(
            id=str(doc["_id"]),
            email=doc["email"],
            name=doc.get("name", ""),
            type=doc.get("type", "rep"),
            balance=int(doc.get("balance", 0)),
            balance_locked=bool(doc.get("balance_locked", False)),
            active_bid_item_id=(
                str(doc["active_bid_item_id"]) if doc.get("active_bid_item_id") else None
            ),
            created_at=doc.get("created_at", datetime.now(APP_TIMEZONE)),
        )

    @staticmethod
    def new_doc(
        email: str,
        name: str = "",
        account_type: str = "rep",
        balance: int = 0,
    ) -> dict[str, Any]:
        """returns a dict of a user ready for insert_one()"""
        return {
            "email": email.strip().lower(),
            "name": name,
            "type": account_type if account_type in ACCOUNT_TYPES else "rep",
            "balance": balance,
            "balance_locked": False,
            "active_bid_item_id": None,
        }
