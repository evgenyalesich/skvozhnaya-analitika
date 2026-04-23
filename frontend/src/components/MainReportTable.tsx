import React, { useEffect, useMemo, useRef, useState } from "react";
import { useColumnResize } from "../hooks/useColumnResize";
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
import Tooltip from "@mui/material/Tooltip";
import Popover from "@mui/material/Popover";
import FormGroup from "@mui/material/FormGroup";
import FormControlLabel from "@mui/material/FormControlLabel";
import Checkbox from "@mui/material/Checkbox";
import Divider from "@mui/material/Divider";
import Button from "@mui/material/Button";
import Badge from "@mui/material/Badge";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import CircularProgress from "@mui/material/CircularProgress";
import Autocomplete from "@mui/material/Autocomplete";
import FormControl from "@mui/material/FormControl";
import InputLabel from "@mui/material/InputLabel";
import Select from "@mui/material/Select";
import MenuItem from "@mui/material/MenuItem";
import TuneIcon from "@mui/icons-material/Tune";
import AddIcon from "@mui/icons-material/Add";
import KeyboardArrowDownIcon from "@mui/icons-material/KeyboardArrowDown";
import KeyboardArrowRightIcon from "@mui/icons-material/KeyboardArrowRight";
import SyncedTableScroll from "./SyncedTableScroll";
import ExportButtons from "./ExportButtons";
import MiniSparkline from "./ui/MiniSparkline";
import EmptyState from "./ui/EmptyState";
import TableSkeleton from "./ui/TableSkeleton";
import { MainReportRow, MainReportWeekTotalRow } from "../hooks/useMainReport";
import { AdvertisingCompanyOption } from "../hooks/useAdvertisingCompanies";

const STORAGE_KEY = "main_report_hidden_cols_v2";
const TREE_STATE_STORAGE_KEY = "main_report_tree_state_v1";

type ViewMode = "month-week-company-bot" | "month-company-week-bot";

type NumRow = {
  entered_all: number;
  budget: number;
  almanah_starts: number;
  direct_source_cnt: number;
  new_in_system: number;
  old_in_system: number;
  platform_cnt: number;
  learning: number;
  started_learning: number;
  mtt: number;
  spin: number;
  cash: number;
  base: number;
  not_started: number;
  channel_subscribed: number;
  saloon: number;
  completed_course: number;
  completed_mtt: number;
  completed_spin: number;
  completed_cash: number;
  completed_base: number;
  interview_reached: number;
  offer_received: number;
  contract_signed: number;
  contract_mtt: number;
  contract_spin: number;
  contract_cash: number;
  distance_grinding: number;
};

interface Props {
  rows: MainReportRow[];
  botRows?: MainReportRow[];
  weekTotals?: MainReportWeekTotalRow[];
  loading: boolean;
  error?: string | null;
  botNameResolver?: (botKey: string) => string;
  selectedMonth?: string;
  onSelectedMonthChange?: (value: string) => void;
  companies?: AdvertisingCompanyOption[];
  onCreateBudget?: (weekStart: string, campaign: string, botKey: string | null, amount: number) => Promise<void>;
}

interface Col {
  key: keyof NumRow | string;
  label: string;
  tooltip?: string;
  isBudget?: boolean;
  kind?: "money" | "percent" | "count";
  compute?: (r: NumRow) => number;
}

const NUM_KEYS: (keyof NumRow)[] = [
  "entered_all", "budget", "almanah_starts", "direct_source_cnt", "new_in_system", "old_in_system", "platform_cnt", "learning", "started_learning",
  "mtt", "spin", "cash", "base", "not_started", "channel_subscribed", "saloon",
  "completed_course", "completed_mtt", "completed_spin", "completed_cash", "completed_base",
  "interview_reached", "offer_received", "contract_signed", "contract_mtt", "contract_spin", "contract_cash",
  "distance_grinding",
];

const COLS: Col[] = [
  { key: "budget", label: "Бюджет $", isBudget: true, kind: "money" },
  { key: "entered_all", label: "Старт в бота", kind: "count" },
  { key: "cpa_start", label: "$ старта", kind: "money", compute: (r) => (r.entered_all ? r.budget / r.entered_all : 0) },
  { key: "almanah_starts", label: "Рег. Альманах", kind: "count" },
  { key: "direct_source_cnt", label: "Прямой источник", kind: "count" },
  { key: "cpa_almanah", label: "$ Альманах", kind: "money", compute: (r) => (r.almanah_starts ? r.budget / r.almanah_starts : 0) },
  { key: "platform_cnt", label: "Рег. на ПХ (ph)", kind: "count" },
  { key: "platform_cr", label: "% ПХ", kind: "percent", compute: (r) => (r.almanah_starts ? (r.platform_cnt / r.almanah_starts) * 100 : 0) },
  { key: "cpa_platform", label: "$ ПХ", kind: "money", compute: (r) => (r.platform_cnt ? r.budget / r.platform_cnt : 0) },
  { key: "started_learning", label: "Старт обучения", kind: "count" },
  { key: "started_course_cr", label: "% обуч.", kind: "percent", compute: (r) => (r.platform_cnt ? (r.started_learning / r.platform_cnt) * 100 : 0) },
  { key: "cpa_learning", label: "$ начала курса", kind: "money", compute: (r) => (r.started_learning ? r.budget / r.started_learning : 0) },
  { key: "completed_course", label: "Прошли курс", kind: "count" },
  { key: "course_cr", label: "% курса", kind: "percent", compute: (r) => (r.started_learning ? (r.completed_course / r.started_learning) * 100 : 0) },
  { key: "cpa_course", label: "$ дошли до конца", kind: "money", compute: (r) => (r.completed_course ? r.budget / r.completed_course : 0) },
  { key: "completed_mtt", label: "МТТ прошли", kind: "count" },
  { key: "completed_spin", label: "SPIN прошли", kind: "count" },
  { key: "completed_cash", label: "КЕШ прошли", kind: "count" },
  { key: "interview_reached", label: "Назначено собеседование", kind: "count" },
  { key: "interview_cr", label: "% предофер", kind: "percent", compute: (r) => (r.started_learning ? (r.interview_reached / r.started_learning) * 100 : 0) },
  { key: "offer_received", label: "Офер лид", kind: "count" },
  { key: "offer_cr", label: "% офер", kind: "percent", compute: (r) => (r.interview_reached ? (r.offer_received / r.interview_reached) * 100 : 0) },
  { key: "contract_signed", label: "Контракт", kind: "count" },
  { key: "contract_cr", label: "% контракт", kind: "percent", compute: (r) => (r.completed_course ? (r.contract_signed / r.completed_course) * 100 : 0) },
  { key: "cpa_contract", label: "$ контракт", kind: "money", compute: (r) => (r.contract_signed ? r.budget / r.contract_signed : 0) },
  { key: "contract_mtt", label: "МТТ контракт", kind: "count" },
  { key: "contract_spin", label: "SPIN контракт", kind: "count" },
  { key: "contract_cash", label: "КЕШ контракт", kind: "count" },
  { key: "distance_grinding", label: "Наигрыш дист.", kind: "count" },
  { key: "learning", label: "Рег. на курс", kind: "count" },
  { key: "base", label: "BASE рег.", kind: "count" },
  { key: "mtt", label: "МТТ рег.", kind: "count" },
  { key: "spin", label: "SPIN рег.", kind: "count" },
  { key: "cash", label: "КЕШ рег.", kind: "count" },
  { key: "not_started", label: "Не начали", kind: "count" },
  { key: "channel_subscribed", label: "Подписки КД", kind: "count" },
  { key: "saloon", label: "Салун", kind: "count" },
  { key: "new_in_system", label: "Новые", kind: "count" },
  { key: "old_in_system", label: "Старые", kind: "count" },
];

const MONTH_NAMES = [
  "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
  "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь",
];

const TABLE_CONTAINER_SX = {
  mt: 1.5,
  borderRadius: "24px",
  border: "1px solid var(--app-shell-border)",
  boxShadow: "var(--app-shell-shadow)",
  background: "var(--app-panel-bg)",
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
    px: 0.22,
    py: 0.2,
    whiteSpace: "nowrap",
    overflow: "hidden",
    textOverflow: "ellipsis",
    fontSize: "0.7rem",
    lineHeight: 1.1,
    borderBottom: "1px solid var(--app-table-divider)",
    borderRight: "1px solid var(--app-table-divider)",
  },
  "& .MuiTableHead-root .MuiTableCell-root": {
    position: "sticky",
    top: 0,
    zIndex: 2,
    backgroundColor: "var(--app-table-head-bg)",
    color: "var(--c-ink2)",
    fontWeight: 700,
    borderBottom: "1px solid var(--app-table-divider)",
    borderRight: "1px solid var(--app-table-divider)",
    whiteSpace: "nowrap",
    overflow: "hidden",
    textOverflow: "ellipsis",
    verticalAlign: "bottom",
    maxWidth: 62,
    px: 0.18,
    py: 0.22,
  },
  "& .MuiTableHead-root .MuiTableCell-root:first-of-type": {
    left: 0,
    zIndex: 3,
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
    fontWeight: 700,
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
  px: 1.15,
  py: 0.42,
  borderRadius: edge === "left" ? "10px 0 0 10px" : "0 10px 10px 0",
  cursor: "pointer",
  fontSize: "0.7rem",
  fontWeight: 700,
  lineHeight: 1.1,
  transition: "all 0.16s ease",
  boxShadow: active ? "0 10px 24px rgba(37, 99, 235, 0.22)" : "none",
  borderLeft: edge === "right" ? "none" : undefined,
  "&:hover": {
    background: active ? "linear-gradient(135deg, #1d4ed8, var(--c-blue))" : "var(--app-table-row-hover)",
  },
});

const loadHidden = (): Set<string> => {
  try {
    const s = localStorage.getItem(STORAGE_KEY);
    if (s) return new Set(JSON.parse(s));
  } catch {}
  return new Set();
};

const saveHidden = (set: Set<string>) => {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(Array.from(set)));
  } catch {}
};

const loadTreeState = () => {
  if (typeof window === "undefined") {
    return null;
  }
  try {
    const raw = window.sessionStorage.getItem(TREE_STATE_STORAGE_KEY);
    if (!raw) return null;
    return JSON.parse(raw) as {
      openMonths?: string[];
      openWeeks?: string[];
      openCompanies?: string[];
    };
  } catch {
    return null;
  }
};

const saveTreeState = (payload: { openMonths: Set<string>; openWeeks: Set<string>; openCompanies: Set<string> }) => {
  if (typeof window === "undefined") {
    return;
  }
  try {
    window.sessionStorage.setItem(
      TREE_STATE_STORAGE_KEY,
      JSON.stringify({
        openMonths: Array.from(payload.openMonths),
        openWeeks: Array.from(payload.openWeeks),
        openCompanies: Array.from(payload.openCompanies),
      }),
    );
  } catch {}
};

const ZERO = (): NumRow => NUM_KEYS.reduce((acc, key) => ({ ...acc, [key]: 0 }), {} as NumRow);

const sumRows = (src: NumRow[]): NumRow => {
  const acc = ZERO();
  src.forEach((r) => NUM_KEYS.forEach((k) => {
    acc[k] += r[k];
  }));
  return acc;
};

const fmt = (n: number) => (n > 0 ? n.toLocaleString("ru-RU") : "0");
const fmtBudget = (n: number) => (n > 0 ? `$${n.toLocaleString("ru-RU", { maximumFractionDigits: 0 })}` : "—");
const fmtMoney = (n: number) => (n > 0 ? `$${n.toFixed(2)}` : "—");
const fmtPercent = (n: number) => `${n.toFixed(2)}%`;
const metricTone = (col: Col, val: number) => {
  if (col.kind === "percent") {
    if (val >= 60) return { color: "var(--app-chip-success)", bg: "rgba(15,159,110,0.10)" };
    if (val >= 25) return { color: "var(--app-chip-warning)", bg: "rgba(201,133,23,0.12)" };
    return { color: "var(--app-chip-danger)", bg: "rgba(220,76,63,0.10)" };
  }
  if (col.kind === "money" && String(col.key).startsWith("cpa")) {
    if (val <= 5) return { color: "var(--app-chip-success)", bg: "rgba(15,159,110,0.10)" };
    if (val <= 15) return { color: "var(--app-chip-warning)", bg: "rgba(201,133,23,0.12)" };
    return { color: "var(--app-chip-danger)", bg: "rgba(220,76,63,0.10)" };
  }
  return null;
};

const monthLabel = (key: string) => {
  const [year, month] = key.split("-");
  return `${MONTH_NAMES[Number(month) - 1] || month} ${year}`;
};

const weekRange = (weekStart: string) => {
  const d = new Date(`${weekStart}T00:00:00`);
  const e = new Date(d);
  e.setDate(d.getDate() + 6);
  const f = (x: Date) =>
    `${String(x.getDate()).padStart(2, "0")}.${String(x.getMonth() + 1).padStart(2, "0")}.${x.getFullYear()}`;
  return `${f(d)} - ${f(e)}`;
};

const getMetricValue = (row: NumRow, col: Col) => (col.compute ? col.compute(row) : row[col.key as keyof NumRow]);

const sparklineValues = (row: NumRow) => [
  row.entered_all,
  row.almanah_starts,
  row.platform_cnt,
  row.started_learning,
  row.completed_course,
  row.contract_signed,
];

const LabelWithTrend: React.FC<{ label: React.ReactNode; row: NumRow; indent?: number }> = ({ label, row, indent = 0 }) => (
  <Stack direction="row" alignItems="center" spacing={1} sx={{ pl: indent }}>
    <Box sx={{ minWidth: 0, flex: 1, overflow: "hidden", textOverflow: "ellipsis" }}>
      {label}
    </Box>
    <MiniSparkline
      values={sparklineValues(row)}
      color="var(--c-blue)"
      fill="color-mix(in srgb, var(--c-blue) 14%, transparent)"
    />
  </Stack>
);

const ProgressMetric: React.FC<{ value: number; color: string }> = ({ value, color }) => (
  <Box sx={{ minWidth: 54 }}>
    <Box component="span">{fmtPercent(value)}</Box>
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
          width: `${Math.max(0, Math.min(100, value))}%`,
          height: "100%",
          borderRadius: "999px",
          background: color,
        }}
      />
    </Box>
  </Box>
);

const toNumRow = (row: MainReportRow): NumRow => ({
  entered_all: row.entered_all ?? 0,
  budget: row.budget ?? 0,
  almanah_starts: row.almanah_starts ?? 0,
  direct_source_cnt: row.direct_source_cnt ?? 0,
  new_in_system: row.new_in_system ?? 0,
  old_in_system: row.old_in_system ?? 0,
  platform_cnt: row.platform_cnt ?? 0,
  learning: row.learning ?? 0,
  started_learning: row.started_learning ?? 0,
  mtt: row.mtt ?? 0,
  spin: row.spin ?? 0,
  cash: row.cash ?? 0,
  base: row.base ?? 0,
  not_started: row.not_started ?? Math.max(0, (row.platform_cnt ?? 0) - (row.started_learning ?? 0)),
  channel_subscribed: row.channel_subscribed ?? 0,
  saloon: row.saloon ?? 0,
  completed_course: row.completed_course ?? 0,
  completed_mtt: row.completed_mtt ?? 0,
  completed_spin: row.completed_spin ?? 0,
  completed_cash: row.completed_cash ?? 0,
  completed_base: row.completed_base ?? 0,
  interview_reached: row.interview_reached ?? 0,
  offer_received: row.offer_received ?? 0,
  contract_signed: row.contract_signed ?? 0,
  contract_mtt: row.contract_mtt ?? 0,
  contract_spin: row.contract_spin ?? 0,
  contract_cash: row.contract_cash ?? 0,
  distance_grinding: row.distance_grinding ?? 0,
});

const toNumWeekTotalRow = (row: MainReportWeekTotalRow): NumRow => ({
  entered_all: row.entered_all ?? 0,
  budget: row.budget ?? 0,
  almanah_starts: row.almanah_starts ?? 0,
  direct_source_cnt: row.direct_source_cnt ?? 0,
  new_in_system: row.new_in_system ?? 0,
  old_in_system: row.old_in_system ?? 0,
  platform_cnt: row.platform_cnt ?? 0,
  learning: row.learning ?? 0,
  started_learning: row.started_learning ?? 0,
  mtt: row.mtt ?? 0,
  spin: row.spin ?? 0,
  cash: row.cash ?? 0,
  base: row.base ?? 0,
  not_started: row.not_started ?? Math.max(0, (row.platform_cnt ?? 0) - (row.started_learning ?? 0)),
  channel_subscribed: row.channel_subscribed ?? 0,
  saloon: row.saloon ?? 0,
  completed_course: row.completed_course ?? 0,
  completed_mtt: row.completed_mtt ?? 0,
  completed_spin: row.completed_spin ?? 0,
  completed_cash: row.completed_cash ?? 0,
  completed_base: row.completed_base ?? 0,
  interview_reached: row.interview_reached ?? 0,
  offer_received: row.offer_received ?? 0,
  contract_signed: row.contract_signed ?? 0,
  contract_mtt: row.contract_mtt ?? 0,
  contract_spin: row.contract_spin ?? 0,
  contract_cash: row.contract_cash ?? 0,
  distance_grinding: row.distance_grinding ?? 0,
});

const MetricCells: React.FC<{
  row: NumRow;
  cols: Col[];
  dimZero?: boolean;
  budgetAction?: React.ReactNode;
}> = ({ row, cols, dimZero, budgetAction }) => (
  <>
    {cols.map((col) => {
      const val = getMetricValue(row, col);
      const isZero = val === 0;
      let content: React.ReactNode;
      if (col.isBudget) content = fmtBudget(val);
      else if (col.kind === "money") content = fmtMoney(val);
      else if (col.kind === "percent") content = fmtPercent(val);
      else content = fmt(val);
      if (col.isBudget && budgetAction && val <= 0) {
        content = budgetAction;
      }
      const tone = metricTone(col, val);
      if (col.kind === "percent") {
        content = <ProgressMetric value={val} color={tone?.color || "var(--c-blue)"} />;
      }

      return (
        <TableCell
          key={col.key}
          align="right"
          sx={{
            color: isZero && dimZero ? "text.disabled" : tone?.color,
            backgroundColor: tone?.bg,
            fontWeight: tone ? 700 : undefined,
          }}
        >
          {content}
        </TableCell>
      );
    })}
  </>
);

const MainReportTable: React.FC<Props> = ({
  rows,
  botRows = [],
  weekTotals = [],
  loading,
  error,
  botNameResolver,
  selectedMonth: controlledSelectedMonth,
  onSelectedMonthChange,
  companies = [],
  onCreateBudget,
}) => {
  const [internalMonth, setInternalMonth] = useState("all");
  const [viewMode, setViewMode] = useState<ViewMode>("month-week-company-bot");
  const [hiddenCols, setHiddenCols] = useState<Set<string>>(loadHidden);
  const [colsAnchor, setColsAnchor] = useState<HTMLElement | null>(null);
  const { getColWidth, handleResizeMouseDown } = useColumnResize("main_report_col_widths_v1");
  const [openMonths, setOpenMonths] = useState<Set<string>>(new Set());
  const [openWeeks, setOpenWeeks] = useState<Set<string>>(new Set());
  const [openCompanies, setOpenCompanies] = useState<Set<string>>(new Set());
  const monthsInitializedRef = useRef(false);
  const [budgetAnchor, setBudgetAnchor] = useState<HTMLElement | null>(null);
  const [budgetWeek, setBudgetWeek] = useState("");
  const [budgetCampaign, setBudgetCampaign] = useState("");
  const [budgetBot, setBudgetBot] = useState("");
  const [budgetAmount, setBudgetAmount] = useState("");
  const [budgetSaving, setBudgetSaving] = useState(false);
  const [budgetError, setBudgetError] = useState<string | null>(null);

  const selectedMonth = controlledSelectedMonth ?? internalMonth;
  const setSelectedMonth = (value: string) => {
    if (onSelectedMonthChange) onSelectedMonthChange(value);
    else setInternalMonth(value);
  };

  const visibleCols = useMemo(() => COLS.filter((c) => !hiddenCols.has(c.key)), [hiddenCols]);
  const weekTotalsMap = useMemo(() => {
    const map = new Map<string, NumRow>();
    weekTotals.forEach((row) => {
      map.set(row.week_start, toNumWeekTotalRow(row));
    });
    return map;
  }, [weekTotals]);
  const monthKeys = useMemo(() => Array.from(new Set(rows.map((row) => row.week_start.slice(0, 7)))).sort(), [rows]);
  const visibleMonthKeys = useMemo(
    () => (selectedMonth === "all" ? monthKeys : monthKeys.filter((month) => month === selectedMonth)),
    [monthKeys, selectedMonth],
  );

  useEffect(() => {
    if (monthsInitializedRef.current) return;
    if (!visibleMonthKeys.length) return;
    monthsInitializedRef.current = true;
    const storedTreeState = loadTreeState();
    if (storedTreeState) {
      setOpenMonths(new Set(storedTreeState.openMonths || []));
      setOpenWeeks(new Set(storedTreeState.openWeeks || []));
      setOpenCompanies(new Set(storedTreeState.openCompanies || []));
      return;
    }
    setOpenMonths(new Set([visibleMonthKeys[visibleMonthKeys.length - 1]]));
  }, [visibleMonthKeys]);

  useEffect(() => {
    saveTreeState({ openMonths, openWeeks, openCompanies });
  }, [openMonths, openWeeks, openCompanies]);

  const companyTree = useMemo(() => {
    const grouped = new Map<string, Map<string, MainReportRow[]>>();
    rows.forEach((row) => {
      const month = row.week_start.slice(0, 7);
      if (!grouped.has(month)) grouped.set(month, new Map());
      const weekMap = grouped.get(month)!;
      if (!weekMap.has(row.week_start)) weekMap.set(row.week_start, []);
      weekMap.get(row.week_start)!.push(row);
    });

    return visibleMonthKeys
      .slice()
      .sort()
      .reverse()
      .map((month) => {
        const weeks = Array.from(grouped.get(month)?.entries() || [])
          .sort(([a], [b]) => b.localeCompare(a))
          .map(([week, companiesRows]) => ({
            week,
            companies: companiesRows.slice().sort((a, b) => b.almanah_starts - a.almanah_starts),
            agg: weekTotalsMap.get(week) || sumRows(companiesRows.map(toNumRow)),
          }));
        return { month, weeks, agg: sumRows(weeks.map((week) => week.agg)) };
      });
  }, [rows, visibleMonthKeys, weekTotalsMap]);

  const botTree = useMemo(() => {
    const companyRowMap = new Map<string, MainReportRow>();
    rows.forEach((row) => companyRowMap.set(`${row.week_start}::${row.company}`, row));

    const monthMap = new Map<string, Map<string, Map<string, MainReportRow[]>>>();
    botRows.forEach((row) => {
      const month = row.week_start.slice(0, 7);
      const company = row.company || "Без категории";
      if (!monthMap.has(month)) monthMap.set(month, new Map());
      const companiesMap = monthMap.get(month)!;
      if (!companiesMap.has(company)) companiesMap.set(company, new Map());
      const weeksMap = companiesMap.get(company)!;
      if (!weeksMap.has(row.week_start)) weeksMap.set(row.week_start, []);
      weeksMap.get(row.week_start)!.push(row);
    });

    return visibleMonthKeys
      .slice()
      .sort()
      .reverse()
      .map((month) => {
        const companiesData = Array.from(monthMap.get(month)?.entries() || [])
          .sort(([a], [b]) => a.localeCompare(b))
          .map(([company, weeksMap]) => {
            const weeks = Array.from(weeksMap.entries())
              .sort(([a], [b]) => b.localeCompare(a))
              .map(([week, bots]) => ({
                week,
                companyRow: companyRowMap.get(`${week}::${company}`),
                bots: bots.slice().sort((a, b) => b.almanah_starts - a.almanah_starts),
              }));
            const companyAgg = sumRows(
              weeks
                .map((item) => item.companyRow)
                .filter((item): item is MainReportRow => Boolean(item))
                .map(toNumRow),
            );
            return { company, weeks, agg: companyAgg };
          });
        return { month, companies: companiesData, agg: sumRows(companiesData.map((item) => item.agg)) };
      });
  }, [rows, botRows, visibleMonthKeys]);

  const weekCompanyBotTree = useMemo(() => {
    const companyRowMap = new Map<string, MainReportRow>();
    rows.forEach((row) => companyRowMap.set(`${row.week_start}::${row.company}`, row));

    const monthMap = new Map<string, Map<string, Map<string, MainReportRow[]>>>();
    botRows.forEach((row) => {
      const month = row.week_start.slice(0, 7);
      if (!monthMap.has(month)) monthMap.set(month, new Map());
      const weeksMap = monthMap.get(month)!;
      if (!weeksMap.has(row.week_start)) weeksMap.set(row.week_start, new Map());
      const companiesMap = weeksMap.get(row.week_start)!;
      const company = row.company || "Без категории";
      if (!companiesMap.has(company)) companiesMap.set(company, []);
      companiesMap.get(company)!.push(row);
    });

    return visibleMonthKeys
      .slice()
      .sort()
      .reverse()
      .map((month) => {
        const weeks = Array.from(monthMap.get(month)?.entries() || [])
          .sort(([a], [b]) => b.localeCompare(a))
          .map(([week, companiesMap]) => {
            const companies = Array.from(companiesMap.entries())
              .sort(([a], [b]) => a.localeCompare(b))
              .map(([company, bots]) => ({
                company,
                row: companyRowMap.get(`${week}::${company}`),
                bots: bots.slice().sort((a, b) => b.almanah_starts - a.almanah_starts),
              }));
            const agg = weekTotalsMap.get(week) || sumRows(
              companies
                .map((item) => item.row)
                .filter((item): item is MainReportRow => Boolean(item))
                .map(toNumRow),
            );
            return { week, companies, agg };
          });
        return { month, weeks, agg: sumRows(weeks.map((item) => item.agg)) };
      });
  }, [rows, botRows, visibleMonthKeys]);

  const grandTotal = useMemo(
    () => sumRows((viewMode === "month-week-company-bot" ? weekCompanyBotTree : botTree).map((item) => item.agg)),
    [weekCompanyBotTree, botTree, viewMode],
  );

  const toggleSet = (setter: React.Dispatch<React.SetStateAction<Set<string>>>, key: string) =>
    setter((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });

  const openBudgetPopover = (
    event: React.MouseEvent<HTMLElement>,
    weekStart: string,
    campaign: string,
    botKey?: string | null,
  ) => {
    setBudgetAnchor(event.currentTarget);
    setBudgetWeek(weekStart);
    setBudgetCampaign(campaign);
    setBudgetBot(botKey && botKey !== "Без бота" ? botKey : "");
    setBudgetAmount("");
    setBudgetError(null);
  };

  const closeBudgetPopover = () => setBudgetAnchor(null);

  const selectedCompany = companies.find((item) => item.company_name === budgetCampaign);
  const botOptions = selectedCompany?.bot_keys || [];

  const saveBudget = async () => {
    if (!onCreateBudget || !budgetCampaign.trim() || !budgetAmount.trim()) return;
    const amount = Number(budgetAmount.replace(",", ".").replace(/\s/g, ""));
    if (!Number.isFinite(amount) || amount <= 0) {
      setBudgetError("Введите корректную сумму");
      return;
    }
    setBudgetSaving(true);
    setBudgetError(null);
    try {
      await onCreateBudget(budgetWeek, budgetCampaign.trim(), budgetBot || null, amount);
      closeBudgetPopover();
    } catch (err: any) {
      setBudgetError(err?.response?.data?.detail || err?.message || "Ошибка сохранения бюджета");
    } finally {
      setBudgetSaving(false);
    }
  };

  const budgetButton = (weekStart: string, campaign: string, botKey?: string | null) =>
    onCreateBudget ? (
      <IconButton size="small" onClick={(event) => openBudgetPopover(event, weekStart, campaign, botKey)}>
        <AddIcon fontSize="small" />
      </IconButton>
    ) : "—";

  const renderBotLabel = (botKey?: string | null) => {
    const value = botKey || "Без бота";
    if (!botKey || botKey === "Без бота") {
      return value;
    }
    return botNameResolver ? botNameResolver(botKey) : value;
  };

  const getExportData = (): (string | number)[][] => {
    const header =
      viewMode === "month-week-company-bot"
        ? ["Месяц", "Неделя", "РК", "Бот", ...visibleCols.map((col) => col.label)]
        : ["Месяц", "РК", "Неделя", "Бот", ...visibleCols.map((col) => col.label)];

    const data: (string | number)[][] = [header];
    if (viewMode === "month-week-company-bot") {
      weekCompanyBotTree.forEach(({ month, weeks }) => {
        weeks.forEach(({ week, companies }) => {
          companies.forEach(({ company, bots }) => {
            bots.forEach((row) => {
              data.push([
                monthLabel(month),
                weekRange(week),
                company,
                renderBotLabel(row.bot_key),
                ...visibleCols.map((col) => getMetricValue(toNumRow(row), col)),
              ]);
            });
          });
        });
      });
    } else {
      botTree.forEach(({ month, companies: companyRows }) => {
        companyRows.forEach(({ company, weeks }) => {
          weeks.forEach(({ week, bots }) => {
            bots.forEach((row) => {
              data.push([
                monthLabel(month),
                company,
                weekRange(week),
                renderBotLabel(row.bot_key),
                ...visibleCols.map((col) => getMetricValue(toNumRow(row), col)),
              ]);
            });
          });
        });
      });
    }
    return data;
  };

  return (
    <TableContainer component={Paper} sx={TABLE_CONTAINER_SX}>
      <Stack
        direction="row"
        alignItems="center"
        justifyContent="space-between"
        sx={{ px: 1.75, py: 1.1, borderBottom: "1px solid var(--app-table-divider)", backgroundColor: "transparent", gap: 1.25, flexWrap: "wrap" }}
      >
        <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap">
          <Typography variant="subtitle1" sx={{ fontSize: "1rem", fontWeight: 800, color: "var(--c-ink)" }}>
            Основной отчёт
          </Typography>
          <Box>
            <Box component="button" onClick={() => setViewMode("month-week-company-bot")} sx={SEGMENT_BUTTON_SX(viewMode === "month-week-company-bot", "left")}>
              Месяц → Неделя → РК → Бот
            </Box>
            <Box component="button" onClick={() => setViewMode("month-company-week-bot")} sx={SEGMENT_BUTTON_SX(viewMode === "month-company-week-bot", "right")}>
              Месяц → РК → Неделя → Бот
            </Box>
          </Box>
          <Box
            component="select"
            value={selectedMonth}
            onChange={(event) => setSelectedMonth(String(event.target.value))}
            className="app-native-select"
            style={{ minWidth: 180, fontSize: 13 }}
          >
            <option value="all">Все месяцы</option>
            {monthKeys.slice().sort().reverse().map((month) => (
              <option key={month} value={month}>
                {monthLabel(month)}
              </option>
            ))}
          </Box>
        </Stack>

        <Stack direction="row" spacing={1} alignItems="center">
          <Tooltip title="Настроить колонки">
            <Button
              size="small"
              variant={hiddenCols.size > 0 ? "contained" : "outlined"}
              onClick={(event) => setColsAnchor(event.currentTarget)}
              startIcon={
                <Badge badgeContent={hiddenCols.size > 0 ? hiddenCols.size : 0} color="warning" invisible={hiddenCols.size === 0}>
                  <TuneIcon fontSize="small" />
                </Badge>
              }
              sx={{ textTransform: "none", fontSize: "0.72rem", px: 1.2, minWidth: "auto" }}
            >
              Столбцы
            </Button>
          </Tooltip>
          <ExportButtons getData={getExportData} baseName="main_report" sheetName="MainReport" disabled={!rows.length} />
        </Stack>
      </Stack>

      {loading && <LinearProgress sx={{ mb: 1 }} />}
      {error && <Typography variant="body2" color="error" sx={{ px: 2, pt: 1 }}>{error}</Typography>}
      {loading && !rows.length && <TableSkeleton columns={Math.min(visibleCols.length + 1, 8)} rows={7} />}

      <Popover
        open={Boolean(colsAnchor)}
        anchorEl={colsAnchor}
        onClose={() => setColsAnchor(null)}
        anchorOrigin={{ vertical: "bottom", horizontal: "right" }}
        transformOrigin={{ vertical: "top", horizontal: "right" }}
      >
        <Stack sx={{ p: 1.5, maxHeight: 520, overflow: "auto", minWidth: 260 }}>
          <Stack direction="row" justifyContent="space-between" alignItems="center" mb={0.5}>
            <Typography variant="caption" color="text.secondary" fontWeight={600}>
              Метрики ({COLS.length - hiddenCols.size}/{COLS.length})
            </Typography>
            <Stack direction="row" spacing={0.5}>
              <Typography variant="caption" color="primary" sx={{ cursor: "pointer" }} onClick={() => { const next = new Set<string>(); setHiddenCols(next); saveHidden(next); }}>
                Все
              </Typography>
              <Typography variant="caption" color="text.secondary">/</Typography>
              <Typography variant="caption" color="primary" sx={{ cursor: "pointer" }} onClick={() => { const next = new Set<string>(COLS.map((col) => String(col.key))); setHiddenCols(next); saveHidden(next); }}>
                Ни одной
              </Typography>
            </Stack>
          </Stack>
          <Divider sx={{ mb: 0.5 }} />
          <FormGroup>
            {COLS.map((col) => (
              <FormControlLabel
                key={col.key}
                control={<Checkbox size="small" checked={!hiddenCols.has(col.key)} onChange={() => {
                  setHiddenCols((prev) => {
                    const next = new Set(prev);
                    if (next.has(col.key)) next.delete(col.key);
                    else next.add(col.key);
                    saveHidden(next);
                    return next;
                  });
                }} />}
                label={<Typography variant="body2">{col.label}</Typography>}
                sx={{ mx: 0 }}
              />
            ))}
          </FormGroup>
        </Stack>
      </Popover>

      <SyncedTableScroll maxHeight="calc(100vh - 240px)" topOffset={0}>
        <Table size="small" sx={TABLE_SX}>
          <colgroup>
            <col style={{ width: getColWidth("__label__", LABEL_COL_WIDTH) }} />
            {visibleCols.map((col) => (
              <col key={col.key} style={{ width: getColWidth(col.key, DATA_COL_WIDTH) }} />
            ))}
          </colgroup>
          <TableHead>
            <TableRow>
              <TableCell sx={{ position: "relative", userSelect: "none", minWidth: getColWidth("__label__", LABEL_COL_WIDTH) }}>
                {viewMode === "month-week-company-bot" ? "Период / Неделя / РК / Бот" : "Период / РК / Неделя / Бот"}
                <span onMouseDown={(e) => handleResizeMouseDown(e, "__label__", e.currentTarget.parentElement?.getBoundingClientRect().width ?? LABEL_COL_WIDTH)} style={{ position: "absolute", right: 0, top: 0, height: "100%", width: 5, cursor: "col-resize" }} />
              </TableCell>
              {visibleCols.map((col) => (
                <TableCell key={col.key} align="right" title={col.label} sx={{ position: "relative", userSelect: "none" }}>
                  {col.label}
                  <span onMouseDown={(e) => handleResizeMouseDown(e, col.key, e.currentTarget.parentElement?.getBoundingClientRect().width ?? DATA_COL_WIDTH)} style={{ position: "absolute", right: 0, top: 0, height: "100%", width: 5, cursor: "col-resize" }} />
                </TableCell>
              ))}
            </TableRow>
          </TableHead>
          <TableBody>
            <TableRow sx={SUMMARY_ROW_SX}>
              <TableCell>
                <LabelWithTrend label="Итого за период" row={grandTotal} />
              </TableCell>
              <MetricCells row={grandTotal} cols={visibleCols} />
            </TableRow>

            {viewMode === "month-week-company-bot" && weekCompanyBotTree.map(({ month, weeks, agg }) => {
              const monthOpen = openMonths.has(month);
              return (
                <React.Fragment key={month}>
                  <TableRow sx={{ ...MONTH_ROW_SX, cursor: "pointer" }} onClick={() => toggleSet(setOpenMonths, month)}>
                    <TableCell>
                      <LabelWithTrend
                        label={
                          <Stack direction="row" spacing={0.5} alignItems="center">
                            {monthOpen ? <KeyboardArrowDownIcon fontSize="small" /> : <KeyboardArrowRightIcon fontSize="small" />}
                            <span>{monthLabel(month)}</span>
                          </Stack>
                        }
                        row={agg}
                      />
                    </TableCell>
                    <MetricCells row={agg} cols={visibleCols} />
                  </TableRow>

                  {monthOpen && weeks.map(({ week, companies: companyRows, agg: weekAgg }) => {
                    const weekOpen = openWeeks.has(week);
                    return (
                      <React.Fragment key={week}>
                        <TableRow sx={{ ...WEEK_ROW_SX, cursor: "pointer" }} onClick={() => toggleSet(setOpenWeeks, week)}>
                          <TableCell sx={{ pl: 1.75 }}>
                            <LabelWithTrend
                              label={
                                <Stack direction="row" spacing={0.5} alignItems="center">
                                  {weekOpen ? <KeyboardArrowDownIcon fontSize="small" /> : <KeyboardArrowRightIcon fontSize="small" />}
                                  <span>{weekRange(week)}</span>
                                </Stack>
                              }
                              row={weekAgg}
                            />
                          </TableCell>
                          <MetricCells row={weekAgg} cols={visibleCols} />
                        </TableRow>

                        {weekOpen && companyRows.map(({ company, row, bots }) => {
                          const companyKey = `${week}::${company}`;
                          const companyOpen = openCompanies.has(companyKey);
                          const companyRow = row ? toNumRow(row) : sumRows(bots.map(toNumRow));
                          return (
                            <React.Fragment key={companyKey}>
                              <TableRow className="data-row" sx={{ backgroundColor: "var(--app-table-subrow-bg)", cursor: "pointer" }} onClick={() => toggleSet(setOpenCompanies, companyKey)}>
                                <TableCell sx={{ pl: 3.75 }}>
                                  <LabelWithTrend
                                    label={
                                      <Stack direction="row" spacing={0.5} alignItems="center">
                                        {companyOpen ? <KeyboardArrowDownIcon fontSize="small" /> : <KeyboardArrowRightIcon fontSize="small" />}
                                        <span>{company}</span>
                                      </Stack>
                                    }
                                    row={companyRow}
                                  />
                                </TableCell>
                                <MetricCells row={companyRow} cols={visibleCols} budgetAction={budgetButton(week, company)} />
                              </TableRow>
                              {companyOpen && bots.map((botRow) => (
                                <TableRow key={`${companyKey}::${botRow.bot_key}`} className="data-row">
                                  <TableCell>
                                    <LabelWithTrend label={renderBotLabel(botRow.bot_key)} row={toNumRow(botRow)} indent={5.5} />
                                  </TableCell>
                                  <MetricCells
                                    row={toNumRow(botRow)}
                                    cols={visibleCols}
                                    dimZero
                                    budgetAction={budgetButton(botRow.week_start, botRow.company, botRow.bot_key || null)}
                                  />
                                </TableRow>
                              ))}
                            </React.Fragment>
                          );
                        })}
                      </React.Fragment>
                    );
                  })}
                </React.Fragment>
              );
            })}

            {viewMode === "month-company-week-bot" && botTree.map(({ month, companies: companyRows, agg }) => {
              const monthOpen = openMonths.has(month);
              return (
                <React.Fragment key={month}>
                  <TableRow sx={{ ...MONTH_ROW_SX, cursor: "pointer" }} onClick={() => toggleSet(setOpenMonths, month)}>
                    <TableCell>
                      <LabelWithTrend
                        label={
                          <Stack direction="row" spacing={0.5} alignItems="center">
                            {monthOpen ? <KeyboardArrowDownIcon fontSize="small" /> : <KeyboardArrowRightIcon fontSize="small" />}
                            <span>{monthLabel(month)}</span>
                          </Stack>
                        }
                        row={agg}
                      />
                    </TableCell>
                    <MetricCells row={agg} cols={visibleCols} />
                  </TableRow>

                  {monthOpen && companyRows.map(({ company, weeks, agg: companyAgg }) => {
                    const companyKey = `${month}::${company}`;
                    const companyOpen = openCompanies.has(companyKey);
                    return (
                      <React.Fragment key={companyKey}>
                        <TableRow sx={{ ...WEEK_ROW_SX, cursor: "pointer" }} onClick={() => toggleSet(setOpenCompanies, companyKey)}>
                          <TableCell sx={{ pl: 1.75 }}>
                            <LabelWithTrend
                              label={
                                <Stack direction="row" spacing={0.5} alignItems="center">
                                  {companyOpen ? <KeyboardArrowDownIcon fontSize="small" /> : <KeyboardArrowRightIcon fontSize="small" />}
                                  <span>{company}</span>
                                </Stack>
                              }
                              row={companyAgg}
                            />
                          </TableCell>
                          <MetricCells row={companyAgg} cols={visibleCols} />
                        </TableRow>

                        {companyOpen && weeks.map(({ week, companyRow, bots }) => {
                          const weekKey = `${companyKey}::${week}`;
                          const weekOpen = openWeeks.has(weekKey);
                          const weekRow = companyRow ? toNumRow(companyRow) : sumRows(bots.map(toNumRow));
                          return (
                            <React.Fragment key={weekKey}>
                              <TableRow className="data-row" sx={{ backgroundColor: "var(--app-table-subrow-bg)", cursor: "pointer" }} onClick={() => toggleSet(setOpenWeeks, weekKey)}>
                                <TableCell sx={{ pl: 3.75 }}>
                                  <LabelWithTrend
                                    label={
                                      <Stack direction="row" spacing={0.5} alignItems="center">
                                        {weekOpen ? <KeyboardArrowDownIcon fontSize="small" /> : <KeyboardArrowRightIcon fontSize="small" />}
                                        <span>{weekRange(week)}</span>
                                      </Stack>
                                    }
                                    row={weekRow}
                                  />
                                </TableCell>
                                <MetricCells row={weekRow} cols={visibleCols} budgetAction={budgetButton(week, company)} />
                              </TableRow>

                              {weekOpen && bots.map((row) => (
                                <TableRow key={`${weekKey}::${row.bot_key}`} className="data-row">
                                  <TableCell>
                                    <LabelWithTrend label={renderBotLabel(row.bot_key)} row={toNumRow(row)} indent={5.5} />
                                  </TableCell>
                                  <MetricCells
                                    row={toNumRow(row)}
                                    cols={visibleCols}
                                    dimZero
                                    budgetAction={budgetButton(row.week_start, row.company, row.bot_key || null)}
                                  />
                                </TableRow>
                              ))}
                            </React.Fragment>
                          );
                        })}
                      </React.Fragment>
                    );
                  })}
                </React.Fragment>
              );
            })}

            {!loading && !rows.length && (
              <TableRow>
                <TableCell colSpan={visibleCols.length + 1} align="center" sx={{ py: 0 }}>
                  <EmptyState
                    compact
                    title="Основной отчет пока пуст"
                    description="Выбери другой период или ослабь фильтры, чтобы построить воронку и увидеть детализацию."
                  />
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </SyncedTableScroll>

      <Popover
        open={Boolean(budgetAnchor)}
        anchorEl={budgetAnchor}
        onClose={closeBudgetPopover}
        anchorOrigin={{ vertical: "bottom", horizontal: "right" }}
        transformOrigin={{ vertical: "top", horizontal: "right" }}
      >
        <Stack spacing={2} sx={{ p: 2, minWidth: 280 }}>
          <Typography variant="subtitle2">
            Бюджет за неделю{budgetWeek ? ` (${weekRange(budgetWeek)})` : ""}
          </Typography>
          <Autocomplete
            freeSolo
            options={companies.map((item) => item.company_name).filter(Boolean)}
            inputValue={budgetCampaign}
            onInputChange={(_, value) => {
              setBudgetCampaign(value);
              setBudgetBot("");
            }}
            renderInput={(params) => <TextField {...params} label="РК" size="small" />}
          />
          {botOptions.length > 0 && (
            <FormControl size="small">
              <InputLabel id="main-report-bot-label">Бот</InputLabel>
              <Select labelId="main-report-bot-label" label="Бот" value={budgetBot} onChange={(event) => setBudgetBot(String(event.target.value))}>
                <MenuItem value=""><em>Все боты РК</em></MenuItem>
                {botOptions.map((bot) => (
                  <MenuItem key={bot} value={bot}>{bot}</MenuItem>
                ))}
              </Select>
            </FormControl>
          )}
          <TextField
            label="Сумма, USD"
            size="small"
            value={budgetAmount}
            onChange={(event) => setBudgetAmount(event.target.value)}
            inputMode="decimal"
            helperText="За всю неделю"
          />
          {budgetError && <Typography variant="body2" color="error">{budgetError}</Typography>}
          <Stack direction="row" spacing={1} justifyContent="flex-end">
            <Button size="small" onClick={closeBudgetPopover} disabled={budgetSaving}>Отмена</Button>
            <Button
              size="small"
              variant="contained"
              onClick={saveBudget}
              disabled={budgetSaving || !budgetCampaign.trim() || !budgetAmount.trim()}
              startIcon={budgetSaving ? <CircularProgress size={14} /> : undefined}
            >
              Сохранить
            </Button>
          </Stack>
        </Stack>
      </Popover>
    </TableContainer>
  );
};

export default MainReportTable;
