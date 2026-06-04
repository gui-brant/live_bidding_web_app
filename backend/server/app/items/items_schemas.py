from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from bson import ObjectId
from pydantic import BaseModel, ConfigDict, Field, field_validator

DEFAULT_ITEM_IMAGE_URL = "https://placehold.co/600x400?text=Item"


# ----------------------------
# Requests

class ItemCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1, description="Item name.")
    description: Optional[str] = Field(default=None, description="Optional item description.")
    image_url: str = Field(..., min_length=1, description="Image URL for the item.")


class ItemUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # PATCH fields should be Optional[...] = None so omission means "don't change it"
    name: Optional[str] = Field(default=None, min_length=1, description="Item name.")
    description: Optional[str] = Field(default=None, description="Item description.")
    image_url: Optional[str] = Field(default=None, min_length=1, description="Image URL for the item.")


# ----------------------------
# Responses

class ItemOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    # Accept Mongo "_id" input, expose as "id" in API
    id: str = Field(..., alias="_id", description="Item id as string.")

    name: str
    description: Optional[str] = None
    image_url: str = Field(default=DEFAULT_ITEM_IMAGE_URL, min_length=1)
    status: Literal["AVAILABLE", "SOLD", "PRE-SOLD", "TEMPORARILY-OWNED"] = "AVAILABLE"

    highest_bid: int = Field(default=0, ge=0)

    highest_bidder_id: Optional[str] = None
    winner_user_id: Optional[str] = None
    active_auction_id: Optional[str] = None

    selected_for_auction: bool = False
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    @field_validator("image_url", mode="before")
    @classmethod
    def _normalize_image_url(cls, value: Any) -> str:
        text = str(value or "").strip()
        return text or DEFAULT_ITEM_IMAGE_URL

    # --- Validators to normalize ObjectId -> str for all id-like fields ---

    @field_validator("id", mode="before")
    @classmethod
    def _id_to_str(cls, v: Any) -> Any:
        if isinstance(v, ObjectId):
            return str(v)
        return v

    @field_validator("highest_bidder_id", "winner_user_id", "active_auction_id", mode="before")
    @classmethod
    def _maybe_object_id_to_str(cls, v: Any) -> Any:
        # If any of these are stored as ObjectId in Mongo, normalize to str.
        if isinstance(v, ObjectId):
            return str(v)
        return v


class ItemsList(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[ItemOut]
