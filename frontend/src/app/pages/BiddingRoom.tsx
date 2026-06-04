import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import {
  getAuctionById,
  placeAuctionBid,
  getBidHistory,
  joinAuction,
  postChatMessage,
  getMyAuctionMessages,
  type BidHistory,
  type ChatMessage
} from "../../api/auctions";
import { connectAuctionRoom, type RoomEvent } from "../../api/auctionRooms";
import { getCurrentUser } from "../../api/auth";
import type { Auction, AuctionItemStatus } from "../../features/auctions/types";
import Button from "../../components/Button";
import Card from "../../components/Card";
import FloatingChat from "../../components/FloatingChat";
import Spinner from "../../components/Spinner";
import { formatLocalDateTime } from "../../utils/datetime";

const BiddingRoom = () => {
  const { auctionId } = useParams();
  const navigate = useNavigate();
  const [auction, setAuction] = useState<Auction | null>(null);
  const [selectedItemId, setSelectedItemId] = useState<string>("");
  const [roomState, setRoomState] = useState({
    activeCount: 0,
    status: "IDLE",
    remainingSeconds: 0
  });
  const [events, setEvents] = useState<Array<{ id: string; message: string }>>([]);
  const [lastBid, setLastBid] = useState<{
    bidderId: string;
    bidderName?: string;
    bidAmount: number;
    itemId: string;
  } | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isBidding, setIsBidding] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isInvited, setIsInvited] = useState(false);
  const [bidHistory, setBidHistory] = useState<BidHistory[]>([]);
  const [allBidHistory, setAllBidHistory] = useState<BidHistory[]>([]);
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([]);
  const [userNameMap, setUserNameMap] = useState<Record<string, string>>({});
  const [itemSearch, setItemSearch] = useState("");
  const [isJoined, setIsJoined] = useState(false);
  const [joinBlocked, setJoinBlocked] = useState(false);
  const [systemNotice, setSystemNotice] = useState<{ title: string; message: string } | null>(null);
  const [layout, setLayout] = useState(
    () => localStorage.getItem("rep_bidding_layout") || "classic"
  );

  const currentUser = getCurrentUser();
  const selectedItemIdRef = useRef(selectedItemId);
  const seenMessageIdsRef = useRef(new Set<string>());
  const lastSeenNoticeRef = useRef<string | null>(null);

  useEffect(() => {
    selectedItemIdRef.current = selectedItemId;
  }, [selectedItemId]);


  useEffect(() => {
    const handleStorage = (event: StorageEvent) => {
      if (event.key === "rep_bidding_layout") {
        setLayout(event.newValue || "classic");
      }
    };
    window.addEventListener("storage", handleStorage);
    return () => window.removeEventListener("storage", handleStorage);
  }, []);

  const displayItem = useMemo(() => {
    if (!auction?.items.length) {
      return null;
    }
    const activeItem =
      auction.items.find((item) =>
        ["LIVE", "TEMPORARILY-OWNED", "PRE-SOLD"].includes(item.status)
      ) ?? auction.items[0];
    return (
      auction.items.find((item) => item.id === selectedItemId) ??
      activeItem
    );
  }, [auction, selectedItemId]);
  const isSelectedItemLocked = displayItem?.status === "PRE-SOLD" || displayItem?.status === "SOLD";

  const filteredItems = useMemo(() => {
    if (!auction?.items.length) {
      return [];
    }
    const query = itemSearch.trim().toLowerCase();
    return auction.items.filter((item) => {
      if (!query) {
        return true;
      }
      const haystack = `${item.title} ${item.description ?? ""}`.toLowerCase();
      return haystack.includes(query);
    });
  }, [auction, itemSearch]);

  const highestBid = useMemo(() => {
    if (!displayItem) {
      return 0;
    }
    return displayItem.highest_bid;
  }, [displayItem]);

  const latestBid = useMemo(() => {
    return bidHistory[0] ?? null;
  }, [bidHistory]);

  const lastBidderLabel = useMemo(() => {
    if (latestBid) {
      return latestBid.bidder_name;
    }
    if (lastBid && lastBid.itemId === selectedItemId) {
      return lastBid.bidderName || lastBid.bidderId;
    }
    return "-";
  }, [latestBid, lastBid, selectedItemId]);

  const winnerTickerItems = useMemo(() => {
    if (!auction?.items.length) {
      return [];
    }
    const nameMap = new Map<string, string>();
    allBidHistory.forEach((bid) => {
      if (bid.bidder_id) {
        nameMap.set(bid.bidder_id, bid.bidder_name);
      }
    });
    chatMessages.forEach((message) => {
      if (message.sender_user_id) {
        nameMap.set(message.sender_user_id, message.sender_name);
      }
    });
    Object.entries(userNameMap).forEach(([id, name]) => {
      if (id && name) {
        nameMap.set(id, name);
      }
    });
    const winners = auction.items.filter((item) => item.winner_user_id);
    if (!winners.length) {
      return [];
    }
    return winners.map((item) => {
      const winnerName =
        item.winner_user_name ||
        (item.winner_user_id ? nameMap.get(item.winner_user_id) : undefined) ||
        item.winner_user_id ||
        "Unknown";
      const amount = (item.highest_bid ?? 0).toFixed(2);
      return `${winnerName} won ${item.title} with $${amount}`;
    });
  }, [auction, allBidHistory, chatMessages, userNameMap]);

  useEffect(() => {
    if (!auctionId) {
      setError("Missing auction id.");
      setIsLoading(false);
      return;
    }
    const loadAuction = async () => {
      setIsLoading(true);
      setError(null);
      try {
        const response = await getAuctionById(auctionId);
        if (!response) {
          setError("Auction not found.");
          return;
        }
        setAuction(response);
        const invited = response.invited_participant_ids?.includes(currentUser?.id ?? "") ?? false;
        setIsInvited(invited);
        setIsJoined(false);
        setJoinBlocked(false);
        const liveItem =
          response.items.find((item) =>
            ["LIVE", "TEMPORARILY-OWNED", "PRE-SOLD"].includes(item.status)
          ) ?? response.items[0];
        setSelectedItemId(liveItem?.id ?? "");

      const history = await getBidHistory(auctionId, liveItem?.id);
      setBidHistory(history);
      const allHistory = await getBidHistory(auctionId);
      setAllBidHistory(allHistory);
      } catch (err) {
        console.error(err);
        setError("Failed to load auction.");
      } finally {
        setIsLoading(false);
      }
    };
    void loadAuction();
  }, [auctionId]);

  useEffect(() => {
    if (!auctionId || !isInvited || isJoined || joinBlocked) {
      return;
    }
    let cancelled = false;

    const attemptJoin = async () => {
      try {
        const joinResult = await joinAuction(auctionId);
        if (cancelled) {
          return;
        }
        const joinedNow = Boolean(joinResult.joined || joinResult.reconnected);
        if (joinedNow) {
          setIsJoined(true);
          setError(null);
        }
      } catch (err) {
        if (cancelled) {
          return;
        }
        const message = err instanceof Error ? err.message : "";
        const lowered = message.toLowerCase();
        if (lowered.includes("join window is closed")) {
          setJoinBlocked(true);
          setError(message);
          return;
        }
        if (lowered && !lowered.includes("not running")) {
          setError(message);
        }
      }
    };

    void attemptJoin();
    const interval = window.setInterval(() => {
      void attemptJoin();
    }, 10000);
    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, [auctionId, isInvited, isJoined, joinBlocked]);

  useEffect(() => {
    if (!auctionId || !isInvited || !isJoined) {
      return;
    }
    const disconnect = connectAuctionRoom(auctionId, (event: RoomEvent) => {
      if (event.type === "room_state") {
        setRoomState((prev) => ({
          ...prev,
          activeCount: event.active_count,
          status: event.status ?? prev.status,
          remainingSeconds: typeof event.remainingSeconds === "number" ? event.remainingSeconds : prev.remainingSeconds
        }));
        if (event.users_table?.length) {
          setUserNameMap((prev) => {
            const next = { ...prev };
            event.users_table?.forEach((row) => {
              if (row.user_id && row.user_name) {
                next[String(row.user_id)] = row.user_name;
              }
            });
            return next;
          });
        }
        setEvents((prev) => [
          { id: `${Date.now()}-room`, message: `Room active users: ${event.active_count}` },
          ...prev
        ]);
      }
      if (event.type === "auction_started") {
        setRoomState((prev) => ({
          ...prev,
          status: "RUNNING",
          remainingSeconds: event.remainingSeconds
        }));
        setEvents((prev) => [{ id: `${Date.now()}-start`, message: "Auction started" }, ...prev]);
        void (async () => {
          try {
            const response = await getAuctionById(auctionId);
            if (response) {
              setAuction(response);
              const liveItem =
                response.items.find((item) =>
                  ["LIVE", "TEMPORARILY-OWNED", "PRE-SOLD"].includes(item.status)
                ) ?? response.items[0];
              setSelectedItemId(liveItem?.id ?? "");
            }
          } catch (err) {
            console.error(err);
          }
        })();
      }
      if (event.type === "auction_paused") {
        setRoomState((prev) => ({
          ...prev,
          status: "PAUSED",
          remainingSeconds: event.remainingSeconds
        }));
        setEvents((prev) => [{ id: `${Date.now()}-pause`, message: "Auction paused" }, ...prev]);
      }
      if (event.type === "auction_resumed") {
        setRoomState((prev) => ({
          ...prev,
          status: "RUNNING",
          remainingSeconds: event.remainingSeconds
        }));
        setEvents((prev) => [{ id: `${Date.now()}-resume`, message: "Auction resumed" }, ...prev]);
      }
      if (event.type === "auction_ended") {
        setRoomState((prev) => ({
          ...prev,
          status: "ENDED",
          remainingSeconds: 0
        }));
        setEvents((prev) => [{ id: `${Date.now()}-end`, message: "Auction ended" }, ...prev]);
      }
      if (event.type === "auction_state_updated") {
        void (async () => {
          try {
            const response = await getAuctionById(auctionId);
            if (response) {
              setAuction(response);
            }
          } catch (err) {
            console.error(err);
          }
        })();
      }
      if (event.type === "timer_tick") {
        setRoomState((prev) => ({ ...prev, remainingSeconds: event.remainingSeconds }));
      }
      if (event.type === "bid_placed") {
        setLastBid({
          bidderId: event.bidderId,
          bidderName: event.bidderName,
          bidAmount: event.bidAmount,
          itemId: event.itemId
        });
        setEvents((prev) => [
          { id: `${Date.now()}-bid`, message: `Bid placed: $${event.bidAmount}` },
          ...prev
        ]);
        setAuction((prev) => {
          if (!prev) {
            return prev;
          }
          return {
            ...prev,
            items: prev.items.map((item) =>
              item.id === event.itemId ? { ...item, highest_bid: event.bidAmount } : item
            )
          };
        });
        if (event.itemId === selectedItemIdRef.current) {
          void (async () => {
            try {
              const history = await getBidHistory(auctionId, selectedItemIdRef.current);
              setBidHistory(history);
            } catch (err) {
              console.error(err);
            }
          })();
        }
      }
      if (event.type === "time_extended") {
        setEvents((prev) => [
          { id: `${Date.now()}-time`, message: "Auction end time extended" },
          ...prev
        ]);
        setAuction((prev) => (prev ? { ...prev, end_time: event.endAt } : prev));
      }
      if (event.type === "current_item_changed") {
        setEvents((prev) => [
          { id: `${Date.now()}-current`, message: `Live item changed: ${event.currentItemId}` },
          ...prev
        ]);
        void (async () => {
          try {
            const response = await getAuctionById(auctionId);
            if (response) {
              setAuction(response);
            const liveItem =
              response.items.find((item) =>
                ["LIVE", "TEMPORARILY-OWNED", "PRE-SOLD"].includes(item.status)
              ) ?? response.items[0];
            setSelectedItemId(liveItem?.id ?? "");
            }
          } catch (err) {
            console.error(err);
          }
        })();
      }
      if (event.type === "item_ended") {
        setEvents((prev) => [
          { id: `${Date.now()}-ended`, message: `Item ended: ${event.itemId}` },
          ...prev
        ]);
        void (async () => {
          try {
            const response = await getAuctionById(auctionId);
            if (response) {
              setAuction(response);
            }
          } catch (err) {
            console.error(err);
          }
          try {
            const history = await getBidHistory(auctionId, selectedItemIdRef.current);
            setBidHistory(history);
            const allHistory = await getBidHistory(auctionId);
            setAllBidHistory(allHistory);
          } catch (err) {
            console.error(err);
          }
        })();
      }
      if (event.type === "increment_changed") {
        setEvents((prev) => [
          { id: `${Date.now()}-increment`, message: `Increment updated: ${event.increment}` },
          ...prev
        ]);
        setAuction((prev) => {
          if (!prev) {
            return prev;
          }
          return {
            ...prev,
            items: prev.items.map((item) =>
              item.id === event.itemId ? { ...item, increment: event.increment } : item
            )
          };
        });
      }
      if (event.type === "auction_message") {
        const targetId = event.user_id;
        const messageType = event.message?.type;
        if (targetId && String(targetId) !== String(currentUser?.id)) {
          return;
        }
        if (messageType === "OUTBID") {
          setSystemNotice({
            title: "Outbid",
            message: event.message?.content || "You were outbid."
          });
        }
        if (messageType === "WON") {
          setSystemNotice({
            title: "Winner",
            message: event.message?.content || "You won this item."
          });
        }
        if (messageType === "INACTIVITY_REMINDER") {
          setSystemNotice({
            title: "Reminder",
            message: event.message?.content || "You have not placed a bid yet."
          });
        }
        if (messageType === "BID_LOCKED") {
          setSystemNotice({
            title: "Bid Locked",
            message: event.message?.content || "You may no longer bid."
          });
        }
      }
      if (event.type === "chat_snapshot") {
        setChatMessages(event.messages);
      }
      if (event.type === "chat_message") {
        setChatMessages((prev) => {
          if (prev.some((message) => message.id === event.message.id)) {
            return prev;
          }
          return [...prev, event.message];
        });
      }
    }, currentUser);

    return () => {
      disconnect();
    };
  }, [auctionId, isInvited, isJoined]);

  useEffect(() => {
    if (!auctionId || !isInvited) {
      return;
    }
    let isActive = true;
    const storageKey = `auction_notice_seen_${auctionId}`;
    if (!lastSeenNoticeRef.current) {
      lastSeenNoticeRef.current = localStorage.getItem(storageKey);
    }

    const parseTime = (value?: string | null) => {
      if (!value) {
        return 0;
      }
      const parsed = Date.parse(value);
      return Number.isNaN(parsed) ? 0 : parsed;
    };

    const pollMessages = async () => {
      if (!isActive) {
        return;
      }
      try {
        const messages = await getMyAuctionMessages(auctionId, 20);
        const lastSeenTime = parseTime(lastSeenNoticeRef.current);
        const systemMessages = messages.filter((message) =>
          ["SYSTEM", "WON"].includes(message.type)
        );
        const unseen = systemMessages.filter(
          (message) => parseTime(message.created_at) > lastSeenTime
        );
        if (!unseen.length) {
          return;
        }
        const newest = unseen.reduce((latest, current) => {
          return parseTime(current.created_at) > parseTime(latest.created_at) ? current : latest;
        }, unseen[0]);
        if (!seenMessageIdsRef.current.has(newest.id)) {
          seenMessageIdsRef.current.add(newest.id);
          setSystemNotice({
            title: newest.type === "WON" ? "Winner" : "Admin Notice",
            message: newest.message || "You have a new notification."
          });
        }
        const newestTime = newest.created_at;
        lastSeenNoticeRef.current = newestTime;
        localStorage.setItem(storageKey, newestTime);
      } catch (err) {
        console.error(err);
      }
    };

    void pollMessages();
    const interval = window.setInterval(pollMessages, 10000);
    return () => {
      isActive = false;
      window.clearInterval(interval);
    };
  }, [auctionId, isInvited]);

  useEffect(() => {
    if (!systemNotice) {
      return;
    }
    const timer = window.setTimeout(() => {
      setSystemNotice(null);
    }, 6000);
    return () => window.clearTimeout(timer);
  }, [systemNotice]);

  useEffect(() => {
    if (roomState.status !== "RUNNING") {
      return;
    }
    const interval = window.setInterval(() => {
      setRoomState((prev) => {
        if (prev.status !== "RUNNING") {
          return prev;
        }
        const nextSeconds = Math.max(0, prev.remainingSeconds - 1);
        return nextSeconds === prev.remainingSeconds ? prev : { ...prev, remainingSeconds: nextSeconds };
      });
    }, 1000);
    return () => window.clearInterval(interval);
  }, [roomState.status]);

  useEffect(() => {
    if (!auctionId || !selectedItemId) {
      return;
    }
    void (async () => {
      try {
        const history = await getBidHistory(auctionId, selectedItemId);
        setBidHistory(history);
        setLastBid(null);
      } catch (err) {
        console.error(err);
      }
    })();
  }, [auctionId, selectedItemId]);

  const formatDuration = (seconds: number) => {
    const safe = Math.max(0, Math.floor(seconds));
    const mins = Math.floor(safe / 60);
    const secs = safe % 60;
    return `${mins}:${secs.toString().padStart(2, "0")}`;
  };

  const statusPillClass = (status?: AuctionItemStatus) => {
    if (status === "LIVE") {
      return "success";
    }
    if (status === "UPCOMING") {
      return "warning";
    }
    if (status === "SOLD") {
      return "neutral";
    }
    if (status === "PRE-SOLD") {
      return "danger";
    }
    if (status === "TEMPORARILY-OWNED") {
      return "warning";
    }
    if (status === "ENDED") {
      return "danger";
    }
    return "neutral";
  };

  const handleBid = async () => {
    if (!auctionId || !selectedItemId || !isInvited) {
      return;
    }
    setIsBidding(true);
    setError(null);
    try {
      await placeAuctionBid(auctionId, selectedItemId);
    } catch (err) {
      console.error(err);
      const message = err instanceof Error ? err.message : "Failed to place bid.";
      setError(message);
    } finally {
      setIsBidding(false);
    }
  };

  const handleSendChat = async (content: string) => {
    if (!auctionId) {
      return;
    }
    const message = await postChatMessage(auctionId, content);
    setChatMessages((prev) => {
      if (prev.some((item) => item.id === message.id)) {
        return prev;
      }
      return [...prev, message];
    });
  };

  const chatDisabled = !isInvited || !isJoined || roomState.status !== "RUNNING";

  return (
    <section className="page">
      <div className="page-header">
        <div>
          <h1>Bidding Room</h1>
          <p className="muted">Live auction updates and bidding.</p>
        </div>
        <Button variant="secondary" onClick={() => navigate("/auctions")}>Back to Auctions</Button>
      </div>

      {systemNotice ? (
        <div className="toast-stack">
          <div className="toast toast-outbid">
            <div>
              <strong>{systemNotice.title}</strong>
              <p>{systemNotice.message}</p>
            </div>
            <button type="button" className="toast-close" onClick={() => setSystemNotice(null)}>
              Dismiss
            </button>
          </div>
        </div>
      ) : null}

      {isLoading ? (
        <div className="center">
          <Spinner />
        </div>
      ) : null}
      {error ? <p className="error">{error}</p> : null}
      {!isInvited ? <p className="error">You are not invited to this auction.</p> : null}

      {auction ? (
        <>
          <div className="winner-ticker">
            <div className={`winner-ticker-track ${winnerTickerItems.length <= 1 ? "static" : ""}`}>
              {(winnerTickerItems.length ? winnerTickerItems : ["No winners yet."]).map((entry, index) => (
                <div key={`winner-${index}`} className="winner-ticker-item">
                  {entry}
                </div>
              ))}
              {winnerTickerItems.length > 1
                ? winnerTickerItems.map((entry, index) => (
                    <div key={`winner-dup-${index}`} className="winner-ticker-item">
                      {entry}
                    </div>
                  ))
                : null}
            </div>
          </div>

          <div className={`bidding-layout bidding-layout-${layout}`}>
          <Card className="bidding-summary-card">
            <div className="stat-row">
              <span>Current Item</span>
              <strong>{displayItem?.title || "-"}</strong>
            </div>
            <div className="stat-row">
              <span>Item Status</span>
              <strong>{displayItem?.status || "-"}</strong>
            </div>
            <div className="stat-row">
              <span>Highest Bid</span>
              <strong>${highestBid.toFixed(2)}</strong>
            </div>
            <div className="stat-row">
              <span>Last Bidder</span>
              <strong>{lastBidderLabel}</strong>
            </div>
            {roomState.status === "RUNNING" || roomState.status === "PAUSED" ? (
              <div className="stat-row">
                <span>Time Remaining</span>
                <strong>{formatDuration(roomState.remainingSeconds)}</strong>
              </div>
            ) : null}
            <div className="stat-row">
              <span>Room Status</span>
              <strong>{roomState.status}</strong>
            </div>
            <div className="stat-row">
              <span>Active Users</span>
              <strong>{roomState.activeCount}</strong>
            </div>
          </Card>

          <Card className="bidding-items-card">
            <h2 className="card-title">Items</h2>
            <div className="item-filter-row">
              <label className="field">
                <span>Search items</span>
                <input
                  type="text"
                  value={itemSearch}
                  onChange={(event) => setItemSearch(event.target.value)}
                  placeholder="Search by name or description"
                />
              </label>
            </div>
            <div className="auction-item-grid">
              {filteredItems.length ? (
                filteredItems.map((item) => (
                  <button
                    key={item.id}
                    type="button"
                    className={`auction-item-card ${selectedItemId === item.id ? "selected" : ""}`}
                    onClick={() => setSelectedItemId(item.id)}
                  >
                    <div className="auction-item-image">
                      <img src={item.image_url} alt={item.title} loading="lazy" />
                    </div>
                    <div className="auction-item-body">
                      <div className="auction-item-header">
                        <h3>{item.title}</h3>
                        <span className={`pill ${statusPillClass(item.status)}`}>{item.status}</span>
                      </div>
                      <p className="auction-item-desc">{item.description || "No description yet."}</p>
                      <div className="auction-item-meta">
                        <span>Highest Bid</span>
                        <strong>${item.highest_bid.toFixed(2)}</strong>
                      </div>
                    </div>
                  </button>
                ))
              ) : (
                <p className="muted">No items match your filters.</p>
              )}
            </div>
            <div className="item-bid-controls">
              <label className="field">
                <span>Selected Item</span>
                <select
                  value={selectedItemId}
                  onChange={(event) => setSelectedItemId(event.target.value)}
                  disabled={!auction.items.length}
                >
                  {auction.items.map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.title} ({item.status})
                    </option>
                  ))}
                </select>
              </label>
              <div className="button-row">
                <Button
                  type="button"
                  disabled={!selectedItemId || isBidding || !isInvited || isSelectedItemLocked}
                  onClick={handleBid}
                >
                  {isBidding ? "Placing Bid..." : "Place Bid"}
                </Button>
              </div>
            </div>
          </Card>

          <Card className="bidding-events-card">
            <h2 className="card-title">Live Events</h2>
            <div className="event-list">
              {events.length ? (
                events.map((event) => (
                  <div key={event.id} className="event-item">
                    {event.message}
                  </div>
                ))
              ) : (
                <p className="muted">Waiting for updates...</p>
              )}
            </div>
          </Card>

          <Card className="bidding-history-card">
            <h2 className="card-title">Bid History</h2>
            <div className="bid-history-list">
              {bidHistory.length ? (
                bidHistory.map((bid) => (
                  <div key={bid.id} className="bid-history-item">
                    <div className="bid-history-left">
                      <strong>{bid.bidder_name}</strong>
                      <span className="muted">{bid.item_title}</span>
                      <span className="muted">{formatLocalDateTime(bid.created_at)}</span>
                    </div>
                    <div className="bid-history-right">
                      <strong>${bid.bid_amount.toFixed(2)}</strong>
                    </div>
                  </div>
                ))
              ) : (
                <p className="muted">No bids yet.</p>
              )}
            </div>
          </Card>
          </div>
        </>
      ) : null}

      <FloatingChat
        title="Auction Chat"
        statusText={`${roomState.activeCount} online`}
        messages={chatMessages}
        currentUserId={currentUser?.id}
        onSend={handleSendChat}
        disabled={chatDisabled}
      />
    </section>
  );
};

export default BiddingRoom;
