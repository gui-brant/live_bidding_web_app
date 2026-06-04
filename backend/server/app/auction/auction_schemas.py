from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class AuctionStartIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dry_run: bool = Field(default=False)
    auction_id: Optional[str] = Field(default=None, min_length=1)


class AuctionCreateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scheduled_starts_at: datetime


class AuctionExtensionOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    at: datetime
    by_user_id: Optional[str] = None
    reason: str
    delta_seconds: int
    bid_id: Optional[str] = None


class AuctionStateOut(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    auction_id: str = Field(..., alias="_id")
    starts_at: Optional[datetime] = None
    ends_at: Optional[datetime] = None
    scheduled_starts_at: Optional[datetime] = None
    scheduled_ends_at: Optional[datetime] = None
    join_deadline: Optional[datetime] = None
    overtime_count: int = 0
    status: Literal["IDLE", "RUNNING", "ENDED"]
    selected_item_ids: list[str] = Field(default_factory=list)
    gift_card_candidate_user_ids: list[str] = Field(default_factory=list)
    invited_user_ids: list[str] = Field(default_factory=list)
    participants: list[str] = Field(default_factory=list)
    extensions: list[AuctionExtensionOut] = Field(default_factory=list)
    highest_bid: int = 0
    highest_bidder_name: Optional[str] = None
    highest_bidder_id: Optional[str] = None
    users_table: list[dict[str, Any]] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _normalize_source(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value

        get = value.get

        def _to_int(raw: Any, *, default: int = 0) -> int:#This helper function attempts to convert the input "raw" value to an integer. 
            #If the conversion fails (e.g., if "raw" is not a valid integer string or is of an incompatible type), it returns a default value (which is 0 by default).
            #This is useful for ensuring that fields expected to be integers are properly normalized, even if the input data is inconsistent.
            try:
                return int(raw)
            except (TypeError, ValueError):
                return default

        def _to_str_list(raw: Any) -> list[str]:#similarly for fields that are expected to be lists of strings
            if not isinstance(raw, (list, tuple, set)):
                return []
            return [str(item) for item in raw if item is not None]

        def _opt_str(raw: Any) -> Optional[str]:#check if raw value is None, if so return None, otherwise convert to string. 
            return None if raw is None else str(raw)

        starts_at = get("starts_at", get("start_time"))
        ends_at = get("ends_at", get("end_time"))
        join_deadline = get("join_deadline", get("initial_bid_deadline"))
        scheduled_starts_at = get("scheduled_starts_at")
        scheduled_ends_at = get("scheduled_ends_at")

        extensions_raw = get("extensions", [])#expected to be a list of dictionaries, but we need to validate and normalize each entry to ensure it has the correct structure and types.
        normalized_extensions: list[dict[str, Any]] = []
        for entry in extensions_raw if isinstance(extensions_raw, list) else []:
            if not isinstance(entry, dict):
                continue
            at = entry.get("at")
            if at is None:
                continue
            reason = entry.get("reason") or "unknown"
            normalized_extensions.append(
                {
                    "at": at,
                    "by_user_id": _opt_str(entry.get("by_user_id")),
                    "reason": reason,
                    "delta_seconds": _to_int(entry.get("delta_seconds", 0)),
                    "bid_id": _opt_str(entry.get("bid_id")),
                }
            )

        users_table = get("users_table", [])
        deadlines = get("deadlines", {})
        status = get("status") or "IDLE"
        source_id = get("auction_id", get("_id", "current"))
        normalized_id = "current" if source_id is None else str(source_id)

        return {
            "_id": normalized_id,
            "starts_at": starts_at,
            "ends_at": ends_at,
            "scheduled_starts_at": scheduled_starts_at,
            "scheduled_ends_at": scheduled_ends_at,
            "join_deadline": join_deadline,
            "overtime_count": _to_int(get("overtime_count", 0)),
            "status": status,
            "selected_item_ids": _to_str_list(get("selected_item_ids", [])),
            "gift_card_candidate_user_ids": _to_str_list(get("gift_card_candidate_user_ids", [])),
            "invited_user_ids": _to_str_list(get("invited_user_ids", [])),
            "participants": _to_str_list(get("participants", [])),
            "extensions": normalized_extensions,
            "highest_bid": _to_int(get("highest_bid", 0)),
            "highest_bidder_name": get("highest_bidder_name"),
            "highest_bidder_id": _opt_str(get("highest_bidder_id")),
            "users_table": users_table if isinstance(users_table, list) else [],
        }


class AuctionEndOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    success: bool
    status: Literal["ENDED"]
    ended_at: datetime


class AuctionJoinOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    success: bool
    joined: bool
    reconnected: bool
    message: str
    auction_id: str


class InviteUsersIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_ids: list[str] = Field(..., min_length=1)


class InviteListOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    auction_id: str
    invited_user_ids: list[str]


class ExtendTimerIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    delta_seconds: int = Field(..., ge=1)
    reason: Optional[str] = None


class ParticipantOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str
    name: Optional[str] = None
    kogbucks_total: int
    kogbucks_held: int
    bidding_power: int
    joined: Optional[bool] = None
    last_bid_item_id: Optional[str] = None
    last_bid_item_title: Optional[str] = None
    last_bid_amount: Optional[int] = None


class ParticipantsOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    participants: list[ParticipantOut]


class DashboardKbsOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    invited_count: int
    joined_count: int
    not_bid_yet_count: int
    not_bid_yet_user_ids: list[str]
    top_by_bidding_power: list[ParticipantOut]


class MyDashboardKbsOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    auction_id: str
    user_id: str
    name: Optional[str] = None
    kogbucks_total: int
    kogbucks_held: int
    bidding_power: int
    invited: bool
    joined: bool
    bid_counter: int


class GiftCardWinnerIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str = Field(..., min_length=1)


class GiftCardWinnerOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    auction_id: str
    user_id: str
    gift_card_winner: bool


class AuctionMessageOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    auction_id: str
    user_id: str
    item_id: Optional[str] = None
    type: Literal["LEADING", "OUTBID", "SYSTEM", "INACTIVITY_REMINDER", "BID_LOCKED", "WON", "GIFT_CARD_ACTION_REQUIRED", "GIFT_CARD_WON"]
    message: str
    created_at: datetime


class AuctionMessagesOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    messages: list[AuctionMessageOut]


class AuctionChatMessageCreateIn(BaseModel):#input model for creating a new chat message in an auction, requires the content of the message with a length between 1 and 1000 characters
    model_config = ConfigDict(extra="forbid")

    content: str = Field(..., min_length=1, max_length=1000)


class AuctionChatMessageOut(BaseModel):#output model for a chat message in an auction
    model_config = ConfigDict(extra="forbid")

    id: str
    sender_user_id: str
    sender_name: str
    sender_role: str
    content: str
    created_at: datetime


class AuctionChatMessagesOut(BaseModel):#output model for the list of chat messages in an auction
    model_config = ConfigDict(extra="forbid")

    auction_id: str
    chat_messages: list[AuctionChatMessageOut]


class ResultItemOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_id: str
    title: Optional[str] = None
    final_bid: int


class MyResultsOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    won: list[ResultItemOut]
    lost: list[ResultItemOut]

class SelectAuctionItemsOut(BaseModel):#output model for the result of selecting items for auction, includes the count of selected items and their IDs
    model_config = ConfigDict(extra="forbid")

    auction_id: str
    selected_count: int
    selected_item_ids: list[str]

class SelectAuctionItemsIn(BaseModel):#input model for selecting items to be included in the auction, requires a list of item IDs with at least one item
    model_config = ConfigDict(extra="forbid")

    auction_id: Optional[str] = Field(default=None, min_length=1)
    item_ids: list[str] = Field(..., min_length=1)
