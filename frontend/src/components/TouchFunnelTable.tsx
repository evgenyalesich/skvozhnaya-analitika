// Таблица воронки с разбивкой по touch-точкам (first/last touch attribution).
// Строки = source (UTM/company), колонки = этапы воронки.
import React, { useMemo, useState, useEffect } from "react";
import axios from "axios";
import Box from "@mui/material/Box";
import Paper from "@mui/material/Paper";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableContainer from "@mui/material/TableContainer";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import Typography from "@mui/material/Typography";
import LinearProgress from "@mui/material/LinearProgress";
import IconButton from "@mui/material/IconButton";
import Collapse from "@mui/material/Collapse";
import Stack from "@mui/material/Stack";
import KeyboardArrowDownIcon from "@mui/icons-material/KeyboardArrowDown";
import KeyboardArrowUpIcon from "@mui/icons-material/KeyboardArrowUp";
import DownloadIcon from "@mui/icons-material/Download";
import { format, parseISO, isValid } from "date-fns";

import { TouchFunnelRow } from "../hooks/useTouchFunnelSummary";

interface TouchFunnelTableProps {
  title: string;
  rows: TouchFunnelRow[];
  loading: boolean;
  botLabel: string;
  mode: "first" | "last";
  startDate?: Date | null;
  endDate?: Date | null;
}

interface ColumnDef {
  key: string;
  label: string;
  type: "count" | "cr" | "percent" | "money";
  stageIndex: number;
}

const STAGES = [
  { key: "entered", label: "Вход" },
  { key: "lead", label: "Лид" },
  { key: "platform", label: "Платформа" },
  { key: "learning", label: "Обучение" },
  { key: "course", label: "Курс" },
  { key: "interview", label: "Собеседование" },
  { key: "passed", label: "Прошел собес" },
  { key: "offer", label: "Оффер" },
  { key: "distance_grinding", label: "Наигрывают дистанцию" },
  { key: "contract", label: "Контракт" },
];

const STAGE_KEYS = STAGES.map((stage) => stage.key);
const CONVERSION_SUFFIX = "_cr";

const COMPACT_CELL_SX = {
  px: 0.22,
  py: 0.24,
  whiteSpace: "nowrap",
  fontSize: "0.8rem",
  lineHeight: 1.2,
};

const HEADER_CELL_SX = {
  px: 0.16,
  py: 0.3,
  whiteSpace: "normal" as const,
  wordBreak: "break-word" as const,
  overflowWrap: "anywhere" as const,
  lineHeight: 1.05,
  verticalAlign: "bottom" as const,
  fontSize: "0.78rem",
};

const TABLE_CONTAINER_SX = {
  mt: 2,
  borderRadius: "24px",
  border: "1px solid var(--app-shell-border)",
  boxShadow: "var(--app-shell-shadow)",
  background: "var(--app-panel-bg)",
  overflowX: "auto",
  overflowY: "hidden",
};

const TABLE_SX = {
  tableLayout: "auto",
  minWidth: "max-content",
  "& .MuiTableCell-root": {
    ...COMPACT_CELL_SX,
    borderBottom: "1px solid var(--app-table-divider)",
  },
  "& .MuiTableHead-root .MuiTableCell-root": {
    position: "sticky",
    top: 0,
    zIndex: 1,
    backgroundColor: "var(--app-table-head-bg)",
    color: "var(--c-ink2)",
    fontWeight: 700,
    letterSpacing: 0,
    borderBottom: "1px solid var(--app-table-divider)",
    ...HEADER_CELL_SX,
    maxWidth: 58,
  },
  "& .MuiTableHead-root .MuiTableCell-root:first-of-type": {
    left: 0,
    zIndex: 2,
  },
  "& .data-row:nth-of-type(even)": {
    backgroundColor: "var(--app-table-row-alt)",
  },
  "& .data-row:hover": {
    backgroundColor: "var(--app-table-row-hover)",
  },
};

const SUMMARY_ROW_SX = {
  backgroundColor: "var(--app-table-summary-bg)",
  "& .MuiTableCell-root": {
    fontWeight: 600,
  },
};

const MONTH_ROW_SX = {
  backgroundColor: "var(--app-table-month-bg)",
  "& .MuiTableCell-root": {
    color: "var(--app-table-month-ink)",
    fontWeight: 700,
    borderBottom: "1px solid var(--app-table-divider)",
  },
};

const WEEK_ROW_SX = {
  backgroundColor: "var(--app-table-week-bg)",
  "& .MuiTableCell-root": {
    color: "var(--app-table-week-ink)",
    fontWeight: 600,
    borderBottom: "1px solid var(--app-table-divider)",
  },
};

const SEGMENT_BUTTON_SX = (active: boolean, edge: "left" | "right", color = "#2563eb") => ({
  border: `1px solid ${color}`,
  backgroundColor: active ? color : "var(--app-panel-muted)",
  color: active ? "#ffffff" : color,
  px: 1.4,
  py: 0.55,
  borderRadius: edge === "left" ? "10px 0 0 10px" : "0 10px 10px 0",
  cursor: "pointer",
  fontSize: "0.75rem",
  fontWeight: 700,
  lineHeight: 1.1,
  transition: "all 0.16s ease",
  boxShadow: active ? `0 6px 16px color-mix(in srgb, ${color} 24%, transparent)` : "none",
  borderLeft: edge === "right" ? "none" : undefined,
});

const percentColor = (percent: number) => {
  if (percent >= 50) return "var(--app-chip-success)";
  if (percent >= 10) return "var(--app-chip-warning)";
  return "var(--app-chip-danger)";
};

const formatPercentValue = (percent: number | null) => {
  if (percent === null || !Number.isFinite(percent)) {
    return "—";
  }
  return `${percent.toFixed(1)}%`;
};

const calculateMedian = (values: number[]) => {
  if (!values.length) {
    return 0;
  }
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  if (sorted.length % 2 === 1) {
    return sorted[mid];
  }
  return (sorted[mid - 1] + sorted[mid]) / 2;
};

const formatAggregateValue = (value: number) => {
  if (!Number.isFinite(value)) {
    return "—";
  }
  return Number.isInteger(value) ? value : value.toFixed(1);
};

const formatMoneyValue = (value: number | null) => {
  if (value === null || !Number.isFinite(value)) {
    return "—";
  }
  return `$${value.toFixed(1)}`;
};

interface WeeklyCacheRow {
  week_start: string;
  week_end: string;
  values: Record<string, number>;
}

const API_BASE = import.meta.env.VITE_API_BASE || "";

const formatMonthLabel = (value: string) => {
  const [year, month] = value.split("-");
  if (!year || !month) return value;
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

const TRAFFIC_METRIC_COLUMNS: ColumnDef[] = [
  { key: "impressions", label: "Показы", type: "count", stageIndex: -1 },
  { key: "clicks", label: "Клики", type: "count", stageIndex: -1 },
  { key: "ctr", label: "CTR", type: "percent", stageIndex: -1 },
  { key: "subscribed", label: "Подписчики КД", type: "count", stageIndex: -1 },
  { key: "cr_subscribed", label: "CR Подписчики КД", type: "percent", stageIndex: -1 },
  { key: "spend", label: "Spend", type: "money", stageIndex: -1 },
  { key: "budget", label: "Budget", type: "money", stageIndex: -1 },
  { key: "done_percent", label: "% Done", type: "percent", stageIndex: -1 },
  { key: "cpm", label: "CPM", type: "money", stageIndex: -1 },
  { key: "cpc", label: "CPC", type: "money", stageIndex: -1 },
  { key: "cpf", label: "CPF", type: "money", stageIndex: -1 },
];

const STAGE_MONEY_COLUMNS: Partial<Record<string, ColumnDef[]>> = {
  contract: [{ key: "contract_cost", label: "Цена контракта", type: "money", stageIndex: -1 }],
};

const getSpendBase = (source: Record<string, number>) => {
  const spend = source.spend ?? 0;
  const budget = source.budget ?? 0;
  return spend > 0 ? spend : budget;
};

const getMetricValue = (source: Record<string, number>, key: string): number | null => {
  const impressions = source.impressions ?? 0;
  const clicks = source.clicks ?? 0;
  const subscribed = source.subscribed ?? 0;
  const spendBase = getSpendBase(source);
  switch (key) {
    case "ctr":
      return impressions ? (clicks / impressions) * 100 : null;
    case "cr_subscribed":
      return clicks ? (subscribed / clicks) * 100 : null;
    case "cpm":
      return impressions ? (spendBase / impressions) * 1000 : null;
    case "cpc":
      return clicks ? spendBase / clicks : null;
    case "cpf":
      return subscribed ? spendBase / subscribed : null;
    case "cpl":
      return source.lead ? spendBase / source.lead : null;
    case "cpa":
      return source.platform ? spendBase / source.platform : null;
    case "contract_cost":
      return source.contract ? spendBase / source.contract : null;
    case "done_percent":
      return source.budget ? (source.spend ?? 0) / source.budget * 100 : null;
    default:
      return null;
  }
};

const WeeklyStats: React.FC<{ groupKey: string; mode: "first" | "last"; startDate?: Date | null; endDate?: Date | null }> = ({
  groupKey,
  mode,
  startDate,
  endDate,
}) => {
  const [monthlyRows, setMonthlyRows] = useState<Record<string, WeeklyCacheRow[]>>({});
  const [loadingWeekly, setLoadingWeekly] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!groupKey) {
      setMonthlyRows({});
      return;
    }
    let cancelled = false;
    const fetchWeekly = async () => {
      setLoadingWeekly(true);
      setError(null);
      try {
        const params = new URLSearchParams();
        params.append("group_key", groupKey);
        params.append("mode", mode);
        if (startDate) {
          params.append("start_date", format(startDate, "yyyy-MM-dd"));
        }
        if (endDate) {
          params.append("end_date", format(endDate, "yyyy-MM-dd"));
        }
        const response = await axios.get(`${API_BASE}/api/reports/touch/weekly`, { params });
        if (cancelled) {
          return;
        }
        const data = response.data?.data || {};
        setMonthlyRows(data);
      } catch (err) {
        if (!cancelled) {
          setMonthlyRows({});
          setError("Не удалось загрузить недельные данные");
        }
      } finally {
        if (!cancelled) {
          setLoadingWeekly(false);
        }
      }
    };
    fetchWeekly();
    return () => {
      cancelled = true;
    };
  }, [groupKey, mode, startDate, endDate]);

  const weeklyRows = useMemo(
    () => {
      const result = Object.values(monthlyRows)
        .flat()
        .map((row) => ({
          weekStart: parseISO(row.week_start),
          weekEnd: parseISO(row.week_end),
          values: row.values || {},
        }))
        .filter((row) => {
          if (startDate && isValid(startDate) && row.weekStart < startDate) return false;
          if (endDate && isValid(endDate) && row.weekStart > endDate) return false;
          return true;
        })
        .sort((a, b) => a.weekStart.getTime() - b.weekStart.getTime());
      return result;
    },
    [monthlyRows, startDate, endDate]
  );

  return (
    <Box sx={{ px: 0.25, py: 0.45 }}>
      <Typography variant="subtitle2" gutterBottom>
        Понедельная статистика
      </Typography>
      {loadingWeekly && <LinearProgress sx={{ mb: 2 }} />}
      {error && (
        <Typography variant="caption" color="error" sx={{ display: "block", mb: 2 }}>
          {error}
        </Typography>
      )}
      <Table size="small" sx={TABLE_SX}>
        <TableHead>
          <TableRow>
            <TableCell sx={{ minWidth: 84, px: 0.16 }}>Дата</TableCell>
            {STAGES.map((s) => (
              <TableCell key={s.key} sx={{ ...HEADER_CELL_SX, minWidth: 46 }}>{s.label}</TableCell>
            ))}
          </TableRow>
        </TableHead>
        <TableBody>
          {weeklyRows.map((row) => (
            <TableRow key={row.weekStart.toISOString()} className="data-row">
              <TableCell>
                {format(row.weekStart, "dd.MM")} - {format(row.weekEnd, "dd.MM")}
              </TableCell>
              {STAGES.map((s) => (
                <TableCell key={s.key}>{row.values[s.key] ?? 0}</TableCell>
              ))}
            </TableRow>
          ))}
          {!weeklyRows.length && !loadingWeekly && (
            <TableRow>
              <TableCell colSpan={STAGES.length + 1}>Нет данных</TableCell>
            </TableRow>
          )}
        </TableBody>
      </Table>
    </Box>
  );
};

interface MonthWeekGroupRow {
  groupKey: string;
  values: Record<string, number>;
}
interface MonthWeekEntry {
  weekStart: Date;
  weekEnd: Date;
  groups: MonthWeekGroupRow[];
}
interface MonthEntry {
  monthKey: string;
  weeks: MonthWeekEntry[];
}

const TouchFunnelTable: React.FC<TouchFunnelTableProps> = ({
  title,
  rows,
  loading,
  botLabel,
  mode,
  startDate,
  endDate,
}) => {
  const [sortKey, setSortKey] = useState<string>("entered");
  const [sortDirection, setSortDirection] = useState<"asc" | "desc">("desc");
  const [expandedRows, setExpandedRows] = useState<string[]>([]);
  const [viewMode, setViewMode] = useState<"group" | "month">("group");
  const [allGroupsWeekly, setAllGroupsWeekly] = useState<Record<string, Record<string, WeeklyCacheRow[]>>>({});
  const [loadingMonthView, setLoadingMonthView] = useState(false);

  useEffect(() => {
    if (viewMode !== "month" || !rows.length) return;
    let cancelled = false;
    const fetchAll = async () => {
      setLoadingMonthView(true);
      try {
        const results = await Promise.all(
          rows.map(async (row) => {
            const params = new URLSearchParams();
            params.append("group_key", row.bot || "");
            params.append("mode", mode);
            if (startDate) params.append("start_date", format(startDate, "yyyy-MM-dd"));
            if (endDate) params.append("end_date", format(endDate, "yyyy-MM-dd"));
            const resp = await axios.get(`${API_BASE}/api/reports/touch/weekly`, { params });
            return {
              groupKey: row.bot || "",
              months: (resp.data?.data || {}) as Record<string, WeeklyCacheRow[]>,
            };
          })
        );
        if (cancelled) return;
        const merged: Record<string, Record<string, WeeklyCacheRow[]>> = {};
        results.forEach(({ groupKey, months }) => { merged[groupKey] = months; });
        setAllGroupsWeekly(merged);
      } catch {
        // silently fail
      } finally {
        if (!cancelled) setLoadingMonthView(false);
      }
    };
    fetchAll();
    return () => { cancelled = true; };
  }, [viewMode, rows, mode, startDate, endDate]);

  const monthViewData = useMemo<MonthEntry[]>(() => {
    if (viewMode !== "month") return [];
    const weekMap = new Map<string, Map<string, MonthWeekGroupRow[]>>();
    const start = startDate && isValid(startDate) ? startDate : null;
    const end = endDate && isValid(endDate) ? endDate : null;
    Object.entries(allGroupsWeekly).forEach(([groupKey, months]) => {
      Object.entries(months).forEach(([monthKey, weekRows]) => {
        weekRows.forEach((wr) => {
          const ws = parseISO(wr.week_start);
          if (start && ws < start) return;
          if (end && ws > end) return;
          if (!weekMap.has(monthKey)) weekMap.set(monthKey, new Map());
          const wm = weekMap.get(monthKey)!;
          if (!wm.has(wr.week_start)) wm.set(wr.week_start, []);
          wm.get(wr.week_start)!.push({ groupKey, values: wr.values });
        });
      });
    });
    const result: MonthEntry[] = [];
    Array.from(weekMap.entries())
      .sort(([a], [b]) => a.localeCompare(b))
      .forEach(([monthKey, wm]) => {
        const weeks: MonthWeekEntry[] = Array.from(wm.entries())
          .sort(([a], [b]) => a.localeCompare(b))
          .map(([weekKey, groups]) => {
            const ws = parseISO(weekKey);
            const we = new Date(ws);
            we.setDate(ws.getDate() + 6);
            return { weekStart: ws, weekEnd: we, groups };
          });
        result.push({ monthKey, weeks });
      });
    return result;
  }, [viewMode, allGroupsWeekly, startDate, endDate]);

  const columns = useMemo<ColumnDef[]>(() => {
    const result: ColumnDef[] = [];
    STAGES.forEach((stage, index) => {
      result.push({
        key: stage.key,
        label: stage.label,
        type: "count",
        stageIndex: index,
      });
      if (stage.key === "entered") {
        result.push(...TRAFFIC_METRIC_COLUMNS);
      }
      if (index > 0) {
        result.push({
          key: `${stage.key}${CONVERSION_SUFFIX}`,
          label: `CR ${stage.label}`,
          type: "cr",
          stageIndex: index,
        });
        result.push(...(STAGE_MONEY_COLUMNS[stage.key] || []));
      }
    });
    return result;
  }, []);

  const columnByKey = useMemo(
    () =>
      columns.reduce((acc, column) => {
        acc[column.key] = column;
        return acc;
      }, {} as Record<string, ColumnDef>),
    [columns]
  );

  const getCountValue = (source: Record<string, number>, stageKey: string) =>
    source[stageKey] ?? 0;

  const getConversionValue = (source: Record<string, number>, stageIndex: number) => {
    if (stageIndex <= 0) {
      return null;
    }
    const currentKey = STAGES[stageIndex].key;
    const prevKey = STAGES[stageIndex - 1].key;
    const current = getCountValue(source, currentKey);
    const previous = getCountValue(source, prevKey);
    if (!previous) {
      return null;
    }
    return (current / previous) * 100;
  };

  const sortedRows = useMemo(() => {
    if (sortKey === "bot") {
      return [...rows].sort((a, b) => {
        const nameA = (a.bot || "").toLowerCase();
        const nameB = (b.bot || "").toLowerCase();
        return sortDirection === "asc" ? nameA.localeCompare(nameB) : nameB.localeCompare(nameA);
      });
    }
    const column = columnByKey[sortKey];
    return [...rows].sort((a, b) => {
      const valuesA = a as Record<string, number>;
      const valuesB = b as Record<string, number>;
      const fallbackA = valuesA[sortKey] ?? 0;
      const fallbackB = valuesB[sortKey] ?? 0;
      const valueA =
        column?.type === "cr"
          ? getConversionValue(valuesA, column.stageIndex) ?? -1
          : column?.type === "percent" || column?.type === "money"
            ? getMetricValue(valuesA, sortKey) ?? fallbackA
            : fallbackA;
      const valueB =
        column?.type === "cr"
          ? getConversionValue(valuesB, column.stageIndex) ?? -1
          : column?.type === "percent" || column?.type === "money"
            ? getMetricValue(valuesB, sortKey) ?? fallbackB
            : fallbackB;
      return sortDirection === "asc" ? valueA - valueB : valueB - valueA;
    });
  }, [rows, sortKey, sortDirection, columnByKey]);

  const aggregateRows = useMemo(() => {
    const baseKeys = [...STAGE_KEYS, "impressions", "clicks", "subscribed", "spend", "budget"];
    const valuesByKey: Record<string, number[]> = baseKeys.reduce((acc, key) => {
      acc[key] = rows.map((row) => (row as any)[key] ?? 0);
      return acc;
    }, {} as Record<string, number[]>);

    const buildRow = (label: string, calculator: (values: number[]) => number) => {
      const aggregated: Record<string, number> = {};
      baseKeys.forEach((key) => {
        aggregated[key] = calculator(valuesByKey[key]);
      });
      return { label, values: aggregated };
    };

    const totalRow = buildRow("Всего", (values) => values.reduce((sum, value) => sum + value, 0));
    const averageRow = buildRow("Средняя", (values) =>
      values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : 0
    );
    const medianRow = buildRow("Медиана", (values) => calculateMedian(values));
    return [totalRow, averageRow, medianRow];
  }, [rows]);

  const handleSort = (key: string) => {
    if (sortKey === key) {
      setSortDirection((prev) => (prev === "asc" ? "desc" : "asc"));
      return;
    }
    setSortKey(key);
    setSortDirection("desc");
  };

  const handleExportSummary = () => {
    const escapeValue = (value: string) => {
      if (value.includes('"') || value.includes(",") || value.includes("\n")) {
        return `"${value.replace(/"/g, '""')}"`;
      }
      return value;
    };
    const header = [botLabel, ...columns.map((column) => column.label)];
    const rowsCsv: string[][] = [
      header,
      ...sortedRows.map((row) => [
        row.bot || "нет метки",
        ...columns.map((column) => {
          if (column.type === "cr") {
            const percent = getConversionValue(row as Record<string, number>, column.stageIndex);
            return formatPercentValue(percent);
          }
          const value = (row as any)[column.key] ?? getMetricValue(row as any, column.key);
          if (column.type === "percent") {
            return formatPercentValue(value);
          }
          if (column.type === "money") {
            return formatMoneyValue(value);
          }
          return String(value ?? 0);
        }),
      ]),
    ];
    const csv = rowsCsv.map((row) => row.map((cell) => escapeValue(cell)).join(",")).join("\n");
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `${title.replace(/\s+/g, "_")}.csv`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  };

  const toggleExpand = (key: string) => {
    setExpandedRows((prev) =>
      prev.includes(key) ? prev.filter((item) => item !== key) : [...prev, key]
    );
  };

  return (
    <TableContainer component={Paper} sx={TABLE_CONTAINER_SX}>
      <Stack
        direction="row"
        alignItems="center"
        justifyContent="space-between"
        sx={{ px: 2, py: 1.25, borderBottom: "1px solid var(--app-table-divider)", backgroundColor: "transparent" }}
      >
        <Stack direction="row" spacing={1.5} alignItems="center" flexWrap="wrap">
          <Typography variant="subtitle1" sx={{ fontSize: "1rem", fontWeight: 700, color: "#0f172a" }}>
            {title}
          </Typography>
          <Typography variant="caption" sx={{ color: "#475569", fontWeight: 700 }}>
            {mode === "first" ? "GLOBAL: FIRST TOUCH" : "GLOBAL: LAST TOUCH"}
          </Typography>
          <Box>
            <Box
              component="button"
              onClick={() => setViewMode("group")}
              sx={SEGMENT_BUTTON_SX(viewMode === "group", "left", "#64748b")}
            >
              Бот → Месяц → Неделя
            </Box>
            <Box
              component="button"
              onClick={() => setViewMode("month")}
              sx={SEGMENT_BUTTON_SX(viewMode === "month", "right", "#64748b")}
            >
              Месяц → Неделя → Бот
            </Box>
          </Box>
        </Stack>
        <IconButton size="small" onClick={handleExportSummary} disabled={!rows.length} title="Скачать CSV">
          <DownloadIcon fontSize="small" />
        </IconButton>
      </Stack>
      {loading && <LinearProgress />}
      {viewMode === "month" && (
        loadingMonthView ? (
          <LinearProgress />
        ) : (
          <Table size="small" sx={TABLE_SX}>
            <TableHead>
              <TableRow>
                <TableCell>{botLabel}</TableCell>
                {columns.map((col) => <TableCell key={col.key}>{col.label}</TableCell>)}
              </TableRow>
            </TableHead>
            <TableBody>
              {monthViewData.map(({ monthKey, weeks }) => (
                <React.Fragment key={monthKey}>
                  <TableRow sx={MONTH_ROW_SX}>
                    <TableCell colSpan={columns.length + 1} sx={{ fontWeight: 700 }}>
                      {formatMonthLabel(monthKey)}
                    </TableCell>
                  </TableRow>
                  {weeks.map(({ weekStart, weekEnd, groups }) => (
                    <React.Fragment key={weekStart.toISOString()}>
                      <TableRow sx={WEEK_ROW_SX}>
                        <TableCell colSpan={columns.length + 1} sx={{ fontWeight: 600, px: 0.14 }}>
                          {format(weekStart, "dd.MM")} – {format(weekEnd, "dd.MM")}
                        </TableCell>
                      </TableRow>
                      {groups.map(({ groupKey, values }) => (
                        <TableRow key={groupKey} className="data-row">
                          <TableCell>{groupKey}</TableCell>
                          {columns.map((column) => {
                            if (column.type === "cr") {
                              const percent = getConversionValue(values, column.stageIndex);
                              return (
                                <TableCell key={column.key}>
                                  <Box component="span" sx={{ color: percent === null ? "text.secondary" : percentColor(percent), fontWeight: 600 }}>
                                    {formatPercentValue(percent)}
                                  </Box>
                                </TableCell>
                              );
                            }
                            if (column.type === "percent") {
                              const percent = getMetricValue(values, column.key);
                              return (
                                <TableCell key={column.key}>
                                  <Box component="span" sx={{ color: percent === null ? "text.secondary" : percentColor(percent), fontWeight: 600 }}>
                                    {formatPercentValue(percent)}
                                  </Box>
                                </TableCell>
                              );
                            }
                            if (column.type === "money") {
                              const money = values[column.key] ?? getMetricValue(values, column.key);
                              return <TableCell key={column.key}>{formatMoneyValue(money)}</TableCell>;
                            }
                            return <TableCell key={column.key}>{values[column.key] ?? 0}</TableCell>;
                          })}
                        </TableRow>
                      ))}
                    </React.Fragment>
                  ))}
                </React.Fragment>
              ))}
              {!monthViewData.length && (
                <TableRow><TableCell colSpan={columns.length + 1}>Нет данных</TableCell></TableRow>
              )}
            </TableBody>
          </Table>
        )
      )}
      {viewMode === "group" && <Table size="small" sx={TABLE_SX}>
        <TableHead>
          <TableRow>
            <TableCell sx={{ width: 20, px: "1px !important" }} />
            <TableCell sx={{ ...HEADER_CELL_SX, minWidth: 150, cursor: "pointer", textAlign: "left" }} onClick={() => handleSort("bot")}>
              {botLabel}
            </TableCell>
            {columns.map((column) => (
              <TableCell key={column.key} sx={{ ...HEADER_CELL_SX, minWidth: 46, cursor: "pointer" }} onClick={() => handleSort(column.key)}>
                {column.label}
              </TableCell>
            ))}
          </TableRow>
        </TableHead>
        <TableBody>
          {aggregateRows.map((summary) => (
            <TableRow
              key={`summary-${summary.label}`}
              sx={SUMMARY_ROW_SX}
            >
              <TableCell />
              <TableCell>{summary.label}</TableCell>
              {columns.map((column) => {
                if (column.type === "cr") {
                  const percent = getConversionValue(summary.values, column.stageIndex);
                  return (
                    <TableCell key={column.key}>
                      <Box
                        component="span"
                        sx={{
                          color: percent === null ? "text.secondary" : percentColor(percent),
                          fontWeight: 600,
                        }}
                      >
                        {formatPercentValue(percent)}
                      </Box>
                    </TableCell>
                  );
                }
                if (column.type === "percent") {
                  const percent = getMetricValue(summary.values, column.key);
                  return (
                    <TableCell key={column.key}>
                      <Box
                        component="span"
                        sx={{
                          color: percent === null ? "text.secondary" : percentColor(percent),
                          fontWeight: 600,
                        }}
                      >
                        {formatPercentValue(percent)}
                      </Box>
                    </TableCell>
                  );
                }
                if (column.type === "money") {
                  const money = summary.values[column.key] ?? getMetricValue(summary.values, column.key);
                  return <TableCell key={column.key}>{formatMoneyValue(money)}</TableCell>;
                }
                return (
                  <TableCell key={column.key}>
                    {formatAggregateValue(summary.values[column.key] ?? 0)}
                  </TableCell>
                );
              })}
            </TableRow>
          ))}
          {sortedRows.map((row) => {
            const rowKey = `${row.bot || "нет метки"}`;
            const expanded = expandedRows.includes(rowKey);
            return (
              <React.Fragment key={rowKey}>
                <TableRow className="data-row">
                  <TableCell>
                    <IconButton size="small" onClick={() => toggleExpand(rowKey)}>
                      {expanded ? <KeyboardArrowUpIcon /> : <KeyboardArrowDownIcon />}
                    </IconButton>
                  </TableCell>
                  <TableCell>{row.bot || "нет метки"}</TableCell>
                  {columns.map((column) => {
                    if (column.type === "cr") {
                      const percent = getConversionValue(row as Record<string, number>, column.stageIndex);
                      return (
                        <TableCell key={column.key}>
                          <Box
                            component="span"
                            sx={{
                              color: percent === null ? "text.secondary" : percentColor(percent),
                              fontWeight: 600,
                            }}
                          >
                            {formatPercentValue(percent)}
                          </Box>
                        </TableCell>
                      );
                    }
                    if (column.type === "percent") {
                      const percent = getMetricValue(row as Record<string, number>, column.key);
                      return (
                        <TableCell key={column.key}>
                          <Box
                            component="span"
                            sx={{
                              color: percent === null ? "text.secondary" : percentColor(percent),
                              fontWeight: 600,
                            }}
                          >
                            {formatPercentValue(percent)}
                          </Box>
                        </TableCell>
                      );
                    }
                    if (column.type === "money") {
                      const money = (row as any)[column.key] ?? getMetricValue(row as any, column.key);
                      return <TableCell key={column.key}>{formatMoneyValue(money)}</TableCell>;
                    }
                    return <TableCell key={column.key}>{(row as any)[column.key] ?? 0}</TableCell>;
                  })}
                </TableRow>
                <TableRow>
                  <TableCell colSpan={columns.length + 2} sx={{ p: 0 }}>
                    <Collapse in={expanded} timeout="auto" unmountOnExit>
                      <Box sx={{ px: 0.25, py: 0.45, backgroundColor: "transparent", borderTop: "1px solid var(--app-table-divider)" }}>
                        <WeeklyStats groupKey={rowKey} mode={mode} startDate={startDate} endDate={endDate} />
                      </Box>
                    </Collapse>
                  </TableCell>
                </TableRow>
              </React.Fragment>
            );
          })}
          {!rows.length && !loading && (
            <TableRow>
              <TableCell colSpan={columns.length + 2}>Нет данных</TableCell>
            </TableRow>
          )}
        </TableBody>
      </Table>}
    </TableContainer>
  );
};

export default TouchFunnelTable;
