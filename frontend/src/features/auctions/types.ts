export type AuctionStatus = "UPCOMING" | "LIVE" | "ENDED";

export type AuctionItemStatus =
  | "UPCOMING"
  | "LIVE"
  | "SOLD"
  | "ENDED"
  | "PRE-SOLD"
  | "TEMPORARILY-OWNED";

export type AuctionItem = {
  id: string;
  title: string;
  image_url: string;
  description?: string;
  status: AuctionItemStatus;
  highest_bid: number;
  increment?: number;
  temp_owner?: string;
  winner_user_id?: string;
  winner_user_name?: string;
  updated_at?: string;
};

export type Auction = {
  id: string;
  title: string;
  status: AuctionStatus;
  start_time: string;
  end_time: string;
  item_ids: string[];
  items: AuctionItem[];
  invited_participant_ids?: string[];
  auction_start_time?: string;
  initial_bid_deadline?: string;
  auction_end_time?: string;
  overtime_count?: number;
  current_item_index?: number;
  current_item_id?: string;
};
