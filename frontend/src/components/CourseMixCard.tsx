import React, { useMemo } from "react";
import Paper from "@mui/material/Paper";
import Typography from "@mui/material/Typography";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableContainer from "@mui/material/TableContainer";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import LinearProgress from "@mui/material/LinearProgress";

import { CourseMixRow } from "../hooks/useCourseMix";

export interface CourseMixCardProps {
  data: CourseMixRow[];
  loading: boolean;
}

const CourseMixCard: React.FC<CourseMixCardProps> = ({ data, loading }) => {
  const total = useMemo(() => data.reduce((sum, row) => sum + (row.users || 0), 0), [data]);
  return (
    <Paper sx={{ mt: 2, p: 2 }}>
      <Typography variant="h6" mb={1}>
        Course mix (MTT/SPIN/CASH)
      </Typography>
      {loading && <LinearProgress />}
      <TableContainer>
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>Курс</TableCell>
              <TableCell>Пользователи</TableCell>
              <TableCell>Доля</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {data.map((row) => {
              const share = total ? ((row.users || 0) / total) * 100 : 0;
              return (
                <TableRow key={row.course}>
                  <TableCell>{row.course}</TableCell>
                  <TableCell>{row.users}</TableCell>
                  <TableCell>{share.toFixed(1)}%</TableCell>
                </TableRow>
              );
            })}
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
};

export default CourseMixCard;
