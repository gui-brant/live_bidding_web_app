import { API_BASE_URL, authStorage } from "./client";
import { endpoints } from "./endpoints";
import type { Auction, AuctionItem } from "../features/auctions/types";


type AuctionItemApi = {
  itemId: string;
  title: string;
  image_url?: string | null;
  description?: string | null;
  status: "UPCOMING" | "LIVE" | "SOLD" | "ENDED" | "PRE-SOLD" | "TEMPORARILY-OWNED";
  highestBid: number;
  increment?: number | null;
  tempOwner?: string | null;
  winnerUserId?: string | null;
  winnerUserName?: string | null;
  updatedAt?: string | null;
};

type AuctionApi = {
  id: string;
  title: string;
  status: "UPCOMING" | "LIVE" | "ENDED";
  startAt: string;
  endAt: string;
  item_ids: string[];
  auctionItems: AuctionItemApi[];
  invitedParticipantIds?: string[] | null;
  auctionStartTime?: string | null;
  initialBidDeadline?: string | null;
  auctionEndTime?: string | null;
  overtimeCount?: number | null;
  current_item_index?: number | null;
  current_item_id?: string | null;
};

type AuctionBidResponse = {
  success: boolean;
  itemId: string;
  bidderId: string;
  bidAmount: number;
  timestamp: string;
};

type AuctionJoinResponse = {
  success: boolean;
  joined: boolean;
  reconnected: boolean;
  message: string;
  auction_id: string;
};

export type BidHistory = {
  id: string;
  auction_id: string;
  item_id: string;
  item_title: string;
  bidder_id: string;
  bidder_name: string;
  bid_amount: number;
  created_at: string;
};

export type ChatMessage = {
  id: string;
  sender_user_id: string;
  sender_name: string;
  sender_role: string;
  content: string;
  created_at: string;
};

export type AuctionMessage = {
  id: string;
  auction_id: string;
  user_id: string;
  item_id?: string | null;
  type: string;
  message: string;
  created_at: string;
};

type BidHistoryApi = {
  id: string;
  auctionId: string;
  itemId: string;
  itemTitle: string;
  bidderId: string;
  bidderName: string;
  bidAmount: number;
  createdAt: string;
};

type ChatMessageApi = {
  id: string;
  sender_user_id: string;
  sender_name: string;
  sender_role: string;
  content: string;
  created_at: string;
};

type AuctionMessageApi = {
  id: string;
  auction_id: string;
  user_id: string;
  item_id?: string | null;
  type?: string | null;
  message?: string | null;
  created_at: string;
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

function mapAuctionItem(item: AuctionItemApi): AuctionItem {
  const image_url = normalizeImageUrl(item.image_url);
  return {
    id: item.itemId,
    title: item.title,
    image_url,
    description: item.description ?? undefined,
    status: item.status,
    highest_bid: item.highestBid ?? 0,
    increment: item.increment ?? 0,
    temp_owner: item.tempOwner ?? undefined,
    winner_user_id: item.winnerUserId ?? undefined,
    winner_user_name: item.winnerUserName ?? undefined,
    updated_at: item.updatedAt ?? undefined
  };
}

function mapAuction(auction: AuctionApi): Auction {
  return {
    id: auction.id,
    title: auction.title,
    status: auction.status,
    start_time: auction.startAt,
    end_time: auction.endAt,
    item_ids: auction.item_ids,
    items: auction.auctionItems.map(mapAuctionItem),
    invited_participant_ids: auction.invitedParticipantIds ?? [],
    auction_start_time: auction.auctionStartTime ?? undefined,
    initial_bid_deadline: auction.initialBidDeadline ?? undefined,
    auction_end_time: auction.auctionEndTime ?? undefined,
    overtime_count: auction.overtimeCount ?? undefined,
    current_item_index: auction.current_item_index ?? undefined,
    current_item_id: auction.current_item_id ?? undefined
  };
}

function mapBidHistory(bid: BidHistoryApi): BidHistory {
  return {
    id: bid.id,
    auction_id: bid.auctionId,
    item_id: bid.itemId,
    item_title: bid.itemTitle,
    bidder_id: bid.bidderId,
    bidder_name: bid.bidderName,
    bid_amount: bid.bidAmount,
    created_at: bid.createdAt
  };
}

function mapChatMessage(message: ChatMessageApi): ChatMessage {
  return {
    id: message.id,
    sender_user_id: message.sender_user_id,
    sender_name: message.sender_name,
    sender_role: message.sender_role,
    content: message.content,
    created_at: message.created_at
  };
}

function mapAuctionMessage(message: AuctionMessageApi): AuctionMessage {
  return {
    id: message.id,
    auction_id: message.auction_id,
    user_id: message.user_id,
    item_id: message.item_id ?? undefined,
    type: message.type ?? "SYSTEM",
    message: message.message ?? "",
    created_at: message.created_at
  };
}

async function fetchAuction<T>(path: string): Promise<T> {
  const token = authStorage.getToken();
  const headers: HeadersInit = { "Content-Type": "application/json" };
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: "GET",
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

export async function getAuctions(): Promise<Auction[]> {
  const response = await fetchAuction<AuctionApi[]>(endpoints.auctions);
  return response.map(mapAuction);
}

export async function getAuctionById(id: string): Promise<Auction | null> {
  const auction = await fetchAuction<AuctionApi>(endpoints.auctionById.replace("{id}", id));
  return auction ? mapAuction(auction) : null;
}

export async function joinAuction(auctionId: string): Promise<AuctionJoinResponse> {
  const token = authStorage.getToken();
  const headers: HeadersInit = { "Content-Type": "application/json" };
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }
  const response = await fetch(`${API_BASE_URL}${endpoints.auctionJoin.replace("{id}", auctionId)}`, {
    method: "POST",
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
  return (await response.json()) as AuctionJoinResponse;
}

export async function placeAuctionBid(auctionId: string, itemId: string): Promise<AuctionBidResponse> {
  const token = authStorage.getToken();
  const headers: HeadersInit = { "Content-Type": "application/json" };
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }
  const response = await fetch(`${API_BASE_URL}${endpoints.auctionBid.replace("{id}", auctionId)}`, {
    method: "POST",
    headers,
    credentials: "include",
    body: JSON.stringify({ item_id: itemId })
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
  return (await response.json()) as AuctionBidResponse;
}

export async function getBidHistory(auctionId: string, itemId?: string): Promise<BidHistory[]> {
  const basePath = endpoints.auctionBidHistory.replace("{id}", auctionId);
  const path = itemId ? `${basePath}?item_id=${encodeURIComponent(itemId)}` : basePath;
  const response = await fetchAuction<BidHistoryApi[]>(path);
  return response.map(mapBidHistory);
}

export async function getChatMessages(auctionId: string, limit = 50): Promise<ChatMessage[]> {
  const basePath = endpoints.auctionChatMessages.replace("{id}", auctionId);
  const path = `${basePath}?limit=${encodeURIComponent(String(limit))}`;
  const response = await fetchAuction<{ chat_messages: ChatMessageApi[] }>(path);
  return (response.chat_messages ?? []).map(mapChatMessage);
}

export async function postChatMessage(auctionId: string, content: string): Promise<ChatMessage> {
  const token = authStorage.getToken();
  const headers: HeadersInit = { "Content-Type": "application/json" };
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }
  const response = await fetch(`${API_BASE_URL}${endpoints.auctionChatMessages.replace("{id}", auctionId)}`, {
    method: "POST",
    headers,
    credentials: "include",
    body: JSON.stringify({ content })
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
  return mapChatMessage((await response.json()) as ChatMessageApi);
}

export async function getMyAuctionMessages(auctionId: string, limit = 20): Promise<AuctionMessage[]> {
  const basePath = endpoints.auctionMessagesMy.replace("{id}", auctionId);
  const path = `${basePath}?limit=${encodeURIComponent(String(limit))}`;
  const response = await fetchAuction<{ messages: AuctionMessageApi[] }>(path);
  return (response.messages ?? []).map(mapAuctionMessage);
}
