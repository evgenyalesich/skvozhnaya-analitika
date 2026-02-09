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
  <Paper sx={{ mt: 2 }}>
    <Typography variant="h6" p={2}>
      Breakdown by {groupBy.replace("_", " ")}
    </Typography>
    {loading && <LinearProgress />}
    <TableContainer>
      <Table size="small">
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
