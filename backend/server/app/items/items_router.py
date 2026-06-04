from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth.auth_deps import get_current_user, require_role
from .items_deps import get_items_service
from .items_schemas import ItemCreate, ItemOut, ItemUpdate, ItemsList
from .items_service import ItemsService

router = APIRouter(prefix="/items", tags=["items"])


def _raise_if_not_found(resource, message: str = "Item not found."):
    if resource is None: 
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=message
        )

#create an item, admin only
@router.post(
    "",
    response_model=ItemOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_role("admin"))],
)
async def create_item_endpoint(
    payload: ItemCreate,
    service: ItemsService = Depends(get_items_service),
):
    # Admin-only create. Router only handles request/response shape;
    # actual Mongo write is delegated to the service.
    item = await service.create_item(name=payload.name, description=payload.description, image_url=payload.image_url)
    return item

# List all items, any authenticated user can access
@router.get(
    "",
    response_model=ItemsList,
    dependencies=[Depends(get_current_user)],
)
async def list_items_endpoint(
    service: ItemsService = Depends(get_items_service),
):
    # Read endpoint for authenticated users (rep/admin).
    items = await service.list_items()
    return ItemsList(items=items)

# Get single item by id, any authenticated user can access
@router.get(
    "/{item_id}",
    response_model=ItemOut,
    dependencies=[Depends(get_current_user)],
)
async def get_item_endpoint(
    item_id: str,
    service: ItemsService = Depends(get_items_service),
):
    # Single-item lookup with consistent 400 (bad id) vs 404 (not found) handling.
    item = await service.get_item(item_id_serve=item_id)
    _raise_if_not_found(item)
    return item

# Admin-only delete item.
@router.delete(
    "/{item_id}",
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_role("admin"))],
)
async def delete_item_endpoint(
    item_id: str,
    service: ItemsService = Depends(get_items_service),
):
    # Admin-only hard delete for MVP.
    deleted = await service.get_item(item_id_serve=item_id)
    _raise_if_not_found(deleted, message="Item not found or already deleted.")
    await service.delete_item(item_id_serve=item_id)
    return {"ok": True}

# Admin-only update item.
@router.patch(
    "/{item_id}",
    response_model=ItemOut,
    dependencies=[Depends(require_role("admin"))],
)
async def update_item_endpoint(
    item_id: str,
    payload: ItemUpdate,
    service: ItemsService = Depends(get_items_service),
):
    # Admin-only patch: reject empty payload so frontend gets a clear 400.
    updates = payload.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No updates provided.")
    item = await service.update_item(item_id_serve=item_id, updates_serve=updates)
    _raise_if_not_found(item, message="Item not found or no changes applied.")
    return item
