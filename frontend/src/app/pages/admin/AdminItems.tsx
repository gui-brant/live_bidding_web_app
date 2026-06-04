import { useEffect, useMemo, useState } from "react";

import { api } from "../../../api";
import type { AdminItem } from "../../../features/admin/types";
import Card from "../../../components/Card";
import Spinner from "../../../components/Spinner";
import Button from "../../../components/Button";

type ItemForm = {
  name: string;
  category: string;
  description: string;
  image_url: string;
};

const CATEGORY_OPTIONS = ["physical item", "gift card"] as const;
const FALLBACK_IMAGE = "https://placehold.co/600x400?text=Item";

const normalizeImageUrlInput = (value: string) => {
  const trimmed = value.trim();
  if (!trimmed) {
    return "";
  }
  try {
    const parsed = new URL(trimmed);
    const mediaUrl = parsed.searchParams.get("mediaurl") || parsed.searchParams.get("imgurl");
    if (mediaUrl) {
      return decodeURIComponent(mediaUrl);
    }
  } catch {
    // ignore parse errors
  }
  if (
    /^https?:\/\//i.test(trimmed) ||
    trimmed.startsWith("data:") ||
    trimmed.startsWith("blob:") ||
    trimmed.startsWith("//")
  ) {
    return trimmed;
  }
  return `https://${trimmed}`;
};

const AdminItems = () => {
  const [items, setItems] = useState<AdminItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState<string | null>(null);
  const [newItem, setNewItem] = useState<ItemForm>({
    name: "",
    category: CATEGORY_OPTIONS[0],
    description: "",
    image_url: ""
  });
  const [edits, setEdits] = useState<Record<string, ItemForm>>({});
  const [showCreate, setShowCreate] = useState(false);

  const loadItems = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const response = await api.admin.listItems();
      setItems(response);
      setEdits((prev) => {
        const next = { ...prev };
        response.forEach((item) => {
          if (!next[item.id]) {
            next[item.id] = {
              name: item.name,
              category: item.category,
              description: item.description ?? "",
              image_url: item.image_url
            };
          }
        });
        return next;
      });
    } catch (err) {
      console.error(err);
      setError("Failed to load items.");
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    void loadItems();
  }, []);

  const hasCreateData = useMemo(() => {
    return Boolean(
      newItem.name.trim() &&
        newItem.image_url.trim() &&
        CATEGORY_OPTIONS.includes(newItem.category as typeof CATEGORY_OPTIONS[number])
    );
  }, [newItem]);

  const handleCreate = async () => {
    if (!hasCreateData) {
      setError("Name and category are required.");
      return;
    }
    setIsSaving("create");
    setError(null);
    try {
      const created = await api.admin.createItem({
        name: newItem.name.trim(),
        category: newItem.category,
        description: newItem.description.trim() || undefined,
        image_url: normalizeImageUrlInput(newItem.image_url)
      });
      setItems((prev) => [created, ...prev]);
      setEdits((prev) => ({
        ...prev,
        [created.id]: {
          name: created.name,
          category: created.category,
          description: created.description ?? "",
          image_url: created.image_url
        }
      }));
      setNewItem({ name: "", category: CATEGORY_OPTIONS[0], description: "", image_url: "" });
    } catch (err) {
      console.error(err);
      setError("Failed to create item.");
    } finally {
      setIsSaving(null);
    }
  };

  const handleUpdate = async (item: AdminItem) => {
    const next = edits[item.id];
    if (!next) {
      return;
    }
    const payload = {
      name: next.name.trim(),
      category: next.category,
      description: next.description.trim() || undefined,
      image_url: normalizeImageUrlInput(next.image_url)
    };
    if (!payload.name || !payload.image_url || !CATEGORY_OPTIONS.includes(payload.category as typeof CATEGORY_OPTIONS[number])) {
      setError("Name, category, and image URL are required.");
      return;
    }
    setIsSaving(item.id);
    setError(null);
    try {
      const updated = await api.admin.updateItem(item.id, payload);
      if (updated) {
        setItems((prev) => prev.map((row) => (row.id === item.id ? updated : row)));
        setEdits((prev) => ({
          ...prev,
          [item.id]: {
            name: updated.name,
            category: updated.category,
            description: updated.description ?? "",
            image_url: updated.image_url
          }
        }));
      }
    } catch (err) {
      console.error(err);
      setError("Failed to update item.");
    } finally {
      setIsSaving(null);
    }
  };

  const handleDelete = async (item: AdminItem) => {
    const confirmed = window.confirm(`Delete ${item.name}? This cannot be undone.`);
    if (!confirmed) {
      return;
    }
    setIsSaving(item.id);
    setError(null);
    try {
      await api.admin.deleteItem(item.id);
      setItems((prev) => prev.filter((row) => row.id !== item.id));
    } catch (err) {
      console.error(err);
      setError("Failed to delete item.");
    } finally {
      setIsSaving(null);
    }
  };

  const visibleItems = useMemo(() => {
    return items.filter((item) => {
      const status = (item.status ?? "").toUpperCase();
      if (status === "SOLD") {
        return false;
      }
      if (item.winner_user_id) {
        return false;
      }
      return true;
    });
  }, [items]);

  return (
    <section className="page">
      <div className="page-header">
        <div>
          <h1>Item Management</h1>
          <p className="muted">Create, edit, and remove auction items.</p>
        </div>
        <div className="button-row">
          <Button type="button" variant="secondary" onClick={() => setShowCreate((prev) => !prev)}>
            {showCreate ? "Close Add Item" : "Add Item"}
          </Button>
          <Button type="button" variant="secondary" onClick={loadItems} disabled={isLoading}>
            {isLoading ? "Refreshing..." : "Refresh"}
          </Button>
        </div>
      </div>

      {isLoading ? (
        <div className="center">
          <Spinner />
        </div>
      ) : null}
      {error ? <p className="error">{error}</p> : null}

      {showCreate ? (
        <Card title="Create Item">
          <div className="form">
            <label className="field">
              <span>Name</span>
              <input
                type="text"
                value={newItem.name}
                onChange={(event) => setNewItem((prev) => ({ ...prev, name: event.target.value }))}
              />
            </label>
            <label className="field">
              <span>Category</span>
              <select
                value={newItem.category}
                onChange={(event) => setNewItem((prev) => ({ ...prev, category: event.target.value }))}
              >
                {CATEGORY_OPTIONS.map((option) => (
                  <option key={option} value={option}>
                    {option}
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              <span>Description</span>
              <textarea
                rows={3}
                value={newItem.description}
                onChange={(event) => setNewItem((prev) => ({ ...prev, description: event.target.value }))}
              />
            </label>
            <label className="field">
              <span>Image URL</span>
              <input
                type="text"
                value={newItem.image_url}
                onChange={(event) => setNewItem((prev) => ({ ...prev, image_url: event.target.value }))}
                placeholder="https://..."
              />
            </label>
            <div className="button-row">
              <Button type="button" disabled={!hasCreateData || isSaving === "create"} onClick={handleCreate}>
                {isSaving === "create" ? "Creating..." : "Create Item"}
              </Button>
            </div>
          </div>
        </Card>
      ) : null}

      {visibleItems.length === 0 && !isLoading ? <p className="muted">No items found.</p> : null}
      <div className="admin-item-grid">
        {visibleItems.map((item) => {
          const row = edits[item.id] ?? {
            name: item.name,
            category: item.category,
            description: item.description ?? "",
            image_url: item.image_url
          };
          const previewUrl = normalizeImageUrlInput(row.image_url) || item.image_url || FALLBACK_IMAGE;
          return (
            <Card key={item.id} className="admin-item-card">
              <div className="admin-item-media">
                <div className="admin-item-image">
                  <img
                    src={previewUrl}
                    alt={row.name || item.name}
                    loading="lazy"
                    onError={(event) => {
                      const img = event.currentTarget;
                      if (img.dataset.fallback === "1") {
                        return;
                      }
                      img.dataset.fallback = "1";
                      img.src = FALLBACK_IMAGE;
                    }}
                  />
                </div>
              </div>
              <div className="admin-item-body">
                <label className="admin-item-field">
                  <span>Name</span>
                  <input
                    type="text"
                    value={row.name}
                    onChange={(event) =>
                      setEdits((prev) => ({
                        ...prev,
                        [item.id]: { ...row, name: event.target.value }
                      }))
                    }
                  />
                </label>
                <label className="admin-item-field">
                  <span>Category</span>
                  <select
                    value={
                      CATEGORY_OPTIONS.includes(row.category as typeof CATEGORY_OPTIONS[number]) ? row.category : ""
                    }
                    onChange={(event) =>
                      setEdits((prev) => ({
                        ...prev,
                        [item.id]: { ...row, category: event.target.value }
                      }))
                    }
                  >
                    <option value="" disabled>
                      Select category
                    </option>
                    {CATEGORY_OPTIONS.map((option) => (
                      <option key={option} value={option}>
                        {option}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="admin-item-field">
                  <span>Description</span>
                  <textarea
                    rows={2}
                    value={row.description}
                    onChange={(event) =>
                      setEdits((prev) => ({
                        ...prev,
                        [item.id]: { ...row, description: event.target.value }
                      }))
                    }
                  />
                </label>
                <label className="admin-item-field">
                  <span>Image URL</span>
                  <input
                    type="text"
                    value={row.image_url}
                    onChange={(event) =>
                      setEdits((prev) => ({
                        ...prev,
                        [item.id]: { ...row, image_url: event.target.value }
                      }))
                    }
                    placeholder="https://..."
                  />
                </label>
                <div className="admin-item-actions">
                  <Button
                    type="button"
                    variant="secondary"
                    disabled={isSaving === item.id}
                    onClick={() => handleUpdate(item)}
                  >
                    {isSaving === item.id ? "Updating..." : "Update"}
                  </Button>
                  <Button
                    type="button"
                    variant="secondary"
                    disabled={isSaving === item.id}
                    onClick={() => handleDelete(item)}
                  >
                    Delete
                  </Button>
                </div>
              </div>
            </Card>
          );
        })}
      </div>
    </section>
  );
};

export default AdminItems;
