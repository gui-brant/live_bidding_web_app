export type UserSummary = {
  id: string;
  username: string;
  role: "REP" | "ADMIN";
  display_name?: string;
  email?: string;
};

export type AdminAuctionItem = {
  id: string;
  title: string;
  category: string;
  status: "UPCOMING" | "LIVE" | "ENDED";
  start_time: string;
  end_time: string;
  current_highest_bid: number;
  description?: string;
  item_ids: string[];
  invited_participant_ids?: string[];
};

export type AdminItem = {
  id: string;
  name: string;
  category: string;
  image_url: string;
  description?: string;
  status?: string;
  compat_item_status?: string;
  winner_user_id?: string | null;
};

export type KogbucksSummary = {
  user_id: string;
  username: string;
  available_balance: number;
  held_balance: number;
};

export type AdminOverview = {
  totalUsers: number;
  activeAuctions: number;
  upcomingAuctions: number;
  systemStatus: string;
};

export type AdminRoomState = {
  auction_id: string;
  status: "IDLE" | "RUNNING" | "PAUSED" | "ENDED";
  remainingSeconds: number;
  active_count: number;
  active_users: string[];
};

export type AdminParticipant = {
  user_id: string;
  name: string;
  kogbucks_total: number;
  kogbucks_held: number;
  bidding_power: number;
  joined?: boolean;
  last_bid_item_id?: string | null;
  last_bid_item_title?: string | null;
  last_bid_amount?: number | null;
};

export type AdminNotificationAudience = "ADMINS" | "REPS" | "ALL";

export type AdminNotificationResult = {
  ok: boolean;
  auctionId: string;
  audience: AdminNotificationAudience;
  itemId?: string | null;
  message: string;
  deliveredCount: number;
};
