from __future__ import annotations

from bson import ObjectId #Mongo uses BSON ObjectIds as default identifiers, but our API currently uses string IDs. This import allows us to work with ObjectIds when interacting with MongoDB.
from typing import Any, Dict, Optional

from app.users.user_schemas import UserOut
from app.helper.timezone import now_in_app_timezone

from app.helper.helpers import _get_user_settings

class UsersService:
    # Thin service wrapper around a Motor collection.
    def __init__(self, *, collection) -> None:
        self._collection = collection

    async def create_user(self, *, payload_serve: Dict[str, Any]) -> UserOut:
        # Insert and return the created user. Password handling is temporary.
        now = now_in_app_timezone()
        doc = payload_serve.copy()
        doc.setdefault("balance_amount", 0)
        doc.setdefault("balance_committed", False)
        doc.setdefault("has_bid", False)
        doc.setdefault("gift_card_winner", False)
        doc["updated_at"] = now
        doc.setdefault("created_at", now)

        result = await self._collection.insert_one(doc)
        inserted = await self._collection.find_one({"_id": result.inserted_id})
        final_doc = inserted or {**doc, "_id": result.inserted_id} # Even if find_one fails, we can still return the inserted data with the generated _id.
        return UserOut.model_validate(final_doc) # Converts Mongo's _id into id string and validates the output dictionary against the UserOut Pydantic model.

    async def delete_user(self, *, user_id_serve: str) -> bool:
        # Delete by the legacy integer `id` field used by the current users router.
        if not ObjectId.is_valid(user_id_serve):
            return False
        result = await self._collection.delete_one({"_id": ObjectId(user_id_serve)})
        return result.deleted_count > 0

    async def update_user(self, *, user_id_serve: str, updates_serve: Dict[str, Any]) -> Optional[UserOut]:
        # Patch fields and return the updated user.
        if not updates_serve:
            return None
        if not ObjectId.is_valid(user_id_serve):
                return None
        updates = updates_serve.copy()
        updates["updated_at"] = now_in_app_timezone()

        await self._collection.update_one({"_id": ObjectId(user_id_serve)}, {"$set": updates})
        doc = await self._collection.find_one({"_id": ObjectId(user_id_serve)})
        if not doc:
            return None
        return UserOut.model_validate(doc)

    async def read_user(self, *, user_id_serve: str):
        if not ObjectId.is_valid(user_id_serve):
            return None
        doc = await self._collection.find_one({"_id": ObjectId(user_id_serve)})
        if not doc:
            return None
        return UserOut.model_validate(doc)

    async def set_user_balance(self, *, user_id_serve: str, kogbucks: int) -> Optional[UserOut]:
        if not ObjectId.is_valid(user_id_serve):
            return None

        now = now_in_app_timezone()
        await self._collection.update_one(
            {"_id": ObjectId(user_id_serve)},
            {
                "$set": {
                    "balance_amount": kogbucks,
                    "kogbucks": kogbucks,
                    "balance_committed": False,
                    "before_bid_amount": 0,
                    "held_item_id": None,
                    "committed_item_id": None,
                    "updated_at": now,
                }
            },
        )
        doc = await self._collection.find_one({"_id": ObjectId(user_id_serve)})
        if not doc:
            return None
        return UserOut.model_validate(doc)
        
    async def update_settings(self, *, user_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if not updates:
            return None
        if not user_id:
            return None
        await self._collection.update_one(
            {"_id": ObjectId(user_id)},
            {"$set": {
                "settings": updates
            }})
        doc = await _get_user_settings(user_id=user_id, users_collection=self._collection)
        return doc

    async def get_settings(self, *, user_id: str) -> Optional[Dict[str, Any]]:
        if not user_id:
            return None
        doc = await _get_user_settings(user_id=user_id, users_collection=self._collection)
        return doc

