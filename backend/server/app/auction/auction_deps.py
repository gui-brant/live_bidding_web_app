from __future__ import annotations

from fastapi import Depends

from .auction_service import AuctionService


def get_auction_collection():
    raise NotImplementedError("Auction collection dependency not provided.")
#This is a placeholder function that should be implemented to return the actual auction collection from the database.


def get_items_collection():
    raise NotImplementedError("Items collection dependency not provided.")
#same as above

def get_users_collection():
    raise NotImplementedError("Users collection dependency not provided.")


def get_bids_collection():
    raise NotImplementedError("Bids collection dependency not provided.")


def get_messages_collection():
    raise NotImplementedError("Messages collection dependency not provided.")


def get_chat_messages_collection():
    raise NotImplementedError("Chat messages collection dependency not provided.")


def get_ws_outbox_collection():#we may not need this if we decide to use a different mechanism for sending real-time updates to clients, 
    #but we can keep it as a placeholder for now in case we want to implement a WS outbox pattern for reliable message delivery in the future
    raise NotImplementedError("WS outbox collection dependency not provided.")


def get_auction_service(
    auction_collection=Depends(get_auction_collection),
    items_collection=Depends(get_items_collection),
    users_collection=Depends(get_users_collection),
    bids_collection=Depends(get_bids_collection),
    messages_collection=Depends(get_messages_collection),
    chat_messages_collection=Depends(get_chat_messages_collection),
    ws_outbox_collection=Depends(get_ws_outbox_collection),
) -> AuctionService:
    return AuctionService(
        auction_collection=auction_collection,
        items_collection=items_collection,
        users_collection=users_collection,
        bids_collection=bids_collection,
        messages_collection=messages_collection,
        ws_outbox_collection=ws_outbox_collection,
        chat_messages_collection=chat_messages_collection,
    )
