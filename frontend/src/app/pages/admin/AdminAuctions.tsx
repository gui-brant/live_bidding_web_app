import { FormEvent, useEffect, useMemo, useState } from "react";
import { NavLink, useNavigate } from "react-router-dom";

import { api } from "../../../api";
import type { AdminAuctionItem, AdminItem, UserSummary } from "../../../features/admin/types";
import Button from "../../../components/Button";
import Card from "../../../components/Card";
import Spinner from "../../../components/Spinner";
import StatusBadge from "../../../components/StatusBadge";
import AdminTable from "../../../components/AdminTable";
import { formatLocalDateTime, toDateTimeLocalInput } from "../../../utils/datetime";

const statusOptions: Array<AdminAuctionItem["status"] | "ALL"> = ["ALL", "UPCOMING", "LIVE"];

type AuctionFormState = {
  title: string;
  category: string;
  description: string;
  start_time: string;
  end_time: string;
  status: AdminAuctionItem["status"];
  item_ids: string[];
};

const emptyForm: AuctionFormState = {
  title: "",
  category: "",
  description: "",
  start_time: "",
  end_time: "",
  status: "UPCOMING",
  item_ids: []
};

const AdminAuctions = () => {
  const navigate = useNavigate();
  const [auctions, setAuctions] = useState<AdminAuctionItem[]>([]);
  const [items, setItems] = useState<AdminItem[]>([]);
  const [selected, setSelected] = useState<AdminAuctionItem | null>(null);
  const [formState, setFormState] = useState<AuctionFormState>(emptyForm);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<AdminAuctionItem["status"] | "ALL">("ALL");
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [minStartLocal, setMinStartLocal] = useState<string>("");
  const [users, setUsers] = useState<UserSummary[]>([]);
  const [inviteAuction, setInviteAuction] = useState<AdminAuctionItem | null>(null);
  const [inviteSelection, setInviteSelection] = useState<string[]>([]);
  const [isInviteOpen, setIsInviteOpen] = useState(false);
  const [inviteError, setInviteError] = useState<string | null>(null);

  useEffect(() => {
    const now = new Date();
    const offsetMs = now.getTimezoneOffset() * 60000;
    const localIso = new Date(now.getTime() - offsetMs).toISOString().slice(0, 16);
    setMinStartLocal(localIso);
  }, []);

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

  const loadAuctions = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const [auctionResponse, itemResponse] = await Promise.all([
        api.admin.listAuctions(),
        api.admin.listItems()
      ]);
      setAuctions(auctionResponse);
      setItems(itemResponse);
    } catch (err) {
      console.error(err);
      setError("Failed to load auctions.");
    } finally {
      setIsLoading(false);
    }
  };

  const loadUsers = async () => {
    try {
      const response = await api.admin.listUsers();
      setUsers(response.filter((user) => user.role === "REP"));
    } catch (err) {
      console.error(err);
      setInviteError("Failed to load users.");
    }
  };

  useEffect(() => {
    void loadAuctions();
    void loadUsers();
  }, []);

  const filteredAuctions = useMemo(() => {
    const query = search.trim().toLowerCase();
    return auctions
      .filter((item) => item.status !== "ENDED")
      .filter((item) => {
        const matchesQuery =
          !query ||
          item.title.toLowerCase().includes(query) ||
          item.category.toLowerCase().includes(query);
        const matchesStatus = statusFilter === "ALL" || item.status === statusFilter;
        return matchesQuery && matchesStatus;
      });
  }, [auctions, search, statusFilter]);

  const openCreateModal = () => {
    setSelected(null);
    setFormState(emptyForm);
    setIsModalOpen(true);
  };

  const openEditModal = (item: AdminAuctionItem) => {
    setSelected(item);
    setFormState({
      title: item.title,
      category: item.category,
      description: item.description ?? "",
      start_time: toDateTimeLocalInput(item.start_time),
      end_time: toDateTimeLocalInput(item.end_time),
      status: item.status,
      item_ids: item.item_ids ?? []
    });
    setIsModalOpen(true);
  };

  const getItemStatusLabel = (item: AdminItem) => {
    const status = (item.status ?? "").toUpperCase();
    const compat = (item.compat_item_status ?? "").toUpperCase();
    if (status === "PRE-SOLD") {
      return "PRE-SOLD";
    }
    if (status === "SOLD" || item.winner_user_id) {
      return "SOLD";
    }
    if (status === "ENDED" || compat === "ENDED") {
      return "ENDED";
    }
    return "";
  };

  const isItemSelectable = (item: AdminItem) => {
    return getItemStatusLabel(item) === "";
  };

  const availableItems = useMemo(() => {
    return items.filter((item) => getItemStatusLabel(item) !== "SOLD");
  }, [items]);

  const toggleItemSelection = (item: AdminItem) => {
    setFormState((prev) => {
      const exists = prev.item_ids.includes(item.id);
      if (!exists && !isItemSelectable(item)) {
        return prev;
      }
      return {
        ...prev,
        item_ids: exists ? prev.item_ids.filter((id) => id !== item.id) : [...prev.item_ids, item.id]
      };
    });
  };

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    setIsSubmitting(true);
    try {
      const payload = {
        ...formState,
        start_time: toIsoString(formState.start_time),
        end_time: toIsoString(formState.end_time)
      };
      if (selected) {
        await api.admin.updateAuction(selected.id, payload);
      } else {
        await api.admin.createAuction(payload);
      }
      setIsModalOpen(false);
      await loadAuctions();
    } catch (err) {
      console.error(err);
      const message = err instanceof Error ? err.message : "Failed to save auction.";
      setError(message);
    } finally {
      setIsSubmitting(false);
    }
  };


  const openInviteModal = (auction: AdminAuctionItem) => {
    setInviteAuction(auction);
    setInviteSelection(auction.invited_participant_ids ?? []);
    setInviteError(null);
    setIsInviteOpen(true);
  };

  const toggleInviteSelection = (userId: string) => {
    setInviteSelection((prev) =>
      prev.includes(userId) ? prev.filter((id) => id !== userId) : [...prev, userId]
    );
  };

  const handleInviteSave = async () => {
    if (!inviteAuction) {
      return;
    }
    setInviteError(null);
    try {
      const updated = await api.admin.inviteParticipants(inviteAuction.id, inviteSelection);
      setAuctions((prev) => prev.map((item) => (item.id === updated.id ? updated : item)));
      setIsInviteOpen(false);
    } catch (err) {
      console.error(err);
      const message = err instanceof Error ? err.message : "Failed to invite participants.";
      setInviteError(message);
    }
  };

  const handleInviteRevoke = async () => {
    if (!inviteAuction) {
      return;
    }
    setInviteError(null);
    try {
      const updated = await api.admin.revokeParticipants(inviteAuction.id, inviteSelection);
      setAuctions((prev) => prev.map((item) => (item.id === updated.id ? updated : item)));
      setIsInviteOpen(false);
    } catch (err) {
      console.error(err);
      const message = err instanceof Error ? err.message : "Failed to revoke participants.";
      setInviteError(message);
    }
  };

  return (
    <section className="page page-wide">
      <div className="page-header">
        <div>
          <h1>Auction Management</h1>
          <p className="muted">Create and update auctions in mock mode.</p>
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
            <select
              className="admin-status"
              value={statusFilter}
              onChange={(event) => setStatusFilter(event.target.value as AdminAuctionItem["status"] | "ALL")}
            >
              {statusOptions.map((status) => (
                <option key={status} value={status}>
                  {status === "ALL" ? "All" : status}
                </option>
              ))}
            </select>
          </div>
          <div className="admin-toolbar-right">
            <Button type="button" onClick={openCreateModal}>
              Create Auction
            </Button>
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
            { key: "category", header: "Category", width: "12%" },
            { key: "items", header: "Items", width: "8%", align: "center" },
            { key: "status", header: "Status", width: "12%", className: "no-ellipsis" },
            { key: "start", header: "Start", width: "14%", className: "no-ellipsis" },
            { key: "end", header: "End", width: "14%", className: "no-ellipsis" },
            { key: "actions", header: "Actions", width: "16%", className: "no-ellipsis" }
          ]}
          rows={filteredAuctions}
          rowKey={(row) => row.id}
          emptyStateText={isLoading ? undefined : "No auctions match your filters."}
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
              <div className="admin-actions" key="actions">
                <Button type="button" variant="secondary" onClick={() => openEditModal(item)} disabled={isSubmitting}>
                  Edit
                </Button>
                <Button type="button" variant="secondary" onClick={() => openInviteModal(item)}>
                  Invite
                </Button>
                <Button type="button" variant="secondary" onClick={() => navigate(`/admin/bidding/${item.id}`)}>
                  Manage Room
                </Button>
              </div>
            ];
          }}
        />
      </Card>

      {isModalOpen ? (
        <div className="modal-overlay" role="dialog" aria-modal="true">
          <Card className="modal-card">
            <h2>{selected ? "Edit Auction" : "Create Auction"}</h2>
            {error ? <p className="error">{error}</p> : null}
            <form className="form" onSubmit={handleSubmit}>
              <label className="field">
                <span>Title</span>
                <input
                  type="text"
                  value={formState.title}
                  onChange={(event) => setFormState({ ...formState, title: event.target.value })}
                  required
                />
              </label>
              <label className="field">
                <span>Category</span>
                <input
                  type="text"
                  value={formState.category}
                  onChange={(event) => setFormState({ ...formState, category: event.target.value })}
                  required
                />
              </label>
              <label className="field">
                <span>Description</span>
                <textarea
                  value={formState.description}
                  onChange={(event) => setFormState({ ...formState, description: event.target.value })}
                />
              </label>
              <label className="field">
                <span>Start Time</span>
                <input
                  type="datetime-local"
                  value={formState.start_time}
                  min={minStartLocal}
                  onChange={(event) => setFormState({ ...formState, start_time: event.target.value })}
                  required
                />
              </label>
              <label className="field">
                <span>End Time</span>
                <input
                  type="datetime-local"
                  value={formState.end_time}
                  onChange={(event) => setFormState({ ...formState, end_time: event.target.value })}
                  required
                />
              </label>
              <label className="field">
                <span>Status</span>
                <select
                  value={formState.status}
                  onChange={(event) => setFormState({ ...formState, status: event.target.value as AdminAuctionItem["status"] })}
                >
                  <option value="UPCOMING">UPCOMING</option>
                  <option value="LIVE">LIVE</option>
                  {selected ? <option value="ENDED">ENDED</option> : null}
                </select>
              </label>
              <label className="field">
                <span>Auction Items</span>
                <div className="item-select">
                  {availableItems.length ? (
                    availableItems.map((item) => {
                      const statusLabel = getItemStatusLabel(item);
                      const isSelected = formState.item_ids.includes(item.id);
                      const selectable = isItemSelectable(item);
                      return (
                        <label
                          key={item.id}
                          className={`item-option ${!selectable ? "item-option-disabled" : ""}`.trim()}
                        >
                          <input
                            type="checkbox"
                            checked={isSelected}
                            disabled={!selectable && !isSelected}
                            onChange={() => toggleItemSelection(item)}
                          />
                          <div className="item-option-details">
                            <strong>{item.name}</strong>
                            <div className="muted">{item.category}</div>
                          </div>
                          {statusLabel ? <span className="item-option-status">{statusLabel}</span> : null}
                        </label>
                      );
                    })
                  ) : (
                    <p className="muted">No items available. Create items first.</p>
                  )}
                </div>
              </label>
              <div className="button-row">
                <Button type="submit" disabled={isSubmitting}>
                  {isSubmitting ? "Saving..." : selected ? "Save Changes" : "Create Auction"}
                </Button>
                <Button type="button" variant="secondary" onClick={() => setIsModalOpen(false)}>
                  Cancel
                </Button>
              </div>
            </form>
          </Card>
        </div>
      ) : null}

      {isInviteOpen ? (
        <div className="modal-overlay" role="dialog" aria-modal="true">
          <Card className="modal-card">
            <h2>Invite Participants</h2>
            {inviteError ? <p className="error">{inviteError}</p> : null}
            <div className="item-select">
              {users.length ? (
                users.map((user) => (
                  <label key={user.id} className="item-option">
                    <input
                      type="checkbox"
                      checked={inviteSelection.includes(user.id)}
                      onChange={() => toggleInviteSelection(user.id)}
                    />
                    <div>
                      <strong>{user.display_name ?? user.username}</strong>
                      <div className="muted">{user.email ?? user.username}</div>
                    </div>
                  </label>
                ))
              ) : (
                <p className="muted">No reps available.</p>
              )}
            </div>
            <div className="button-row">
              <Button type="button" onClick={handleInviteSave}>
                Save Invites
              </Button>
              <Button type="button" variant="secondary" onClick={handleInviteRevoke}>
                Remove Invites
              </Button>
              <Button type="button" variant="secondary" onClick={() => setIsInviteOpen(false)}>
                Close
              </Button>
            </div>
          </Card>
        </div>
      ) : null}
    </section>
  );
};

export default AdminAuctions;
