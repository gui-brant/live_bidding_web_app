export type UserRole = "REP" | "ADMIN";

export type User = {
  id: string;
  username: string;
  role: UserRole;
  email?: string;
  display_name?: string;
};

export type NotificationPreferences = {
  enable_in_app: boolean;
  enable_email: boolean;
  notify_outbid: boolean;
  notify_auction_timeframe: boolean;
  notify_auction_win: boolean;
};

export type Kogbucks = {
  available_balance: number;
  held_balance: number;
  is_on_hold: boolean;
  hold_context?: unknown;
};

export type AuthResponse = {
  access_token: string;
};

export type MockUser = {
  id: string;
  username: string;
  role: UserRole;
  display_name?: string;
  email?: string;
  created_at?: number;
};

export type RegisterPayload = {
  email: string;
  display_name?: string;
  role: UserRole;
};
