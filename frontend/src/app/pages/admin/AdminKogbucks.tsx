import { useEffect, useState } from "react";

import { api } from "../../../api";
import type { KogbucksSummary } from "../../../features/admin/types";
import Button from "../../../components/Button";
import Card from "../../../components/Card";
import Spinner from "../../../components/Spinner";
import AdminTable from "../../../components/AdminTable";

const AdminKogbucks = () => {
  const [summaries, setSummaries] = useState<KogbucksSummary[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [edits, setEdits] = useState<Record<string, string>>({});
  const [isSaving, setIsSaving] = useState<string | null>(null);

  const loadSummaries = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const response = await api.admin.listKogbucks();
      setSummaries(response);
      setEdits(() => {
        const next: Record<string, string> = {};
        response.forEach((user) => {
          next[user.user_id] = user.available_balance.toString();
        });
        return next;
      });
    } catch (err) {
      console.error(err);
      setError("Failed to load Kogbucks data.");
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    void loadSummaries();
  }, []);

  const handleReset = async (userId: string) => {
    const confirmed = window.confirm("Reset Kogbucks for this user?");
    if (!confirmed) {
      return;
    }
    setError(null);
    setMessage(null);
    setIsSaving(userId);
    try {
      await api.admin.resetKogbucks(userId);
      await loadSummaries();
      setMessage("Kogbucks reset complete.");
    } catch (err) {
      console.error(err);
      const message = err instanceof Error ? err.message : "Failed to reset Kogbucks.";
      setError(message);
    } finally {
      setIsSaving(null);
    }
  };

  const handleSave = async (userId: string) => {
    const raw = edits[userId];
    const value = Number(raw);
    if (!Number.isFinite(value) || value < 0) {
      setError("Enter a valid non-negative amount.");
      return;
    }
    setError(null);
    setMessage(null);
    setIsSaving(userId);
    try {
      await api.admin.setKogbucks(userId, Math.floor(value));
      await loadSummaries();
      setMessage("Kogbucks updated.");
    } catch (err) {
      console.error(err);
      const message = err instanceof Error ? err.message : "Failed to update Kogbucks.";
      setError(message);
    } finally {
      setIsSaving(null);
    }
  };

  return (
    <section className="page">
      <div className="page-header">
        <div>
          <h1>Kogbucks Management</h1>
          <p className="muted">Adjust balances during admin operations.</p>
        </div>
      </div>

      {isLoading ? (
        <div className="center">
          <Spinner />
        </div>
      ) : null}
      {error ? <p className="error">{error}</p> : null}
      {message ? <p className="success">{message}</p> : null}

      <Card>
        <AdminTable
          columns={[
            { key: "user", header: "User", width: "22%" },
            { key: "edit", header: "Set Available", width: "20%", className: "no-ellipsis" },
            {
              key: "available",
              header: "Available",
              width: "16%",
              align: "right",
              className: "no-ellipsis"
            },
            {
              key: "held",
              header: "Held",
              width: "16%",
              align: "right",
              className: "no-ellipsis"
            },
            { key: "status", header: "Status", width: "10%", className: "no-ellipsis" },
            { key: "action", header: "Action", width: "16%", className: "no-ellipsis" }
          ]}
          rows={summaries}
          rowKey={(row) => row.user_id}
          emptyStateText={isLoading ? undefined : "No Kogbucks data available."}
          renderRow={(item) => {
            const statusLabel = item.held_balance > 0 ? "On Hold" : "Available";
            return [
              item.username,
              <input
                key="edit"
                type="number"
                min={0}
                value={edits[item.user_id] ?? ""}
                onChange={(event) =>
                  setEdits((prev) => ({
                    ...prev,
                    [item.user_id]: event.target.value
                  }))
                }
              />,
              `$${item.available_balance.toFixed(2)}`,
              `$${item.held_balance.toFixed(2)}`,
              <span key="status" className={`pill ${statusLabel === "On Hold" ? "warning" : "success"}`}>
                {statusLabel}
              </span>,
              <div key="action" className="admin-actions">
                <Button
                  type="button"
                  variant="secondary"
                  disabled={isSaving === item.user_id}
                  onClick={() => handleSave(item.user_id)}
                >
                  Save
                </Button>
                <Button
                  type="button"
                  variant="secondary"
                  disabled={isSaving === item.user_id}
                  onClick={() => handleReset(item.user_id)}
                >
                  Reset
                </Button>
              </div>
            ];
          }}
        />
      </Card>
      <p className="muted">TODO: Add quarterly reset + ledger integration.</p>
    </section>
  );
};

export default AdminKogbucks;

