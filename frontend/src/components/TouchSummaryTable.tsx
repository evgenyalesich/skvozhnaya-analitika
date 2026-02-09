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

import { TouchSummaryRow } from "../hooks/useTouchSummary";

export interface TouchSummaryTableProps {
  data: TouchSummaryRow[];
  loading: boolean;
  mode: "first" | "last";
}

const TouchSummaryTable: React.FC<TouchSummaryTableProps> = ({ data, loading, mode }) => (
  <Paper sx={{ mt: 2 }}>
    <Typography variant="h6" p={2}>
      Total C ({mode === "first" ? "First touch" : "Last touch"})
    </Typography>
    {loading && <LinearProgress />}
    <TableContainer>
      <Table size="small">
        <TableHead>
          <TableRow>
            <TableCell>Бот</TableCell>
            <TableCell>РК</TableCell>
            <TableCell>Пользователи</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {data.map((row, idx) => (
            <TableRow key={`${row.bot}-${row.campaign}-${idx}`} hover>
              <TableCell>{row.bot || "нет метки"}</TableCell>
              <TableCell>{row.campaign || "нет метки"}</TableCell>
              <TableCell>{row.users}</TableCell>
            </TableRow>
          ))}
          {!data.length && (
            <TableRow>
              <TableCell colSpan={3}>Нет данных</TableCell>
            </TableRow>
          )}
        </TableBody>
      </Table>
    </TableContainer>
  </Paper>
);

export default TouchSummaryTable;
