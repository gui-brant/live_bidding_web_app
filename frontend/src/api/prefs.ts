import { apiRequest } from "./client";
import { endpoints } from "./endpoints";
import type { NotificationPreferences } from "./types";

export async function get(): Promise<NotificationPreferences> {
  return apiRequest<NotificationPreferences>({
    path: endpoints.prefs,
    mock: () => ({
      enable_in_app: true,
      enable_email: true,
      notify_outbid: true,
      notify_auction_timeframe: true,
      notify_auction_win: true
    })
  });
}

export async function update(prefs: NotificationPreferences): Promise<NotificationPreferences> {
  return apiRequest<NotificationPreferences>({
    path: endpoints.prefs,
    options: { method: "PATCH", body: prefs },
    mock: () => prefs
  });
}
