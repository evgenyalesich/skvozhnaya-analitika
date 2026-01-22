import React, { useState } from "react";
import Grid from "@mui/material/Grid";
import Typography from "@mui/material/Typography";
import FilterPanel from "../components/FilterPanel";
import OverviewTabs from "../components/OverviewTabs";
import MetricCard from "../components/MetricCard";
import LineChartCard from "../components/LineChartCard";
import RawUsersTable from "../components/RawUsersTable";
import { useReports } from "../hooks/useReports";
import { useBots } from "../hooks/useBots";

const OverviewPage: React.FC = () => {
  const { bots } = useBots();
  const { total, daily, raw, loading, refresh } = useReports();
  const [filters, setFilters] = useState({ startDate: null, endDate: null, bot: "" });
  const [tab, setTab] = useState<"overview" | "conversions" | "details" | "raw">("overview");

  const handleFilterChange = (key: string, value: any) => {
    setFilters((prev) => ({ ...prev, [key]: value }));
  };

  return (
    <section>
      <Typography variant="h4" mt={2} mb={1}>
        Analytics Dashboard
      </Typography>
      <FilterPanel bots={bots} filters={filters} onChange={handleFilterChange} onApply={refresh} />
      <OverviewTabs value={tab} onChange={setTab} />
      <Grid container spacing={2} mt={2}>
        <Grid item xs={12} md={4}>
          <MetricCard label="Users at Funnel Start" value={total?.total_users ?? "—"} />
        </Grid>
        <Grid item xs={12} md={4}>
          <MetricCard label="Total Budget" value={total?.total_budget ?? "—"} />
        </Grid>
        <Grid item xs={12} md={4}>
          <MetricCard label="CAC" value={total?.cac?.toFixed(2) ?? "—"} caption="Cost per acquisition" />
        </Grid>
      </Grid>
      <LineChartCard title="Daily New Users" data={daily.map((point) => ({ date: point.date, users: point.users }))} />
      <RawUsersTable users={raw} />
      {loading && <Typography variant="body2">Loading...</Typography>}
    </section>
  );
};

export default OverviewPage;
