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
  <Card sx={{ minWidth: 180 }}>
    <CardContent>
      <Typography variant="subtitle2" color="textSecondary">
        {label}
      </Typography>
      <Typography variant="h4" mt={1}>
        {value}
      </Typography>
      {caption && (
        <Typography variant="caption" color="textSecondary">
          {caption}
        </Typography>
      )}
    </CardContent>
  </Card>
);

export default MetricCard;
