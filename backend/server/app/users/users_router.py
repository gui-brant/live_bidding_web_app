from __future__ import annotations # allows for forward references in type hints, which can be useful for self-referential types or when the type is defined later in the code.

from fastapi import APIRouter, Depends, HTTPException, status # APIRouter is used to create a router for handling user-related endpoints. Depends is used for dependency injection, HTTPException is used to raise HTTP errors, and status provides HTTP status codes.
from app.auth.auth_deps import get_current_user, require_role # Importing the dependency function to get the current authenticated user, which can be used in endpoints that require authentication.
from app.users.user_schemas import UserCreate, UserUpdate, UserOut, SetUserKogbucksIn, UserSettingsUpdate# Importing Pydantic models for user creation and update, which define the expected structure of the request payloads.
from app.users.users_deps import get_users_service # Importing the dependency function to get the UsersService instance, which will be used to perform operations on the user data.
from app.users.users_service import UsersService # Importing the UsersService class, which contains the business logic for creating, updating, and deleting users.

from pymongo.errors import DuplicateKeyError

router = APIRouter(prefix="/users", tags=["users"]) 

def _require_current_user_id(current_user) -> str:
    """
    Extract user id from auth dependency and ensure it exists.
    Raises 404 if missing.
    """
    # Commented out because it was this was not retrieving the id in practice
    # user_id = (
    #     str(current_user.get("id"))
    #     if isinstance(current_user, dict)
    #     else getattr(current_user, "id", None)
    # )
    user_id = str(current_user.get("_id"))

    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invalid user context."
        )

    return user_id

def _raise_if_not_found(resource, message: str = "User not found."):
    if resource is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=message
        )


@router.post(
    "/{user_id}/balance_amount",
    response_model=UserOut,
    dependencies=[Depends(require_role("admin"))],
)
async def set_user_kogbucks_endpoint(
    user_id: str,
    payload: SetUserKogbucksIn,
    service: UsersService = Depends(get_users_service),
):
    user = await service.set_user_balance(user_id_serve=user_id, kogbucks=payload.balance_amount)
    _raise_if_not_found(user)
    return user

@router.post("", status_code=status.HTTP_201_CREATED, response_model=UserOut)
async def create_user_endpoint(
    payload: UserCreate,
    service: UsersService = Depends(get_users_service),
):
    try:
        user = await service.create_user(payload_serve=payload.model_dump())
        return user
    except DuplicateKeyError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already used."
        )

@router.get("/me", response_model=UserOut)
async def read_user_endpoint(
    dependencies=Depends(get_current_user),
    service: UsersService = Depends(get_users_service),
):
    current_user_id = _require_current_user_id(dependencies)
    user = await service.read_user(user_id_serve=current_user_id)
    _raise_if_not_found(user)
    return user

@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user_endpoint(
    dependencies=Depends(get_current_user),
    service: UsersService = Depends(get_users_service),
):
    current_user_id = _require_current_user_id(dependencies)
    deleted = await service.delete_user(user_id_serve=current_user_id)

    if not deleted:
        raise HTTPException(status_code=404, detail="User not found.")

    return

@router.patch("/me", response_model=UserOut)
async def update_user_endpoint(
    payload: UserUpdate,
    dependencies=Depends(get_current_user),
    service: UsersService = Depends(get_users_service),
):
    updates = payload.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No updates provided.")

    current_user_id = _require_current_user_id(dependencies)
    try:
        user = await service.update_user(user_id_serve=current_user_id, updates_serve=updates)
        _raise_if_not_found(user)
        return user
    except DuplicateKeyError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already used."
        )

@router.patch("/me/settings")
async def update_settings(
    payload: UserSettingsUpdate,
    dependencies = Depends(get_current_user),
    service: UsersService = Depends(get_users_service),
):
    updates = payload.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No updates provided.")

    current_user_id = _require_current_user_id(dependencies)
    settings = await service.update_settings(user_id=current_user_id, updates=updates)
    return settings

@router.get("/me/settings")
async def get_settings(
    dependencies = Depends(get_current_user),
    service: UsersService = Depends(get_users_service)
):
    current_user_id = _require_current_user_id(dependencies)
    settings = await service.get_settings(user_id=current_user_id)
    if settings is None:
        raise HTTPException(status_code=500, detail="User does not have a settings field")
    return settings
