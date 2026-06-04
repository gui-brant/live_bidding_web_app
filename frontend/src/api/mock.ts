import type { AuthResponse, Kogbucks, NotificationPreferences, User } from "./types";

export const mockAuthResponse = (companyToken: string): AuthResponse => ({
  access_token: `mock-token-${companyToken || "dev"}`
});

export const mockUser = (): User => ({
  id: "user-rep",
  username: "rep",
  role: "REP",
  email: "rep@example.com",
  display_name: "Alex Rep"
});

export const mockKogbucks = (): Kogbucks => ({
  available_balance: 1200,
  held_balance: 150,
  is_on_hold: true,
  hold_context: {
    reason: "Pending approval"
  }
});

export const mockPreferences = (): NotificationPreferences => ({
  enable_email: true,
  enable_in_app: true,
  notify_outbid: true,
  notify_auction_timeframe: true,
  notify_auction_win: true,
});
