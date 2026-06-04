import type { AuctionStatus } from "../features/auctions/types";

type StatusBadgeProps = {
  status: AuctionStatus;
};

const StatusBadge = ({ status }: StatusBadgeProps) => {
  return <span className={`status-badge ${status.toLowerCase()}`}>{status}</span>;
};

export default StatusBadge;

