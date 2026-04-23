import React from "react";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import Typography from "@mui/material/Typography";
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from "recharts";

export interface LineChartCardProps {
  title: string;
  data: { date: string; users: number }[];
}

const LineChartCard: React.FC<LineChartCardProps> = ({ title, data }) => (
  <Card
    sx={{
      mt: 2,
      mb: 2,
      borderRadius: "24px",
      border: "1px solid var(--app-shell-border)",
      background: "var(--app-panel-bg)",
      boxShadow: "var(--app-shell-shadow)",
    }}
  >
    <CardContent sx={{ p: 2.25 }}>
      <Typography variant="h6" gutterBottom sx={{ color: "var(--c-ink)", fontWeight: 800 }}>
        {title}
      </Typography>
      <ResponsiveContainer width="100%" height={240}>
        <LineChart data={data} margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
          <CartesianGrid stroke="var(--app-table-divider)" strokeDasharray="3 3" />
          <XAxis dataKey="date" tick={{ fontSize: 12, fill: "var(--c-ink2)" }} axisLine={{ stroke: "var(--app-table-divider)" }} tickLine={{ stroke: "var(--app-table-divider)" }} />
          <YAxis allowDecimals={false} tick={{ fill: "var(--c-ink2)" }} axisLine={{ stroke: "var(--app-table-divider)" }} tickLine={{ stroke: "var(--app-table-divider)" }} />
          <Tooltip
            contentStyle={{
              borderRadius: 16,
              border: "1px solid var(--app-shell-border)",
              background: "var(--app-panel-bg)",
              color: "var(--c-ink)",
            }}
          />
          <Line type="monotone" dataKey="users" stroke="var(--c-blue)" strokeWidth={3} dot={{ r: 2, fill: "var(--c-blue)" }} />
        </LineChart>
      </ResponsiveContainer>
    </CardContent>
  </Card>
);

export default LineChartCard;
