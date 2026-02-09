import React, { useMemo, useState } from "react";
import Paper from "@mui/material/Paper";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableContainer from "@mui/material/TableContainer";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import Typography from "@mui/material/Typography";
import LinearProgress from "@mui/material/LinearProgress";
import Stack from "@mui/material/Stack";
import FormControl from "@mui/material/FormControl";
import InputLabel from "@mui/material/InputLabel";
import Select from "@mui/material/Select";
import MenuItem from "@mui/material/MenuItem";
import { format, parseISO, isValid } from "date-fns";
import { RoistatWeeklyRow } from "../hooks/useRoistatWeekly";

interface WeeklyTableProps {
  rows: RoistatWeeklyRow[];
  loading: boolean;
  error?: string | null;
  selectedMonth?: string;
  onSelectedMonthChange?: (value: string) => void;
}

const pct = (num: number, den: number) => {
  if (!den) return "0.00%";
  return `${((num / den) * 100).toFixed(2)}%`;
};

const buildCr = (row: {
  almanah_starts: number;
  platform: number;
  learning: number;
  mtt: number;
  spin: number;
  cash: number;
  not_started: number;
  saloon: number;
}) => ({
  learningCr: pct(row.learning, row.platform),
  mttCr: pct(row.mtt, row.learning),
  spinCr: pct(row.spin, row.mtt),
  cashCr: pct(row.cash, row.spin),
  notStartedCr: pct(row.not_started, row.cash),
  saloonCr: pct(row.saloon, row.not_started),
});

const monthLabel = (monthKey: string) => {
  const [year, month] = monthKey.split("-");
  const names = [
    "Январь",
    "Февраль",
    "Март",
    "Апрель",
    "Май",
    "Июнь",
    "Июль",
    "Август",
    "Сентябрь",
    "Октябрь",
    "Ноябрь",
    "Декабрь",
  ];
  const m = Number(month);
  return `${names[m - 1] || month} ${year}`;
};

const endOfMonth = (d: Date) => new Date(d.getFullYear(), d.getMonth() + 1, 0);
const safeParse = (value: string) => {
  try {
    const dt = parseISO(value);
    return isValid(dt) ? dt : null;
  } catch {
    return null;
  }
};

const WeeklyTable: React.FC<WeeklyTableProps> = ({
  rows,
  loading,
  error,
  selectedMonth: controlledSelectedMonth,
  onSelectedMonthChange,
}) => {
  const [internalMonth, setInternalMonth] = useState<string>("all");
  const selectedMonth = controlledSelectedMonth ?? internalMonth;
  const setSelectedMonth = (value: string) => {
    if (onSelectedMonthChange) {
      onSelectedMonthChange(value);
      return;
    }
    setInternalMonth(value);
  };

  const grouped = useMemo(() => {
    const sorted = [...rows].sort((a, b) => a.week_start.localeCompare(b.week_start));
    const bucket = new Map<string, RoistatWeeklyRow[]>();
    sorted.forEach((row) => {
      const dt = safeParse(row.week_start);
      if (!dt) return;
      const key = format(dt, "yyyy-MM");
      const current = bucket.get(key) || [];
      current.push(row);
      bucket.set(key, current);
    });
    return bucket;
  }, [rows]);

  const monthKeys = useMemo(() => Array.from(grouped.keys()).sort(), [grouped]);

  const visibleMonthKeys = useMemo(() => {
    if (selectedMonth === "all") return monthKeys;
    return monthKeys.filter((m) => m === selectedMonth);
  }, [monthKeys, selectedMonth]);

  return (
    <Paper sx={{ mt: 2, p: 2 }}>
      <Stack direction="row" justifyContent="space-between" alignItems="center" mb={1}>
        <Typography variant="h6">
        Weekly
        </Typography>
        <FormControl size="small" sx={{ minWidth: 220 }}>
          <InputLabel id="weekly-month-label">Месяц</InputLabel>
          <Select
            labelId="weekly-month-label"
            label="Месяц"
            value={selectedMonth}
            onChange={(event) => setSelectedMonth(String(event.target.value))}
          >
            <MenuItem value="all">Все месяцы</MenuItem>
            {monthKeys.map((month) => (
              <MenuItem key={month} value={month}>
                {monthLabel(month)}
              </MenuItem>
            ))}
          </Select>
        </FormControl>
      </Stack>
      {loading && <LinearProgress sx={{ mb: 1 }} />}
      {error && (
        <Typography variant="body2" color="error" mb={1}>
          {error}
        </Typography>
      )}
      <TableContainer>
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>Период</TableCell>
              <TableCell align="right">Старт в бота</TableCell>
              <TableCell align="right">Регистрация на платформе</TableCell>
              <TableCell align="right">Регистрация на курс</TableCell>
              <TableCell align="right">CR %</TableCell>
              <TableCell align="right">mtt</TableCell>
              <TableCell align="right">CR %</TableCell>
              <TableCell align="right">spin</TableCell>
              <TableCell align="right">CR %</TableCell>
              <TableCell align="right">cash</TableCell>
              <TableCell align="right">CR %</TableCell>
              <TableCell align="right">Не начали курс</TableCell>
              <TableCell align="right">CR %</TableCell>
              <TableCell align="right">Салун</TableCell>
              <TableCell align="right">CR %</TableCell>
              <TableCell align="right">Бюджет</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {visibleMonthKeys.map((monthKey) => {
              const monthRows = grouped.get(monthKey) || [];
              const monthTotals = monthRows.reduce(
                (acc, row) => ({
                  almanah_starts: acc.almanah_starts + row.almanah_starts,
                  platform: acc.platform + row.platform,
                  learning: acc.learning + row.learning,
                  mtt: acc.mtt + row.mtt,
                  spin: acc.spin + row.spin,
                  cash: acc.cash + row.cash,
                  not_started: acc.not_started + row.not_started,
                  saloon: acc.saloon + row.saloon,
                  budget: acc.budget + row.budget,
                }),
                {
                  almanah_starts: 0,
                  platform: 0,
                  learning: 0,
                  mtt: 0,
                  spin: 0,
                  cash: 0,
                  not_started: 0,
                  saloon: 0,
                  budget: 0,
                }
              );
              return (
                <React.Fragment key={monthKey}>
                  {(() => {
                    const cr = buildCr(monthTotals);
                    return (
                      <TableRow sx={{ backgroundColor: "#ede7f6" }}>
                        <TableCell sx={{ fontWeight: 700 }}>{monthLabel(monthKey)}</TableCell>
                        <TableCell align="right" sx={{ fontWeight: 700 }}>{monthTotals.almanah_starts}</TableCell>
                        <TableCell align="right" sx={{ fontWeight: 700 }}>{monthTotals.platform}</TableCell>
                        <TableCell align="right" sx={{ fontWeight: 700 }}>{monthTotals.learning}</TableCell>
                        <TableCell align="right" sx={{ fontWeight: 700 }}>{cr.learningCr}</TableCell>
                        <TableCell align="right" sx={{ fontWeight: 700 }}>{monthTotals.mtt}</TableCell>
                        <TableCell align="right" sx={{ fontWeight: 700 }}>{cr.mttCr}</TableCell>
                        <TableCell align="right" sx={{ fontWeight: 700 }}>{monthTotals.spin}</TableCell>
                        <TableCell align="right" sx={{ fontWeight: 700 }}>{cr.spinCr}</TableCell>
                        <TableCell align="right" sx={{ fontWeight: 700 }}>{monthTotals.cash}</TableCell>
                        <TableCell align="right" sx={{ fontWeight: 700 }}>{cr.cashCr}</TableCell>
                        <TableCell align="right" sx={{ fontWeight: 700 }}>{monthTotals.not_started}</TableCell>
                        <TableCell align="right" sx={{ fontWeight: 700 }}>{cr.notStartedCr}</TableCell>
                        <TableCell align="right" sx={{ fontWeight: 700 }}>{monthTotals.saloon}</TableCell>
                        <TableCell align="right" sx={{ fontWeight: 700 }}>{cr.saloonCr}</TableCell>
                        <TableCell align="right" sx={{ fontWeight: 700 }}>{Number(monthTotals.budget || 0).toFixed(2)}</TableCell>
                      </TableRow>
                    );
                  })()}
                  {monthRows.map((row, idx) => (
                    (() => {
                      const cr = buildCr(row);
                      const start = safeParse(row.week_start);
                      if (!start) {
                        return null;
                      }
                      const end = new Date(start);
                      end.setDate(start.getDate() + 6);
                      const monthEnd = endOfMonth(start);
                      const displayEnd = end > monthEnd ? monthEnd : end;
                      return (
                        <TableRow key={row.week_start}>
                          <TableCell>{`${idx + 1} неделя (${format(start, "dd.MM")} - ${format(displayEnd, "dd.MM")})`}</TableCell>
                          <TableCell align="right">{row.almanah_starts}</TableCell>
                          <TableCell align="right">{row.platform}</TableCell>
                          <TableCell align="right">{row.learning}</TableCell>
                          <TableCell align="right">{cr.learningCr}</TableCell>
                          <TableCell align="right">{row.mtt}</TableCell>
                          <TableCell align="right">{cr.mttCr}</TableCell>
                          <TableCell align="right">{row.spin}</TableCell>
                          <TableCell align="right">{cr.spinCr}</TableCell>
                          <TableCell align="right">{row.cash}</TableCell>
                          <TableCell align="right">{cr.cashCr}</TableCell>
                          <TableCell align="right">{row.not_started}</TableCell>
                          <TableCell align="right">{cr.notStartedCr}</TableCell>
                          <TableCell align="right">{row.saloon}</TableCell>
                          <TableCell align="right">{cr.saloonCr}</TableCell>
                          <TableCell align="right">{Number(row.budget || 0).toFixed(2)}</TableCell>
                        </TableRow>
                      );
                    })()
                  ))}
                </React.Fragment>
              );
            })}
            {!rows.length && !loading && (
              <TableRow>
                <TableCell colSpan={16}>Нет данных</TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </TableContainer>
    </Paper>
  );
};

export default WeeklyTable;
