import React from "react";
import Paper from "@mui/material/Paper";
import Table from "@mui/material/Table";
import TableHead from "@mui/material/TableHead";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableRow from "@mui/material/TableRow";
import TableContainer from "@mui/material/TableContainer";
import Typography from "@mui/material/Typography";
import LinearProgress from "@mui/material/LinearProgress";
import { ConversionRow } from "../hooks/useReports";

export interface ConversionsTableProps {
  conversions: ConversionRow[];
  loading: boolean;
}

const ConversionsTable: React.FC<ConversionsTableProps> = ({ conversions, loading }) => {
  const totalEntered = conversions.reduce((sum, row) => sum + row.entered, 0);
  const totalConverted = conversions.reduce((sum, row) => sum + row.converted, 0);
  const totalRate = totalEntered ? (totalConverted / totalEntered) * 100 : 0;

  return (
    <Paper sx={{ mt: 2 }}>
      <Typography variant="h6" p={2}>
        Conversions
      </Typography>
      {loading && <LinearProgress />}
      <TableContainer>
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>Bot</TableCell>
              <TableCell>Entered Users</TableCell>
              <TableCell>Converted Users</TableCell>
              <TableCell>Conversion %</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {conversions.map((row) => (
              <TableRow key={row.bot_key} hover>
                <TableCell>{row.bot_key}</TableCell>
                <TableCell>{row.entered}</TableCell>
                <TableCell>{row.converted}</TableCell>
                <TableCell>{row.conversion_rate.toFixed(2)}%</TableCell>
              </TableRow>
            ))}
            <TableRow>
              <TableCell sx={{ fontWeight: "bold" }}>Total</TableCell>
              <TableCell sx={{ fontWeight: "bold" }}>{totalEntered}</TableCell>
              <TableCell sx={{ fontWeight: "bold" }}>{totalConverted}</TableCell>
              <TableCell sx={{ fontWeight: "bold" }}>{totalRate.toFixed(2)}%</TableCell>
            </TableRow>
          </TableBody>
        </Table>
      </TableContainer>
    </Paper>
  );
};

export default ConversionsTable;
