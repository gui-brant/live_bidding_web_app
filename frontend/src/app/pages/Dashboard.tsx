import { useCallback, useEffect, useState } from "react";

import { api } from "../../api";
import type { Kogbucks, User } from "../../api/types";
import Button from "../../components/Button";
import Card from "../../components/Card";
import Spinner from "../../components/Spinner";
import { formatLocalDateTime } from "../../utils/datetime";

type WonItem = {
  id: string;
  title: string;
  auctionTitle: string;
  winningBid: number;
  status: string;
  updatedAt?: string;
};

const Dashboard = () => {
  const [user, setUser] = useState<User | null>(null);
  const [kogbucks, setKogbucks] = useState<Kogbucks | null>(null);
  const [wonItems, setWonItems] = useState<WonItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    setIsLoading(true);
    setError(null);

    try {
      const [userResponse, kogbucksResponse] = await Promise.all([
        api.me.getMe(),
        api.kogbucks.getMe()
      ]);
      setUser(userResponse);
      setKogbucks({
        ...kogbucksResponse,
        is_on_hold: kogbucksResponse.held_balance > 0
      });

      try {
        const auctionsResponse = await api.auctions.getAuctions();
        if (userResponse) {
          const wins = auctionsResponse.flatMap((auction) =>
            auction.items
              .filter((item) => item.winner_user_id === userResponse.id)
              .map((item) => ({
                id: item.id,
                title: item.title,
                auctionTitle: auction.title,
                winningBid: item.highest_bid ?? 0,
                status: item.status,
                updatedAt: item.updated_at
              }))
          );
          wins.sort((a, b) => {
            const aTime = a.updatedAt ? new Date(a.updatedAt).getTime() : 0;
            const bTime = b.updatedAt ? new Date(b.updatedAt).getTime() : 0;
            return bTime - aTime;
          });
          setWonItems(wins);
        } else {
          setWonItems([]);
        }
      } catch (err) {
        console.error(err);
        setWonItems([]);
        setError("Failed to load data. Showing cached values when available.");
      }
    } catch (err) {
      console.error(err);
      setError("Failed to load data. Showing cached values when available.");
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadData();
  }, [loadData]);

  const statusLabel = kogbucks?.held_balance && kogbucks.held_balance > 0 ? "On Hold" : "Available";
  const availableBalance = kogbucks ? kogbucks.available_balance.toFixed(2) : "0.00";
  const heldBalance = kogbucks ? kogbucks.held_balance.toFixed(2) : "0.00";

  return (
    <section className="page">
      <div className="page-header">
        <div>
          <h1>Dashboard</h1>
          <p className="muted">Your Kogbucks summary and profile info.</p>
        </div>
        <Button variant="secondary" onClick={loadData} disabled={isLoading}>
          Refresh
        </Button>
      </div>

      {isLoading ? (
        <div className="center">
          <Spinner />
        </div>
      ) : null}
      {error ? <p className="error">{error}</p> : null}

      <div className="grid">
        <Card title="Kogbucks Summary">
          <div className="stat-row">
            <span>Available Balance</span>
            <strong>${availableBalance}</strong>
          </div>
          <div className="stat-row">
            <span>Held Balance</span>
            <strong>${heldBalance}</strong>
          </div>
          <div className="stat-row">
            <span>Status</span>
            <span className={`pill ${statusLabel === "On Hold" ? "warning" : "success"}`}>
              {statusLabel}
            </span>
          </div>
        </Card>

        <Card title="User Info">
          <div className="stat-row">
            <span>Role</span>
            <strong>{user?.role ?? "-"}</strong>
          </div>
          <div className="stat-row">
            <span>Name</span>
            <strong>{user?.display_name ?? "-"}</strong>
          </div>
          <div className="stat-row">
            <span>Email</span>
            <strong>{user?.email ?? "-"}</strong>
          </div>
        </Card>
      </div>

      <Card title="Won Items">
        {wonItems.length ? (
          <div className="bid-history-list">
            {wonItems.map((item) => (
              <div key={`${item.id}-${item.auctionTitle}`} className="bid-history-item">
                <div className="bid-history-left">
                  <strong>{item.title}</strong>
                  <span className="muted">
                    {item.auctionTitle} · {item.status}
                  </span>
                  {item.updatedAt ? (
                    <span className="muted">{formatLocalDateTime(item.updatedAt)}</span>
                  ) : null}
                </div>
                <div className="bid-history-right">
                  <strong>${item.winningBid.toFixed(2)}</strong>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <p className="muted">No won items yet.</p>
        )}
      </Card>
    </section>
  );
};

export default Dashboard;
