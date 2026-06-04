from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.auction.auction_schemas import AuctionStateOut
from app.items.items_schemas import ItemOut
from app.users.user_schemas import UserOut


class BidPlaceIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    auction_id: str = Field(..., min_length=1)
    item_id: str = Field(..., min_length=1)


class BidResultOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    success: bool
    updated_item: ItemOut
    updated_user: UserOut
    auction_state: AuctionStateOut
    users_table: list[dict[str, Any]] = Field(default_factory=list)  # leave as-is for now
    message: Optional[str] = None

    # Optional “nice to have” fields (won’t break existing clients)
    bid_amount: Optional[int] = None
    previous_highest_bid: Optional[int] = None
    bid_time: Optional[datetime] = None
