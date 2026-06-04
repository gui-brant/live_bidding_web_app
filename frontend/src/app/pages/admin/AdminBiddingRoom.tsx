import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { api } from "../../../api";
import { getAuctionById, getBidHistory, postChatMessage, type BidHistory, type ChatMessage } from "../../../api/auctions";
import { connectAuctionRoom, type RoomEvent } from "../../../api/auctionRooms";
import { getCurrentUser } from "../../../api/auth";
import type { Auction } from "../../../features/auctions/types";
import type { AdminParticipant } from "../../../features/admin/types";
import Button from "../../../components/Button";
import Card from "../../../components/Card";
import FloatingChat from "../../../components/FloatingChat";
import Spinner from "../../../components/Spinner";
import AdminTable from "../../../components/AdminTable";
import { formatLocalDateTime, toDateTimeLocalInput } from "../../../utils/datetime";

const AdminBiddingRoom = () => {
  const { auctionId } = useParams();
  const navigate = useNavigate();
  const [auction, setAuction] = useState<Auction | null>(null);
  const [startTime, setStartTime] = useState("");
  const [endTime, setEndTime] = useState("");
  const [selectedItemId, setSelectedItemId] = useState<string>("");
  const [increment, setIncrement] = useState("0");
  const [roomState, setRoomState] = useState({ remainingSeconds: 0, status: "IDLE", activeCount: 0 });
  const [events, setEvents] = useState<Array<{ id: string; message: string }>>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [bidHistory, setBidHistory] = useState<BidHistory[]>([]);
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([]);
  const [participants, setParticipants] = useState<AdminParticipant[]>([]);
  const [notifyAudience, setNotifyAudience] = useState<"REPS" | "ADMINS" | "ALL">("REPS");
  const [notifyItemId, setNotifyItemId] = useState("");
  const [notifyMessage, setNotifyMessage] = useState("");
  const [notifyStatus, setNotifyStatus] = useState<string | null>(null);
  const [notifyError, setNotifyError] = useState<string | null>(null);

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

  const selectedItemIdRef = useRef(selectedItemId);

  useEffect(() => {
    selectedItemIdRef.current = selectedItemId;
  }, [selectedItemId]);


  const winnerInfo = useMemo(() => {
    const candidate = displayItem;
    if (!candidate) {
      return null;
    }
    if (!candidate.winner_user_id) {
      return {
        label: candidate.status === "ENDED" ? "No winner" : "Pending",
        itemTitle: candidate.title
      };
    }
    const winnerBid = bidHistory.find(
      (bid) => bid.item_id === candidate.id && bid.bidder_id === candidate.winner_user_id
    );
    const participantName = participants.find(
      (participant) => participant.user_id === candidate.winner_user_id
    )?.name;
    return {
      label: winnerBid?.bidder_name || participantName || candidate.winner_user_id,
      itemTitle: candidate.title
    };
  }, [displayItem, bidHistory, participants]);

  const toDateTimeLocal = (value: string) => toDateTimeLocalInput(value);

  const toIsoString = (value: string) => {
    if (!value) {
      return "";
    }
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) {
      return value;
    }
    return date.toISOString();
  };

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
        const [response, participantResponse] = await Promise.all([
          getAuctionById(auctionId),
          api.admin.listAuctionParticipants(auctionId)
        ]);
        if (!response) {
          setError("Auction not found.");
          return;
        }
        setAuction(response);
        setParticipants(participantResponse);
        setStartTime(toDateTimeLocal(response.start_time));
        setEndTime(toDateTimeLocal(response.end_time));
        const liveItem =
          response.items.find((item) =>
            ["LIVE", "TEMPORARILY-OWNED", "PRE-SOLD"].includes(item.status)
          ) ?? response.items[0];
        const liveItemId = liveItem?.id ?? "";
        setSelectedItemId(liveItemId);
        setIncrement(String(liveItem?.increment ?? 0));
        try {
          const history = await getBidHistory(auctionId, liveItemId);
          setBidHistory(history);
        } catch (err) {
          console.error(err);
        }
      } catch (err) {
        console.error(err);
        setError("Failed to load auction.");
      } finally {
        setIsLoading(false);
      }
    };
    void loadAuction();
  }, [auctionId]);

  const loadParticipants = async () => {
    if (!auctionId) {
      return;
    }
    try {
      const response = await api.admin.listAuctionParticipants(auctionId);
      setParticipants(response);
    } catch (err) {
      console.error(err);
    }
  };

  useEffect(() => {
    if (!auctionId) {
      return;
    }
    const currentUser = getCurrentUser();
    const disconnect = connectAuctionRoom(auctionId, (event: RoomEvent) => {
      if (event.type === "room_state") {
        setRoomState((prev) => ({
          ...prev,
          activeCount: event.active_count,
          status: event.status ?? prev.status,
          remainingSeconds: typeof event.remainingSeconds === "number" ? event.remainingSeconds : prev.remainingSeconds
        }));
        void loadParticipants();
      }
      if (event.type === "time_extended") {
        setEvents((prev) => [
          { id: `${Date.now()}-time`, message: "Auction end time extended" },
          ...prev
        ]);
      }
      if (event.type === "current_item_changed") {
        setEvents((prev) => [
          { id: `${Date.now()}-item`, message: `Live item changed: ${event.currentItemId}` },
          ...prev
        ]);
        void loadParticipants();
        void (async () => {
          const response = await getAuctionById(auctionId);
          if (response) {
            setAuction(response);
            const liveItem =
              response.items.find((item) =>
                ["LIVE", "TEMPORARILY-OWNED", "PRE-SOLD"].includes(item.status)
              ) ?? response.items[0];
            setSelectedItemId(liveItem?.id ?? "");
            setIncrement(String(liveItem?.increment ?? 0));
          }
        })();
      }
      if (event.type === "item_ended") {
        setEvents((prev) => [
          { id: `${Date.now()}-ended`, message: `Item ended: ${event.itemId}` },
          ...prev
        ]);
        void loadParticipants();
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
              setIncrement(String(liveItem?.increment ?? 0));
            }
          } catch (err) {
            console.error(err);
          }
          try {
            const history = await getBidHistory(auctionId, selectedItemIdRef.current);
            setBidHistory(history);
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
      }
      if (event.type === "bid_placed") {
        const bidderLabel = event.bidderName || event.bidderId;
        setEvents((prev) => [
          { id: `${Date.now()}-bid`, message: `Bid: $${event.bidAmount} by ${bidderLabel}` },
          ...prev
        ]);
        void loadParticipants();
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
      if (event.type === "timer_tick") {
        setRoomState((prev) => ({ ...prev, remainingSeconds: event.remainingSeconds }));
      }
      if (event.type === "auction_started") {
        setRoomState((prev) => ({ ...prev, status: "RUNNING", remainingSeconds: event.remainingSeconds }));
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
              setIncrement(String(liveItem?.increment ?? 0));
            }
          } catch (err) {
            console.error(err);
          }
        })();
      }
      if (event.type === "auction_paused") {
        setRoomState((prev) => ({ ...prev, status: "PAUSED", remainingSeconds: event.remainingSeconds }));
      }
      if (event.type === "auction_resumed") {
        setRoomState((prev) => ({ ...prev, status: "RUNNING", remainingSeconds: event.remainingSeconds }));
      }
      if (event.type === "auction_ended") {
        setRoomState((prev) => ({ ...prev, status: "ENDED", remainingSeconds: 0 }));
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
    }, currentUser, "admin");

    return () => disconnect();
  }, [auctionId]);

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
        const selected = auction?.items.find((item) => item.id === selectedItemId);
        if (selected) {
          setIncrement(String(selected.increment ?? 0));
        }
      } catch (err) {
        console.error(err);
      }
    })();
  }, [auctionId, selectedItemId, auction]);

  const formatDuration = (seconds: number) => {
    const safe = Math.max(0, Math.floor(seconds));
    const mins = Math.floor(safe / 60);
    const secs = safe % 60;
    return `${mins}:${secs.toString().padStart(2, "0")}`;
  };

  const formatMoney = (value?: number) => {
    const safe = Number.isFinite(value ?? 0) ? (value ?? 0) : 0;
    return `$${safe.toFixed(2)}`;
  };

  const participantRows = useMemo(() => {
    const leadingUserIds = new Set(
      (auction?.items ?? [])
        .map((item) => item.temp_owner)
        .filter((value): value is string => Boolean(value))
    );

    return participants.map((participant) => {
      const joined = participant.joined !== false;
      const hasBidAny = Boolean(participant.last_bid_item_id || participant.last_bid_amount);
      let statusLabel = "NOT BID";
      if (!joined) {
        statusLabel = "NOT JOIN";
      } else if (leadingUserIds.has(participant.user_id)) {
        statusLabel = "LEADING";
      } else if (hasBidAny) {
        statusLabel = "OUTBID";
      }

      const bidItemLabel = participant.last_bid_item_title || participant.last_bid_item_id || "-";
      const bidAmount = participant.last_bid_amount ?? undefined;
      return {
        id: participant.user_id,
        name: participant.name,
        balance: participant.bidding_power,
        bidAmount,
        bidItem: bidItemLabel,
        status: statusLabel
      };
    });
  }, [participants, auction]);

  const handleTimeframeSave = async () => {
    if (!auctionId) {
      return;
    }
    setError(null);
    try {
      const updated = await api.admin.updateAuctionTimeframe(
        auctionId,
        toIsoString(startTime),
        toIsoString(endTime)
      );
      setAuction((prev) => (prev ? { ...prev, start_time: updated.start_time, end_time: updated.end_time } : prev));
    } catch (err) {
      console.error(err);
      const message = err instanceof Error ? err.message : "Failed to update timeframe.";
      setError(message);
    }
  };

  const handleStart = async () => {
    if (!auctionId) {
      return;
    }
    setError(null);
    try {
      const state = await api.admin.startAuctionRoom(auctionId);
      setRoomState({ remainingSeconds: state.remainingSeconds, status: state.status, activeCount: state.active_count });
      setEvents((prev) => [{ id: `${Date.now()}-start`, message: "Auction started" }, ...prev]);
      try {
        const response = await getAuctionById(auctionId);
        if (response) {
          setAuction(response);
          const liveItem =
            response.items.find((item) =>
              ["LIVE", "TEMPORARILY-OWNED", "PRE-SOLD"].includes(item.status)
            ) ?? response.items[0];
          setSelectedItemId(liveItem?.id ?? "");
          setIncrement(String(liveItem?.increment ?? 0));
        }
      } catch (err) {
        console.error(err);
      }
    } catch (err) {
      console.error(err);
      const message = err instanceof Error ? err.message : "Failed to start auction.";
      setError(message);
    }
  };

  const handlePause = async () => {
    if (!auctionId) {
      return;
    }
    setError(null);
    try {
      const state = await api.admin.pauseAuctionRoom(auctionId);
      setRoomState({ remainingSeconds: state.remainingSeconds, status: state.status, activeCount: state.active_count });
      setEvents((prev) => [{ id: `${Date.now()}-pause`, message: "Auction paused" }, ...prev]);
    } catch (err) {
      console.error(err);
      const message = err instanceof Error ? err.message : "Failed to pause auction.";
      setError(message);
    }
  };

  const handleResume = async () => {
    if (!auctionId) {
      return;
    }
    setError(null);
    try {
      const state = await api.admin.resumeAuctionRoom(auctionId);
      setRoomState({ remainingSeconds: state.remainingSeconds, status: state.status, activeCount: state.active_count });
      setEvents((prev) => [{ id: `${Date.now()}-resume`, message: "Auction resumed" }, ...prev]);
    } catch (err) {
      console.error(err);
      const message = err instanceof Error ? err.message : "Failed to resume auction.";
      setError(message);
    }
  };

  const handleEnd = async () => {
    if (!auctionId) {
      return;
    }
    setError(null);
    try {
      const state = await api.admin.endAuctionRoom(auctionId);
      setRoomState({ remainingSeconds: state.remainingSeconds, status: state.status, activeCount: state.active_count });
      setEvents((prev) => [{ id: `${Date.now()}-end`, message: "Auction ended" }, ...prev]);
    } catch (err) {
      console.error(err);
      const message = err instanceof Error ? err.message : "Failed to end auction.";
      setError(message);
    }
  };

  const handleActivateItem = async () => {
    if (!auctionId || !selectedItemId) {
      return;
    }
    setError(null);
    try {
      await api.admin.activateAuctionItem(auctionId, selectedItemId);
    } catch (err) {
      console.error(err);
      const message = err instanceof Error ? err.message : "Failed to activate item.";
      setError(message);
    }
  };

  const handleEndItem = async () => {
    if (!auctionId || !selectedItemId) {
      return;
    }
    setError(null);
    try {
      await api.admin.endAuctionItem(auctionId, selectedItemId);
    } catch (err) {
      console.error(err);
      const message = err instanceof Error ? err.message : "Failed to end item.";
      setError(message);
    }
  };

  const handleIncrementSave = async () => {
    if (!auctionId || !selectedItemId) {
      return;
    }
    const value = Number(increment);
    if (!Number.isFinite(value) || value < 0) {
      setError("Increment must be a non-negative number.");
      return;
    }
    setError(null);
    try {
      await api.admin.updateAuctionIncrement(auctionId, selectedItemId, value);
    } catch (err) {
      console.error(err);
      const message = err instanceof Error ? err.message : "Failed to update increment.";
      setError(message);
    }
  };

  const handleSendNotification = async () => {
    if (!auctionId) {
      return;
    }
    const message = notifyMessage.trim();
    if (!message) {
      setNotifyError("Message cannot be blank.");
      setNotifyStatus(null);
      return;
    }
    setNotifyError(null);
    setNotifyStatus(null);
    try {
      const result = await api.admin.sendAuctionNotification(
        auctionId,
        message,
        notifyAudience,
        notifyItemId || undefined
      );
      setNotifyMessage("");
      setNotifyStatus(`Sent to ${result.deliveredCount} ${result.audience.toLowerCase()}.`);
    } catch (err) {
      console.error(err);
      const message = err instanceof Error ? err.message : "Failed to send notification.";
      setNotifyError(message);
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

  const chatDisabled = roomState.status !== "RUNNING";

  return (
    <section className="page">
      <div className="page-header">
        <div>
          <h1>Admin Bidding Room</h1>
          <p className="muted">Control live bidding and items.</p>
        </div>
        <Button variant="secondary" onClick={() => navigate("/admin/auctions")}>Back</Button>
      </div>

      {isLoading ? (
        <div className="center">
          <Spinner />
        </div>
      ) : null}
      {error ? <p className="error">{error}</p> : null}

      {auction ? (
        <>
          <Card>
            <div className="stat-row">
              <span>Live Item</span>
              <strong>{displayItem?.title || "-"}</strong>
            </div>
            <div className="stat-row">
              <span>Winner</span>
              <strong>{winnerInfo?.label ?? "-"}</strong>
            </div>
            {winnerInfo?.itemTitle ? (
              <div className="stat-row">
                <span>Winner Item</span>
                <strong>{winnerInfo.itemTitle}</strong>
              </div>
            ) : null}
            <div className="stat-row">
              <span>Room Status</span>
              <strong>{roomState.status}</strong>
            </div>
            {roomState.status === "RUNNING" || roomState.status === "PAUSED" ? (
              <div className="stat-row">
                <span>Item Timer</span>
                <strong>{formatDuration(roomState.remainingSeconds)}</strong>
              </div>
            ) : null}
          </Card>

          <Card>
            <h2 className="card-title">Timeframe</h2>
            <div className="form">
              <label className="field">
                <span>Start</span>
                <input
                  type="datetime-local"
                  value={startTime}
                  onChange={(event) => setStartTime(event.target.value)}
                />
              </label>
              <label className="field">
                <span>End</span>
                <input
                  type="datetime-local"
                  value={endTime}
                  onChange={(event) => setEndTime(event.target.value)}
                />
              </label>
              <div className="button-row">
                <Button type="button" onClick={handleTimeframeSave}>
                  Save Timeframe
                </Button>
              </div>
            </div>
          </Card>

          <Card>
            <h2 className="card-title">Item Controls</h2>
            <label className="field">
              <span>Current Item</span>
              <select
                value={selectedItemId}
                onChange={(event) => setSelectedItemId(event.target.value)}
              >
                {auction.items.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.title} ({item.status})
                  </option>
                ))}
              </select>
            </label>
            <div className="button-row">
              <Button type="button" onClick={handleActivateItem}>
                Set Live
              </Button>
              <Button type="button" variant="secondary" onClick={handleEndItem}>
                End Item
              </Button>
            </div>
            <label className="field">
              <span>Bidding Increment</span>
              <input
                type="number"
                min={0}
                value={increment}
                onChange={(event) => setIncrement(event.target.value)}
              />
            </label>
            <div className="button-row">
              <Button type="button" onClick={handleIncrementSave}>
                Update Increment
              </Button>
            </div>
          </Card>

          <Card>
            <h2 className="card-title">Admin Notifications</h2>
            <div className="form">
              <label className="field">
                <span>Audience</span>
                <select
                  value={notifyAudience}
                  onChange={(event) =>
                    setNotifyAudience(event.target.value as "REPS" | "ADMINS" | "ALL")
                  }
                >
                  <option value="REPS">Reps</option>
                  <option value="ADMINS">Admins</option>
                  <option value="ALL">Everyone</option>
                </select>
              </label>
              <label className="field">
                <span>Item (optional)</span>
                <select value={notifyItemId} onChange={(event) => setNotifyItemId(event.target.value)}>
                  <option value="">All items</option>
                  {auction.items.map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.title}
                    </option>
                  ))}
                </select>
              </label>
              <label className="field">
                <span>Message</span>
                <textarea
                  rows={3}
                  maxLength={1000}
                  value={notifyMessage}
                  onChange={(event) => setNotifyMessage(event.target.value)}
                  placeholder="Write a notification to send to reps..."
                />
              </label>
              <div className="button-row">
                <Button type="button" onClick={handleSendNotification}>
                  Send Notification
                </Button>
              </div>
              {notifyStatus ? <p className="success">{notifyStatus}</p> : null}
              {notifyError ? <p className="error">{notifyError}</p> : null}
            </div>
          </Card>

          <Card>
            <h2 className="card-title">Live Bidding Table</h2>
            <AdminTable
              columns={[
                { key: "name", header: "User", width: "24%" },
                { key: "balance", header: "Kogbucks Balance", width: "18%" },
                { key: "bid", header: "Bidding Price", width: "18%" },
                { key: "bidItem", header: "Bid Item", width: "20%" },
                { key: "status", header: "Bidding Status", width: "20%", className: "no-ellipsis" }
              ]}
              rows={participantRows}
              rowKey={(row) => row.id}
              emptyStateText="No participants yet."
              renderRow={(row) => [
                <span key="name">{row.name}</span>,
                <span key="balance">{formatMoney(row.balance)}</span>,
                <span key="bid">{row.bidAmount !== undefined ? formatMoney(row.bidAmount) : "-"}</span>,
                <span key="bidItem">{row.bidItem}</span>,
                <span key="status">{row.status}</span>
              ]}
            />
          </Card>

          <Card>
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

          <Card>
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

          <Card>
            <h2 className="card-title">Room Controls</h2>
            <div className="button-row">
              <Button type="button" onClick={handleStart}>
                Start Auction
              </Button>
              <Button type="button" variant="secondary" onClick={handlePause}>
                Pause Auction
              </Button>
              <Button type="button" onClick={handleResume}>
                Resume Auction
              </Button>
              <Button type="button" variant="secondary" onClick={handleEnd}>
                End Auction
              </Button>
            </div>
          </Card>
        </>
      ) : null}

      <FloatingChat
        title="Auction Chat"
        statusText={`${roomState.activeCount} online`}
        messages={chatMessages}
        currentUserId={getCurrentUser()?.id}
        onSend={handleSendChat}
        disabled={chatDisabled}
      />
    </section>
  );
};

export default AdminBiddingRoom;
