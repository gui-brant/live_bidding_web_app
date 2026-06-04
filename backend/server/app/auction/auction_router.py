from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status, HTTPException

from app.auth.auth_deps import get_current_user, require_role

from ..helper.helpers import _parse_object_id

from .auction_deps import get_auction_service
from .auction_schemas import (
    AuctionChatMessageCreateIn,
    AuctionChatMessageOut,
    AuctionChatMessagesOut,
    AuctionCreateIn,
    AuctionEndOut,
    AuctionJoinOut,
    AuctionMessagesOut,
    AuctionStartIn,
    AuctionStateOut,
    DashboardKbsOut,
    ExtendTimerIn,
    GiftCardWinnerIn,
    GiftCardWinnerOut,
    InviteListOut,
    InviteUsersIn,
    MyDashboardKbsOut,
    MyResultsOut,
    ParticipantsOut,
    SelectAuctionItemsIn,
    SelectAuctionItemsOut,
)
from .auction_service import AuctionService
from .auction_ws import (
    EVENT_AUCTION_ENDED,
    EVENT_AUCTION_INVITES_UPDATED,
    EVENT_AUCTION_PARTICIPANT_JOINED,
    EVENT_AUCTION_STARTED,
    EVENT_AUCTION_STATE_UPDATED,
    ws_event,
)

router = APIRouter(prefix="/auctions", tags=["auction"])


def _extract_user_id(user: object) -> str:
    if isinstance(user, dict):
        value = user.get("id") or user.get("_id") or user.get("user_id")
    else:
        value = getattr(user, "id", None) or getattr(user, "_id", None) or getattr(user, "user_id", None)
    if value is None:
        raise ValueError("Missing authenticated user id.")
    return str(value)


def _extract_user_role(user: object) -> str:
    if isinstance(user, dict):
        value = user.get("role")
    else:
        value = getattr(user, "role", None)
    if value is None:
        return "rep"
    return str(value).lower()

@router.post(
    "",
    response_model=AuctionStateOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_role("admin"))],
)
async def create_auction(
    payload: AuctionCreateIn | None = None,
    service: AuctionService = Depends(get_auction_service),
):
    scheduled_starts_at = payload.scheduled_starts_at if payload else None
    return await service.create_auction(scheduled_starts_at=scheduled_starts_at)
@router.post(
    "/start",
    response_model=AuctionStateOut,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_role("admin"))],
)
async def start_auction(
    payload: AuctionStartIn | None = None,
    service: AuctionService = Depends(get_auction_service),
):
    _ = payload.dry_run if payload else None
    target_auction_id = (payload.auction_id if payload and payload.auction_id else "current")
    state = await service.start_auction(auction_id=target_auction_id)
    auction_id = state.auction_id
    await service.queue_ws_events(#broadcast auction start event to all clients so they can update their UI accordingly
        auction_id=auction_id,
        events=[
            ws_event(EVENT_AUCTION_STARTED, auction_id=auction_id, state=state),
            ws_event(EVENT_AUCTION_STATE_UPDATED, auction_id=auction_id, state=state),
        ],
    )
    return state


@router.get(
    "/state",
    response_model=AuctionStateOut,
    dependencies=[Depends(get_current_user)],
)
async def get_auction_state_current(service: AuctionService = Depends(get_auction_service)):
    # Frontend polling endpoint (rep/admin): fetch live timer + status for the active auction doc.
    return await service.get_auction_state(auction_id="current")


@router.get(
    "/{auction_id}/state",
    response_model=AuctionStateOut,
    dependencies=[Depends(get_current_user)],
)
async def get_auction_state_by_id(
    auction_id: str,
    service: AuctionService = Depends(get_auction_service),
):
    # Same as /state, but explicit auction id (useful if frontend stores auction id in route/state).
    return await service.get_auction_state(auction_id=auction_id)


@router.delete(
    "/{auction_id}",
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_role("admin"))],
)
async def delete_auction(
    auction_id: str,
    service: AuctionService = Depends(get_auction_service),
):
    deleted = await service.delete_auction(auction_id=auction_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Auction not found or already deleted.",
        )
    return {"ok": True}


@router.post(#join auction, only for reps
    "/{auction_id}/join",
    response_model=AuctionJoinOut,
    dependencies=[Depends(require_role("rep"))],
)
async def join_auction(
    auction_id: str,
    user=Depends(get_current_user),
    service: AuctionService = Depends(get_auction_service),
):
    user_id = _extract_user_id(user)
    result = await service.join_auction(auction_id=auction_id, user_id=user_id)
    state = await service.get_auction_state(auction_id=auction_id)#fetch current auction state for WS broadcast.
    await service.queue_ws_events(
        auction_id=auction_id,
        events=[
            ws_event(
                EVENT_AUCTION_PARTICIPANT_JOINED,#broadcast new participant joined event so clients can show updated participant list in real-time
                auction_id=auction_id,
                user_id=user_id,
                reconnected=bool(result.get("reconnected", False)),
            ),
            ws_event(EVENT_AUCTION_STATE_UPDATED, auction_id=auction_id, state=state),
        ],
    )
    return result


@router.post( #invitations to auction, only for admin
    "/{auction_id}/invites",
    response_model=InviteListOut,
    dependencies=[Depends(require_role("admin"))],
)
async def add_invites( #add invitations to auction
    auction_id: str,
    payload: InviteUsersIn,
    service: AuctionService = Depends(get_auction_service),
):
    result = await service.add_invites(auction_id=auction_id, user_ids=payload.user_ids)
    await service.queue_ws_event(
        auction_id=auction_id,
        event=ws_event(#broadcast updated invites list
            EVENT_AUCTION_INVITES_UPDATED,
            auction_id=auction_id,
            action="add",
            invited_user_ids=result["invited_user_ids"],
        ),
    )
    return result


@router.delete(#remove invitations to auction
    "/{auction_id}/invites",
    response_model=InviteListOut,
    dependencies=[Depends(require_role("admin"))],#still only admin can remove invites
)
async def remove_invites(
    auction_id: str,
    payload: InviteUsersIn,
    service: AuctionService = Depends(get_auction_service),
):
    result = await service.remove_invites(auction_id=auction_id, user_ids=payload.user_ids)
    await service.queue_ws_event(
        auction_id=auction_id,
        event=ws_event(#broadcast updated invites list
            EVENT_AUCTION_INVITES_UPDATED,
            auction_id=auction_id,
            action="remove",
            invited_user_ids=result["invited_user_ids"],
        ),
    )
    return result


@router.get(#list invitations to auction
    "/{auction_id}/invites",
    response_model=InviteListOut,
    dependencies=[Depends(require_role("admin"))],
)
async def get_invites(
    auction_id: str,
    service: AuctionService = Depends(get_auction_service),
):
    return await service.get_invites(auction_id=auction_id)


@router.post(#extend auction timer, only for admin
    "/{auction_id}/extend",
    response_model=AuctionStateOut,
    dependencies=[Depends(require_role("admin"))],
)
async def extend_auction_timer(
    auction_id: str,
    payload: ExtendTimerIn,
    user=Depends(get_current_user),
    service: AuctionService = Depends(get_auction_service),
):
    # Manual extension path (ST-140): admin triggers custom delta_seconds.
    # Keep this separate from late-bid auto extension in bid flow.
    reason = payload.reason or "admin"
    state = await service.extend_timer(
        auction_id=auction_id,
        delta_seconds=payload.delta_seconds,
        by_user_id=_extract_user_id(user),
        reason=reason,
    )
    return state


@router.get(
    "/{auction_id}/participants",
    response_model=ParticipantsOut,
    dependencies=[Depends(require_role("admin"))],
)
async def list_participants_by_bidding_power(
    auction_id: str,
    sort: str = Query(default="bidding_power"),
    order: str = Query(default="desc"),
    include_invited: bool = Query(default=False),
    include_bid_info: bool = Query(default=False),
    service: AuctionService = Depends(get_auction_service),
):
    _ = sort
    return await service.get_sorted_participants(
        auction_id=auction_id,
        order=order,
        include_invited=include_invited,
        include_bid_info=include_bid_info,
    )


@router.get( #dashboard kbs, only for admin, I should later make a dashboard for reps as well
    "/{auction_id}/dashboard/kbs",
    response_model=DashboardKbsOut,
    dependencies=[Depends(require_role("admin"))],
)
async def dashboard_kbs(
    auction_id: str,
    service: AuctionService = Depends(get_auction_service),
):
    return await service.get_dashboard_kbs(auction_id=auction_id)


@router.get( #dashboard kbs for reps, only for reps, shows only their own kbs
    "/{auction_id}/dashboard/my-kbs",
    response_model=MyDashboardKbsOut,
    dependencies=[Depends(require_role("rep"))],
)
async def my_dashboard_kbs(
    auction_id: str,
    user=Depends(get_current_user),
    service: AuctionService = Depends(get_auction_service),
):
    return await service.get_my_dashboard_kbs(
        auction_id=auction_id,
        user_id=_extract_user_id(user),
    )


@router.get(
    "/{auction_id}/messages/my",
    response_model=AuctionMessagesOut,
    dependencies=[Depends(require_role("rep"))],
)
async def my_messages(
    auction_id: str,
    user=Depends(get_current_user),
    service: AuctionService = Depends(get_auction_service),
):
    # Frontend: personal live notifications (OUTBID/WON/INACTIVITY_REMINDER/BID_LOCKED) are replayed here.
    return await service.list_messages_for_user(auction_id=auction_id, user_id=_extract_user_id(user))

# Note: chat messages are separate from system messages. This endpoint is for fetching the chat messages that a rep has access to, while the /{auction_id}/messages endpoint (not implemented here) would be for fetching all system messages for the auction. Keeping them separate allows for better organization and access control of different message types in the frontend.
@router.get(
    "/{auction_id}/chat/messages",
    response_model=AuctionChatMessagesOut,
)
async def list_chat_messages(
    auction_id: str,
    limit: int = Query(default=50, ge=1, le=100),
    user=Depends(get_current_user),
    service: AuctionService = Depends(get_auction_service),
):
    return await service.list_chat_messages(
        auction_id=auction_id,
        user_id=_extract_user_id(user),
        user_role=_extract_user_role(user),
        limit=limit,
    )


@router.post(
    "/{auction_id}/chat/messages",
    response_model=AuctionChatMessageOut,
    status_code=status.HTTP_201_CREATED,
)
async def post_chat_message(
    auction_id: str,
    payload: AuctionChatMessageCreateIn,
    user=Depends(get_current_user),
    service: AuctionService = Depends(get_auction_service),
):
    message = await service.post_chat_message(
        auction_id=auction_id,
        user_id=_extract_user_id(user),
        user_role=_extract_user_role(user),
        content=payload.content,
    )
    return message


@router.get(
    "/{auction_id}/my-results",
    response_model=MyResultsOut,
    dependencies=[Depends(require_role("rep"))],
)
async def my_results(
    auction_id: str,
    user=Depends(get_current_user),
    service: AuctionService = Depends(get_auction_service),
):
    return await service.get_my_results(auction_id=auction_id, user_id=_extract_user_id(user))


@router.post(
    "/{auction_id}/gift-card/winner",
    response_model=GiftCardWinnerOut,
    dependencies=[Depends(require_role("admin"))],
)
async def mark_gift_card_winner(
    auction_id: str,
    payload: GiftCardWinnerIn,
    service: AuctionService = Depends(get_auction_service),
):
    return await service.mark_gift_card_winner(auction_id=auction_id, user_id=payload.user_id)


@router.post(
    "/{auction_id}/gift-card/winner/{user_id}/confirm",
    response_model=GiftCardWinnerOut,
    dependencies=[Depends(require_role("admin"))],
)
async def confirm_gift_card_sent(
    auction_id: str,
    user_id: str,
    service: AuctionService = Depends(get_auction_service),
):
    return await service.confirm_gift_card_sent(auction_id=auction_id, user_id=user_id)


@router.post(
    "/{auction_id}/end",
    response_model=AuctionEndOut,
    dependencies=[Depends(require_role("admin"))],
)
async def end_auction(
    auction_id: str,
    service: AuctionService = Depends(get_auction_service),
):
    result = await service.close_auction_and_distribute(auction_id=auction_id)
    state = await service.get_auction_state(auction_id=auction_id)
    await service.queue_ws_events(
        auction_id=auction_id,
        events=[#broadcast auction ended
            ws_event(EVENT_AUCTION_ENDED, auction_id=auction_id, result=result, state=state),
            ws_event(EVENT_AUCTION_STATE_UPDATED, auction_id=auction_id, state=state),
        ],
    )
    return result

@router.post(
    "/auction/items/select",
    response_model=SelectAuctionItemsOut,
    dependencies=[Depends(require_role("admin"))],
)
async def select_auction_items(
    payload: SelectAuctionItemsIn,
    auction_id: str = Query(default="current", min_length=1),
    service: AuctionService = Depends(get_auction_service),
):
    target_auction_id = payload.auction_id or auction_id
    item_ids = [_parse_object_id(item_id, field_name="item_id") for item_id in payload.item_ids]
    result = await service.select_items_for_auction(item_ids=item_ids, auction_id=target_auction_id)
    if result["selected_count"] == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No available items were selected. Ensure item IDs exist and are AVAILABLE.",
        )
    return result
