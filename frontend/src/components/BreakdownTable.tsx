// Таблица разбивки по utm_source/utm_campaign/bot_key (breakdown endpoint).
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

interface BreakdownRow {
  group: string;
  users: number;
  budget: number;
}

interface BreakdownTableProps {
  data: BreakdownRow[];
  loading: boolean;
  groupBy: string;
}

const BreakdownTable: React.FC<BreakdownTableProps> = ({ data, loading, groupBy }) => (
  <Paper
    sx={{
      mt: 2,
      borderRadius: "24px",
      border: "1px solid var(--app-shell-border)",
      background: "var(--app-panel-bg)",
      boxShadow: "var(--app-shell-shadow)",
      overflow: "hidden",
    }}
  >
    <Typography variant="h6" p={2} sx={{ color: "var(--c-ink)", fontWeight: 800 }}>
      Breakdown by {groupBy.replace("_", " ")}
    </Typography>
    {loading && <LinearProgress />}
    <TableContainer>
      <Table
        size="small"
        sx={{
          "& .MuiTableCell-root": {
            borderBottom: "1px solid var(--app-table-divider)",
          },
          "& .MuiTableHead-root .MuiTableCell-root": {
            backgroundColor: "var(--app-table-head-bg)",
            color: "var(--c-ink2)",
            fontWeight: 700,
          },
          "& .MuiTableBody-root .MuiTableRow-root:nth-of-type(even)": {
            backgroundColor: "var(--app-table-row-alt)",
          },
        }}
      >
        <TableHead>
          <TableRow>
            <TableCell>Group</TableCell>
            <TableCell>Users</TableCell>
            <TableCell>Budget</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {data.map((row) => (
            <TableRow key={`${row.group}-${row.users}`} hover>
              <TableCell>{row.group || "—"}</TableCell>
              <TableCell>{row.users}</TableCell>
              <TableCell>{row.budget?.toFixed(2)}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </TableContainer>
  </Paper>
);

export default BreakdownTable;
