import React from "react";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableContainer from "@mui/material/TableContainer";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import Paper from "@mui/material/Paper";
import Typography from "@mui/material/Typography";

export interface RawUsersTableProps {
  users: Array<Record<string, any>>;
}

const RawUsersTable: React.FC<RawUsersTableProps> = ({ users }) => (
  <TableContainer component={Paper} sx={{ mt: 2 }}>
    <Typography variant="h6" p={2}>
      RAW Users ({users.length})
    </Typography>
    <Table size="small">
      <TableHead>
        <TableRow>
          <TableCell>ID</TableCell>
          <TableCell>Bot Key</TableCell>
          <TableCell>TG User ID</TableCell>
          <TableCell>Created At</TableCell>
          <TableCell>UTM Source</TableCell>
          <TableCell>UTM Campaign</TableCell>
          <TableCell>Budget</TableCell>
        </TableRow>
      </TableHead>
      <TableBody>
        {users.map((user) => (
          <TableRow key={user.id} hover>
            <TableCell>{user.id}</TableCell>
            <TableCell>{user.bot_key}</TableCell>
            <TableCell>{user.tg_user_id}</TableCell>
            <TableCell>{user.created_at}</TableCell>
            <TableCell>{user.utm_source || "(none)"}</TableCell>
            <TableCell>{user.utm_campaign || "(none)"}</TableCell>
            <TableCell>{user.budget?.toFixed(2) ?? "0"}</TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  </TableContainer>
);

export default RawUsersTable;
