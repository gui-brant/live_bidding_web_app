import { useEffect, useMemo, useState } from "react";

import { api } from "../../../api";
import type { UserSummary } from "../../../features/admin/types";
import Card from "../../../components/Card";
import Spinner from "../../../components/Spinner";
import Button from "../../../components/Button";
import AdminTable from "../../../components/AdminTable";

const roleOptions: Array<"ALL" | "REP" | "ADMIN"> = ["ALL", "REP", "ADMIN"];

const AdminUsers = () => {
  const [users, setUsers] = useState<UserSummary[]>([]);
  const [roleFilter, setRoleFilter] = useState<"ALL" | "REP" | "ADMIN">("ALL");
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [nameEdits, setNameEdits] = useState<Record<string, string>>({});
  const [isSaving, setIsSaving] = useState<string | null>(null);

  const loadUsers = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const response = await api.admin.listUsers();
      setUsers(response);
      setNameEdits((prev) => {
        const next = { ...prev };
        response.forEach((user) => {
          if (!next[user.id]) {
            next[user.id] = user.display_name ?? "";
          }
        });
        return next;
      });
    } catch (err) {
      console.error(err);
      setError("Failed to load users.");
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    void loadUsers();
  }, []);

  const filteredUsers = useMemo(() => {
    if (roleFilter === "ALL") {
      return users;
    }
    return users.filter((user) => user.role === roleFilter);
  }, [users, roleFilter]);

  const handleSaveName = async (user: UserSummary) => {
    const nextName = nameEdits[user.id]?.trim();
    if (!nextName || nextName === (user.display_name ?? "")) {
      return;
    }
    setIsSaving(user.id);
    setError(null);
    try {
      const updated = await api.admin.updateUserName(user.id, nextName);
      if (updated) {
        setUsers((prev) => prev.map((item) => (item.id === user.id ? updated : item)));
      }
    } catch (err) {
      console.error(err);
      setError("Failed to update display name.");
    } finally {
      setIsSaving(null);
    }
  };

  return (
    <section className="page">
      <div className="page-header">
        <div>
          <h1>User Management</h1>
          <p className="muted">View users and update display names.</p>
        </div>
      </div>

      <Card>
        <div className="admin-filters">
          <select value={roleFilter} onChange={(event) => setRoleFilter(event.target.value as "ALL" | "REP" | "ADMIN")}>
            {roleOptions.map((option) => (
              <option key={option} value={option}>
                {option === "ALL" ? "All Roles" : option}
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

      <Card>
        <AdminTable
          columns={[
            { key: "username", header: "Username", width: "25%" },
            { key: "role", header: "Role", width: "10%", align: "center", className: "no-ellipsis" },
            { key: "display", header: "Display Name", width: "25%", className: "col-display" },
            { key: "email", header: "Email", width: "25%" },
            { key: "action", header: "Action", width: "15%", className: "col-action no-ellipsis" }
          ]}
          rows={filteredUsers}
          rowKey={(row) => row.id}
          emptyStateText={isLoading ? undefined : "No users found."}
          renderRow={(user) => [
            user.username,
            user.role,
            <input
              key="display"
              type="text"
              value={nameEdits[user.id] ?? ""}
              onChange={(event) =>
                setNameEdits((prev) => ({ ...prev, [user.id]: event.target.value }))
              }
            />,
            user.email ?? "-",
            <Button
              key="action"
              type="button"
              variant="secondary"
              disabled={isSaving === user.id}
              onClick={() => handleSaveName(user)}
            >
              {isSaving === user.id ? "Saving..." : "Save"}
            </Button>
          ]}
        />
      </Card>
      <p className="muted">TODO: Add role assignment once backend is ready.</p>
    </section>
  );
};

export default AdminUsers;

