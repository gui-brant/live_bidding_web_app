from __future__ import annotations

import base64
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from bson import ObjectId

from .wishlist_schemas import (
    WishlistAggItem,
    WishlistAggResponse,
    WishlistItemDetail,
    WishlistItemOut,
    WishlistRepEntry,
)
from app.helper.timezone import now_in_app_timezone

# Images are stored alongside the code in backend/server/app/wishlist/uploads/
UPLOAD_DIR = Path(__file__).resolve().parent / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_WISHLIST_IMAGE = "https://placehold.co/600x400?text=Wishlist+Item"


def _save_image(image_base64: str) -> str:
    """Decode a base64 image and save to the uploads folder. Returns the filename."""
    data = base64.b64decode(image_base64)
    filename = f"{uuid.uuid4().hex}.png"
    (UPLOAD_DIR / filename).write_bytes(data)
    return filename


class WishlistService:
    def __init__(self, *, collection, users_collection) -> None:
        self._col = collection
        self._users = users_collection

    # ---- rep helpers --------------------------------------------------------

    async def add_item(
        self,
        *,
        user_id: str,
        name: str,
        category: str,
        image_base64: Optional[str] = None,
    ) -> WishlistItemOut:
        now = now_in_app_timezone()
        if image_base64:
            filename = _save_image(image_base64)
            image_url = f"/wishlist/images/{filename}"
        else:
            image_url = DEFAULT_WISHLIST_IMAGE

        # fetch user info for denormalisation
        user_doc = await self._users.find_one({"_id": {"$in": _candidate_ids(user_id)}})
        user_email = user_doc.get("email", "") if user_doc else ""
        user_name = user_doc.get("name", user_doc.get("display_name", "")) if user_doc else ""

        doc: Dict[str, Any] = {
            "user_id": user_id,
            "user_email": user_email,
            "user_name": user_name,
            "name": name.strip().lower(),
            "category": category,
            "image_url": image_url,
            "created_at": now,
        }
        result = await self._col.insert_one(doc)
        inserted = await self._col.find_one({"_id": result.inserted_id})
        return WishlistItemOut.model_validate(inserted or {**doc, "_id": result.inserted_id})

    async def list_my_items(self, *, user_id: str) -> List[WishlistItemOut]:
        cursor = self._col.find({"user_id": user_id})
        return [WishlistItemOut.model_validate(doc) async for doc in cursor]

    async def delete_item(self, *, item_id: str, user_id: str) -> bool:
        if not ObjectId.is_valid(item_id):
            return False
        result = await self._col.delete_one({"_id": ObjectId(item_id), "user_id": user_id})
        return result.deleted_count > 0

    # ---- admin helpers ------------------------------------------------------

    async def aggregate_for_admin(self) -> WishlistAggResponse:
        """Return counts grouped by (category, name) for pie charts."""
        pipeline = [
            {"$group": {"_id": {"category": "$category", "name": "$name"}, "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
        ]
        results: Dict[str, List[WishlistAggItem]] = {"physical": [], "giftcard": []}
        async for doc in self._col.aggregate(pipeline):
            cat = doc["_id"]["category"]
            name = doc["_id"]["name"]
            count = doc["count"]
            if cat in results:
                results[cat].append(WishlistAggItem(name=name, count=count))
        return WishlistAggResponse(physical=results["physical"], giftcard=results["giftcard"])

    async def item_detail(self, *, name: str, category: str) -> WishlistItemDetail:
        """Return all reps who wishlisted a specific item, sorted by popularity."""
        cursor = self._col.find({"name": name, "category": category})
        reps: List[WishlistRepEntry] = []
        async for doc in cursor:
            reps.append(
                WishlistRepEntry(
                    user_id=str(doc["user_id"]),
                    user_email=doc.get("user_email", ""),
                    user_name=doc.get("user_name", ""),
                    image_url=doc.get("image_url"),
                )
            )
        count = len(reps)
        return WishlistItemDetail(name=name, category=category, count=count, reps=reps)


def _candidate_ids(user_id: str) -> list:
    vals: list[object] = [user_id]
    if ObjectId.is_valid(user_id):
        vals.append(ObjectId(user_id))
    return vals
