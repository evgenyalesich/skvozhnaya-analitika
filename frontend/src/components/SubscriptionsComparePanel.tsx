import React from "react";
import Paper from "@mui/material/Paper";
import Typography from "@mui/material/Typography";
import Table from "@mui/material/Table";
import TableHead from "@mui/material/TableHead";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableRow from "@mui/material/TableRow";
import TableContainer from "@mui/material/TableContainer";
import LinearProgress from "@mui/material/LinearProgress";
import Stack from "@mui/material/Stack";
import FormControl from "@mui/material/FormControl";
import InputLabel from "@mui/material/InputLabel";
import Select from "@mui/material/Select";
import MenuItem from "@mui/material/MenuItem";
import FormGroup from "@mui/material/FormGroup";
import FormControlLabel from "@mui/material/FormControlLabel";
import Checkbox from "@mui/material/Checkbox";
import IconButton from "@mui/material/IconButton";
import KeyboardArrowDownIcon from "@mui/icons-material/KeyboardArrowDown";
import KeyboardArrowRightIcon from "@mui/icons-material/KeyboardArrowRight";
import Box from "@mui/material/Box";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Legend } from "recharts";

import { SubscriptionCompareRow } from "../hooks/useSubscriptionsCompare";

export interface SubscriptionsComparePanelProps {
  data: SubscriptionCompareRow[];
  loading: boolean;
  groupBy: "campaign" | "overall";
  onGroupByChange: (value: "campaign" | "overall") => void;
  interval: "day" | "week";
  onIntervalChange: (value: "day" | "week") => void;
}

type GroupRow = {
  key: string;
  rows: SubscriptionCompareRow[];
  bots: BotRow[];
  bot_starts: number;
  almanah_starts: number;
  channel_subscribed: number;
  channel_unsubscribed: number;
  channel_total: number;
  saloon_subscribed: number;
  saloon_unsubscribed: number;
  saloon_total: number;
};

type BotRow = {
  key: string;
  rows: SubscriptionCompareRow[];
  bot_starts: number;
  almanah_starts: number;
  channel_subscribed: number;
  channel_unsubscribed: number;
  channel_total: number;
  saloon_subscribed: number;
  saloon_unsubscribed: number;
  saloon_total: number;
};

const median = (values: number[]) => {
  if (!values.length) return 0;
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  if (sorted.length % 2) return sorted[mid];
  return (sorted[mid - 1] + sorted[mid]) / 2;
};

const pct = (num: number, den: number) => {
  if (!den) return "—";
  return `${((num / den) * 100).toFixed(2)}%`;
};

const formatWeekRange = (weekStart: string | null | undefined) => {
  if (!weekStart) return "";
  const start = new Date(`${weekStart}T00:00:00`);
  if (Number.isNaN(start.getTime())) return weekStart;
  const end = new Date(start);
  end.setDate(start.getDate() + 6);
  const fmt = (d: Date) =>
    `${String(d.getDate()).padStart(2, "0")}.${String(d.getMonth() + 1).padStart(2, "0")}.${d.getFullYear()}`;
  return `${fmt(start)} – ${fmt(end)}`;
};

const formatMonthLabel = (monthKey: string) => {
  if (!monthKey) return "Все месяцы";
  const [year, month] = monthKey.split("-");
  const monthIndex = Number(month) - 1;
  const monthNames = [
    "январь",
    "февраль",
    "март",
    "апрель",
    "май",
    "июнь",
    "июль",
    "август",
    "сентябрь",
    "октябрь",
    "ноябрь",
    "декабрь",
  ];
  return `${monthNames[monthIndex] || month} ${year}`;
};

const SubscriptionsComparePanel: React.FC<SubscriptionsComparePanelProps> = ({
  data,
  loading,
  groupBy: _groupBy,
  onGroupByChange: _onGroupByChange,
  interval,
  onIntervalChange,
}) => {
  const [visible, setVisible] = React.useState<Record<string, boolean>>({
    bot_starts: true,
    almanah_starts: true,
    channel_subscribed: true,
    channel_unsubscribed: false,
    channel_total: true,
    saloon_subscribed: false,
    saloon_unsubscribed: false,
    saloon_total: false,
    cr_kd: true,
    cr_saloon: false,
  });
  const [expandedCampaigns, setExpandedCampaigns] = React.useState<Set<string>>(new Set());
  const [expandedBots, setExpandedBots] = React.useState<Set<string>>(new Set());
  const [selectedMonth, setSelectedMonth] = React.useState<string>("");
  const effectiveGroupBy: "campaign" = "campaign";

  const monthOptions = React.useMemo(() => {
    const set = new Set<string>();
    data.forEach((row) => {
      if (!row.date) return;
      const key = row.date.slice(0, 7);
      if (/^\d{4}-\d{2}$/.test(key)) {
        set.add(key);
      }
    });
    return Array.from(set).sort();
  }, [data]);

  React.useEffect(() => {
    if (interval !== "week") {
      setSelectedMonth("");
      return;
    }
    if (!selectedMonth && monthOptions.length) {
      setSelectedMonth(monthOptions[monthOptions.length - 1]);
    }
  }, [interval, monthOptions, selectedMonth]);

  const filteredData = React.useMemo(() => {
    if (interval !== "week" || !selectedMonth) {
      return data;
    }
    return data.filter((row) => typeof row.date === "string" && row.date.startsWith(selectedMonth));
  }, [data, interval, selectedMonth]);

  const aggregateRows = React.useCallback((rows: SubscriptionCompareRow[]) => {
    const sortedRows = [...rows].sort((a, b) => (a.date || "").localeCompare(b.date || ""));
    return {
      rows: sortedRows,
      bot_starts: sortedRows.reduce((s, r) => s + (r.bot_starts || 0), 0),
      almanah_starts: sortedRows.reduce((s, r) => s + (r.almanah_starts || 0), 0),
      channel_subscribed: sortedRows.reduce((s, r) => s + (r.channel_subscribed || 0), 0),
      channel_unsubscribed: sortedRows.reduce((s, r) => s + (r.channel_unsubscribed || 0), 0),
      channel_total: sortedRows.reduce((s, r) => s + (r.channel_total || 0), 0),
      saloon_subscribed: sortedRows.reduce((s, r) => s + (r.saloon_subscribed || 0), 0),
      saloon_unsubscribed: sortedRows.reduce((s, r) => s + (r.saloon_unsubscribed || 0), 0),
      saloon_total: sortedRows.reduce((s, r) => s + (r.saloon_total || 0), 0),
    };
  }, []);

  const groups = React.useMemo(() => {
    const map = new Map<string, SubscriptionCompareRow[]>();
    filteredData.forEach((row) => {
      const key = (row.campaign || "все").trim() || "все";
      const bucket = map.get(key) || [];
      bucket.push(row);
      map.set(key, bucket);
    });
    return Array.from(map.entries())
      .map(([key, rows]) => {
      const bots: BotRow[] = [];
      if (effectiveGroupBy !== "overall") {
        const botsMap = new Map<string, SubscriptionCompareRow[]>();
        rows.forEach((row) => {
          const botKey = (row.bot_key || "unknown").trim() || "unknown";
          const botRows = botsMap.get(botKey) || [];
          botRows.push(row);
          botsMap.set(botKey, botRows);
        });
        bots.push(
          ...Array.from(botsMap.entries())
            .map(([botKey, botRows]) => ({
              key: botKey,
              ...aggregateRows(botRows),
            }))
            .sort((a, b) => b.bot_starts - a.bot_starts)
        );
      }

        return {
          key,
          bots,
          ...aggregateRows(rows),
        };
      })
      .sort((a, b) => b.bot_starts - a.bot_starts);
  }, [filteredData, aggregateRows, effectiveGroupBy]);

  const summary = React.useMemo(() => {
    const total = groups.reduce(
      (acc, g) => ({
        bot_starts: acc.bot_starts + g.bot_starts,
        almanah_starts: acc.almanah_starts + g.almanah_starts,
        channel_subscribed: acc.channel_subscribed + g.channel_subscribed,
        channel_unsubscribed: acc.channel_unsubscribed + g.channel_unsubscribed,
        channel_total: acc.channel_total + g.channel_total,
        saloon_subscribed: acc.saloon_subscribed + g.saloon_subscribed,
        saloon_unsubscribed: acc.saloon_unsubscribed + g.saloon_unsubscribed,
        saloon_total: acc.saloon_total + g.saloon_total,
      }),
      {
        bot_starts: 0,
        almanah_starts: 0,
        channel_subscribed: 0,
        channel_unsubscribed: 0,
        channel_total: 0,
        saloon_subscribed: 0,
        saloon_unsubscribed: 0,
        saloon_total: 0,
      },
    );
    const n = groups.length || 1;
    const avg = {
      bot_starts: total.bot_starts / n,
      almanah_starts: total.almanah_starts / n,
      channel_subscribed: total.channel_subscribed / n,
      channel_unsubscribed: total.channel_unsubscribed / n,
      channel_total: total.channel_total / n,
      saloon_subscribed: total.saloon_subscribed / n,
      saloon_unsubscribed: total.saloon_unsubscribed / n,
      saloon_total: total.saloon_total / n,
    };
    const med = {
      bot_starts: median(groups.map((g) => g.bot_starts)),
      almanah_starts: median(groups.map((g) => g.almanah_starts)),
      channel_subscribed: median(groups.map((g) => g.channel_subscribed)),
      channel_unsubscribed: median(groups.map((g) => g.channel_unsubscribed)),
      channel_total: median(groups.map((g) => g.channel_total)),
      saloon_subscribed: median(groups.map((g) => g.saloon_subscribed)),
      saloon_unsubscribed: median(groups.map((g) => g.saloon_unsubscribed)),
      saloon_total: median(groups.map((g) => g.saloon_total)),
    };
    return { total, avg, med };
  }, [groups]);

  const chartData = React.useMemo(() => {
    const map = new Map<string, any>();
    filteredData.forEach((row) => {
      const key = row.date;
      const existing = map.get(key) || {
        date: key,
        bot_starts: 0,
        almanah_starts: 0,
        channel_subscribed: 0,
        channel_unsubscribed: 0,
        channel_total: 0,
        saloon_subscribed: 0,
        saloon_unsubscribed: 0,
        saloon_total: 0,
      };
      existing.bot_starts += row.bot_starts || 0;
      existing.almanah_starts += row.almanah_starts || 0;
      existing.channel_subscribed += row.channel_subscribed || 0;
      existing.channel_unsubscribed += row.channel_unsubscribed || 0;
      existing.saloon_subscribed += row.saloon_subscribed || 0;
      existing.saloon_unsubscribed += row.saloon_unsubscribed || 0;
      existing.channel_total = Math.max(existing.channel_total, row.channel_total || 0);
      existing.saloon_total = Math.max(existing.saloon_total, row.saloon_total || 0);
      map.set(key, existing);
    });
    return Array.from(map.values()).sort((a, b) => (a.date || "").localeCompare(b.date || ""));
  }, [filteredData]);

  const toggle = (key: string) => setVisible((prev) => ({ ...prev, [key]: !prev[key] }));
  const toggleCampaign = (key: string) =>
    setExpandedCampaigns((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  const toggleBot = (key: string) =>
    setExpandedBots((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });

  const renderMetricCells = (row: any, isPercentFromStarts = true) => (
    <>
      {visible.bot_starts && <TableCell>{Math.round(row.bot_starts || 0)}</TableCell>}
      {visible.almanah_starts && <TableCell>{Math.round(row.almanah_starts || 0)}</TableCell>}
      {visible.channel_subscribed && <TableCell>{Math.round(row.channel_subscribed || 0)}</TableCell>}
      {visible.channel_unsubscribed && <TableCell>{Math.round(row.channel_unsubscribed || 0)}</TableCell>}
      {visible.cr_kd && (
        <TableCell>
          {pct(Number(row.channel_subscribed || 0), Number(isPercentFromStarts ? row.bot_starts || 0 : row.almanah_starts || 0))}
        </TableCell>
      )}
      {visible.channel_total && <TableCell>{Math.round(row.channel_total || 0)}</TableCell>}
      {visible.saloon_subscribed && <TableCell>{Math.round(row.saloon_subscribed || 0)}</TableCell>}
      {visible.saloon_unsubscribed && <TableCell>{Math.round(row.saloon_unsubscribed || 0)}</TableCell>}
      {visible.cr_saloon && (
        <TableCell>{pct(Number(row.saloon_subscribed || 0), Number(isPercentFromStarts ? row.bot_starts || 0 : row.almanah_starts || 0))}</TableCell>
      )}
      {visible.saloon_total && <TableCell>{Math.round(row.saloon_total || 0)}</TableCell>}
    </>
  );

  return (
    <Paper sx={{ mt: 2, p: 2 }}>
      <Typography variant="h6" mb={1}>
        TG SUBS: старты и подписки
      </Typography>
      <Stack direction="row" spacing={2} alignItems="center" sx={{ mb: 1, flexWrap: "wrap" }}>
        <FormControl size="small" sx={{ minWidth: 160 }}>
          <InputLabel id="subs-compare-interval">Интервал</InputLabel>
          <Select
            labelId="subs-compare-interval"
            value={interval}
            label="Интервал"
            onChange={(event) => onIntervalChange(event.target.value as "day" | "week")}
          >
            <MenuItem value="day">По дням</MenuItem>
            <MenuItem value="week">По неделям</MenuItem>
          </Select>
        </FormControl>
        {interval === "week" && (
          <FormControl size="small" sx={{ minWidth: 180 }}>
            <InputLabel id="subs-compare-month">Месяц</InputLabel>
            <Select
              labelId="subs-compare-month"
              value={selectedMonth}
              label="Месяц"
              onChange={(event) => setSelectedMonth(event.target.value)}
            >
              <MenuItem value="">Все месяцы</MenuItem>
              {monthOptions.map((month) => (
                <MenuItem key={month} value={month}>
                  {formatMonthLabel(month)}
                </MenuItem>
              ))}
            </Select>
          </FormControl>
        )}
      </Stack>
      <FormGroup row sx={{ mb: 1 }}>
        <FormControlLabel control={<Checkbox checked={visible.bot_starts} onChange={() => toggle("bot_starts")} />} label="Старты боты" />
        <FormControlLabel control={<Checkbox checked={visible.almanah_starts} onChange={() => toggle("almanah_starts")} />} label="Старты Альманах" />
        <FormControlLabel control={<Checkbox checked={visible.channel_subscribed} onChange={() => toggle("channel_subscribed")} />} label="Подписки Канал" />
        <FormControlLabel control={<Checkbox checked={visible.channel_unsubscribed} onChange={() => toggle("channel_unsubscribed")} />} label="Отписки Канал" />
        <FormControlLabel control={<Checkbox checked={visible.cr_kd} onChange={() => toggle("cr_kd")} />} label="CR Канал" />
        <FormControlLabel control={<Checkbox checked={visible.channel_total} onChange={() => toggle("channel_total")} />} label="Всего Канал" />
        <FormControlLabel control={<Checkbox checked={visible.saloon_subscribed} onChange={() => toggle("saloon_subscribed")} />} label="Подписки Салун" />
        <FormControlLabel control={<Checkbox checked={visible.saloon_unsubscribed} onChange={() => toggle("saloon_unsubscribed")} />} label="Отписки Салун" />
        <FormControlLabel control={<Checkbox checked={visible.cr_saloon} onChange={() => toggle("cr_saloon")} />} label="CR Салун" />
        <FormControlLabel control={<Checkbox checked={visible.saloon_total} onChange={() => toggle("saloon_total")} />} label="Всего Салун" />
      </FormGroup>
      {loading && <LinearProgress />}
      {chartData.length > 0 && (
        <Box sx={{ height: 280, mb: 2 }}>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={chartData} margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
              <XAxis dataKey="date" tick={{ fontSize: 12 }} />
              <YAxis allowDecimals={false} />
              <Tooltip />
              <Legend />
              {visible.bot_starts && <Bar dataKey="bot_starts" name="Старты боты" fill="#1976d2" />}
              {visible.almanah_starts && <Bar dataKey="almanah_starts" name="Старты Альманах" fill="#7b1fa2" />}
              {visible.channel_subscribed && <Bar dataKey="channel_subscribed" name="Подписки Канал" fill="#2e7d32" />}
              {visible.channel_unsubscribed && <Bar dataKey="channel_unsubscribed" name="Отписки Канал" fill="#d32f2f" />}
              {visible.channel_total && <Bar dataKey="channel_total" name="Всего Канал" fill="#0288d1" />}
              {visible.saloon_subscribed && <Bar dataKey="saloon_subscribed" name="Подписки Салун" fill="#388e3c" />}
              {visible.saloon_unsubscribed && <Bar dataKey="saloon_unsubscribed" name="Отписки Салун" fill="#c62828" />}
              {visible.saloon_total && <Bar dataKey="saloon_total" name="Всего Салун" fill="#6a1b9a" />}
            </BarChart>
          </ResponsiveContainer>
        </Box>
      )}
      <TableContainer>
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>РК</TableCell>
              <TableCell>Период</TableCell>
              {visible.bot_starts && <TableCell>Старты боты</TableCell>}
              {visible.almanah_starts && <TableCell>Старты Альманах</TableCell>}
              {visible.channel_subscribed && <TableCell>Подписки Канал</TableCell>}
              {visible.channel_unsubscribed && <TableCell>Отписки Канал</TableCell>}
              {visible.cr_kd && <TableCell>CR Канал</TableCell>}
              {visible.channel_total && <TableCell>Всего Канал</TableCell>}
              {visible.saloon_subscribed && <TableCell>Подписки Салун</TableCell>}
              {visible.saloon_unsubscribed && <TableCell>Отписки Салун</TableCell>}
              {visible.cr_saloon && <TableCell>CR Салун</TableCell>}
              {visible.saloon_total && <TableCell>Всего Салун</TableCell>}
            </TableRow>
          </TableHead>
          <TableBody>
            <TableRow sx={{ backgroundColor: "rgba(0,0,0,0.04)" }}>
              <TableCell sx={{ fontWeight: 700 }}>Всего</TableCell>
              <TableCell>—</TableCell>
              {renderMetricCells(summary.total)}
            </TableRow>
            <TableRow sx={{ backgroundColor: "rgba(0,0,0,0.02)" }}>
              <TableCell sx={{ fontWeight: 700 }}>Средняя</TableCell>
              <TableCell>—</TableCell>
              {renderMetricCells(summary.avg)}
            </TableRow>
            <TableRow sx={{ backgroundColor: "rgba(0,0,0,0.02)" }}>
              <TableCell sx={{ fontWeight: 700 }}>Медиана</TableCell>
              <TableCell>—</TableCell>
              {renderMetricCells(summary.med)}
            </TableRow>
            {groups.map((group) => {
              const openCampaign = expandedCampaigns.has(group.key);
              return (
                <React.Fragment key={group.key}>
                  <TableRow>
                    <TableCell>
                      <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
                        <IconButton size="small" onClick={() => toggleCampaign(group.key)}>
                          {openCampaign ? <KeyboardArrowDownIcon /> : <KeyboardArrowRightIcon />}
                        </IconButton>
                        {group.key}
                      </Box>
                    </TableCell>
                    <TableCell>{interval === "day" ? "Все дни" : "Все недели"}</TableCell>
                    {renderMetricCells(group)}
                  </TableRow>
                  {openCampaign &&
                    group.bots.map((bot) => {
                      const botKey = `${group.key}:${bot.key}`;
                      const openBot = expandedBots.has(botKey);
                      return (
                        <React.Fragment key={botKey}>
                          <TableRow>
                            <TableCell>
                              <Box sx={{ display: "flex", alignItems: "center", gap: 1, pl: 4 }}>
                                <IconButton size="small" onClick={() => toggleBot(botKey)}>
                                  {openBot ? <KeyboardArrowDownIcon /> : <KeyboardArrowRightIcon />}
                                </IconButton>
                                {bot.key}
                              </Box>
                            </TableCell>
                            <TableCell>{interval === "day" ? "Все дни" : "Все недели"}</TableCell>
                            {renderMetricCells(bot)}
                          </TableRow>
                          {openBot &&
                            bot.rows.map((row, idx) => (
                              <TableRow key={`${botKey}:${row.date}:${idx}`}>
                                <TableCell sx={{ pl: 10 }}>Дата</TableCell>
                                <TableCell>{interval === "week" ? formatWeekRange(row.date) : row.date}</TableCell>
                                {renderMetricCells(row, true)}
                              </TableRow>
                            ))}
                        </React.Fragment>
                      );
                    })}
                </React.Fragment>
              );
            })}
          </TableBody>
        </Table>
      </TableContainer>
    </Paper>
  );
};

export default SubscriptionsComparePanel;
