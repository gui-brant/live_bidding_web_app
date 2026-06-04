from __future__ import annotations

from fastapi import Depends

from .items_service import ItemsService


def get_items_collection():
    # This is intentionally a stub.
    # main.py (or tests) should override it with the real Mongo `items` collection.
    raise NotImplementedError("Items collection dependency not provided.")


def get_items_service(collection=Depends(get_items_collection)) -> ItemsService:
    # Dependency chain used by router endpoints.
    # FastAPI resolves collection first, then creates one ItemsService instance per request.
    return ItemsService(collection=collection)
