import { API_BASE_URL, authStorage } from "./client";
import { endpoints } from "./endpoints";
import type {
  AdminAuctionItem,
  AdminItem,
  AdminOverview,
  KogbucksSummary,
  UserSummary,
  AdminRoomState,
  AdminParticipant,
  AdminNotificationAudience,
  AdminNotificationResult
} from "../features/admin/types";

type AdminUserApi = {
  id: string;
  email?: string;
  role?: string;
  display_name?: string;
  balance_amount: number;
  balance_committed: boolean;
  before_bid_amount: number;
  held_item_id?: string | null;
};

function mapRole(role?: string): UserSummary["role"] {
  return role === "admin" ? "ADMIN" : "REP";
}

function mapAdminUser(user: AdminUserApi): UserSummary {
  return {
    id: user.id,
    username: user.email ?? user.id,
    role: mapRole(user.role),
    display_name: user.display_name,
    email: user.email
  };
}

function mapKogbucks(user: AdminUserApi): KogbucksSummary {
  const hasHold = Boolean(user.held_item_id) || Boolean(user.balance_committed);
  return {
    user_id: user.id,
    username: user.email ?? user.id,
    available_balance: user.balance_amount ?? 0,
    held_balance: hasHold ? user.before_bid_amount ?? 0 : 0
  };
}

type AdminAuctionApi = {
  id: string;
  title: string;
  category: string;
  status: "UPCOMING" | "LIVE" | "ENDED";
  startAt: string;
  endAt: string;
  currentHighestBid: number;
  description?: string | null;
  updatedAt?: string | null;
  itemIds?: string[] | null;
  invitedParticipantIds?: string[] | null;
};

function mapAdminAuction(item: AdminAuctionApi): AdminAuctionItem {
  return {
    id: item.id,
    title: item.title,
    category: item.category,
    status: item.status,
    start_time: item.startAt,
    end_time: item.endAt,
    current_highest_bid: item.currentHighestBid,
    description: item.description ?? undefined,
    item_ids: item.itemIds ?? [],
    invited_participant_ids: item.invitedParticipantIds ?? []
  };
}

type AdminItemApi = {
  id: string;
  title?: string;
  name?: string;
  category: string;
  image_url?: string | null;
  description?: string | null;
  status?: string | null;
  compat_item_status?: string | null;
  winner_user_id?: string | null;
};

type ParticipantsApi = {
  participants: AdminParticipant[];
};

const DEFAULT_ITEM_IMAGE = "https://placehold.co/600x400?text=Item";

function normalizeImageUrl(value?: string | null): string {
  const trimmed = (value ?? "").trim();
  if (!trimmed) {
    return DEFAULT_ITEM_IMAGE;
  }
  try {
    const parsed = new URL(trimmed);
    const mediaUrl = parsed.searchParams.get("mediaurl") || parsed.searchParams.get("imgurl");
    if (mediaUrl) {
      return decodeURIComponent(mediaUrl);
    }
  } catch {
    // ignore parse errors
  }
  if (
    /^https?:\/\//i.test(trimmed) ||
    trimmed.startsWith("data:") ||
    trimmed.startsWith("blob:") ||
    trimmed.startsWith("//")
  ) {
    return trimmed;
  }
  return `https://${trimmed}`;
}

function mapAdminItem(item: AdminItemApi): AdminItem {
  const image_url = normalizeImageUrl(item.image_url);
  return {
    id: item.id,
    name: item.title ?? item.name ?? "Untitled Item",
    category: item.category,
    image_url,
    description: item.description ?? undefined,
    status: item.status ?? undefined,
    compat_item_status: item.compat_item_status ?? undefined,
    winner_user_id: item.winner_user_id ?? null
  };
}

async function adminRequest<T>(path: string, options?: RequestInit): Promise<T> {
  const token = authStorage.getToken();
  const headers: HeadersInit = { "Content-Type": "application/json" };
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers,
    credentials: "include"
  });
  if (response.status === 401) {
    authStorage.clearToken();
    window.location.href = "/auth";
    throw new Error("Unauthorized");
  }
  if (!response.ok) {
    let detail = `Request failed: ${response.status}`;
    try {
      const data = (await response.json()) as { detail?: string };
      if (data?.detail) {
        detail = data.detail;
      }
    } catch {
      // ignore
    }
    throw new Error(detail);
  }
  return (await response.json()) as T;
}

export async function getAdminOverview(): Promise<AdminOverview> {
  const [users, auctions] = await Promise.all([listUsers(), listAuctions()]);
  const totalRepUsers = users.filter((user) => user.role === "REP").length;

  return {
    totalUsers: totalRepUsers,
    activeAuctions: auctions.filter((item) => item.status === "LIVE").length,
    upcomingAuctions: auctions.filter((item) => item.status === "UPCOMING").length,
    systemStatus: "Live"
  };
}

export async function listUsers(): Promise<UserSummary[]> {
  const users = await adminRequest<AdminUserApi[]>(endpoints.adminUsers, { method: "GET" });
  return users.map(mapAdminUser);
}

export async function updateUserName(userId: string, displayName: string): Promise<UserSummary | null> {
  const user = await adminRequest<AdminUserApi | null>(`${endpoints.adminUsers}/${userId}`, {
    method: "PATCH",
    body: JSON.stringify({ display_name: displayName })
  });
  return user ? mapAdminUser(user) : null;
}

export async function listAuctions(): Promise<AdminAuctionItem[]> {
  const auctions = await adminRequest<AdminAuctionApi[]>(endpoints.adminAuctions, { method: "GET" });
  return auctions.map(mapAdminAuction);
}

export async function listAuctionParticipants(auctionId: string): Promise<AdminParticipant[]> {
  const path = `${endpoints.auctionParticipants.replace("{id}", auctionId)}?include_invited=true&include_bid_info=true`;
  const response = await adminRequest<ParticipantsApi>(path, { method: "GET" });
  return response.participants ?? [];
}

export async function startAuctionRoom(auctionId: string): Promise<AdminRoomState> {
  return adminRequest<AdminRoomState>(endpoints.adminAuctionStart.replace("{id}", auctionId), {
    method: "POST"
  });
}

export async function pauseAuctionRoom(auctionId: string): Promise<AdminRoomState> {
  return adminRequest<AdminRoomState>(endpoints.adminAuctionPause.replace("{id}", auctionId), {
    method: "POST"
  });
}

export async function resumeAuctionRoom(auctionId: string): Promise<AdminRoomState> {
  return adminRequest<AdminRoomState>(endpoints.adminAuctionResume.replace("{id}", auctionId), {
    method: "POST"
  });
}

export async function endAuctionRoom(auctionId: string): Promise<AdminRoomState> {
  return adminRequest<AdminRoomState>(endpoints.adminAuctionEnd.replace("{id}", auctionId), {
    method: "POST"
  });
}

export async function updateAuctionStatus(
  id: string,
  status: AdminAuctionItem["status"]
): Promise<AdminAuctionItem | null> {
  const auction = await adminRequest<AdminAuctionApi>(endpoints.adminAuctionStatus.replace("{id}", id), {
    method: "PATCH",
    body: JSON.stringify({ status })
  });
  return mapAdminAuction(auction);
}

export async function inviteParticipants(auctionId: string, userIds: string[]): Promise<AdminAuctionItem> {
  const auction = await adminRequest<AdminAuctionApi>(endpoints.adminAuctionInvite.replace("{id}", auctionId), {
    method: "POST",
    body: JSON.stringify({ userIds })
  });
  return mapAdminAuction(auction);
}

export async function revokeParticipants(auctionId: string, userIds: string[]): Promise<AdminAuctionItem> {
  const auction = await adminRequest<AdminAuctionApi>(endpoints.adminAuctionInvite.replace("{id}", auctionId), {
    method: "DELETE",
    body: JSON.stringify({ userIds })
  });
  return mapAdminAuction(auction);
}

export async function updateAuctionTimeframe(auctionId: string, startAt: string, endAt: string): Promise<AdminAuctionItem> {
  const auction = await adminRequest<AdminAuctionApi>(endpoints.adminAuctionTimeframe.replace("{id}", auctionId), {
    method: "POST",
    body: JSON.stringify({ startAt, endAt })
  });
  return mapAdminAuction(auction);
}

export async function activateAuctionItem(auctionId: string, itemId: string): Promise<AdminAuctionItem> {
  const auction = await adminRequest<AdminAuctionApi>(
    endpoints.adminAuctionActivateItem.replace("{id}", auctionId).replace("{itemId}", itemId),
    { method: "POST" }
  );
  return mapAdminAuction(auction);
}

export async function endAuctionItem(auctionId: string, itemId: string): Promise<AdminAuctionItem> {
  const auction = await adminRequest<AdminAuctionApi>(
    endpoints.adminAuctionEndItem.replace("{id}", auctionId).replace("{itemId}", itemId),
    { method: "POST" }
  );
  return mapAdminAuction(auction);
}

export async function updateAuctionIncrement(
  auctionId: string,
  itemId: string,
  increment: number
): Promise<AdminAuctionItem> {
  const auction = await adminRequest<AdminAuctionApi>(endpoints.adminAuctionIncrement.replace("{id}", auctionId), {
    method: "POST",
    body: JSON.stringify({ itemId, increment })
  });
  return mapAdminAuction(auction);
}

export async function createAuction(
  payload: Omit<AdminAuctionItem, "id" | "current_highest_bid">
): Promise<AdminAuctionItem> {
  const auction = await adminRequest<AdminAuctionApi>(endpoints.adminAuctions, {
    method: "POST",
    body: JSON.stringify({
      title: payload.title,
      category: payload.category,
      startAt: payload.start_time,
      endAt: payload.end_time,
      status: payload.status,
      description: payload.description,
      itemIds: payload.item_ids
    })
  });
  return mapAdminAuction(auction);
}

export async function updateAuction(
  id: string,
  payload: Partial<AdminAuctionItem>
): Promise<AdminAuctionItem | null> {
  const auction = await adminRequest<AdminAuctionApi>(endpoints.adminAuctionById.replace("{id}", id), {
    method: "PATCH",
    body: JSON.stringify({
      title: payload.title,
      category: payload.category,
      startAt: payload.start_time,
      endAt: payload.end_time,
      status: payload.status,
      description: payload.description,
      itemIds: payload.item_ids
    })
  });
  return mapAdminAuction(auction);
}

export async function listItems(): Promise<AdminItem[]> {
  const items = await adminRequest<AdminItemApi[]>(endpoints.auctionItems, { method: "GET" });
  return items.map(mapAdminItem);
}

export async function createItem(payload: Omit<AdminItem, "id">): Promise<AdminItem> {
  const item = await adminRequest<AdminItemApi>(endpoints.auctionItems, {
    method: "POST",
    body: JSON.stringify({
      title: payload.name,
      category: payload.category,
      description: payload.description,
      image_url: payload.image_url
    })
  });
  return mapAdminItem(item);
}

export async function updateItem(id: string, payload: Partial<AdminItem>): Promise<AdminItem | null> {
  const item = await adminRequest<AdminItemApi>(endpoints.auctionItemById.replace("{id}", id), {
    method: "PATCH",
    body: JSON.stringify({
      title: payload.name,
      category: payload.category,
      description: payload.description,
      image_url: payload.image_url
    })
  });
  return mapAdminItem(item);
}

export async function deleteItem(id: string): Promise<void> {
  await adminRequest<void>(endpoints.auctionItemById.replace("{id}", id), {
    method: "DELETE"
  });
}

export async function listKogbucks(): Promise<KogbucksSummary[]> {
  const users = await adminRequest<AdminUserApi[]>(endpoints.adminUsers, { method: "GET" });
  return users
    .filter((user) => (user.role ?? "").toLowerCase() === "rep")
    .map(mapKogbucks);
}

export async function resetKogbucks(userId: string): Promise<{ ok: boolean }> {
  await adminRequest<{ ok: boolean } | AdminUserApi>(endpoints.adminUserKogbucks.replace("{id}", userId), {
    method: "POST",
    body: JSON.stringify({ kogbucks: 0 })
  });
  return { ok: true };
}

export async function setKogbucks(userId: string, kogbucks: number): Promise<{ ok: boolean }> {
  await adminRequest<{ ok: boolean } | AdminUserApi>(endpoints.adminUserKogbucks.replace("{id}", userId), {
    method: "POST",
    body: JSON.stringify({ kogbucks })
  });
  return { ok: true };
}

export async function sendAuctionNotification(
  auctionId: string,
  message: string,
  audience: AdminNotificationAudience = "REPS",
  itemId?: string
): Promise<AdminNotificationResult> {
  return adminRequest<AdminNotificationResult>(endpoints.adminAuctionNotifications.replace("{id}", auctionId), {
    method: "POST",
    body: JSON.stringify({
      message,
      audience,
      itemId
    })
  });
}
