import { useCallback, useEffect, useState } from "react";

import { api } from "../../api";
import type { WishlistItem } from "../../api/wishlist";
import { API_BASE_URL } from "../../api/client";
import Card from "../../components/Card";
import Spinner from "../../components/Spinner";

const Wishlist = () => {
  const [items, setItems] = useState<WishlistItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // form state
  const [name, setName] = useState("");
  const [category, setCategory] = useState<"physical" | "giftcard">("physical");
  const [imageFile, setImageFile] = useState<File | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const loadItems = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await api.wishlist.getMyWishlist();
      setItems(data);
    } catch (err) {
      console.error(err);
      setError("Failed to load wishlist.");
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadItems();
  }, [loadItems]);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0] ?? null;
    setImageFile(file);
  };

  const fileToBase64 = (file: File): Promise<string> =>
    new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => {
        const result = reader.result as string;
        // strip the data:...;base64, prefix
        resolve(result.split(",")[1]);
      };
      reader.onerror = reject;
      reader.readAsDataURL(file);
    });

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;
    setIsSubmitting(true);
    try {
      let imageBase64: string | null = null;
      if (imageFile) {
        imageBase64 = await fileToBase64(imageFile);
      }
      await api.wishlist.addWishlistItem({
        name: name.trim(),
        category,
        image_base64: imageBase64,
      });
      setName("");
      setCategory("physical");
      setImageFile(null);
      // reset file input
      const fileInput = document.getElementById("wishlist-image-input") as HTMLInputElement | null;
      if (fileInput) fileInput.value = "";
      await loadItems();
    } catch (err) {
      console.error(err);
      setError("Failed to add item.");
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleDelete = async (itemId: string) => {
    try {
      await api.wishlist.deleteWishlistItem(itemId);
      await loadItems();
    } catch (err) {
      console.error(err);
      setError("Failed to delete item.");
    }
  };

  const resolveImage = (url?: string | null) => {
    if (!url) return undefined;
    if (url.startsWith("http")) return url;
    return `${API_BASE_URL}${url}`;
  };

  return (
    <section className="page">
      <div className="page-header">
        <div>
          <h1>My Wishlist</h1>
          <p className="muted">Add items you'd like to see in future auctions.</p>
        </div>
      </div>

      <Card title="Add Item" className="wishlist-form-card">
        <form onSubmit={handleSubmit} className="wishlist-form">
          <div className="form-row">
            <label htmlFor="wishlist-name">Item Name</label>
            <input
              id="wishlist-name"
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Amazon Gift Card"
              required
            />
          </div>
          <div className="form-row">
            <label htmlFor="wishlist-category">Category</label>
            <select
              id="wishlist-category"
              value={category}
              onChange={(e) => setCategory(e.target.value as "physical" | "giftcard")}
            >
              <option value="physical">Physical Item</option>
              <option value="giftcard">Gift Card</option>
            </select>
          </div>
          <div className="form-row">
            <label htmlFor="wishlist-image-input">Image (optional)</label>
            <input
              id="wishlist-image-input"
              type="file"
              accept="image/*"
              onChange={handleFileChange}
            />
          </div>
          <button type="submit" className="btn btn-primary" disabled={isSubmitting || !name.trim()}>
            {isSubmitting ? "Adding..." : "Add to Wishlist"}
          </button>
        </form>
      </Card>

      {isLoading ? (
        <div className="center">
          <Spinner />
        </div>
      ) : null}

      {error ? <p className="error">{error}</p> : null}

      {!isLoading && items.length === 0 ? (
        <p className="muted" style={{ textAlign: "center", marginTop: "2rem" }}>
          Your wishlist is empty. Add items above!
        </p>
      ) : null}

      {items.length > 0 ? (
        <div className="wishlist-items-grid">
          {items.map((item) => (
            <Card key={item.id} className="wishlist-item-card">
              <div className="wishlist-item-row">
                {item.image_url ? (
                  <img
                    className="wishlist-item-thumb"
                    src={resolveImage(item.image_url)}
                    alt={item.name}
                  />
                ) : (
                  <div className="wishlist-item-thumb wishlist-item-thumb-placeholder">
                    {item.category === "giftcard" ? "🎁" : "📦"}
                  </div>
                )}
                <div className="wishlist-item-info">
                  <strong>{item.name}</strong>
                  <span className={`wishlist-cat-badge wishlist-cat-${item.category}`}>
                    {item.category === "giftcard" ? "Gift Card" : "Physical"}
                  </span>
                </div>
                <button
                  type="button"
                  className="btn btn-danger btn-sm"
                  onClick={() => handleDelete(item.id)}
                  title="Remove"
                >
                  ✕
                </button>
              </div>
            </Card>
          ))}
        </div>
      ) : null}
    </section>
  );
};

export default Wishlist;
