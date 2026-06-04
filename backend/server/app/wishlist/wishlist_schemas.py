from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from bson import ObjectId
from pydantic import BaseModel, ConfigDict, Field, field_validator


# ----------------------------
# Requests

class WishlistItemCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1, description="Wishlist item name.")
    category: Literal["physical", "giftcard"] = Field(..., description="Type of wishlist item.")
    # image_base64 is optional; if provided will be stored server-side
    image_base64: Optional[str] = Field(default=None, description="Optional base64-encoded image string.")


class WishlistItemUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Optional[str] = Field(default=None, min_length=1)
    category: Optional[Literal["physical", "giftcard"]] = None
    image_base64: Optional[str] = None


# ----------------------------
# Responses

class WishlistItemOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    id: str = Field(..., alias="_id", serialization_alias="id", description="Wishlist item id.")
    user_id: str = Field(..., description="Owner rep user id.")
    user_email: Optional[str] = None
    user_name: Optional[str] = None
    name: str
    category: Literal["physical", "giftcard"]
    image_url: Optional[str] = None
    created_at: Optional[datetime] = None

    @field_validator("id", "user_id", mode="before")
    @classmethod
    def _oid_to_str(cls, v: Any) -> Any:
        if isinstance(v, ObjectId):
            return str(v)
        return v


class WishlistItemsList(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[WishlistItemOut]


# --- Admin aggregation helpers ---

class WishlistAggItem(BaseModel):
    """A single slice for the pie chart."""
    name: str
    count: int


class WishlistAggCategory(BaseModel):
    category: Literal["physical", "giftcard"]
    items: list[WishlistAggItem]


class WishlistAggResponse(BaseModel):
    physical: list[WishlistAggItem]
    giftcard: list[WishlistAggItem]


class WishlistRepEntry(BaseModel):
    """One rep who wishlisted a specific item."""
    user_id: str
    user_email: str
    user_name: str
    image_url: Optional[str] = None

    @field_validator("user_id", mode="before")
    @classmethod
    def _oid_to_str(cls, v: Any) -> Any:
        if isinstance(v, ObjectId):
            return str(v)
        return v


class WishlistItemDetail(BaseModel):
    """Detail view when a pie-chart slice is clicked."""
    name: str
    category: Literal["physical", "giftcard"]
    count: int
    reps: list[WishlistRepEntry]
