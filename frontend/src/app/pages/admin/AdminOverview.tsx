import { useEffect, useState } from "react";

import { api } from "../../../api";
import type { AdminOverview as AdminOverviewData } from "../../../features/admin/types";
import Card from "../../../components/Card";
import Spinner from "../../../components/Spinner";

const AdminOverview = () => {
  const [overview, setOverview] = useState<AdminOverviewData | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const loadOverview = async () => {
      setIsLoading(true);
      setError(null);
      try {
        const response = await api.admin.getAdminOverview();
        setOverview(response);
      } catch (err) {
        console.error(err);
        setError("Failed to load admin overview.");
      } finally {
        setIsLoading(false);
      }
    };

    void loadOverview();
  }, []);

  return (
    <section className="page">
      <div className="page-header">
        <div>
          <h1>Admin Overview</h1>
          <p className="muted">System snapshots and quick metrics.</p>
        </div>
      </div>

      {isLoading ? (
        <div className="center">
          <Spinner />
        </div>
      ) : null}
      {error ? <p className="error">{error}</p> : null}

      {overview ? (
        <div className="grid">
          <Card title="Total Users">
            <strong className="kpi">{overview.totalUsers}</strong>
          </Card>
          <Card title="Active Auctions">
            <strong className="kpi">{overview.activeAuctions}</strong>
          </Card>
          <Card title="Upcoming Auctions">
            <strong className="kpi">{overview.upcomingAuctions}</strong>
          </Card>
          <Card title="System Status">
            <strong className="kpi">{overview.systemStatus}</strong>
          </Card>
        </div>
      ) : null}
    </section>
  );
};

export default AdminOverview;
