import { useEffect, useMemo, useState } from "react";
import { NavLink } from "react-router-dom";

import { api } from "../../../api";
import { getAuctionById, getBidHistory, type BidHistory } from "../../../api/auctions";
import type { AdminAuctionItem } from "../../../features/admin/types";
import type { Auction } from "../../../features/auctions/types";
import Button from "../../../components/Button";
import Card from "../../../components/Card";
import Spinner from "../../../components/Spinner";
import StatusBadge from "../../../components/StatusBadge";
import AdminTable from "../../../components/AdminTable";
import { formatLocalDateTime } from "../../../utils/datetime";

const AdminPastAuctions = () => {
  const [auctions, setAuctions] = useState<AdminAuctionItem[]>([]);
  const [search, setSearch] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedAuction, setSelectedAuction] = useState<AdminAuctionItem | null>(null);
  const [reportAuction, setReportAuction] = useState<Auction | null>(null);
  const [reportBids, setReportBids] = useState<BidHistory[]>([]);
  const [reportError, setReportError] = useState<string | null>(null);
  const [isReportLoading, setIsReportLoading] = useState(false);
  const [itemFilter, setItemFilter] = useState("ALL");
  const [userFilter, setUserFilter] = useState("ALL");
  const [showAllAuctions, setShowAllAuctions] = useState(false);

  const closeReport = () => {
    setSelectedAuction(null);
    setReportAuction(null);
    setReportBids([]);
    setReportError(null);
  };

  const loadAuctions = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const response = await api.admin.listAuctions();
      setAuctions(response);
    } catch (err) {
      console.error(err);
      setError("Failed to load past auctions.");
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    void loadAuctions();
  }, []);

  const filteredAuctions = useMemo(() => {
    const query = search.trim().toLowerCase();
    return auctions.filter((item) => {
      if (item.status !== "ENDED") {
        return false;
      }
      if (!query) {
        return true;
      }
      return item.title.toLowerCase().includes(query) || item.category.toLowerCase().includes(query);
    });
  }, [auctions, search]);

  const visibleAuctions = useMemo(() => {
    if (showAllAuctions) {
      return filteredAuctions;
    }
    return filteredAuctions.slice(0, 10);
  }, [filteredAuctions, showAllAuctions]);

  const loadReport = async (auction: AdminAuctionItem) => {
    setSelectedAuction(auction);
    setReportError(null);
    setIsReportLoading(true);
    setItemFilter("ALL");
    setUserFilter("ALL");
    try {
      const [auctionDetail, bids] = await Promise.all([
        getAuctionById(auction.id),
        getBidHistory(auction.id)
      ]);
      setReportAuction(auctionDetail);
      setReportBids(bids);
    } catch (err) {
      console.error(err);
      setReportError("Failed to load auction report.");
    } finally {
      setIsReportLoading(false);
    }
  };

  const filteredBids = useMemo(() => {
    return reportBids.filter((bid) => {
      if (itemFilter !== "ALL" && bid.item_id !== itemFilter) {
        return false;
      }
      if (userFilter !== "ALL" && bid.bidder_id !== userFilter) {
        return false;
      }
      return true;
    });
  }, [reportBids, itemFilter, userFilter]);

  const reportTotals = useMemo(() => {
    const items = reportAuction?.items ?? [];
    const totalKogbucks = items.reduce((sum, item) => {
      if (!item.winner_user_id) {
        return sum;
      }
      return sum + (item.highest_bid ?? 0);
    }, 0);

    const topBid = reportBids.reduce<BidHistory | null>((max, bid) => {
      if (!max || bid.bid_amount > max.bid_amount) {
        return bid;
      }
      return max;
    }, null);

    return {
      totalKogbucks,
      totalBids: reportBids.length,
      topBid
    };
  }, [reportAuction, reportBids]);

  const winnerRows = useMemo(() => {
    if (!reportAuction) {
      return [];
    }
    return reportAuction.items.map((item) => {
      const winnerId = item.winner_user_id;
      const winnerBid = reportBids.find(
        (bid) => bid.item_id === item.id && bid.bidder_id === winnerId
      );
      return {
        id: item.id,
        title: item.title,
        winner: winnerBid?.bidder_name || winnerId || "No winner",
        amount: item.highest_bid ?? 0
      };
    });
  }, [reportAuction, reportBids]);

  const userOptions = useMemo(() => {
    const map = new Map<string, string>();
    reportBids.forEach((bid) => {
      if (!map.has(bid.bidder_id)) {
        map.set(bid.bidder_id, bid.bidder_name || bid.bidder_id);
      }
    });
    return Array.from(map.entries()).map(([id, name]) => ({ id, name }));
  }, [reportBids]);

  const repsByBidPower = useMemo(() => {
    const map = new Map<string, { id: string; name: string; bidPower: number }>();
    reportBids.forEach((bid) => {
      const current = map.get(bid.bidder_id);
      const nextPower = current ? Math.max(current.bidPower, bid.bid_amount) : bid.bid_amount;
      map.set(bid.bidder_id, {
        id: bid.bidder_id,
        name: bid.bidder_name || bid.bidder_id,
        bidPower: nextPower
      });
    });
    return Array.from(map.values()).sort((a, b) => b.bidPower - a.bidPower);
  }, [reportBids]);

  return (
    <section className="page page-wide">
      <div className="page-header">
        <div>
          <h1>Past Auctions</h1>
          <p className="muted">Review ended auctions with detailed reports.</p>
        </div>
      </div>

      <div className="tabs admin-auction-tabs">
        <NavLink end to="/admin/auctions" className={({ isActive }) => `tab ${isActive ? "active" : ""}`}>
          Active Auctions
        </NavLink>
        <NavLink to="/admin/auctions/past" className={({ isActive }) => `tab ${isActive ? "active" : ""}`}>
          Past Auctions
        </NavLink>
      </div>

      <Card>
        <div className="admin-toolbar">
          <div className="admin-toolbar-left">
            <input
              className="admin-search"
              type="text"
              placeholder="Search by title or category"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
            />
          </div>
          <div className="admin-toolbar-right">
            {filteredAuctions.length > 10 ? (
              <Button
                type="button"
                variant="secondary"
                onClick={() => setShowAllAuctions((prev) => !prev)}
              >
                {showAllAuctions ? "Show Latest 10" : "Expand All"}
              </Button>
            ) : null}
          </div>
        </div>
      </Card>

      {isLoading ? (
        <div className="center">
          <Spinner />
        </div>
      ) : null}
      {error ? <p className="error">{error}</p> : null}

      <Card className="admin-auction-card">
        <AdminTable
          columns={[
            { key: "title", header: "Title", width: "24%" },
            { key: "category", header: "Category", width: "14%" },
            { key: "items", header: "Items", width: "10%", align: "center" },
            { key: "status", header: "Status", width: "12%", className: "no-ellipsis" },
            { key: "start", header: "Start", width: "14%", className: "no-ellipsis" },
            { key: "end", header: "End", width: "14%", className: "no-ellipsis" },
            { key: "actions", header: "Actions", width: "12%", className: "no-ellipsis" }
          ]}
          rows={visibleAuctions}
          rowKey={(row) => row.id}
          emptyStateText={isLoading ? undefined : "No past auctions found."}
          renderRow={(item) => {
            return [
              <span className="admin-title" key="title">
                {item.title}
              </span>,
              item.category,
              <span key="items-count" className="admin-items-count">
                {item.item_ids?.length ?? 0}
              </span>,
              <span key="status">
                <StatusBadge status={item.status} />
              </span>,
              <span className="admin-time" key="start">
                {formatLocalDateTime(item.start_time)}
              </span>,
              <span className="admin-time" key="end">
                {formatLocalDateTime(item.end_time)}
              </span>,
              <div key="actions" className="admin-actions">
                <Button type="button" variant="secondary" onClick={() => loadReport(item)}>
                  View Report
                </Button>
              </div>
            ];
          }}
        />
      </Card>

      {selectedAuction ? (
        <div className="modal-overlay report-modal-overlay" role="dialog" aria-modal="true" onClick={closeReport}>
          <div className="modal-card report-modal-card" onClick={(event) => event.stopPropagation()}>
            <Button type="button" variant="secondary" className="report-close-outer" onClick={closeReport}>
              Close
            </Button>
            <Card className="admin-report-card report-modal-content">
              <div className="report-modal-header">
                <div className="report-header-body">
                  <div className="report-title">
                    <span className="report-eyebrow">Auction Report</span>
                    <h2>{selectedAuction.title}</h2>
                    <p className="muted">Summary of auction performance, winners, and bidding history.</p>
                  </div>
                  <div className="report-header-right">
                    <div className="report-meta-card">
                      <StatusBadge status={selectedAuction.status} />
                      <div className="report-meta-list">
                        <div className="report-meta-row">
                        <span>Start</span>
                        <strong>{formatLocalDateTime(selectedAuction.start_time)}</strong>
                      </div>
                      <div className="report-meta-row">
                        <span>End</span>
                        <strong>{formatLocalDateTime(selectedAuction.end_time)}</strong>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            {isReportLoading ? (
              <div className="center">
                <Spinner />
              </div>
            ) : null}
            {reportError ? <p className="error">{reportError}</p> : null}

            {reportAuction ? (
              <>
                <div className="report-kpi-grid">
                  <div className="kpi-card kpi-primary">
                    <div className="kpi-icon" aria-hidden="true">
                      <svg viewBox="0 0 24 24">
                        <path
                          d="M4 6h16M4 10h16M6 14h12M8 18h8"
                          fill="none"
                          stroke="currentColor"
                          strokeWidth="1.5"
                          strokeLinecap="round"
                          strokeLinejoin="round"
                        />
                      </svg>
                    </div>
                    <div className="kpi-body">
                      <span>Total Kogbucks Earned</span>
                      <strong>${reportTotals.totalKogbucks.toFixed(2)}</strong>
                      <small>From finalized winning bids</small>
                    </div>
                  </div>
                  <div className="kpi-card">
                    <div className="kpi-icon" aria-hidden="true">
                      <svg viewBox="0 0 24 24">
                        <path
                          d="M4 12h16M12 4v16"
                          fill="none"
                          stroke="currentColor"
                          strokeWidth="1.5"
                          strokeLinecap="round"
                        />
                      </svg>
                    </div>
                    <div className="kpi-body">
                      <span>Total Bids</span>
                      <strong>{reportTotals.totalBids}</strong>
                      <small>Across all auction items</small>
                    </div>
                  </div>
                  <div className="kpi-card">
                    <div className="kpi-icon" aria-hidden="true">
                      <svg viewBox="0 0 24 24">
                        <path
                          d="M12 3l2.6 5.2 5.7.8-4.1 4 1 5.7L12 16l-5.2 2.7 1-5.7-4.1-4 5.7-.8L12 3z"
                          fill="none"
                          stroke="currentColor"
                          strokeWidth="1.5"
                          strokeLinecap="round"
                          strokeLinejoin="round"
                        />
                      </svg>
                    </div>
                    <div className="kpi-body">
                      <span>Highest Bid</span>
                      <strong>
                        {reportTotals.topBid
                          ? `$${reportTotals.topBid.bid_amount.toFixed(2)}`
                          : "-"}
                      </strong>
                      <small>
                        {reportTotals.topBid
                          ? `${reportTotals.topBid.bidder_name} · ${reportTotals.topBid.item_title}`
                          : "No bids recorded"}
                      </small>
                    </div>
                  </div>
                </div>

                <div className="report-section">
                  <div className="section-header">
                    <div>
                      <h3>Reps by Bid Power</h3>
                      <p className="muted">Sorted by each rep&apos;s highest bid in this auction.</p>
                    </div>
                  </div>
                  <div className="report-table report-table-compact">
                    <AdminTable
                      columns={[
                        { key: "rep", header: "Rep", width: "60%" },
                        { key: "power", header: "Highest Bid", width: "40%", align: "right" }
                      ]}
                      rows={repsByBidPower}
                      rowKey={(row) => row.id}
                      emptyStateText="No bids recorded."
                      renderRow={(row) => [
                        <span key="rep">{row.name}</span>,
                        <span key="power" className="history-amount">
                          ${row.bidPower.toFixed(2)}
                        </span>
                      ]}
                    />
                  </div>
                </div>

                <div className="report-section">
                  <div className="section-header">
                    <div>
                      <h3>Winners by Item</h3>
                      <p className="muted">Final winners and closing amounts per item.</p>
                    </div>
                  </div>
                  <div className="report-table report-table-compact">
                    <AdminTable
                      columns={[
                        { key: "item", header: "Item", width: "40%" },
                        { key: "winner", header: "Winner", width: "35%" },
                        { key: "amount", header: "Final Bid", width: "25%", align: "right" }
                      ]}
                      rows={winnerRows}
                      rowKey={(row) => row.id}
                      emptyStateText="No items recorded."
                      renderRow={(row) => [
                        <span key="item" className="winner-item">
                          {row.title}
                        </span>,
                        <span key="winner" className="winner-user">
                          {row.winner}
                        </span>,
                        <span key="amount" className="winner-amount">
                          ${row.amount.toFixed(2)}
                        </span>
                      ]}
                    />
                  </div>
                </div>

                <div className="report-section">
                  <div className="report-toolbar">
                    <div className="toolbar-group">
                      <span>Item</span>
                      <select value={itemFilter} onChange={(event) => setItemFilter(event.target.value)}>
                        <option value="ALL">All Items</option>
                        {reportAuction.items.map((item) => (
                          <option key={item.id} value={item.id}>
                            {item.title}
                          </option>
                        ))}
                      </select>
                    </div>
                    <div className="toolbar-group">
                      <span>User</span>
                      <select value={userFilter} onChange={(event) => setUserFilter(event.target.value)}>
                        <option value="ALL">All Users</option>
                        {userOptions.map((user) => (
                          <option key={user.id} value={user.id}>
                            {user.name}
                          </option>
                        ))}
                      </select>
                    </div>
                  </div>

                  <div className="section-header">
                    <div>
                      <h3>Bidding History</h3>
                      <p className="muted">Chronological record of bids for the auction.</p>
                    </div>
                  </div>
                  <div className="report-table report-table-history">
                    <AdminTable
                      columns={[
                        { key: "bidder", header: "User", width: "28%" },
                        { key: "item", header: "Item", width: "32%" },
                        { key: "amount", header: "Bid", width: "18%", align: "right" },
                        { key: "time", header: "Time", width: "22%", className: "no-ellipsis" }
                      ]}
                      rows={filteredBids}
                      rowKey={(row) => row.id}
                      emptyStateText="No bids found."
                      renderRow={(bid) => [
                        <span key="bidder">{bid.bidder_name}</span>,
                        <span key="item">{bid.item_title}</span>,
                        <span key="amount" className="history-amount">
                          ${bid.bid_amount.toFixed(2)}
                        </span>,
                        <span key="time" className="history-time">
                          {formatLocalDateTime(bid.created_at)}
                        </span>
                      ]}
                    />
                  </div>
                </div>
              </>
            ) : null}
            </Card>
          </div>
        </div>
      ) : null}
    </section>
  );
};

export default AdminPastAuctions;
