from __future__ import annotations

from typing import Any, Dict, Optional, List

from bson import ObjectId

from .items_schemas import DEFAULT_ITEM_IMAGE_URL, ItemOut
from app.helper.timezone import now_in_app_timezone


def _normalize_item_doc(doc: Dict[str, Any]) -> Dict[str, Any]:
    # Canonical ownership field is highest_bidder_id; tolerate legacy temp_owner on old records.
    normalized = dict(doc)
    if normalized.get("highest_bidder_id") is None and normalized.get("temp_owner") is not None:
        normalized["highest_bidder_id"] = normalized.get("temp_owner")
    normalized.pop("temp_owner", None)
    raw_image = normalized.get("image_url")
    normalized["image_url"] = str(raw_image or "").strip() or DEFAULT_ITEM_IMAGE_URL
    return normalized


class ItemsService:
    def __init__(self, *, collection) -> None:
        self._collection = collection

    async def create_item(self, *, name: str, description: Optional[str], image_url: str) -> ItemOut:
        now = now_in_app_timezone()

        doc: Dict[str, Any] = {
            "name": name,
            "description": description,
            "image_url": image_url.strip(),
            "status": "AVAILABLE",
            "highest_bid": 0,
            "highest_bidder_id": None,
            "winner_user_id": None,
            "active_auction_id": None,
            "selected_for_auction": False,
            "created_at": now,
            "updated_at": now,
        }

        result = await self._collection.insert_one(doc)
        inserted = await self._collection.find_one({"_id": result.inserted_id})
        final_doc = inserted or {**doc, "_id": result.inserted_id}

        return ItemOut.model_validate(_normalize_item_doc(final_doc))

    async def list_items(self) -> List[ItemOut]:
        cursor = self._collection.find({})
        return [ItemOut.model_validate(_normalize_item_doc(doc)) async for doc in cursor]

    async def get_item(self, *, item_id_serve: str) -> Optional[ItemOut]:
        if not ObjectId.is_valid(item_id_serve):
            return None
        doc = await self._collection.find_one({"_id": ObjectId(item_id_serve)})
        if not doc:
            return None
        return ItemOut.model_validate(_normalize_item_doc(doc))

    async def delete_item(self, *, item_id_serve: str) -> bool:
        if not ObjectId.is_valid(item_id_serve):
            return False
        result = await self._collection.delete_one({"_id": ObjectId(item_id_serve)})
        return result.deleted_count > 0

    async def update_item(self, *, item_id_serve: str, updates_serve: Dict[str, Any]) -> Optional[ItemOut]:
        if not updates_serve:
            return None
        if not ObjectId.is_valid(item_id_serve):
            return None

        updates = updates_serve.copy()
        updates["updated_at"] = now_in_app_timezone()

        await self._collection.update_one({"_id": ObjectId(item_id_serve)}, {"$set": updates})
        doc = await self._collection.find_one({"_id": ObjectId(item_id_serve)})
        if not doc:
            return None
        return ItemOut.model_validate(_normalize_item_doc(doc))
