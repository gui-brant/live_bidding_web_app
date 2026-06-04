import { API_BASE_URL, authStorage } from "./client";
import type { User } from "./types";

export type RoomStateEvent = {
  type: "room_state";
  auction_id: string;
  status?: string;
  remainingSeconds?: number;
  active_users: string[];
  active_count: number;
  users_table?: Array<{ user_id?: string; user_name?: string }>;
};

export type AuctionStateUpdatedEvent = {
  type: "auction_state_updated";
  auction_id: string;
  state?: BackendState;
};

export type AuctionStartedEvent = {
  type: "auction_started";
  auction_id: string;
  remainingSeconds: number;
};

export type AuctionPausedEvent = {
  type: "auction_paused";
  auction_id: string;
  remainingSeconds: number;
};

export type AuctionResumedEvent = {
  type: "auction_resumed";
  auction_id: string;
  remainingSeconds: number;
};

export type AuctionEndedEvent = {
  type: "auction_ended";
  auction_id: string;
  endedAt: string;
};

export type BidPlacedEvent = {
  type: "bid_placed";
  auction_id: string;
  itemId: string;
  bidderId: string;
  bidderName?: string;
  bidAmount: number;
  timestamp: string;
};

export type TimerTickEvent = {
  type: "timer_tick";
  auction_id: string;
  remainingSeconds: number;
};

export type ItemAdvancedEvent = {
  type: "item_advanced";
  auction_id: string;
  currentItemId: string;
  currentItemIndex: number;
};

export type TimeExtendedEvent = {
  type: "time_extended";
  auction_id: string;
  endAt: string;
  overtimeCount: number;
};

export type CurrentItemChangedEvent = {
  type: "current_item_changed";
  auction_id: string;
  currentItemId: string;
  currentItemIndex: number;
};

export type ItemEndedEvent = {
  type: "item_ended";
  auction_id: string;
  itemId: string;
};

export type IncrementChangedEvent = {
  type: "increment_changed";
  auction_id: string;
  itemId: string;
  increment: number;
};

export type AuctionMessageEvent = {
  type: "auction_message";
  auction_id: string;
  user_id?: string;
  itemId?: string;
  message?: {
    type?: string;
    content?: string;
  };
};

export type ChatMessage = {
  id: string;
  sender_user_id: string;
  sender_name: string;
  sender_role: string;
  content: string;
  created_at: string;
};

export type ChatSnapshotEvent = {
  type: "chat_snapshot";
  auction_id: string;
  messages: ChatMessage[];
};

export type ChatMessageEvent = {
  type: "chat_message";
  auction_id: string;
  message: ChatMessage;
};

export type RoomEvent =
  | RoomStateEvent
  | AuctionStateUpdatedEvent
  | AuctionStartedEvent
  | AuctionPausedEvent
  | AuctionResumedEvent
  | AuctionEndedEvent
  | BidPlacedEvent
  | TimerTickEvent
  | ItemAdvancedEvent
  | TimeExtendedEvent
  | CurrentItemChangedEvent
  | ItemEndedEvent
  | IncrementChangedEvent
  | AuctionMessageEvent
  | ChatSnapshotEvent
  | ChatMessageEvent;

type BackendState = {
  status?: string;
  participants?: Array<string | number>;
  ends_at?: string;
  end_time?: string;
  current_item_id?: string;
  current_item_index?: number;
  overtime_count?: number;
  users_table?: Array<{ user_id?: string; user_name?: string }>;
};

type BackendEvent = {
  type?: string;
  auction_id?: string;
  server_time?: string;
  state?: BackendState;
  chat_messages?: ChatMessageApi[];
  extension?: {
    at?: string;
  };
  item_id?: string;
  user_id?: string;
  bidder_id?: string;
  bidder_name?: string;
  bid_amount?: number;
  message?: {
    type?: string;
    content?: string;
  };
};

type ChatMessageApi = {
  id: string;
  sender_user_id: string;
  sender_name: string;
  sender_role: string;
  content: string;
  created_at: string;
};

function normalizeChatMessage(message?: ChatMessageApi): ChatMessage | null {
  if (!message) {
    return null;
  }
  return {
    id: message.id,
    sender_user_id: message.sender_user_id,
    sender_name: message.sender_name,
    sender_role: message.sender_role,
    content: message.content,
    created_at: message.created_at
  };
}

const LEGACY_EVENT_TYPES = new Set<string>([
  "room_state",
  "auction_started",
  "auction_paused",
  "auction_resumed",
  "auction_ended",
  "bid_placed",
  "timer_tick",
  "item_advanced",
  "time_extended",
  "current_item_changed",
  "item_ended",
  "increment_changed"
]);

function toWebSocketUrl(path: string) {
  const base = API_BASE_URL.replace(/^http/, "ws");
  return `${base}${path}`;
}

function parseIsoAsUtc(value: string): number {
  if (!value) {
    return NaN;
  }
  if (/[zZ]$|[+-]\d{2}:\d{2}$/.test(value)) {
    return Date.parse(value);
  }
  return Date.parse(`${value}Z`);
}

function computeRemainingSeconds(endAt?: string): number {
  if (!endAt) {
    return 0;
  }
  const millis = parseIsoAsUtc(endAt) - Date.now();
  if (!Number.isFinite(millis)) {
    return 0;
  }
  return Math.max(0, Math.floor(millis / 1000));
}

function normalizeRoomState(backend: BackendEvent): RoomStateEvent | null {
  const state = backend.state;
  if (!state) {
    return null;
  }

  const activeUsers = Array.isArray(state.participants)
    ? state.participants.map((value) => String(value))
    : [];

  return {
    type: "room_state",
    auction_id: backend.auction_id ?? "",
    status: state.status,
    remainingSeconds: computeRemainingSeconds(state.ends_at ?? state.end_time),
    active_users: activeUsers,
    active_count: activeUsers.length,
    users_table: Array.isArray(state.users_table) ? state.users_table : undefined
  };
}

function normalizeBackendEvents(raw: BackendEvent): RoomEvent[] {
  if (typeof raw?.type !== "string") {
    return [];
  }

  if (LEGACY_EVENT_TYPES.has(raw.type)) {
    return [raw as unknown as RoomEvent];
  }

  const auctionId = raw.auction_id ?? "";
  switch (raw.type) {
    case "auction.snapshot":
    case "auction.state_updated": {
      const events: RoomEvent[] = [];
      events.push({
        type: "auction_state_updated",
        auction_id: auctionId,
        state: raw.state
      });
      const roomState = normalizeRoomState(raw);
      if (roomState) {
        events.push(roomState);
      }
      if (raw.state?.current_item_id) {
        events.push({
          type: "current_item_changed",
          auction_id: auctionId,
          currentItemId: raw.state.current_item_id,
          currentItemIndex: raw.state.current_item_index ?? 0
        });
      }
      if (raw.chat_messages) {
        const messages = raw.chat_messages
          .map((message) => normalizeChatMessage(message))
          .filter((message): message is ChatMessage => Boolean(message));
        events.push({
          type: "chat_snapshot",
          auction_id: auctionId,
          messages
        });
      }
      return events;
    }
    case "auction.started": {
      return [
        {
          type: "auction_started",
          auction_id: auctionId,
          remainingSeconds: computeRemainingSeconds(raw.state?.ends_at ?? raw.state?.end_time)
        }
      ];
    }
    case "auction.ended": {
      return [
        {
          type: "auction_ended",
          auction_id: auctionId,
          endedAt: raw.server_time ?? new Date().toISOString()
        }
      ];
    }
    case "auction.timer_extended": {
      const endAt = raw.state?.ends_at ?? raw.state?.end_time ?? raw.extension?.at ?? raw.server_time ?? new Date().toISOString();
      return [
        {
          type: "time_extended",
          auction_id: auctionId,
          endAt,
          overtimeCount: Number(raw.state?.overtime_count ?? 0)
        }
      ];
    }
    case "bid.placed": {
      return [
        {
          type: "bid_placed",
          auction_id: auctionId,
          itemId: raw.item_id ?? "",
          bidderId: raw.bidder_id ?? "",
          bidderName: raw.bidder_name,
          bidAmount: Number(raw.bid_amount ?? 0),
          timestamp: raw.server_time ?? new Date().toISOString()
        }
      ];
    }
    case "auction.message": {
      return [
        {
          type: "auction_message",
          auction_id: auctionId,
          user_id: raw.user_id,
          itemId: raw.item_id ?? "",
          message: raw.message
        }
      ];
    }
    case "auction.chat_message": {
      const message = normalizeChatMessage(raw.message as ChatMessageApi);
      if (!message) {
        return [];
      }
      return [
        {
          type: "chat_message",
          auction_id: auctionId,
          message
        }
      ];
    }
    default:
      return [];
  }
}

export function connectAuctionRoom(
  auctionId: string,
  onEvent: (event: RoomEvent) => void,
  currentUser?: User | null,
  role?: "admin" | "rep"
) {
  const params = new URLSearchParams();
  const token = authStorage.getToken();
  if (token && token !== "cookie-session") {
    params.set("token", token);
  }
  if (currentUser?.id) {
    params.set("user_id", currentUser.id);
  }
  if (role) {
    params.set("role", role);
  }
  const query = params.toString() ? `?${params.toString()}` : "";
  const socket = new WebSocket(toWebSocketUrl(`/ws/auctions/${auctionId}${query}`));

  socket.onmessage = (event) => {
    try {
      const parsed = JSON.parse(event.data) as BackendEvent;
      const normalized = normalizeBackendEvents(parsed);
      for (const roomEvent of normalized) {
        onEvent(roomEvent);
      }
    } catch (error) {
      console.warn("Failed to parse room event.", error);
    }
  };

  socket.onerror = (event) => {
    console.warn("Auction room socket error.", event);
  };

  return () => {
    socket.close();
  };
}
