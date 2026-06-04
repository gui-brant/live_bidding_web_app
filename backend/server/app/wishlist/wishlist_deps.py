from __future__ import annotations

from fastapi import Depends

from .wishlist_service import WishlistService


def get_wishlist_collection():
    raise NotImplementedError("Wishlist collection dependency not provided.")


def get_users_collection():
    raise NotImplementedError("Users collection dependency not provided.")


def get_wishlist_service(
    collection=Depends(get_wishlist_collection),
    users_collection=Depends(get_users_collection),
) -> WishlistService:
    return WishlistService(collection=collection, users_collection=users_collection)
