from __future__ import annotations

from fastapi import APIRouter, Depends

from app.auth.auth_deps import get_current_user, require_role

from .bids_deps import get_bids_service
from .bids_schemas import BidPlaceIn, BidResultOut
from .bids_service import BidsService

router = APIRouter(prefix="/bids", tags=["bids"])


@router.post(
    "/place",
    response_model=BidResultOut,
    dependencies=[Depends(require_role("rep"))],
)
async def place_bid(
    payload: BidPlaceIn,
    user=Depends(get_current_user),
    service: BidsService = Depends(get_bids_service),
):
    return await service.place_bid(
        current_user=user,
        auction_id=payload.auction_id,
        item_id=payload.item_id,
    )


@router.get(
    "/eligibility",
    dependencies=[Depends(require_role("rep"))],
)
async def get_bid_eligibility(
    auction_id: str,
    item_id: str,
    user=Depends(get_current_user),
    service: BidsService = Depends(get_bids_service),
):
    return await service.get_eligibility(current_user=user, auction_id=auction_id, item_id=item_id)
