import React from "react";
import Paper from "@mui/material/Paper";
import Typography from "@mui/material/Typography";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";

interface FunnelStagesSummaryProps {
  stages: Record<string, number>;
}

const STAGE_LABELS: Array<{ key: string; label: string }> = [
  { key: "entered", label: "Entered" },
  { key: "lead", label: "Альманах" },
  { key: "platform", label: "Platform" },
  { key: "learning", label: "Learning" },
  { key: "course", label: "Course" },
  { key: "interview", label: "Interview" },
  { key: "passed", label: "Passed" },
  { key: "offer", label: "Offer" },
  { key: "distance_grinding", label: "Distance Grinding" },
  { key: "contract", label: "Contract" },
];

const FunnelStagesSummary: React.FC<FunnelStagesSummaryProps> = ({ stages }) => {
  return (
    <Paper sx={{ mt: 2, p: 2, borderRadius: "24px", border: "1px solid var(--app-shell-border)", background: "var(--app-panel-bg)", boxShadow: "var(--app-shell-shadow)", overflow: "hidden" }}>
      <Typography variant="h6" mb={1} sx={{ color: "var(--c-ink)", fontWeight: 800 }}>
        Funnel Summary
      </Typography>
      <Table size="small" sx={{
        "& .MuiTableCell-root": { borderBottom: "1px solid var(--app-table-divider)" },
        "& .MuiTableHead-root .MuiTableCell-root": { backgroundColor: "var(--app-table-head-bg)", color: "var(--c-ink2)", fontWeight: 700 },
        "& .MuiTableBody-root .MuiTableRow-root:nth-of-type(even)": { backgroundColor: "var(--app-table-row-alt)" },
      }}>
        <TableHead>
          <TableRow>
            <TableCell>Stage</TableCell>
            <TableCell align="right">Users</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {STAGE_LABELS.map((stage) => (
            <TableRow key={stage.key}>
              <TableCell>{stage.label}</TableCell>
              <TableCell align="right">{(stages[stage.key] || 0).toLocaleString()}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </Paper>
  );
};

export default FunnelStagesSummary;
