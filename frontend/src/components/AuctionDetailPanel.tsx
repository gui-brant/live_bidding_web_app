import type { Auction } from "../features/auctions/types";
import Button from "./Button";
import StatusBadge from "./StatusBadge";
import { formatLocalDateTime } from "../utils/datetime";

type AuctionDetailPanelProps = {
  item: Auction | null;
  onClose: () => void;
  onEnterRoom: (auctionId: string) => void;
  isInvited: boolean;
};

const AuctionDetailPanel = ({ item, onClose, onEnterRoom, isInvited }: AuctionDetailPanelProps) => {
  const fallbackImage =
    "data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='300' height='200'><rect width='100%' height='100%' fill='%23eef2ff'/><text x='50%' y='50%' dominant-baseline='middle' text-anchor='middle' fill='%235b6b8a' font-family='Arial' font-size='16'>Item</text></svg>";

  if (!item) {
    return (
      <aside className="auction-detail empty">
        <p className="muted">Select an auction to see details.</p>
      </aside>
    );
  }

  return (
    <aside className="auction-detail">
      <div className="auction-detail-header">
        <h2>{item.title}</h2>
        <StatusBadge status={item.status} />
      </div>
      <p className="muted">
        {item.items.length
          ? `${item.items.length} item(s)`
          : "No items attached"}
      </p>
      <div className="auction-detail-meta">
        <div>
          <span>Start</span>
          <strong>{formatLocalDateTime(item.start_time)}</strong>
        </div>
        <div>
          <span>End</span>
          <strong>{formatLocalDateTime(item.end_time)}</strong>
        </div>
      </div>
      {item.items.length ? (
        <div className="auction-detail-list">
          {item.items.map((auctionItem) => (
            <div key={auctionItem.id} className="auction-detail-item">
              <div className="auction-detail-item-media">
                <img
                  src={auctionItem.image_url}
                  alt={auctionItem.title}
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
              </div>
              <div className="auction-detail-item-info">
                <strong>{auctionItem.title}</strong>
                {auctionItem.description ? (
                  <p className="muted">{auctionItem.description}</p>
                ) : null}
              </div>
              <div className="auction-detail-item-meta">
                <span>${auctionItem.highest_bid.toFixed(2)}</span>
              </div>
            </div>
          ))}
        </div>
      ) : null}
      <div className="button-row">
        <Button
          type="button"
          disabled={!item.items.length || !isInvited}
          onClick={() => onEnterRoom(item.id)}
        >
          Bid
        </Button>
        <Button type="button" variant="secondary" onClick={onClose}>
          Close
        </Button>
      </div>
      {!isInvited ? <p className="error">You are not invited to this auction.</p> : null}
      <p className="muted">Bidding happens in the live room.</p>
    </aside>
  );
};

export default AuctionDetailPanel;
