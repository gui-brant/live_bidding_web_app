import { useCallback, useEffect, useState } from "react";

import { api } from "../../../api";
import type {
  WishlistAggResponse,
  WishlistAggSlice,
  WishlistItemDetail,
} from "../../../api/wishlist";
import { API_BASE_URL } from "../../../api/client";
import Card from "../../../components/Card";
import Spinner from "../../../components/Spinner";

// ---- Tiny SVG pie chart ---------------------------------------------------

const COLORS = [
  "#2563eb",
  "#38bdf8",
  "#6366f1",
  "#f59e0b",
  "#10b981",
  "#ef4444",
  "#8b5cf6",
  "#ec4899",
  "#14b8a6",
  "#f97316",
];

type PieSlice = { label: string; value: number };

function PieChart({
  slices,
  size = 220,
  onSliceClick,
}: {
  slices: PieSlice[];
  size?: number;
  onSliceClick?: (label: string) => void;
}) {
  if (slices.length === 0) {
    return (
      <div
        style={{
          width: size,
          height: size,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          color: "var(--color-muted)",
        }}
      >
        No data
      </div>
    );
  }

  const total = slices.reduce((s, sl) => s + sl.value, 0);
  const cx = size / 2;
  const cy = size / 2;
  const r = size / 2 - 4;

  let cumAngle = -Math.PI / 2;
  const paths: JSX.Element[] = [];

  slices.forEach((sl, i) => {
    const angle = (sl.value / total) * 2 * Math.PI;
    const x1 = cx + r * Math.cos(cumAngle);
    const y1 = cy + r * Math.sin(cumAngle);
    const x2 = cx + r * Math.cos(cumAngle + angle);
    const y2 = cy + r * Math.sin(cumAngle + angle);
    const largeArc = angle > Math.PI ? 1 : 0;

    paths.push(
      <path
        key={i}
        d={`M${cx},${cy} L${x1},${y1} A${r},${r} 0 ${largeArc} 1 ${x2},${y2} Z`}
        fill={COLORS[i % COLORS.length]}
        stroke="var(--color-surface)"
        strokeWidth={2}
        style={{ cursor: onSliceClick ? "pointer" : "default" }}
        onClick={() => onSliceClick?.(sl.label)}
      >
        <title>
          {sl.label}: {sl.value}
        </title>
      </path>
    );

    cumAngle += angle;
  });

  return (
    <div className="pie-chart-container">
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
        {paths}
      </svg>
      <ul className="pie-legend">
        {slices.map((sl, i) => (
          <li
            key={sl.label}
            className="pie-legend-item"
            style={{ cursor: onSliceClick ? "pointer" : "default" }}
            onClick={() => onSliceClick?.(sl.label)}
          >
            <span
              className="pie-legend-swatch"
              style={{ background: COLORS[i % COLORS.length] }}
            />
            {sl.label} ({sl.value})
          </li>
        ))}
      </ul>
    </div>
  );
}

// ---- Page component -------------------------------------------------------

const AdminWishlist = () => {
  const [agg, setAgg] = useState<WishlistAggResponse | null>(null);
  const [detail, setDetail] = useState<WishlistItemDetail | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadAgg = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await api.wishlist.getWishlistAggregate();
      setAgg(data);
    } catch (err) {
      console.error(err);
      setError("Failed to load wishlist data.");
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadAgg();
  }, [loadAgg]);

  const handleSliceClick = async (itemName: string, category: "physical" | "giftcard") => {
    setDetailLoading(true);
    setDetail(null);
    try {
      const data = await api.wishlist.getWishlistItemDetail(itemName, category);
      setDetail(data);
    } catch (err) {
      console.error(err);
      setError("Failed to load item details.");
    } finally {
      setDetailLoading(false);
    }
  };

  const resolveImage = (url?: string | null) => {
    if (!url) return undefined;
    if (url.startsWith("http")) return url;
    return `${API_BASE_URL}${url}`;
  };

  const physicalSlices: PieSlice[] =
    agg?.physical.map((s) => ({ label: s.name, value: s.count })) ?? [];
  const giftcardSlices: PieSlice[] =
    agg?.giftcard.map((s) => ({ label: s.name, value: s.count })) ?? [];

  return (
    <section className="page">
      <div className="page-header">
        <div>
          <h1>Wishlist Overview</h1>
          <p className="muted">See what reps are wishing for, grouped by category.</p>
        </div>
      </div>

      {isLoading ? (
        <div className="center">
          <Spinner />
        </div>
      ) : null}

      {error ? <p className="error">{error}</p> : null}

      {agg ? (
        <div className="wishlist-pie-row">
          <Card title="Physical Items" className="wishlist-pie-card">
            <PieChart
              slices={physicalSlices}
              onSliceClick={(label) => handleSliceClick(label, "physical")}
            />
          </Card>
          <Card title="Gift Cards" className="wishlist-pie-card">
            <PieChart
              slices={giftcardSlices}
              onSliceClick={(label) => handleSliceClick(label, "giftcard")}
            />
          </Card>
        </div>
      ) : null}

      {detailLoading ? (
        <div className="center" style={{ marginTop: "1rem" }}>
          <Spinner />
        </div>
      ) : null}

      {detail ? (
        <Card
          title={`"${detail.name}" — ${detail.category === "giftcard" ? "Gift Card" : "Physical"} (${detail.count} wish${detail.count === 1 ? "" : "es"})`}
          className="wishlist-detail-card"
        >
          <button
            type="button"
            className="btn btn-sm"
            style={{ marginBottom: "0.75rem" }}
            onClick={() => setDetail(null)}
          >
            ← Back to charts
          </button>
          {detail.reps.length === 0 ? (
            <p className="muted">No reps found.</p>
          ) : (
            <ul className="wishlist-rep-list">
              {detail.reps.map((rep, idx) => (
                <li key={`${rep.user_id}-${idx}`} className="wishlist-rep-row">
                  {rep.image_url ? (
                    <img
                      className="wishlist-rep-thumb"
                      src={resolveImage(rep.image_url)}
                      alt="item"
                    />
                  ) : (
                    <div className="wishlist-rep-thumb wishlist-rep-thumb-placeholder">
                      {detail.category === "giftcard" ? "🎁" : "📦"}
                    </div>
                  )}
                  <div className="wishlist-rep-info">
                    <strong>{rep.user_name || rep.user_email}</strong>
                    <span className="muted" style={{ marginLeft: "0.5rem" }}>
                      {rep.user_email}
                    </span>
                    <span className="muted" style={{ marginLeft: "0.5rem" }}>
                      — {detail.name}
                    </span>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Card>
      ) : null}
    </section>
  );
};

export default AdminWishlist;
