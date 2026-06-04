import { API_BASE_URL, apiRequest, authStorage } from "./client";
import { endpoints } from "./endpoints";

// ---- Types ----------------------------------------------------------------

export type WishlistItem = {
  id: string;
  user_id: string;
  user_email?: string;
  user_name?: string;
  name: string;
  category: "physical" | "giftcard";
  image_url?: string | null;
  created_at?: string;
};

export type WishlistAggSlice = {
  name: string;
  count: number;
};

export type WishlistAggResponse = {
  physical: WishlistAggSlice[];
  giftcard: WishlistAggSlice[];
};

export type WishlistRepEntry = {
  user_id: string;
  user_email: string;
  user_name: string;
  image_url?: string | null;
};

export type WishlistItemDetail = {
  name: string;
  category: "physical" | "giftcard";
  count: number;
  reps: WishlistRepEntry[];
};

// ---- Rep API --------------------------------------------------------------

export async function getMyWishlist(): Promise<WishlistItem[]> {
  const data = await apiRequest<{ items: WishlistItem[] }>({
    path: "/wishlist",
    options: { method: "GET" },
    mock: () => ({ items: [] }),
  });
  return data.items;
}

export async function addWishlistItem(payload: {
  name: string;
  category: "physical" | "giftcard";
  image_base64?: string | null;
}): Promise<WishlistItem> {
  return apiRequest<WishlistItem>({
    path: "/wishlist",
    options: { method: "POST", body: payload },
    mock: () => ({
      id: "mock",
      user_id: "mock",
      name: payload.name,
      category: payload.category,
      image_url: null,
    }),
  });
}

export async function deleteWishlistItem(itemId: string): Promise<void> {
  await apiRequest<{ ok: boolean }>({
    path: `/wishlist/${itemId}`,
    options: { method: "DELETE" },
    mock: () => ({ ok: true }),
  });
}

// ---- Admin API ------------------------------------------------------------

export async function getWishlistAggregate(): Promise<WishlistAggResponse> {
  return apiRequest<WishlistAggResponse>({
    path: "/wishlist/admin/aggregate",
    options: { method: "GET" },
    mock: () => ({ physical: [], giftcard: [] }),
  });
}

export async function getWishlistItemDetail(
  name: string,
  category: string
): Promise<WishlistItemDetail> {
  const params = new URLSearchParams({ name, category });
  return apiRequest<WishlistItemDetail>({
    path: `/wishlist/admin/detail?${params.toString()}`,
    options: { method: "GET" },
    mock: () => ({ name, category: category as "physical" | "giftcard", count: 0, reps: [] }),
  });
}
