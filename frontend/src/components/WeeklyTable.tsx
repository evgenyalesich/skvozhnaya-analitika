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

const toNumber = (value: unknown) => {
  const num = Number(value);
  return Number.isFinite(num) ? num : 0;
};

const displayNumber = (value: unknown) => toNumber(value);

const pct = (num: number, den: number) => {
  const safeNum = toNumber(num);
  const safeDen = toNumber(den);
  if (!safeDen) return "0.00%";
  return `${((safeNum / safeDen) * 100).toFixed(2)}%`;
};

const buildCr = (row: {
  almanah_starts: number;
  platform: number;
  learning: number;
  mtt: number;
  spin: number;
  cash: number;
  not_started: number;
  channel_subscribed: number;
  saloon: number;
  completed_course: number;
  distance_grinding: number;
  contract_signed: number;
}) => ({
  learningCr: pct(toNumber(row.learning), toNumber(row.platform)),
  startedCourseCr: pct(
    toNumber(row.mtt) + toNumber(row.spin) + toNumber(row.cash),
    toNumber(row.learning)
  ),
  mttCr: pct(toNumber(row.mtt), toNumber(row.learning)),
  spinCr: pct(toNumber(row.spin), toNumber(row.mtt)),
  cashCr: pct(toNumber(row.cash), toNumber(row.spin)),
  notStartedCr: pct(toNumber(row.not_started), toNumber(row.cash)),
  channelCr: pct(toNumber(row.channel_subscribed), toNumber(row.not_started)),
  saloonCr: pct(toNumber(row.saloon), toNumber(row.not_started)),
  courseCr: pct(toNumber(row.completed_course), toNumber(row.learning)),
  distanceCr: pct(toNumber(row.distance_grinding), toNumber(row.completed_course)),
  contractCr: pct(toNumber(row.contract_signed), toNumber(row.distance_grinding)),
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

const sumStartedCourse = (row: { mtt: number; spin: number; cash: number }) =>
  toNumber(row.mtt) + toNumber(row.spin) + toNumber(row.cash);
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
              <TableCell align="right">Начали курс</TableCell>
              <TableCell align="right">CR %</TableCell>
              <TableCell align="right">Прошли курс</TableCell>
              <TableCell align="right">CR %</TableCell>
              <TableCell align="right">Наигрыш дистанции</TableCell>
              <TableCell align="right">CR %</TableCell>
              <TableCell align="right">Подписали контракт</TableCell>
              <TableCell align="right">CR %</TableCell>
              <TableCell align="right">mtt</TableCell>
              <TableCell align="right">CR %</TableCell>
              <TableCell align="right">spin</TableCell>
              <TableCell align="right">CR %</TableCell>
              <TableCell align="right">cash</TableCell>
              <TableCell align="right">CR %</TableCell>
              <TableCell align="right">Не начали курс</TableCell>
              <TableCell align="right">CR %</TableCell>
              <TableCell align="right">Подписки КД</TableCell>
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
                  almanah_starts: acc.almanah_starts + toNumber(row.almanah_starts),
                  platform: acc.platform + toNumber(row.platform),
                  learning: acc.learning + toNumber(row.learning),
                  mtt: acc.mtt + toNumber(row.mtt),
                  spin: acc.spin + toNumber(row.spin),
                  cash: acc.cash + toNumber(row.cash),
                  not_started: acc.not_started + toNumber(row.not_started),
                  channel_subscribed: acc.channel_subscribed + toNumber(row.channel_subscribed),
                  saloon: acc.saloon + toNumber(row.saloon),
                  completed_course: acc.completed_course + toNumber(row.completed_course),
                  distance_grinding: acc.distance_grinding + toNumber(row.distance_grinding),
                  contract_signed: acc.contract_signed + toNumber(row.contract_signed),
                  budget: acc.budget + toNumber(row.budget),
                }),
                {
                  almanah_starts: 0,
                  platform: 0,
                  learning: 0,
                  mtt: 0,
                  spin: 0,
                  cash: 0,
                  not_started: 0,
                  channel_subscribed: 0,
                  saloon: 0,
                  completed_course: 0,
                  distance_grinding: 0,
                  contract_signed: 0,
                  budget: 0,
                }
              );
              return (
                <React.Fragment key={monthKey}>
                  {(() => {
                    const cr = buildCr(monthTotals);
                    const startedCourse = sumStartedCourse(monthTotals);
                    return (
                      <TableRow sx={{ backgroundColor: "#ede7f6" }}>
                        <TableCell sx={{ fontWeight: 700 }}>{monthLabel(monthKey)}</TableCell>
                        <TableCell align="right" sx={{ fontWeight: 700 }}>{displayNumber(monthTotals.almanah_starts)}</TableCell>
                        <TableCell align="right" sx={{ fontWeight: 700 }}>{displayNumber(monthTotals.platform)}</TableCell>
                        <TableCell align="right" sx={{ fontWeight: 700 }}>{displayNumber(monthTotals.learning)}</TableCell>
                        <TableCell align="right" sx={{ fontWeight: 700 }}>{cr.learningCr}</TableCell>
                        <TableCell align="right" sx={{ fontWeight: 700 }}>{startedCourse}</TableCell>
                        <TableCell align="right" sx={{ fontWeight: 700 }}>{cr.startedCourseCr}</TableCell>
                        <TableCell align="right" sx={{ fontWeight: 700 }}>{displayNumber(monthTotals.completed_course)}</TableCell>
                        <TableCell align="right" sx={{ fontWeight: 700 }}>{cr.courseCr}</TableCell>
                        <TableCell align="right" sx={{ fontWeight: 700 }}>{displayNumber(monthTotals.distance_grinding)}</TableCell>
                        <TableCell align="right" sx={{ fontWeight: 700 }}>{cr.distanceCr}</TableCell>
                        <TableCell align="right" sx={{ fontWeight: 700 }}>{displayNumber(monthTotals.contract_signed)}</TableCell>
                        <TableCell align="right" sx={{ fontWeight: 700 }}>{cr.contractCr}</TableCell>
                        <TableCell align="right" sx={{ fontWeight: 700 }}>{displayNumber(monthTotals.mtt)}</TableCell>
                        <TableCell align="right" sx={{ fontWeight: 700 }}>{cr.mttCr}</TableCell>
                        <TableCell align="right" sx={{ fontWeight: 700 }}>{displayNumber(monthTotals.spin)}</TableCell>
                        <TableCell align="right" sx={{ fontWeight: 700 }}>{cr.spinCr}</TableCell>
                        <TableCell align="right" sx={{ fontWeight: 700 }}>{displayNumber(monthTotals.cash)}</TableCell>
                        <TableCell align="right" sx={{ fontWeight: 700 }}>{cr.cashCr}</TableCell>
                        <TableCell align="right" sx={{ fontWeight: 700 }}>{displayNumber(monthTotals.not_started)}</TableCell>
                        <TableCell align="right" sx={{ fontWeight: 700 }}>{cr.notStartedCr}</TableCell>
                        <TableCell align="right" sx={{ fontWeight: 700 }}>{displayNumber(monthTotals.channel_subscribed)}</TableCell>
                        <TableCell align="right" sx={{ fontWeight: 700 }}>{cr.channelCr}</TableCell>
                        <TableCell align="right" sx={{ fontWeight: 700 }}>{displayNumber(monthTotals.saloon)}</TableCell>
                        <TableCell align="right" sx={{ fontWeight: 700 }}>{cr.saloonCr}</TableCell>
                        <TableCell align="right" sx={{ fontWeight: 700 }}>{Number(monthTotals.budget || 0).toFixed(2)}</TableCell>
                      </TableRow>
                    );
                  })()}
                  {monthRows.map((row) => (
                    (() => {
                      const cr = buildCr(row);
                      const startedCourse = sumStartedCourse(row);
                      const start = safeParse(row.week_start);
                      if (!start) {
                        return null;
                      }
                      const end = new Date(start);
                      end.setDate(start.getDate() + 6);
                      return (
                        <TableRow key={row.week_start}>
                          <TableCell>{`${format(start, "dd.MM")} - ${format(end, "dd.MM")}`}</TableCell>
                          <TableCell align="right">{displayNumber(row.almanah_starts)}</TableCell>
                          <TableCell align="right">{displayNumber(row.platform)}</TableCell>
                          <TableCell align="right">{displayNumber(row.learning)}</TableCell>
                          <TableCell align="right">{cr.learningCr}</TableCell>
                          <TableCell align="right">{startedCourse}</TableCell>
                          <TableCell align="right">{cr.startedCourseCr}</TableCell>
                          <TableCell align="right">{displayNumber(row.completed_course)}</TableCell>
                          <TableCell align="right">{cr.courseCr}</TableCell>
                          <TableCell align="right">{displayNumber(row.distance_grinding)}</TableCell>
                          <TableCell align="right">{cr.distanceCr}</TableCell>
                          <TableCell align="right">{displayNumber(row.contract_signed)}</TableCell>
                          <TableCell align="right">{cr.contractCr}</TableCell>
                          <TableCell align="right">{displayNumber(row.mtt)}</TableCell>
                          <TableCell align="right">{cr.mttCr}</TableCell>
                          <TableCell align="right">{displayNumber(row.spin)}</TableCell>
                          <TableCell align="right">{cr.spinCr}</TableCell>
                          <TableCell align="right">{displayNumber(row.cash)}</TableCell>
                          <TableCell align="right">{cr.cashCr}</TableCell>
                          <TableCell align="right">{displayNumber(row.not_started)}</TableCell>
                          <TableCell align="right">{cr.notStartedCr}</TableCell>
                          <TableCell align="right">{displayNumber(row.channel_subscribed)}</TableCell>
                          <TableCell align="right">{cr.channelCr}</TableCell>
                          <TableCell align="right">{displayNumber(row.saloon)}</TableCell>
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
                <TableCell colSpan={26}>Нет данных</TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </TableContainer>
    </Paper>
  );
};

export default WeeklyTable;
