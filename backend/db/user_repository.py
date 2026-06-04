from __future__ import annotations

from typing import Any
from bson import ObjectId

from .models import UserDoc

class UserRepository:
    # pass in the db collection for fetching the data
    def __init__(self, collection) -> None:
        self._col = collection

    async def get_by_email(self, email: str) -> UserDoc:
        doc = await self._col.fine_one({"email": email.strip().lower()})
        if doc is None:
            return None
        return UserDoc.from_doc(doc)

    async def get_by_id(self, user_id: str) -> Any:
        if not ObjectId.is_valid(user_id):
            return None
        doc = await self._col.find_one({"_id": ObjectId(user_id)})
        return UserDoc.from_doc(doc)
    
    async def get_balance(self, user_id: str) -> int:
        user = await self.get_by_id(user_id)
        if user is None:
            # TODO: handle error
            raise ValueError("User not found.")
        # maybe we want to do some sort of preprocessing on this value before returning
        return user.balance

    async def add_balance(self, user_id: str, amount: int) -> UserDoc:
        if amount <= 0:
            # TODO: handle error
            raise ValueError("Amount must be positive.")
        doc = await self._col.find_one_and_update(
            {"_id": ObjectId(user_id)},
            {"$inc": {"balance": amount}},
            return_document=True
        )
        # TODO: maybe this is unnecessary and this function can just be void. check if returning a doc is actually needed
        return UserDoc.from_doc(doc)

    # TODO: check how people are modelling users on the backend layer and implement accordingly
    #async def add_user(self, )

