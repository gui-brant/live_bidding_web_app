from __future__ import annotations

from fastapi import Depends

from .bids_service import BidsService


def get_users_collection():
    raise NotImplementedError("Users collection dependency not provided.")


def get_items_collection():
    raise NotImplementedError("Items collection dependency not provided.")


def get_auction_collection():
    raise NotImplementedError("Auction collection dependency not provided.")


def get_bids_collection():
    raise NotImplementedError("Bids collection dependency not provided.")


def get_messages_collection():
    raise NotImplementedError("Auction messages collection dependency not provided.")


def get_ws_outbox_collection():
    raise NotImplementedError("WS outbox collection dependency not provided.")


def get_bids_service(
    users_collection=Depends(get_users_collection),
    items_collection=Depends(get_items_collection),
    auction_collection=Depends(get_auction_collection),
    bids_collection=Depends(get_bids_collection),
    messages_collection=Depends(get_messages_collection),
    ws_outbox_collection=Depends(get_ws_outbox_collection),
) -> BidsService:
    return BidsService(
        users_collection=users_collection,
        items_collection=items_collection,
        auction_collection=auction_collection,
        bids_collection=bids_collection,
        messages_collection=messages_collection,
        ws_outbox_collection=ws_outbox_collection,
    )
