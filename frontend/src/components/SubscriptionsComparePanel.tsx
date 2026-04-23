import React from "react";
import Box from "@mui/material/Box";
import Paper from "@mui/material/Paper";
import Typography from "@mui/material/Typography";
import Stack from "@mui/material/Stack";
import Grid from "@mui/material/Grid";
import Chip from "@mui/material/Chip";
import LinearProgress from "@mui/material/LinearProgress";
import FormControl from "@mui/material/FormControl";
import InputLabel from "@mui/material/InputLabel";
import Select from "@mui/material/Select";
import MenuItem from "@mui/material/MenuItem";
import FormGroup from "@mui/material/FormGroup";
import FormControlLabel from "@mui/material/FormControlLabel";
import Checkbox from "@mui/material/Checkbox";
import Table from "@mui/material/Table";
import TableHead from "@mui/material/TableHead";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableRow from "@mui/material/TableRow";
import TableContainer from "@mui/material/TableContainer";
import IconButton from "@mui/material/IconButton";
import KeyboardArrowDownIcon from "@mui/icons-material/KeyboardArrowDown";
import KeyboardArrowRightIcon from "@mui/icons-material/KeyboardArrowRight";
import MiniSparkline from "./ui/MiniSparkline";
import EmptyState from "./ui/EmptyState";
import TableSkeleton from "./ui/TableSkeleton";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from "recharts";

import { SubscriptionCompareRow } from "../hooks/useSubscriptionsCompare";

export interface SubscriptionsComparePanelProps {
  data: SubscriptionCompareRow[];
  overall?: {
    date: string;
    bot_starts: number;
    almanah_starts: number;
    channel_subscribed: number;
    channel_unsubscribed: number;
    saloon_subscribed: number;
    saloon_unsubscribed: number;
  }[];
  summary?: {
    channel: { active: number; subscribed: number; unsubscribed: number; total_in_channel?: number; not_in_bot?: number };
    saloon: { active: number; subscribed: number; unsubscribed: number; total_in_channel?: number; not_in_bot?: number };
  } | null;
  loading: boolean;
  groupBy: "campaign" | "bot" | "overall";
  onGroupByChange: (value: "campaign" | "bot" | "overall") => void;
  interval: "day" | "week";
  onIntervalChange: (value: "day" | "week") => void;
  resolveName?: (key: string) => string;
}

// ── colours ──────────────────────────────────────────────────────────────────
const COLORS = {
  bot_starts:          "#1976d2",
  almanah_starts:      "#7b1fa2",
  channel_subscribed:  "#2e7d32",
  channel_unsubscribed:"#d32f2f",
  saloon_subscribed:   "#00897b",
  saloon_unsubscribed: "#c62828",
};

// ── helpers ───────────────────────────────────────────────────────────────────
const pct = (num: number, den: number) =>
  den ? `${((num / den) * 100).toFixed(1)}%` : "—";

const fmt = (n: number | undefined | null) =>
  n == null ? "—" : n.toLocaleString("ru-RU");

const heatColor = (percentValue: number) => {
  if (percentValue >= 35) return { color: "var(--app-chip-success)", bg: "rgba(15,159,110,0.10)" };
  if (percentValue >= 15) return { color: "var(--app-chip-warning)", bg: "rgba(201,133,23,0.12)" };
  return { color: "var(--app-chip-danger)", bg: "rgba(220,76,63,0.10)" };
};

const formatWeekRange = (weekStart: string | null | undefined) => {
  if (!weekStart) return "";
  const start = new Date(`${weekStart}T00:00:00`);
  if (Number.isNaN(start.getTime())) return weekStart;
  const end = new Date(start);
  end.setDate(start.getDate() + 6);
  const d = (x: Date) =>
    `${String(x.getDate()).padStart(2, "0")}.${String(x.getMonth() + 1).padStart(2, "0")}.${x.getFullYear()}`;
  return `${d(start)} – ${d(end)}`;
};

const formatMonthLabel = (key: string) => {
  const [year, month] = key.split("-");
  const names = ["янв","фев","мар","апр","май","июн","июл","авг","сен","окт","ноя","дек"];
  return `${names[Number(month) - 1] || month} ${year}`;
};

const median = (vals: number[]) => {
  if (!vals.length) return 0;
  const s = [...vals].sort((a, b) => a - b);
  const m = Math.floor(s.length / 2);
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
};

// ── stat card ─────────────────────────────────────────────────────────────────
interface StatCardProps {
  title: string;
  color: string;
  total?: number;
  active: number;
  notInBot?: number;
  subscribedPeriod: number;
  unsubscribedPeriod: number;
}
const StatCard: React.FC<StatCardProps> = ({ title, color, total, active, notInBot, subscribedPeriod, unsubscribedPeriod }) => {
  const botPct = total ? (active / total) * 100 : 0;
  return (
    <Paper variant="outlined" sx={{ p: 2, flex: 1, borderLeft: `4px solid ${color}`, borderColor: "var(--app-shell-border)", background: "var(--app-panel-bg)" }}>
      <Typography variant="subtitle1" fontWeight={700} mb={1}>{title}</Typography>
      <Stack spacing={0.5}>
        {total != null && (
          <Stack direction="row" justifyContent="space-between">
            <Typography variant="body2" color="text.secondary">Всего в канале</Typography>
            <Typography variant="body2" fontWeight={700}>{fmt(total)}</Typography>
          </Stack>
        )}
        <Stack direction="row" justifyContent="space-between">
          <Typography variant="body2" color="text.secondary">Есть в боте</Typography>
          <Typography variant="body2" fontWeight={700} color={color}>{fmt(active)}</Typography>
        </Stack>
        {total != null && (
          <Box>
            <LinearProgress
              variant="determinate"
              value={Math.min(botPct, 100)}
              sx={{ height: 6, borderRadius: 3, bgcolor: "var(--app-panel-muted)", "& .MuiLinearProgress-bar": { bgcolor: color } }}
            />
            <Typography variant="caption" color="text.secondary">{botPct.toFixed(1)}% охват ботом</Typography>
          </Box>
        )}
        {notInBot != null && (
          <Stack direction="row" justifyContent="space-between">
            <Typography variant="body2" color="text.secondary">Не в боте</Typography>
            <Chip label={fmt(notInBot)} size="small" sx={{ bgcolor: "var(--app-panel-muted)", fontSize: 12 }} />
          </Stack>
        )}
        <Box sx={{ borderTop: "1px solid", borderColor: "divider", pt: 0.5, mt: 0.5 }}>
          <Stack direction="row" justifyContent="space-between">
            <Typography variant="body2" color="text.secondary">Подписались за период</Typography>
            <Typography variant="body2" color="success.main">+{fmt(subscribedPeriod)}</Typography>
          </Stack>
          <Stack direction="row" justifyContent="space-between">
            <Typography variant="body2" color="text.secondary">Отписались за период</Typography>
            <Typography variant="body2" color="error.main">−{fmt(unsubscribedPeriod)}</Typography>
          </Stack>
        </Box>
      </Stack>
    </Paper>
  );
};

// ── aggregation helper ────────────────────────────────────────────────────────
const aggregateRows = (rows: SubscriptionCompareRow[]) => {
  const sorted = [...rows].sort((a, b) => (a.date || "").localeCompare(b.date || ""));
  return {
    rows: sorted,
    bot_starts:           sorted.reduce((s, r) => s + (r.bot_starts || 0), 0),
    almanah_starts:       sorted.reduce((s, r) => s + (r.almanah_starts || 0), 0),
    channel_subscribed:   sorted.reduce((s, r) => s + (r.channel_subscribed || 0), 0),
    channel_unsubscribed: sorted.reduce((s, r) => s + (r.channel_unsubscribed || 0), 0),
    saloon_subscribed:    sorted.reduce((s, r) => s + (r.saloon_subscribed || 0), 0),
    saloon_unsubscribed:  sorted.reduce((s, r) => s + (r.saloon_unsubscribed || 0), 0),
  };
};

// ── custom tooltip ────────────────────────────────────────────────────────────
const CustomTooltip = ({ active, payload, label, interval }: any) => {
  if (!active || !payload?.length) return null;
  return (
    <Paper sx={{ p: 1.5, fontSize: 13, minWidth: 180, border: "1px solid var(--app-shell-border)", background: "var(--app-panel-bg)" }}>
      <Typography variant="caption" fontWeight={700} display="block" mb={0.5}>
        {interval === "week" ? formatWeekRange(label) : label}
      </Typography>
      {payload.map((p: any) => (
        <Stack key={p.dataKey} direction="row" justifyContent="space-between" spacing={3}>
          <Typography variant="caption" color={p.color}>{p.name}</Typography>
          <Typography variant="caption" fontWeight={700}>{fmt(p.value)}</Typography>
        </Stack>
      ))}
    </Paper>
  );
};

// ── main component ────────────────────────────────────────────────────────────
const SubscriptionsComparePanel: React.FC<SubscriptionsComparePanelProps> = ({
  data,
  overall,
  summary,
  loading,
  groupBy,
  interval,
  onIntervalChange,
  resolveName,
}) => {
  const resolveLabel = (key: string) => resolveName ? resolveName(key) : key;
  const [visible, setVisible] = React.useState<Record<string, boolean>>({
    bot_starts: true,
    almanah_starts: true,
    channel_subscribed: true,
    channel_unsubscribed: false,
    saloon_subscribed: true,
    saloon_unsubscribed: false,
  });
  const [expandedCampaigns, setExpandedCampaigns] = React.useState<Set<string>>(new Set());
  const [expandedBots, setExpandedBots] = React.useState<Set<string>>(new Set());
  const [selectedMonth, setSelectedMonth] = React.useState<string | null>(null);

  const toggle = (key: string) => setVisible((prev) => ({ ...prev, [key]: !prev[key] }));

  // month options from data
  const monthOptions = React.useMemo(() => {
    const set = new Set<string>();
    data.forEach((r) => { if (r.date) { const k = r.date.slice(0, 7); if (/^\d{4}-\d{2}$/.test(k)) set.add(k); } });
    return Array.from(set).sort();
  }, [data]);

  React.useEffect(() => {
    if (interval !== "week") { setSelectedMonth(null); return; }
    // null = not yet initialized → auto-select latest month
    // "" = user explicitly chose "Все месяцы" → keep it
    setSelectedMonth((curr) => curr === null ? (monthOptions.length ? monthOptions[monthOptions.length - 1] : "") : curr);
  }, [interval, monthOptions]);

  const filteredData = React.useMemo(() =>
    interval !== "week" || !selectedMonth  // null or "" = no month filter
      ? data
      : data.filter((r) => typeof r.date === "string" && r.date.startsWith(selectedMonth)),
    [data, interval, selectedMonth]
  );

  // chart data aggregated across all campaigns
  const chartData = React.useMemo(() => {
    const source = overall?.length ? overall : filteredData;
    const filtered = interval !== "week" || !selectedMonth
      ? source
      : source.filter((r) => typeof r.date === "string" && r.date.startsWith(selectedMonth));
    const map = new Map<string, any>();
    filtered.forEach((r) => {
      const key = r.date;
      const e = map.get(key) || { date: key, bot_starts: 0, almanah_starts: 0, channel_subscribed: 0, channel_unsubscribed: 0, saloon_subscribed: 0, saloon_unsubscribed: 0 };
      e.bot_starts           += (r as any).bot_starts           || 0;
      e.almanah_starts       += (r as any).almanah_starts       || 0;
      e.channel_subscribed   += (r as any).channel_subscribed   || 0;
      e.channel_unsubscribed += (r as any).channel_unsubscribed || 0;
      e.saloon_subscribed    += (r as any).saloon_subscribed    || 0;
      e.saloon_unsubscribed  += (r as any).saloon_unsubscribed  || 0;
      map.set(key, e);
    });
    return Array.from(map.values()).sort((a, b) => (a.date || "").localeCompare(b.date || ""));
  }, [filteredData, overall, interval, selectedMonth]);

  // groups: top-level key is bot_key in bot mode, campaign otherwise
  const groups = React.useMemo(() => {
    const map = new Map<string, SubscriptionCompareRow[]>();
    filteredData.forEach((r) => {
      const key = groupBy === "bot"
        ? ((r.bot_key || "unknown").trim() || "unknown")
        : ((r.campaign || "все").trim() || "все");
      map.set(key, [...(map.get(key) || []), r]);
    });
    return Array.from(map.entries()).map(([key, rows]) => {
      // In bot mode rows are already per-bot — no sub-bot grouping needed
      const botsMap = new Map<string, SubscriptionCompareRow[]>();
      if (groupBy !== "bot") {
        rows.forEach((r) => { const bk = (r.bot_key || "unknown").trim() || "unknown"; botsMap.set(bk, [...(botsMap.get(bk) || []), r]); });
      }
      const bots = Array.from(botsMap.entries())
        .map(([bk, br]) => ({ key: bk, ...aggregateRows(br) }))
        .sort((a, b) => b.bot_starts - a.bot_starts);
      return { key, bots, ...aggregateRows(rows) };
    }).sort((a, b) => b.bot_starts - a.bot_starts);
  }, [filteredData, groupBy]);

  const totals = React.useMemo(() => groups.reduce(
    (acc, g) => ({
      bot_starts:           acc.bot_starts + g.bot_starts,
      almanah_starts:       acc.almanah_starts + g.almanah_starts,
      channel_subscribed:   acc.channel_subscribed + g.channel_subscribed,
      channel_unsubscribed: acc.channel_unsubscribed + g.channel_unsubscribed,
      saloon_subscribed:    acc.saloon_subscribed + g.saloon_subscribed,
      saloon_unsubscribed:  acc.saloon_unsubscribed + g.saloon_unsubscribed,
    }),
    { bot_starts: 0, almanah_starts: 0, channel_subscribed: 0, channel_unsubscribed: 0, saloon_subscribed: 0, saloon_unsubscribed: 0 }
  ), [groups]);

  const toggleCampaign = (key: string) => setExpandedCampaigns((prev) => { const n = new Set(prev); n.has(key) ? n.delete(key) : n.add(key); return n; });
  const toggleBot = (key: string) => setExpandedBots((prev) => { const n = new Set(prev); n.has(key) ? n.delete(key) : n.add(key); return n; });

  const sparkValues = (row: any) => {
    if (Array.isArray(row.rows) && row.rows.length) {
      return row.rows.map((item: any) => Number(item.bot_starts || item.channel_subscribed || 0));
    }
    return [
      Number(row.bot_starts || 0),
      Number(row.almanah_starts || 0),
      Number(row.channel_subscribed || 0),
      Number(row.saloon_subscribed || 0),
    ];
  };

  const renderCrCell = (value: number, denom: number) => {
    const percent = denom ? (value / denom) * 100 : 0;
    const tone = heatColor(percent);
    return (
      <TableCell align="right" sx={{ ...tone, fontWeight: 700 }}>
        <Box sx={{ minWidth: 54 }}>
          <Box component="span">{pct(value, denom)}</Box>
          <Box sx={{ mt: 0.45, height: 4, borderRadius: "999px", background: "var(--app-panel-muted)", overflow: "hidden" }}>
            <Box sx={{ width: `${Math.max(0, Math.min(100, percent))}%`, height: "100%", borderRadius: "999px", background: tone.color }} />
          </Box>
        </Box>
      </TableCell>
    );
  };

  const renderCells = (row: any) => (
    <>
      <TableCell align="right">{fmt(row.bot_starts)}</TableCell>
      <TableCell align="right">{fmt(row.almanah_starts)}</TableCell>
      <TableCell align="right" sx={{ color: "success.main" }}>+{fmt(row.channel_subscribed)}</TableCell>
      <TableCell align="right" sx={{ color: "error.main" }}>−{fmt(row.channel_unsubscribed)}</TableCell>
      {renderCrCell(row.channel_subscribed, row.bot_starts)}
      <TableCell align="right" sx={{ color: "success.main" }}>+{fmt(row.saloon_subscribed)}</TableCell>
      <TableCell align="right" sx={{ color: "error.main" }}>−{fmt(row.saloon_unsubscribed)}</TableCell>
      {renderCrCell(row.saloon_subscribed, row.bot_starts)}
    </>
  );

  return (
    <Box sx={{ mt: 2 }}>
      <Typography variant="h6" fontWeight={700} mb={2}>TG SUBS: старты и подписки</Typography>

      {/* ── stat cards ───────────────────────────────────────────────────── */}
      {summary && (
        <Stack direction={{ xs: "column", md: "row" }} spacing={2} mb={3}>
          <StatCard
            title="Карточный Домик"
            color={COLORS.channel_subscribed}
            total={summary.channel.total_in_channel}
            active={summary.channel.active}
            notInBot={summary.channel.not_in_bot}
            subscribedPeriod={summary.channel.subscribed}
            unsubscribedPeriod={summary.channel.unsubscribed}
          />
          <StatCard
            title="Салун"
            color={COLORS.saloon_subscribed}
            total={summary.saloon.total_in_channel}
            active={summary.saloon.active}
            notInBot={summary.saloon.not_in_bot}
            subscribedPeriod={summary.saloon.subscribed}
            unsubscribedPeriod={summary.saloon.unsubscribed}
          />
        </Stack>
      )}

      {/* ── controls ─────────────────────────────────────────────────────── */}
      <Paper sx={{ p: 2, mb: 2, borderRadius: "24px", border: "1px solid var(--app-shell-border)", background: "var(--app-panel-bg)", boxShadow: "var(--app-shell-shadow)" }}>
        <Stack direction="row" spacing={2} alignItems="center" flexWrap="wrap" mb={1.5}>
          <FormControl size="small" sx={{ minWidth: 160 }}>
            <InputLabel>Интервал</InputLabel>
            <Select value={interval} label="Интервал" onChange={(e) => onIntervalChange(e.target.value as "day" | "week")}>
              <MenuItem value="day">По дням</MenuItem>
              <MenuItem value="week">По неделям</MenuItem>
            </Select>
          </FormControl>
          {interval === "week" && (
            <FormControl size="small" sx={{ minWidth: 160 }}>
              <InputLabel>Месяц</InputLabel>
              <Select value={selectedMonth ?? ""} label="Месяц" displayEmpty onChange={(e) => setSelectedMonth(e.target.value || "")}>
                <MenuItem value="">Все месяцы</MenuItem>
                {monthOptions.map((m) => <MenuItem key={m} value={m}>{formatMonthLabel(m)}</MenuItem>)}
              </Select>
            </FormControl>
          )}
        </Stack>
        <FormGroup row sx={{ gap: 0.5 }}>
          {([
            ["bot_starts",          "Старты боты",              COLORS.bot_starts],
            ["almanah_starts",      "Старты Альманах",          COLORS.almanah_starts],
            ["channel_subscribed",  "Подписки КД",              COLORS.channel_subscribed],
            ["channel_unsubscribed","Отписки КД",               COLORS.channel_unsubscribed],
            ["saloon_subscribed",   "Подписки Салун",           COLORS.saloon_subscribed],
            ["saloon_unsubscribed", "Отписки Салун",            COLORS.saloon_unsubscribed],
          ] as [string, string, string][]).map(([key, label, color]) => (
            <FormControlLabel
              key={key}
              control={
                <Checkbox
                  checked={visible[key]}
                  onChange={() => toggle(key)}
                  size="small"
                  sx={{ color, "&.Mui-checked": { color } }}
                />
              }
              label={<Typography variant="body2">{label}</Typography>}
            />
          ))}
        </FormGroup>
      </Paper>

      {loading && <LinearProgress sx={{ mb: 1 }} />}
      {loading && !data.length && <TableSkeleton columns={8} rows={6} />}

      {/* ── line chart ───────────────────────────────────────────────────── */}
      {!loading && !chartData.length ? (
        <Paper sx={{ p: 0, mb: 2, borderRadius: "24px", border: "1px solid var(--app-shell-border)", background: "var(--app-panel-bg)", boxShadow: "var(--app-shell-shadow)", overflow: "hidden" }}>
          <EmptyState title="Для TG SUBS пока нет графика" description="Как только по выбранному периоду появятся данные, здесь покажем динамику стартов и подписок." />
        </Paper>
      ) : (
        <Paper sx={{ p: 2, mb: 2, borderRadius: "24px", border: "1px solid var(--app-shell-border)", background: "var(--app-panel-bg)", boxShadow: "var(--app-shell-shadow)" }}>
          <ResponsiveContainer width="100%" height={300}>
            <LineChart data={chartData} margin={{ top: 8, right: 24, bottom: 8, left: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--app-table-divider)" />
              <XAxis
                dataKey="date"
                tick={{ fontSize: 11, fill: "var(--c-ink2)" }}
                tickFormatter={(v) => interval === "week" ? formatWeekRange(v).split("–")[0].trim() : v}
              />
              <YAxis allowDecimals={false} tick={{ fontSize: 11, fill: "var(--c-ink2)" }} width={45} />
              <Tooltip content={<CustomTooltip interval={interval} />} />
              <Legend iconType="circle" iconSize={8} wrapperStyle={{ fontSize: 12 }} />
              {visible.bot_starts          && <Line type="monotone" dataKey="bot_starts"           name="Старты боты"     stroke={COLORS.bot_starts}           strokeWidth={2} dot={false} />}
              {visible.almanah_starts      && <Line type="monotone" dataKey="almanah_starts"       name="Старты Альманах" stroke={COLORS.almanah_starts}       strokeWidth={2} dot={false} />}
              {visible.channel_subscribed  && <Line type="monotone" dataKey="channel_subscribed"   name="Подписки КД"     stroke={COLORS.channel_subscribed}   strokeWidth={2} dot={false} />}
              {visible.channel_unsubscribed && <Line type="monotone" dataKey="channel_unsubscribed" name="Отписки КД"     stroke={COLORS.channel_unsubscribed} strokeWidth={2} dot={false} strokeDasharray="4 2" />}
              {visible.saloon_subscribed   && <Line type="monotone" dataKey="saloon_subscribed"    name="Подписки Салун"  stroke={COLORS.saloon_subscribed}    strokeWidth={2} dot={false} />}
              {visible.saloon_unsubscribed && <Line type="monotone" dataKey="saloon_unsubscribed"  name="Отписки Салун"   stroke={COLORS.saloon_unsubscribed}  strokeWidth={2} dot={false} strokeDasharray="4 2" />}
            </LineChart>
          </ResponsiveContainer>
        </Paper>
      )}

      {/* ── table ────────────────────────────────────────────────────────── */}
      <Paper sx={{ p: 0, borderRadius: "24px", border: "1px solid var(--app-shell-border)", background: "var(--app-panel-bg)", boxShadow: "var(--app-shell-shadow)", overflow: "hidden" }}>
        <TableContainer>
          <Table size="small" sx={{
            "& .MuiTableCell-root": { borderBottom: "1px solid var(--app-table-divider)", py: 1.1 },
            "& .MuiTableHead-root .MuiTableCell-root": { backgroundColor: "var(--app-table-head-bg)", color: "var(--c-ink2)", fontWeight: 700 },
            "& .MuiTableBody-root .MuiTableRow-root:nth-of-type(even)": { backgroundColor: "var(--app-table-row-alt)" },
            "& .MuiTableBody-root .MuiTableRow-root:hover": { backgroundColor: "var(--app-table-row-hover)" },
          }}>
            <TableHead>
              <TableRow>
                <TableCell sx={{ fontWeight: 700 }}>{groupBy === "bot" ? "Бот" : "РК"}</TableCell>
                <TableCell sx={{ fontWeight: 700 }}>Период</TableCell>
                <TableCell align="right" sx={{ fontWeight: 700 }}>Старты</TableCell>
                <TableCell align="right" sx={{ fontWeight: 700 }}>Альманах</TableCell>
                <TableCell align="right" sx={{ fontWeight: 700, color: "success.main" }}>КД +</TableCell>
                <TableCell align="right" sx={{ fontWeight: 700, color: "error.main" }}>КД −</TableCell>
                <TableCell align="right" sx={{ fontWeight: 700 }}>CR КД</TableCell>
                <TableCell align="right" sx={{ fontWeight: 700, color: "success.main" }}>Салун +</TableCell>
                <TableCell align="right" sx={{ fontWeight: 700, color: "error.main" }}>Салун −</TableCell>
                <TableCell align="right" sx={{ fontWeight: 700 }}>CR Салун</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {/* totals row */}
              <TableRow sx={{ backgroundColor: "var(--app-table-summary-bg)" }}>
                <TableCell sx={{ fontWeight: 700 }}>Итого</TableCell>
                <TableCell>—</TableCell>
                {renderCells(totals)}
              </TableRow>
              <TableRow sx={{ backgroundColor: "var(--app-table-row-alt)" }}>
                <TableCell sx={{ color: "text.secondary" }}>Медиана</TableCell>
                <TableCell>—</TableCell>
                {renderCells({
                  bot_starts:           median(groups.map((g) => g.bot_starts)),
                  almanah_starts:       median(groups.map((g) => g.almanah_starts)),
                  channel_subscribed:   median(groups.map((g) => g.channel_subscribed)),
                  channel_unsubscribed: median(groups.map((g) => g.channel_unsubscribed)),
                  saloon_subscribed:    median(groups.map((g) => g.saloon_subscribed)),
                  saloon_unsubscribed:  median(groups.map((g) => g.saloon_unsubscribed)),
                })}
              </TableRow>
              {/* campaign groups */}
              {groups.map((group) => {
                const open = expandedCampaigns.has(group.key);
                return (
                  <React.Fragment key={group.key}>
                    <TableRow hover>
                      <TableCell>
                        <Box sx={{ display: "flex", alignItems: "center", gap: 0.5 }}>
                          <IconButton size="small" onClick={() => toggleCampaign(group.key)}>
                            {open ? <KeyboardArrowDownIcon fontSize="small" /> : <KeyboardArrowRightIcon fontSize="small" />}
                          </IconButton>
                          <Typography variant="body2" fontWeight={600}>{groupBy === "bot" ? resolveLabel(group.key) : group.key}</Typography>
                          <MiniSparkline
                            values={sparkValues(group)}
                            color="var(--c-blue)"
                            fill="color-mix(in srgb, var(--c-blue) 12%, transparent)"
                          />
                        </Box>
                      </TableCell>
                      <TableCell><Typography variant="caption" color="text.secondary">Все {interval === "day" ? "дни" : "недели"}</Typography></TableCell>
                      {renderCells(group)}
                    </TableRow>
                    {/* bot mode: expand directly to date rows */}
                    {open && groupBy === "bot" && group.rows.map((row, idx) => (
                      <TableRow key={`${group.key}:${row.date}:${idx}`} sx={{ backgroundColor: "var(--app-table-subrow-bg)" }}>
                        <TableCell sx={{ pl: 6 }}>
                          <Typography variant="caption" color="text.secondary">
                            {interval === "week" ? formatWeekRange(row.date) : row.date}
                          </Typography>
                        </TableCell>
                        <TableCell />
                        {renderCells(row)}
                      </TableRow>
                    ))}
                    {/* campaign mode: expand to bots, then to date rows */}
                    {open && groupBy !== "bot" && group.bots.map((bot) => {
                      const botKey = `${group.key}:${bot.key}`;
                      const openBot = expandedBots.has(botKey);
                      return (
                        <React.Fragment key={botKey}>
                          <TableRow sx={{ backgroundColor: "var(--app-table-week-bg)" }} hover>
                            <TableCell sx={{ pl: 5 }}>
                              <Box sx={{ display: "flex", alignItems: "center", gap: 0.5 }}>
                                <IconButton size="small" onClick={() => toggleBot(botKey)}>
                                  {openBot ? <KeyboardArrowDownIcon fontSize="small" /> : <KeyboardArrowRightIcon fontSize="small" />}
                                </IconButton>
                                <Typography variant="body2" color="text.secondary">{resolveLabel(bot.key)}</Typography>
                                <MiniSparkline
                                  values={sparkValues(bot)}
                                  color="var(--c-green)"
                                  fill="color-mix(in srgb, var(--c-green) 12%, transparent)"
                                />
                              </Box>
                            </TableCell>
                            <TableCell><Typography variant="caption" color="text.secondary">Все {interval === "day" ? "дни" : "недели"}</Typography></TableCell>
                            {renderCells(bot)}
                          </TableRow>
                          {openBot && bot.rows.map((row, idx) => (
                            <TableRow key={`${botKey}:${row.date}:${idx}`} sx={{ backgroundColor: "var(--app-table-subrow-bg)" }}>
                              <TableCell sx={{ pl: 10 }}>
                                <Typography variant="caption" color="text.secondary">
                                  {interval === "week" ? formatWeekRange(row.date) : row.date}
                                </Typography>
                              </TableCell>
                              <TableCell />
                              {renderCells(row)}
                            </TableRow>
                          ))}
                        </React.Fragment>
                      );
                    })}
                  </React.Fragment>
                );
              })}
              {!loading && !groups.length && (
                <TableRow>
                  <TableCell colSpan={10} sx={{ py: 0 }}>
                    <EmptyState compact title="TG SUBS пуст под текущие фильтры" description="Попробуй другой период, интервал или более широкий набор данных." />
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </TableContainer>
      </Paper>
    </Box>
  );
};

export default SubscriptionsComparePanel;
