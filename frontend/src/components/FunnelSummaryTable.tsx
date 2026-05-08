// Сводная таблица воронки по группам (бот или компания).
// Показывает entered/lead/platform/learning/course/interview/offer/contract + impressions/clicks/spend/budget.
// При клике по строке — выделяет группу (selectedGroup), что влияет на FunnelView ниже.
import React, { useMemo, useState, useEffect } from "react";
import axios from "axios";
import { addDays, addWeeks, format, parseISO, startOfWeek, isValid } from "date-fns";
import { FilterValues, buildFilterParams, buildQueryParams } from "../hooks/useReports";
import { useColumnResize } from "../hooks/useColumnResize";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip as RechartTooltip, Legend, ResponsiveContainer,
} from "recharts";
import Box from "@mui/material/Box";
import Paper from "@mui/material/Paper";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableContainer from "@mui/material/TableContainer";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import Typography from "@mui/material/Typography";
import Alert from "@mui/material/Alert";
import IconButton from "@mui/material/IconButton";
import Tooltip from "@mui/material/Tooltip";
import Popover from "@mui/material/Popover";
import FormGroup from "@mui/material/FormGroup";
import FormControlLabel from "@mui/material/FormControlLabel";
import Checkbox from "@mui/material/Checkbox";
import Button from "@mui/material/Button";
import Badge from "@mui/material/Badge";
import Collapse from "@mui/material/Collapse";
import Stack from "@mui/material/Stack";
import LinearProgress from "@mui/material/LinearProgress";
import KeyboardArrowDownIcon from "@mui/icons-material/KeyboardArrowDown";
import KeyboardArrowUpIcon from "@mui/icons-material/KeyboardArrowUp";
import TuneIcon from "@mui/icons-material/Tune";
import ExportButtons from "./ExportButtons";
import { downloadXlsxData } from "../utils/exportUtils";
import { FunnelSummaryRow } from "../hooks/useFunnelSummary";
import MiniSparkline from "./ui/MiniSparkline";
import EmptyState from "./ui/EmptyState";
import TableSkeleton from "./ui/TableSkeleton";

const API_BASE = import.meta.env.VITE_API_BASE || "";

const SYSTEM_STATUS_COLUMNS = [
  { key: "new_in_system", label: "Новые в системе" },
  { key: "old_in_system", label: "Старые в системе" },
];

const COMPACT_CELL_SX = {
  px: 0.18,
  py: 0.18,
  whiteSpace: "nowrap",
  overflow: "hidden",
  textOverflow: "ellipsis",
  fontSize: "0.73rem",
  lineHeight: 1.15,
};

const HEADER_CELL_SX = {
  px: 0.14,
  py: 0.22,
  whiteSpace: "nowrap" as const,
  overflow: "hidden" as const,
  textOverflow: "ellipsis" as const,
  lineHeight: 1.0,
  verticalAlign: "bottom" as const,
  fontSize: "0.7rem",
};

const TABLE_CONTAINER_SX = {
  mt: 2,
  borderRadius: "24px",
  border: "1px solid var(--app-shell-border)",
  boxShadow: "var(--app-shell-shadow)",
  background: "var(--app-panel-bg)",
  overflow: "hidden",
};

const TABLE_SCROLL_SX = {
  overflowX: "auto",
  overflowY: "hidden",
};

const LABEL_COL_WIDTH = 155;
const DATA_COL_WIDTH = 62;

const TABLE_SX = {
  tableLayout: "fixed",
  width: "max-content",
  minWidth: "max-content",
  "& .MuiTableCell-root": {
    ...COMPACT_CELL_SX,
    borderBottom: "1px solid var(--app-table-divider)",
    borderRight: "1px solid var(--app-table-divider)",
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
    borderRight: "1px solid var(--app-table-divider)",
    ...HEADER_CELL_SX,
    maxWidth: 62,
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

const SEGMENT_BUTTON_SX = (active: boolean, edge: "left" | "right") => ({
  border: "1px solid var(--c-blue)",
  background: active ? "linear-gradient(135deg, var(--c-blue), #1d4ed8)" : "var(--app-panel-muted)",
  color: active ? "#ffffff" : "var(--c-blue)",
  px: 1.4,
  py: 0.55,
  borderRadius: edge === "left" ? "10px 0 0 10px" : "0 10px 10px 0",
  cursor: "pointer",
  fontSize: "0.75rem",
  fontWeight: 700,
  lineHeight: 1.1,
  transition: "all 0.16s ease",
  boxShadow: active ? "0 10px 24px rgba(37, 99, 235, 0.22)" : "none",
  borderLeft: edge === "right" ? "none" : undefined,
  "&:hover": {
    background: active ? "linear-gradient(135deg, #1d4ed8, var(--c-blue))" : "var(--app-table-row-hover)",
  },
});

const STAGES = [
  { key: "entered", label: "Вход" },
  { key: "lead", label: "Рег. Альманах" },
  { key: "platform", label: "Рег. Платформа" },
  { key: "learning", label: "Старт обучения" },
  { key: "course", label: "Окончили Курс" },
  { key: "interview", label: "Назначено собеседование" },
  { key: "passed", label: "Прошел собес" },
  { key: "offer", label: "Оффер" },
  { key: "distance_grinding", label: "Наигрывают дистанцию" },
  { key: "contract", label: "Контракт" },
];

const STAGE_KEYS = [...SYSTEM_STATUS_COLUMNS.map((column) => column.key), ...STAGES.map((stage) => stage.key)];
const CONVERSION_SUFFIX = "_cr";

const downloadCsv = (filename: string, rows: string[][]) => {
  const escapeValue = (value: string) => {
    if (value.includes('"') || value.includes(",") || value.includes("\n")) {
      return `"${value.replace(/"/g, '""')}"`;
    }
    return value;
  };
  const csv = rows.map((row) => row.map((cell) => escapeValue(cell)).join(",")).join("\n");
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
};

interface FunnelSummaryTableProps {
  title: string;
  rows: FunnelSummaryRow[];
  nameLabel: string;
  nameResolver?: (value: string) => string;
  groupType?: "bot" | "company";
  groupMeta?: Record<string, { bots?: string[] }>;
  botLabelResolver?: (botKey: string) => string;
  startDate?: Date | null;
  endDate?: Date | null;
  selectedGroup?: string | null;
  onGroupSelect?: (group: string | null) => void;
  columnSettingsKey?: string;
  activeFilters?: FilterValues;
  totalOverride?: Record<string, number>;
  weeklySource?: "default" | "main_report";
}

interface ColumnDef {
  key: string;
  label: string;
  type: "count" | "cr" | "percent" | "money";
  stageIndex: number;
}

const percentColor = (percent: number) => {
  if (percent >= 50) return "var(--app-chip-success)";
  if (percent >= 10) return "var(--app-chip-warning)";
  return "var(--app-chip-danger)";
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

const formatPercentValue = (percent: number | null) => {
  if (percent === null || !Number.isFinite(percent)) {
    return "—";
  }
  return `${percent.toFixed(1)}%`;
};

const renderPercentWithProgress = (percent: number | null) => {
  const color = percent === null ? "var(--c-ink3)" : percentColor(percent);
  return (
    <Box sx={{ minWidth: 54 }}>
      <Box component="span" sx={{ color, fontWeight: 600 }}>
        {formatPercentValue(percent)}
      </Box>
      {percent !== null && (
        <Box
          sx={{
            mt: 0.45,
            height: 4,
            borderRadius: "999px",
            background: "var(--app-panel-muted)",
            overflow: "hidden",
          }}
        >
          <Box
            sx={{
              width: `${Math.max(0, Math.min(100, percent))}%`,
              height: "100%",
              borderRadius: "999px",
              background: color,
            }}
          />
        </Box>
      )}
    </Box>
  );
};

const stageSparkline = (source: Record<string, number>) => [
  source.entered ?? 0,
  source.lead ?? 0,
  source.platform ?? 0,
  source.learning ?? 0,
  source.course ?? 0,
  source.contract ?? 0,
];

const renderStatusCount = (key: string, value: number) => {
  const color = key === "new_in_system" ? "var(--app-chip-success)" : "var(--app-chip-warning)";
  return (
    <Box component="span" sx={{ color, fontWeight: 700 }}>
      {formatAggregateValue(value)}
    </Box>
  );
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
  lead: [{ key: "cpl", label: "CPL", type: "money", stageIndex: -1 }],
  platform: [{ key: "cpa", label: "CPA", type: "money", stageIndex: -1 }],
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

interface GroupWeeklyStatsProps {
  groupKey: string;
  groupType?: "bot" | "company";
  startDate?: Date | null;
  endDate?: Date | null;
  columns: ColumnDef[];
  activeFilters?: FilterValues;
  weeklySource?: "default" | "main_report";
}

interface WeeklyRow {
  weekStart: Date;
  weekEnd: Date;
  values: Record<string, number>;
}

interface WeeklyCacheRow {
  week_start: string;
  week_end: string;
  values: Record<string, number>;
}

const entryLabelByGroupType = (_groupType: "bot" | "company") => "Входов всего";

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

const GroupWeeklyStats: React.FC<GroupWeeklyStatsProps> = ({
  groupKey,
  groupType = "bot",
  startDate,
  endDate,
  columns,
  activeFilters,
  weeklySource = "default",
}) => {
  const [monthlyRows, setMonthlyRows] = useState<Record<string, WeeklyCacheRow[]>>({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const { getColWidth, handleResizeMouseDown } = useColumnResize(
    `funnel_group_weekly_col_widths_v1_${groupType}`
  );

  useEffect(() => {
    if (!groupKey) {
      setMonthlyRows({});
      return;
    }
    let cancelled = false;
    const fetchWeekly = async () => {
      setLoading(true);
      setError(null);
      try {
        if (weeklySource === "main_report") {
          const params = new URLSearchParams();
          if (startDate && isValid(startDate)) {
            const value = format(startDate, "yyyy-MM-dd");
            params.append("event_start", value);
            if ((activeFilters?.touchMode || "event") !== "event") {
              params.append("first_touch_start", value);
            }
          }
          if (endDate && isValid(endDate)) {
            const value = format(endDate, "yyyy-MM-dd");
            params.append("event_end", value);
            if ((activeFilters?.touchMode || "event") !== "event") {
              params.append("first_touch_end", value);
            }
          }
          const touchMode = activeFilters?.touchMode || "event";
          if (touchMode !== "event") {
            params.append("mode", touchMode);
          }
          params.append("display_mode", "weekly");
          // For first/last touch, passing `bots` here also affects cohort CTE and can zero-out
          // data for non-lead bots. In those modes we fetch then filter rows client-side.
          const shouldPassBotParam = groupType === "bot" && touchMode === "event";
          if (shouldPassBotParam) {
            params.append("bots", groupKey);
          } else if (groupType !== "bot") {
            params.append("advertising_companies", groupKey);
          }
          activeFilters?.utmSource.forEach((value) => params.append("utm_source", value));
          activeFilters?.utmCampaign.forEach((value) => params.append("utm_campaign", value));
          activeFilters?.utmMedium.forEach((value) => params.append("utm_medium", value));
          activeFilters?.utmContent.forEach((value) => params.append("utm_content", value));
          activeFilters?.utmTerm.forEach((value) => params.append("utm_term", value));

          const response = await axios.get(`${API_BASE}/api/reports/roistat-weekly/companies-weekly`, { params });
          if (cancelled) {
            return;
          }
          const allSourceRows = groupType === "bot" ? (response.data?.bot_rows || []) : (response.data?.rows || []);
          const sourceRows = groupType === "bot"
            ? allSourceRows.filter((row: any) => String(row.bot_key || "") === String(groupKey))
            : allSourceRows;
          const months: Record<string, WeeklyCacheRow[]> = {};
          sourceRows.forEach((row: any) => {
            const weekStart = row.week_start;
            const monthKey = String(weekStart).slice(0, 7);
            const weekEnd = format(addDays(parseISO(weekStart), 6), "yyyy-MM-dd");
            if (!months[monthKey]) {
              months[monthKey] = [];
            }
            months[monthKey].push({
              week_start: weekStart,
              week_end: weekEnd,
              values: {
                entered: Number(row.entered_all || 0),
                new_in_system: Number(row.new_in_system || 0),
                old_in_system: Number(row.old_in_system || 0),
                lead: Number(row.almanah_starts || 0),
                platform: Number(row.platform_cnt || 0),
                learning: Number(row.started_learning || 0),
                course: Number(row.completed_course || 0),
                interview: Number(row.interview_reached || 0),
                passed: 0,
                offer: Number(row.offer_received || 0),
                contract: Number(row.contract_signed || 0),
                distance_grinding: Number(row.distance_grinding || 0),
              },
            });
          });
          setMonthlyRows(months);
        } else {
          const hasDateRange = Boolean(activeFilters?.startDate && activeFilters?.endDate);
          const response = hasDateRange
            ? await axios.get(`${API_BASE}/api/reports/funnel-start/summary-weekly`, {
                params: buildQueryParams({
                  group_by: groupType === "bot" ? "bot_key" : "advertising_company",
                  group_key: groupKey,
                  touch_mode: activeFilters?.touchMode || "event",
                  ...(activeFilters ? buildFilterParams(activeFilters) : {}),
                }),
              })
            : await axios.get(`${API_BASE}/api/reports/weekly`, {
                params: { group_by: groupType, group_key: groupKey },
              });
          if (cancelled) {
            return;
          }
          const months = response.data?.months || {};
          setMonthlyRows(months);
        }
      } catch (err) {
        if (!cancelled) {
          setMonthlyRows({});
          setError("Не удалось загрузить недельные данные");
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    };
    fetchWeekly();
    return () => {
      cancelled = true;
    };
  }, [groupKey, groupType, activeFilters, weeklySource, startDate, endDate]);

  const [expandedGroupMonths, setExpandedGroupMonths] = useState<Set<string>>(new Set());
  const toggleGroupMonth = (m: string) => setExpandedGroupMonths((prev) => {
    const next = new Set(prev);
    if (next.has(m)) next.delete(m); else next.add(m);
    return next;
  });

  const allWeeklyRows = useMemo<WeeklyRow[]>(() => {
    const start = startDate && isValid(startDate) ? startOfWeek(startDate, { weekStartsOn: 1 }) : null;
    const end = endDate && isValid(endDate) ? startOfWeek(endDate, { weekStartsOn: 1 }) : null;
    const result: WeeklyRow[] = [];
    Object.values(monthlyRows).forEach((rows) => {
      rows.forEach((row) => {
        const weekStart = parseISO(row.week_start);
        if (start && weekStart < start) return;
        if (end && weekStart > end) return;
        result.push({
          weekStart,
          weekEnd: parseISO(row.week_end),
          values: row.values,
        });
      });
    });
    return result.sort((a, b) => a.weekStart.getTime() - b.weekStart.getTime());
  }, [monthlyRows, startDate, endDate]);

  const monthKeys = useMemo(
    () => Array.from(new Set(allWeeklyRows.map((week) => format(week.weekStart, "yyyy-MM")))).sort(),
    [allWeeklyRows]
  );

  const getWeeklyExportData = (): (string | number)[][] => [
    [
      "Дата",
      entryLabelByGroupType(groupType),
      ...SYSTEM_STATUS_COLUMNS.map((column) => column.label),
      ...STAGES.slice(1).map((stage) => stage.label),
    ],
    ...allWeeklyRows.map((week) => [
      `${format(week.weekStart, "dd.MM")} – ${format(week.weekEnd, "dd.MM")}`,
      week.values.entered ?? 0,
      ...SYSTEM_STATUS_COLUMNS.map((column) => week.values[column.key] ?? 0),
      ...STAGES.slice(1).map((stage) => week.values[stage.key] ?? 0),
    ]),
  ];

  const handleExportWeekly = () => {
    if (!allWeeklyRows.length) return;
    downloadCsv(`weekly_${groupType}_${groupKey}.csv`, getWeeklyExportData().map((r) => r.map(String)));
  };

  const handleExportWeeklyXlsx = () => {
    if (!allWeeklyRows.length) return;
    downloadXlsxData(`weekly_${groupType}_${groupKey}.xlsx`, getWeeklyExportData(), "Weekly");
  };

  const monthlyChartData = useMemo(() => {
    return monthKeys.map((monthKey) => {
      const weeks = allWeeklyRows.filter((w) => format(w.weekStart, "yyyy-MM") === monthKey);
      const vals: Record<string, number> = {};
      ["entered", "lead", "platform", "learning", "course", "interview", "offer", "contract"].forEach((k) => {
        vals[k] = weeks.reduce((s, w) => s + (w.values[k] || 0), 0);
      });
      return { month: formatMonthLabel(monthKey), ...vals };
    });
  }, [monthKeys, allWeeklyRows]);

  if (loading) {
    return <TableSkeleton columns={Math.min(columns.length + 2, 8)} rows={6} />;
  }
  if (error) {
    return <Alert severity="error">{error}</Alert>;
  }
  if (!monthKeys.length) {
    return <EmptyState compact title="Недельных данных пока нет" description="Когда появятся срезы по неделям, здесь будет видна динамика по этапам." />;
  }

  const totalCols = columns.length + 2; // expand + date + columns

  return (
    <Box>
      {monthlyChartData.length > 0 && (
        <Box sx={{ height: 200, px: 1, pt: 0.5, pb: 0 }}>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={monthlyChartData} margin={{ top: 2, right: 8, left: -24, bottom: 28 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
              <XAxis dataKey="month" tick={{ fontSize: 9 }} angle={-25} textAnchor="end" interval={0} />
              <YAxis tick={{ fontSize: 9 }} />
              <RechartTooltip contentStyle={{ fontSize: 11 }} />
              <Legend wrapperStyle={{ fontSize: 10 }} />
              <Bar dataKey="entered"   name="Вход"          fill="#2563eb" maxBarSize={12} />
              <Bar dataKey="lead"      name="Рег. Альманах"            fill="#16a34a" maxBarSize={12} />
              <Bar dataKey="platform"  name="Рег. Платформа"           fill="#0891b2" maxBarSize={12} />
              <Bar dataKey="learning"  name="Старт обучения"           fill="#7c3aed" maxBarSize={12} />
              <Bar dataKey="course"    name="Окончили Курс"            fill="#d97706" maxBarSize={12} />
              <Bar dataKey="interview" name="Назначено собеседование"  fill="#db2777" maxBarSize={12} />
              <Bar dataKey="offer"     name="Оффер"         fill="#ea580c" maxBarSize={12} />
              <Bar dataKey="contract"  name="Контракт"      fill="#dc2626" maxBarSize={12} />
            </BarChart>
          </ResponsiveContainer>
        </Box>
      )}
      <Stack direction="row" spacing={1} alignItems="center" sx={{ px: 1, pb: 0.5, pt: 0.5 }}>
        <ExportButtons
          getData={getWeeklyExportData}
          baseName={`weekly_${groupType}_${groupKey}`}
          sheetName="Weekly"
          disabled={!allWeeklyRows.length}
        />
      </Stack>
      <Table size="small" sx={TABLE_SX}>
        <colgroup>
          <col style={{ width: 32 }} />
          <col style={{ width: getColWidth("__label__", LABEL_COL_WIDTH) }} />
          {columns.map((column) => (
            <col key={column.key} style={{ width: getColWidth(column.key, DATA_COL_WIDTH) }} />
          ))}
        </colgroup>
        <TableHead>
          <TableRow>
            <TableCell sx={{ width: 20, px: "1px !important" }} />
            <TableCell sx={{ position: "relative", userSelect: "none", minWidth: getColWidth("__label__", LABEL_COL_WIDTH), px: 0.16 }}>
              Месяц / Дата
              <span onMouseDown={(e) => handleResizeMouseDown(e, "__label__", e.currentTarget.parentElement?.getBoundingClientRect().width ?? LABEL_COL_WIDTH)} style={{ position: "absolute", right: 0, top: 0, height: "100%", width: 6, cursor: "col-resize" }} />
            </TableCell>
            {columns.map((column) => (
              <TableCell key={column.key} sx={{ ...HEADER_CELL_SX, position: "relative", userSelect: "none", minWidth: 40 }} title={column.label}>
                {column.label}
                <span onMouseDown={(e) => handleResizeMouseDown(e, column.key, e.currentTarget.parentElement?.getBoundingClientRect().width ?? DATA_COL_WIDTH)} style={{ position: "absolute", right: 0, top: 0, height: "100%", width: 5, cursor: "col-resize" }} />
              </TableCell>
            ))}
          </TableRow>
        </TableHead>
        <TableBody>
          {monthKeys.map((monthKey) => {
            const monthExpanded = expandedGroupMonths.has(monthKey);
            const monthWeeks = allWeeklyRows.filter(
              (w) => format(w.weekStart, "yyyy-MM") === monthKey
            );
            return (
              <React.Fragment key={monthKey}>
                <TableRow
                  sx={{ ...MONTH_ROW_SX, cursor: "pointer" }}
                  onClick={() => toggleGroupMonth(monthKey)}
                >
                  <TableCell sx={{ px: "1px !important" }}>
                    <IconButton size="small">
                      {monthExpanded ? <KeyboardArrowUpIcon fontSize="small" /> : <KeyboardArrowDownIcon fontSize="small" />}
                    </IconButton>
                  </TableCell>
                  <TableCell colSpan={totalCols - 1} sx={{ fontWeight: 700, minWidth: LABEL_COL_WIDTH }}>
                    {formatMonthLabel(monthKey)}
                  </TableCell>
                </TableRow>
                {monthExpanded && monthWeeks.map((week) => (
                  <TableRow key={`${week.weekStart.toISOString()}`} className="data-row">
                    <TableCell />
                    <TableCell sx={{ whiteSpace: "nowrap", minWidth: LABEL_COL_WIDTH }}>
                      <Stack direction="row" alignItems="center" justifyContent="space-between" spacing={1}>
                        <span>{format(week.weekStart, "dd.MM")} – {format(week.weekEnd, "dd.MM")}</span>
                        <MiniSparkline
                          values={stageSparkline(week.values)}
                          color="var(--c-blue)"
                          fill="color-mix(in srgb, var(--c-blue) 12%, transparent)"
                        />
                      </Stack>
                    </TableCell>
                    {columns.map((column) => {
                      if (column.type === "cr") {
                        const percent = getConversionValue(week.values, column.stageIndex);
                        return <TableCell key={column.key}>{renderPercentWithProgress(percent)}</TableCell>;
                      }
                      if (column.type === "percent") {
                        const percent = getMetricValue(week.values, column.key);
                        return <TableCell key={column.key}>{renderPercentWithProgress(percent)}</TableCell>;
                      }
                      if (column.type === "money") {
                        const money = week.values[column.key] ?? getMetricValue(week.values, column.key);
                        return <TableCell key={column.key}>{formatMoneyValue(money)}</TableCell>;
                      }
                      if (column.key === "new_in_system" || column.key === "old_in_system") {
                        return <TableCell key={column.key}>{renderStatusCount(column.key, week.values[column.key] ?? 0)}</TableCell>;
                      }
                      return <TableCell key={column.key}>{week.values[column.key] ?? 0}</TableCell>;
                    })}
                  </TableRow>
                ))}
              </React.Fragment>
            );
          })}
        </TableBody>
      </Table>
    </Box>
  );
};


// Grouped view: month -> week -> group rows
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

const FunnelSummaryTable: React.FC<FunnelSummaryTableProps> = ({
  title,
  rows,
  nameLabel,
  nameResolver,
  groupType = "bot",
  groupMeta,
  botLabelResolver,
  startDate,
  endDate,
  selectedGroup,
  onGroupSelect,
  columnSettingsKey,
  activeFilters,
  totalOverride,
  weeklySource = "default",
}) => {
  const [sortKey, setSortKey] = useState<string>("entered");
  const [sortDirection, setSortDirection] = useState<"asc" | "desc">("desc");
  const [expandedRows, setExpandedRows] = useState<string[]>([]);
  const [viewMode, setViewMode] = useState<"group" | "month">("group");
  const [showStats, setShowStats] = useState(false);
  const [expandedMonths, setExpandedMonths] = useState<Set<string>>(new Set());
  const [expandedWeeks, setExpandedWeeks] = useState<Set<string>>(new Set());
  const [allGroupsWeekly, setAllGroupsWeekly] = useState<Record<string, Record<string, WeeklyCacheRow[]>>>({});
  const [loadingMonthView, setLoadingMonthView] = useState(false);
  const [columnsAnchorEl, setColumnsAnchorEl] = useState<HTMLElement | null>(null);
  const [hiddenColumns, setHiddenColumns] = useState<Set<string>>(new Set());
  const { getColWidth, handleResizeMouseDown } = useColumnResize(
    `funnel_summary_col_widths_v1_${columnSettingsKey ?? groupType}`
  );

  useEffect(() => {
    if (viewMode !== "month" || !rows.length) return;
    let cancelled = false;
    const fetchAll = async () => {
      setLoadingMonthView(true);
      try {
        const results = await Promise.all(
          rows.map(async (row) => {
            if (weeklySource === "main_report") {
              const params = new URLSearchParams();
              if (startDate && isValid(startDate)) {
                const value = format(startDate, "yyyy-MM-dd");
                params.append("event_start", value);
                if ((activeFilters?.touchMode || "event") !== "event") {
                  params.append("first_touch_start", value);
                }
              }
              if (endDate && isValid(endDate)) {
                const value = format(endDate, "yyyy-MM-dd");
                params.append("event_end", value);
                if ((activeFilters?.touchMode || "event") !== "event") {
                  params.append("first_touch_end", value);
                }
              }
              const touchMode = activeFilters?.touchMode || "event";
              if (touchMode !== "event") {
                params.append("mode", touchMode);
              }
              params.append("display_mode", "weekly");
              if (groupType === "bot") {
                if (touchMode === "event") {
                  params.append("bots", row.group);
                }
              } else {
                params.append("advertising_companies", row.group);
              }
              activeFilters?.utmSource.forEach((value) => params.append("utm_source", value));
              activeFilters?.utmCampaign.forEach((value) => params.append("utm_campaign", value));
              activeFilters?.utmMedium.forEach((value) => params.append("utm_medium", value));
              activeFilters?.utmContent.forEach((value) => params.append("utm_content", value));
              activeFilters?.utmTerm.forEach((value) => params.append("utm_term", value));

              const resp = await axios.get(`${API_BASE}/api/reports/roistat-weekly/companies-weekly`, { params });
              const allSourceRows = groupType === "bot" ? (resp.data?.bot_rows || []) : (resp.data?.rows || []);
              const sourceRows = groupType === "bot"
                ? allSourceRows.filter((item: any) => String(item.bot_key || "") === String(row.group))
                : allSourceRows;
              const months: Record<string, WeeklyCacheRow[]> = {};
              sourceRows.forEach((item: any) => {
                const weekStart = item.week_start;
                const monthKey = String(weekStart).slice(0, 7);
                const weekEnd = format(addDays(parseISO(weekStart), 6), "yyyy-MM-dd");
                if (!months[monthKey]) {
                  months[monthKey] = [];
                }
                months[monthKey].push({
                  week_start: weekStart,
                  week_end: weekEnd,
                  values: {
                    entered: Number(item.entered_all || 0),
                    new_in_system: Number(item.new_in_system || 0),
                    old_in_system: Number(item.old_in_system || 0),
                    lead: Number(item.almanah_starts || 0),
                    platform: Number(item.platform_cnt || 0),
                    learning: Number(item.started_learning || 0),
                    course: Number(item.completed_course || 0),
                    interview: Number(item.interview_reached || 0),
                    passed: 0,
                    offer: Number(item.offer_received || 0),
                    contract: Number(item.contract_signed || 0),
                    distance_grinding: Number(item.distance_grinding || 0),
                  },
                });
              });
              return { groupKey: row.group, months };
            }

            const hasDateRange = Boolean(activeFilters?.startDate && activeFilters?.endDate);
            const resp = hasDateRange
              ? await axios.get(`${API_BASE}/api/reports/funnel-start/summary-weekly`, {
                  params: buildQueryParams({
                    group_by: groupType === "bot" ? "bot_key" : "advertising_company",
                    group_key: row.group,
                    touch_mode: activeFilters?.touchMode || "event",
                    ...(activeFilters ? buildFilterParams(activeFilters) : {}),
                  }),
                })
              : await axios.get(`${API_BASE}/api/reports/weekly`, {
                  params: { group_by: groupType, group_key: row.group },
                });
            return { groupKey: row.group, months: (resp.data?.months || {}) as Record<string, WeeklyCacheRow[]> };
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
  }, [viewMode, rows, groupType, weeklySource, activeFilters, startDate, endDate]);

  const monthViewData = useMemo<MonthEntry[]>(() => {
    if (viewMode !== "month") return [];
    const weekMap = new Map<string, Map<string, MonthWeekGroupRow[]>>();
    const start = startDate && isValid(startDate) ? startOfWeek(startDate, { weekStartsOn: 1 }) : null;
    const end = endDate && isValid(endDate) ? startOfWeek(endDate, { weekStartsOn: 1 }) : null;
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
            const weekStart = parseISO(weekKey);
            return {
              weekStart,
              weekEnd: parseISO(weekKey.replace(/\d{4}-\d{2}-\d{2}/, (d) => {
                const dt = parseISO(d);
                dt.setDate(dt.getDate() + 6);
                return format(dt, "yyyy-MM-dd");
              })),
              groups,
            };
          });
        result.push({ monthKey, weeks });
      });
    return result;
  }, [viewMode, allGroupsWeekly, startDate, endDate]);

  const columns = useMemo<ColumnDef[]>(() => {
    const isTouch = (activeFilters?.touchMode ?? "event") !== "event";
    const result: ColumnDef[] = [];
    STAGES.forEach((stage, index) => {
      result.push({
        key: stage.key,
        label: stage.key === "entered" ? entryLabelByGroupType(groupType) : stage.label,
        type: "count",
        stageIndex: index,
      });
      if (stage.key === "entered") {
        if (!isTouch) {
          result.push(
            ...SYSTEM_STATUS_COLUMNS.map((column) => ({
              key: column.key,
              label: column.label,
              type: "count" as const,
              stageIndex: -1,
            }))
          );
        }
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
  }, [groupType, activeFilters?.touchMode]);

  useEffect(() => {
    if (!columnSettingsKey) {
      setHiddenColumns(new Set());
      return;
    }
    try {
      const raw = localStorage.getItem(`funnel_summary_hidden_cols_${columnSettingsKey}_v1`);
      if (!raw) {
        setHiddenColumns(new Set());
        return;
      }
      const parsed = JSON.parse(raw);
      setHiddenColumns(new Set(Array.isArray(parsed) ? parsed : []));
    } catch {
      setHiddenColumns(new Set());
    }
  }, [columnSettingsKey]);

  useEffect(() => {
    if (!columnSettingsKey) {
      return;
    }
    try {
      localStorage.setItem(
        `funnel_summary_hidden_cols_${columnSettingsKey}_v1`,
        JSON.stringify(Array.from(hiddenColumns))
      );
    } catch {
      // ignore storage errors
    }
  }, [columnSettingsKey, hiddenColumns]);

  const visibleColumns = useMemo(
    () => columns.filter((column) => !hiddenColumns.has(column.key)),
    [columns, hiddenColumns]
  );

  const columnByKey = useMemo(
    () =>
      columns.reduce((acc, column) => {
        acc[column.key] = column;
        return acc;
      }, {} as Record<string, ColumnDef>),
    [columns]
  );

  const sortedRows = useMemo(() => {
    if (sortKey === "name") {
      return [...rows].sort((a, b) => {
        const nameA = (nameResolver ? nameResolver(a.group) : a.group).toLowerCase();
        const nameB = (nameResolver ? nameResolver(b.group) : b.group).toLowerCase();
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
  }, [rows, sortKey, sortDirection, nameResolver, columnByKey]);

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

    let totalRow: { label: string; values: Record<string, number> };
    if (totalOverride) {
      const aggregated: Record<string, number> = {};
      baseKeys.forEach((key) => {
        aggregated[key] = totalOverride[key] ?? valuesByKey[key].reduce((sum, v) => sum + v, 0);
      });
      totalRow = { label: "Всего", values: aggregated };
    } else {
      totalRow = buildRow("Всего", (values) => values.reduce((sum, value) => sum + value, 0));
    }
    const averageRow = buildRow("Средняя", (values) =>
      values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : 0
    );
    const medianRow = buildRow("Медиана", (values) => calculateMedian(values));
    return [totalRow, averageRow, medianRow];
  }, [rows, totalOverride]);

  const toggleExpand = (group: string) => {
    setExpandedRows((prev) =>
      prev.includes(group) ? [] : [group]
    );
  };

  const handleSort = (key: string) => {
    if (sortKey === key) {
      setSortDirection((prev) => (prev === "asc" ? "desc" : "asc"));
      return;
    }
    setSortKey(key);
    setSortDirection("desc");
  };

  const getSummaryExportData = (): (string | number)[][] => {
    const header = [nameLabel, ...visibleColumns.map((column) => column.label)];
    return [
      header,
      ...sortedRows.map((row) => [
        nameResolver ? nameResolver(row.group) : row.group,
        ...visibleColumns.map((column) => {
          if (column.type === "cr") {
            const percent = getConversionValue(row as Record<string, number>, column.stageIndex);
            return formatPercentValue(percent);
          }
          const value = (row as any)[column.key] ?? getMetricValue(row as any, column.key);
          if (column.type === "percent") return formatPercentValue(value);
          if (column.type === "money") return formatMoneyValue(value);
          return value ?? 0;
        }),
      ]),
    ];
  };

  const handleExportSummary = () => {
    downloadCsv(`${title.replace(/\s+/g, "_")}.csv`, getSummaryExportData().map((r) => r.map(String)));
  };

  const groupLabel = groupType === "bot" ? "Бот" : "РК";

  const toggleMonth = (monthKey: string) => {
    setExpandedMonths((prev) => {
      const next = new Set(prev);
      if (next.has(monthKey)) next.delete(monthKey); else next.add(monthKey);
      return next;
    });
  };
  const toggleWeek = (weekKey: string) => {
    setExpandedWeeks((prev) => {
      const next = new Set(prev);
      if (next.has(weekKey)) next.delete(weekKey); else next.add(weekKey);
      return next;
    });
  };

  const renderMonthView = () => {
    if (loadingMonthView) {
      return <TableSkeleton columns={Math.min(visibleColumns.length + 2, 8)} rows={7} />;
    }
    if (!monthViewData.length) {
      return <EmptyState compact title="Месячная детализация пуста" description="Попробуй сменить период или убрать часть фильтров, чтобы раскрыть срезы по неделям." />;
    }
    return (
      <Table size="small" sx={TABLE_SX}>
        <colgroup>
          <col style={{ width: 32 }} />
          <col style={{ width: getColWidth("__label__", LABEL_COL_WIDTH) }} />
          {visibleColumns.map((col) => (
            <col key={col.key} style={{ width: getColWidth(col.key, DATA_COL_WIDTH) }} />
          ))}
        </colgroup>
        <TableHead>
          <TableRow>
            <TableCell sx={{ width: 20, px: "1px !important" }} />
            <TableCell sx={{ position: "relative", userSelect: "none" }}>
              {groupLabel}
              <span onMouseDown={(e) => handleResizeMouseDown(e, "__label__", e.currentTarget.parentElement?.getBoundingClientRect().width ?? LABEL_COL_WIDTH)} style={{ position: "absolute", right: 0, top: 0, height: "100%", width: 5, cursor: "col-resize" }} />
            </TableCell>
            {visibleColumns.map((col) => (
              <TableCell key={col.key} sx={{ ...HEADER_CELL_SX, position: "relative", userSelect: "none" }} title={col.label}>
                {col.label}
                <span onMouseDown={(e) => handleResizeMouseDown(e, col.key, e.currentTarget.parentElement?.getBoundingClientRect().width ?? DATA_COL_WIDTH)} style={{ position: "absolute", right: 0, top: 0, height: "100%", width: 5, cursor: "col-resize" }} />
              </TableCell>
            ))}
          </TableRow>
        </TableHead>
        <TableBody>
          {monthViewData.map(({ monthKey, weeks }) => {
            const monthExpanded = expandedMonths.has(monthKey);
            return (
              <React.Fragment key={monthKey}>
                <TableRow sx={MONTH_ROW_SX} style={{ cursor: "pointer" }} onClick={() => toggleMonth(monthKey)}>
                  <TableCell>
                    <IconButton size="small">
                      {monthExpanded ? <KeyboardArrowUpIcon /> : <KeyboardArrowDownIcon />}
                    </IconButton>
                  </TableCell>
                  <TableCell colSpan={visibleColumns.length + 1} sx={{ fontWeight: 700, minWidth: LABEL_COL_WIDTH }}>
                    {formatMonthLabel(monthKey)}
                  </TableCell>
                </TableRow>
                {monthExpanded && weeks.map(({ weekStart, weekEnd, groups }) => {
                  const weekKey = weekStart.toISOString();
                  const weekExpanded = expandedWeeks.has(weekKey);
                  return (
                    <React.Fragment key={weekKey}>
                      <TableRow sx={WEEK_ROW_SX} style={{ cursor: "pointer" }} onClick={() => toggleWeek(weekKey)}>
                        <TableCell>
                          <IconButton size="small">
                            {weekExpanded ? <KeyboardArrowUpIcon /> : <KeyboardArrowDownIcon />}
                          </IconButton>
                        </TableCell>
                        <TableCell colSpan={visibleColumns.length + 1} sx={{ fontWeight: 600, px: 0.14, minWidth: LABEL_COL_WIDTH }}>
                          {format(weekStart, "dd.MM")} – {format(weekEnd, "dd.MM")}
                        </TableCell>
                      </TableRow>
                      {weekExpanded && groups.map(({ groupKey, values }) => (
                        <TableRow key={groupKey} className="data-row">
                          <TableCell />
                          <TableCell sx={{ minWidth: LABEL_COL_WIDTH }}>
                            {nameResolver ? nameResolver(groupKey) : groupKey}
                          </TableCell>
                          {visibleColumns.map((column) => {
                            if (column.type === "cr") {
                              const percent = getConversionValue(values, column.stageIndex);
                              return <TableCell key={column.key}>{renderPercentWithProgress(percent)}</TableCell>;
                            }
                            if (column.type === "percent") {
                              const percent = getMetricValue(values, column.key);
                              return <TableCell key={column.key}>{renderPercentWithProgress(percent)}</TableCell>;
                            }
                            if (column.type === "money") {
                              const money = values[column.key] ?? getMetricValue(values, column.key);
                              return <TableCell key={column.key}>{formatMoneyValue(money)}</TableCell>;
                            }
                            if (column.key === "new_in_system" || column.key === "old_in_system") {
                              return <TableCell key={column.key}>{renderStatusCount(column.key, values[column.key] ?? 0)}</TableCell>;
                            }
                            return <TableCell key={column.key}>{values[column.key] ?? 0}</TableCell>;
                          })}
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
    );
  };

  return (
    <Paper sx={TABLE_CONTAINER_SX}>
      <Stack
        direction="row"
        alignItems="center"
        justifyContent="space-between"
        flexWrap="wrap"
        useFlexGap
        spacing={1}
        sx={{ px: 2, py: 1.25, borderBottom: "1px solid var(--app-table-divider)", backgroundColor: "transparent" }}
      >
        <Stack direction="row" spacing={1.5} alignItems="center">
          <Typography variant="subtitle1" sx={{ fontSize: "1rem", fontWeight: 800, color: "var(--c-ink)" }}>
            {title}
          </Typography>
          <Box>
            <Box
              component="button"
              onClick={() => setViewMode("group")}
              sx={SEGMENT_BUTTON_SX(viewMode === "group", "left")}
            >
              {groupLabel} → Месяц → Неделя
            </Box>
            <Box
              component="button"
              onClick={() => setViewMode("month")}
              sx={SEGMENT_BUTTON_SX(viewMode === "month", "right")}
            >
              Месяц → Неделя → {groupLabel}
            </Box>
          </Box>
          <Box
            component="button"
            onClick={() => setShowStats((v) => !v)}
            sx={SEGMENT_BUTTON_SX(showStats, "left")}
            style={{ borderRadius: 10 }}
          >
            {showStats ? "Скрыть медиану/среднее" : "Показать медиану/среднее"}
          </Box>
        </Stack>
        <ExportButtons
          getData={getSummaryExportData}
          baseName={title.replace(/\s+/g, "_")}
          sheetName="Summary"
          disabled={!rows.length}
        />
        {columnSettingsKey ? (
          <>
            <Tooltip title="Настроить столбцы">
              <Button
                variant="outlined"
                size="small"
                startIcon={
                  <Badge color="primary" badgeContent={hiddenColumns.size}>
                    <TuneIcon fontSize="small" />
                  </Badge>
                }
                onClick={(event) => setColumnsAnchorEl(event.currentTarget)}
              >
                Столбцы
              </Button>
            </Tooltip>
            <Popover
              open={Boolean(columnsAnchorEl)}
              anchorEl={columnsAnchorEl}
              onClose={() => setColumnsAnchorEl(null)}
              anchorOrigin={{ vertical: "bottom", horizontal: "right" }}
              transformOrigin={{ vertical: "top", horizontal: "right" }}
            >
              <Box sx={{ p: 1.5, minWidth: 280, maxHeight: 420, overflowY: "auto" }}>
                <Typography variant="subtitle2" sx={{ mb: 1 }}>
                  Показать столбцы
                </Typography>
                <FormGroup>
                  {columns.map((column) => {
                    const checked = !hiddenColumns.has(column.key);
                    return (
                      <FormControlLabel
                        key={column.key}
                        control={
                          <Checkbox
                            size="small"
                            checked={checked}
                            onChange={() =>
                              setHiddenColumns((prev) => {
                                const next = new Set(prev);
                                if (next.has(column.key)) {
                                  next.delete(column.key);
                                } else {
                                  next.add(column.key);
                                }
                                return next;
                              })
                            }
                          />
                        }
                        label={<Typography variant="body2">{column.label}</Typography>}
                      />
                    );
                  })}
                </FormGroup>
                <Stack direction="row" spacing={1} sx={{ mt: 1 }}>
                  <Button size="small" onClick={() => setHiddenColumns(new Set())}>
                    Показать все
                  </Button>
                  <Button
                    size="small"
                    color="inherit"
                    onClick={() => setHiddenColumns(new Set(columns.map((column) => column.key)))}
                  >
                    Скрыть все
                  </Button>
                </Stack>
              </Box>
            </Popover>
          </>
        ) : null}
      </Stack>
      <TableContainer sx={TABLE_SCROLL_SX}>
        {loadingMonthView && viewMode === "month" && <LinearProgress sx={{ mx: 1.5 }} />}
        {viewMode === "month" ? renderMonthView() : null}
        {viewMode === "group" && <Table size="small" sx={TABLE_SX}>
          <colgroup>
            <col style={{ width: 32 }} />
            <col style={{ width: getColWidth("__label__", LABEL_COL_WIDTH) }} />
            {visibleColumns.map((column) => (
              <col key={column.key} style={{ width: getColWidth(column.key, DATA_COL_WIDTH) }} />
            ))}
          </colgroup>
          <TableHead>
            <TableRow>
              <TableCell sx={{ width: 20, px: "1px !important" }} />
              <TableCell sx={{ ...HEADER_CELL_SX, position: "relative", userSelect: "none", minWidth: getColWidth("__label__", LABEL_COL_WIDTH), cursor: "pointer", textAlign: "left" }} onClick={() => handleSort("name")}>
                {nameLabel}
                <span onMouseDown={(e) => { e.stopPropagation(); handleResizeMouseDown(e, "__label__", e.currentTarget.parentElement?.getBoundingClientRect().width ?? LABEL_COL_WIDTH); }} style={{ position: "absolute", right: 0, top: 0, height: "100%", width: 5, cursor: "col-resize" }} />
              </TableCell>
              {visibleColumns.map((column) => (
                <TableCell
                  key={column.key}
                  sx={{ ...HEADER_CELL_SX, position: "relative", userSelect: "none", minWidth: 40, cursor: "pointer" }}
                  onClick={() => handleSort(column.key)}
                  title={column.label}
                >
                  {column.label}
                  <span onMouseDown={(e) => { e.stopPropagation(); handleResizeMouseDown(e, column.key, e.currentTarget.parentElement?.getBoundingClientRect().width ?? DATA_COL_WIDTH); }} style={{ position: "absolute", right: 0, top: 0, height: "100%", width: 5, cursor: "col-resize" }} />
                </TableCell>
              ))}
            </TableRow>
          </TableHead>
          <TableBody>
            {aggregateRows.filter((r) => r.label === "Всего" || showStats).map((summary) => (
              <TableRow
                key={`summary-${summary.label}`}
                sx={SUMMARY_ROW_SX}
              >
                <TableCell />
                <TableCell sx={{ minWidth: LABEL_COL_WIDTH }}>
                  <Stack direction="row" alignItems="center" justifyContent="space-between" spacing={1}>
                    <span>{summary.label}</span>
                    <MiniSparkline
                      values={stageSparkline(summary.values)}
                      color="var(--c-blue)"
                      fill="color-mix(in srgb, var(--c-blue) 12%, transparent)"
                    />
                  </Stack>
                </TableCell>
                {visibleColumns.map((column) => {
                  if (column.type === "cr") {
                    const percent = getConversionValue(summary.values, column.stageIndex);
                    return <TableCell key={column.key}>{renderPercentWithProgress(percent)}</TableCell>;
                  }
                  if (column.type === "percent") {
                    const percent = getMetricValue(summary.values, column.key);
                    return <TableCell key={column.key}>{renderPercentWithProgress(percent)}</TableCell>;
                  }
                      if (column.type === "money") {
                        const money = summary.values[column.key] ?? getMetricValue(summary.values, column.key);
                        return <TableCell key={column.key}>{formatMoneyValue(money)}</TableCell>;
                      }
                      if (column.key === "new_in_system" || column.key === "old_in_system") {
                        return (
                          <TableCell key={column.key}>
                            {renderStatusCount(column.key, summary.values[column.key] ?? 0)}
                          </TableCell>
                        );
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
              const expanded = expandedRows.includes(row.group);
              return (
                <React.Fragment key={row.group}>
                  <TableRow
                    className="data-row"
                    onClick={() => onGroupSelect?.(selectedGroup === row.group ? null : row.group)}
                    sx={{
                      cursor: onGroupSelect ? "pointer" : "default",
                      backgroundColor: selectedGroup === row.group ? "var(--app-table-row-hover) !important" : undefined,
                      outline: selectedGroup === row.group ? "2px solid var(--c-blue)" : undefined,
                    }}
                  >
                    <TableCell>
                      <IconButton size="small" onClick={(e) => { e.stopPropagation(); toggleExpand(row.group); }}>
                        {expanded ? <KeyboardArrowUpIcon /> : <KeyboardArrowDownIcon />}
                      </IconButton>
                    </TableCell>
                <TableCell>
                  <Stack direction="row" alignItems="center" justifyContent="space-between" spacing={1}>
                    <Box sx={{ minWidth: 0 }}>
                      {nameResolver ? nameResolver(row.group) : row.group}
                    </Box>
                    <MiniSparkline
                      values={stageSparkline(row as unknown as Record<string, number>)}
                      color="var(--c-blue)"
                      fill="color-mix(in srgb, var(--c-blue) 12%, transparent)"
                    />
                  </Stack>
                  {groupMeta?.[row.group]?.bots?.length ? (
                    <Typography variant="caption" color="text.secondary" component="div" sx={{ mt: 0.5 }}>
                      Боты:{" "}
                      {groupMeta[row.group].bots
                        .map((botKey) => botLabelResolver?.(botKey) ?? botKey)
                        .filter(Boolean)
                        .join(", ")}
                    </Typography>
                  ) : null}
                </TableCell>
                    {visibleColumns.map((column) => {
                      if (column.type === "cr") {
                        const percent = getConversionValue(
                          row as Record<string, number>,
                          column.stageIndex
                        );
                        return <TableCell key={column.key}>{renderPercentWithProgress(percent)}</TableCell>;
                      }
                      if (column.type === "percent") {
                        const percent = getMetricValue(row as Record<string, number>, column.key);
                        return <TableCell key={column.key}>{renderPercentWithProgress(percent)}</TableCell>;
                      }
                      if (column.type === "money") {
                        const money = (row as any)[column.key] ?? getMetricValue(row as any, column.key);
                        return <TableCell key={column.key}>{formatMoneyValue(money)}</TableCell>;
                      }
                      if (column.key === "new_in_system" || column.key === "old_in_system") {
                        return (
                          <TableCell key={column.key}>
                            {renderStatusCount(column.key, (row as any)[column.key] ?? 0)}
                          </TableCell>
                        );
                      }
                      return <TableCell key={column.key}>{(row as any)[column.key] ?? 0}</TableCell>;
                    })}
                  </TableRow>
                  <TableRow>
                    <TableCell colSpan={visibleColumns.length + 2} sx={{ p: 0 }}>
                      <Collapse in={expanded} timeout="auto" unmountOnExit>
                        <Box sx={{ px: 0, py: 0, backgroundColor: "transparent", borderTop: "1px solid var(--app-table-divider)" }}>
                          <Typography variant="subtitle2" sx={{ px: 1, pt: 0.5 }} gutterBottom>
                            Помесячная статистика
                          </Typography>
                          <GroupWeeklyStats
                            groupKey={row.group}
                            groupType={groupType}
                            startDate={startDate}
                            endDate={endDate}
                            columns={visibleColumns}
                            activeFilters={activeFilters}
                            weeklySource={weeklySource}
                          />
                        </Box>
                      </Collapse>
                    </TableCell>
                  </TableRow>
                </React.Fragment>
              );
            })}
            {!rows.length && (
              <TableRow>
                <TableCell colSpan={visibleColumns.length + 2} sx={{ py: 0 }}>
                  <EmptyState compact title="Воронка пока пустая" description="Нет строк под текущий период или набор фильтров. Попробуй расширить диапазон дат." />
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>}
      </TableContainer>
    </Paper>
  );
};

export default FunnelSummaryTable;
