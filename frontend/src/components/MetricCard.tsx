import React from "react";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import Typography from "@mui/material/Typography";

export interface MetricCardProps {
  label: string;
  value: string | number;
  caption?: string;
}

const MetricCard: React.FC<MetricCardProps> = ({ label, value, caption }) => (
  <Card
    sx={{
      minWidth: 180,
      borderRadius: "24px",
      border: "1px solid var(--app-shell-border)",
      background: "var(--app-panel-bg)",
      boxShadow: "var(--app-shell-shadow)",
    }}
  >
    <CardContent sx={{ p: 2.25 }}>
      <Typography variant="subtitle2" sx={{ color: "var(--c-ink2)", fontWeight: 700 }}>
        {label}
      </Typography>
      <Typography variant="h4" mt={1.25} sx={{ color: "var(--c-ink)", fontWeight: 800 }}>
        {value}
      </Typography>
      {caption && (
        <Typography variant="caption" sx={{ color: "var(--c-ink2)", fontWeight: 600 }}>
          {caption}
        </Typography>
      )}
    </CardContent>
  </Card>
);

export default MetricCard;
