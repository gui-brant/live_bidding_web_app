import type { Auction } from "../features/auctions/types";
import StatusBadge from "./StatusBadge";
import Button from "./Button";
import { formatLocalDateTime } from "../utils/datetime";

type AuctionCardProps = {
  item: Auction;
  onSelect: (item: Auction) => void;
};

const AuctionCard = ({ item, onSelect }: AuctionCardProps) => {
  const primaryItem =
    item.items.find((entry) => entry.image_url && !entry.image_url.includes("placehold.co")) ??
    item.items[0];
  const extraCount = Math.max(0, item.items.length - 1);
  const fallbackImage =
    "data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='600' height='400'><rect width='100%' height='100%' fill='%23eef2ff'/><text x='50%' y='50%' dominant-baseline='middle' text-anchor='middle' fill='%235b6b8a' font-family='Arial' font-size='24'>Auction</text></svg>";

  const normalizeImageSrc = (value?: string) => {
    const trimmed = (value ?? "").trim();
    if (!trimmed) {
      return fallbackImage;
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
  const imageSrc = normalizeImageSrc(primaryItem?.image_url);

  return (
    <article className="auction-card">
      <img
        src={imageSrc}
        alt={item.title}
        loading="lazy"
        onError={(event) => {
          const img = event.currentTarget;
          if (img.dataset.fallback === "1") {
            return;
          }
          img.dataset.fallback = "1";
          img.src = fallbackImage;
        }}
      />
      <div className="auction-card-body">
        <div className="auction-card-header">
          <h3>{item.title}</h3>
          <StatusBadge status={item.status} />
        </div>
        <p className="muted">
          {primaryItem ? primaryItem.title : "No items attached"}
          {extraCount > 0 ? ` +${extraCount} more` : ""}
        </p>
        <div className="auction-card-meta">
          <span>Start: {formatLocalDateTime(item.start_time)}</span>
          <span>End: {formatLocalDateTime(item.end_time)}</span>
        </div>
        <div className="auction-card-meta">
          <span>Items</span>
          <strong>{item.items.length}</strong>
        </div>
        <Button type="button" variant="secondary" onClick={() => onSelect(item)}>
          View
        </Button>
      </div>
    </article>
  );
};

export default AuctionCard;
