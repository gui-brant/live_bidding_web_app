from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse

from app.auth.auth_deps import get_current_user, require_role
from .wishlist_deps import get_wishlist_service
from .wishlist_schemas import (
    WishlistAggResponse,
    WishlistItemCreate,
    WishlistItemDetail,
    WishlistItemOut,
    WishlistItemsList,
)
from .wishlist_service import UPLOAD_DIR, WishlistService

router = APIRouter(prefix="/wishlist", tags=["wishlist"])


# ---- Rep endpoints --------------------------------------------------------

@router.post(
    "",
    response_model=WishlistItemOut,
    status_code=status.HTTP_201_CREATED,
)
async def add_wishlist_item(
    payload: WishlistItemCreate,
    user=Depends(get_current_user),
    service: WishlistService = Depends(get_wishlist_service),
):
    """Rep adds an item to their private wishlist."""
    user_id = str(user["_id"]) if isinstance(user, dict) else str(getattr(user, "_id", getattr(user, "id", user.get("_id"))))
    return await service.add_item(
        user_id=user_id,
        name=payload.name,
        category=payload.category,
        image_base64=payload.image_base64,
    )


@router.get(
    "",
    response_model=WishlistItemsList,
)
async def list_my_wishlist(
    user=Depends(get_current_user),
    service: WishlistService = Depends(get_wishlist_service),
):
    """Rep views their own wishlist."""
    user_id = _extract_user_id(user)
    items = await service.list_my_items(user_id=user_id)
    return WishlistItemsList(items=items)


@router.delete(
    "/{item_id}",
    status_code=status.HTTP_200_OK,
)
async def delete_wishlist_item(
    item_id: str,
    user=Depends(get_current_user),
    service: WishlistService = Depends(get_wishlist_service),
):
    """Rep deletes one of their own wishlist items."""
    user_id = _extract_user_id(user)
    deleted = await service.delete_item(item_id=item_id, user_id=user_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Wishlist item not found.")
    return {"ok": True}


# ---- Image serving --------------------------------------------------------

@router.get("/images/{filename}")
async def serve_wishlist_image(filename: str):
    """Serve an uploaded wishlist image from the uploads folder."""
    path = UPLOAD_DIR / filename
    if not path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Image not found.")
    return FileResponse(path, media_type="image/png")


# ---- Admin endpoints ------------------------------------------------------

@router.get(
    "/admin/aggregate",
    response_model=WishlistAggResponse,
    dependencies=[Depends(require_role("admin"))],
)
async def admin_wishlist_aggregate(
    service: WishlistService = Depends(get_wishlist_service),
):
    """Admin: aggregated pie-chart data for physical & giftcard wishlists."""
    return await service.aggregate_for_admin()


@router.get(
    "/admin/detail",
    response_model=WishlistItemDetail,
    dependencies=[Depends(require_role("admin"))],
)
async def admin_wishlist_detail(
    name: str,
    category: str,
    service: WishlistService = Depends(get_wishlist_service),
):
    """Admin: list reps who wishlisted a specific item (pie slice clicked)."""
    return await service.item_detail(name=name, category=category)


# ---- helpers ---------------------------------------------------------------

def _extract_user_id(user) -> str:
    if isinstance(user, dict):
        return str(user["_id"])
    return str(getattr(user, "_id", getattr(user, "id", "")))
