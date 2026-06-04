import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import { api } from "../../api";
import { getAuctions } from "../../api/auctions";
import { getCurrentUser } from "../../api/auth";
import type { Auction, AuctionStatus } from "../../features/auctions/types";
import AuctionCard from "../../components/AuctionCard";
import AuctionDetailPanel from "../../components/AuctionDetailPanel";
import Button from "../../components/Button";
import Card from "../../components/Card";
import Spinner from "../../components/Spinner";

const statusOptions: Array<{ label: string; value: AuctionStatus | "ALL" }> = [
  { label: "All", value: "ALL" },
  { label: "Upcoming", value: "UPCOMING" },
  { label: "Live", value: "LIVE" },
  { label: "Ended", value: "ENDED" }
];

const Auctions = () => {
  const navigate = useNavigate();
  const [items, setItems] = useState<Auction[]>([]);
  const [selected, setSelected] = useState<Auction | null>(null);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<AuctionStatus | "ALL">("ALL");
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [kogbucks, setKogbucks] = useState({ available: 0, held: 0, status: "Available" });

  const loadData = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const [auctions, kogbucksResponse] = await Promise.all([
        getAuctions(),
        api.kogbucks.getMe()
      ]);
      setItems(auctions);
      setSelected(auctions[0] ?? null);
      setKogbucks({
        available: kogbucksResponse.available_balance,
        held: kogbucksResponse.held_balance,
        status: kogbucksResponse.held_balance > 0 ? "On Hold" : "Available"
      });
    } catch (err) {
      console.error(err);
      setError("Failed to load auctions.");
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    void loadData();
  }, []);

  const filteredItems = useMemo(() => {
    const query = search.trim().toLowerCase();
    return items.filter((auction) => {
      const matchesQuery =
        !query ||
        auction.title.toLowerCase().includes(query) ||
        auction.items.some((item) => item.title.toLowerCase().includes(query));
      const matchesStatus = statusFilter === "ALL" || auction.status === statusFilter;
      return matchesQuery && matchesStatus;
    });
  }, [items, search, statusFilter]);

  const handleEnterRoom = (auctionId: string) => {
    navigate(`/bidding/${auctionId}`);
  };

  const currentUser = getCurrentUser();
  const isInvited = Boolean(
    selected?.invited_participant_ids?.includes(currentUser?.id ?? "")
  );

  return (
    <section className="page">
      <div className="page-header">
        <div>
          <h1>Auctions</h1>
          <p className="muted">Browse live and upcoming auctions.</p>
        </div>
        <Button variant="secondary" onClick={loadData} disabled={isLoading}>
          Refresh
        </Button>
      </div>

      <Card className="auction-kogbucks">
        <div>
          <h2 className="card-title">Kogbucks Summary</h2>
          <div className="stat-row">
            <span>Available Balance</span>
            <strong>${kogbucks.available.toFixed(2)}</strong>
          </div>
          <div className="stat-row">
            <span>Held Balance</span>
            <strong>${kogbucks.held.toFixed(2)}</strong>
          </div>
          <div className="stat-row">
            <span>Status</span>
            <span className={`pill ${kogbucks.status === "On Hold" ? "warning" : "success"}`}>
              {kogbucks.status}
            </span>
          </div>
        </div>
        <p className="muted">Bidding will require all available Kogbucks (future rule).</p>
      </Card>

      <Card>
        <div className="auction-filters">
          <input
            type="text"
            placeholder="Search by title or category"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
          />
          <select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value as AuctionStatus | "ALL")}>
            {statusOptions.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </div>
      </Card>

      {isLoading ? (
        <div className="center">
          <Spinner />
        </div>
      ) : null}
      {error ? <p className="error">{error}</p> : null}

      <div className="auction-layout">
        <div className="auction-grid">
          {filteredItems.map((item) => (
            <AuctionCard key={item.id} item={item} onSelect={setSelected} />
          ))}
          {!filteredItems.length && !isLoading ? (
            <p className="muted">No auctions match your filters.</p>
          ) : null}
        </div>
        <AuctionDetailPanel
          item={selected}
          onClose={() => setSelected(null)}
          onEnterRoom={handleEnterRoom}
          isInvited={isInvited}
        />
      </div>
    </section>
  );
};

export default Auctions;

