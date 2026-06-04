from __future__ import annotations

from fastapi import Depends

from app.users.users_service import UsersService


def get_users_collection():
    # Override this in app startup to inject the Motor collection.
    raise NotImplementedError("Users collection dependency not provided.")


def get_users_service(collection=Depends(get_users_collection)) -> UsersService:
    # Build the service with the injected collection.
    return UsersService(collection=collection)
