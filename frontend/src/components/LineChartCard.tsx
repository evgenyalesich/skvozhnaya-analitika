import React from "react";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import Typography from "@mui/material/Typography";
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts";

export interface LineChartCardProps {
  title: string;
  data: { date: string; users: number }[];
}

const LineChartCard: React.FC<LineChartCardProps> = ({ title, data }) => (
  <Card sx={{ mt: 2, mb: 2 }}>
    <CardContent>
      <Typography variant="h6" gutterBottom>
        {title}
      </Typography>
      <ResponsiveContainer width="100%" height={240}>
        <LineChart data={data} margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
          <XAxis dataKey="date" tick={{ fontSize: 12 }} />
          <YAxis allowDecimals={false} />
          <Tooltip />
          <Line type="monotone" dataKey="users" stroke="#1976d2" strokeWidth={2} dot={{ r: 2 }} />
        </LineChart>
      </ResponsiveContainer>
    </CardContent>
  </Card>
);

export default LineChartCard;
