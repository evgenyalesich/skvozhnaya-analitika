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
import Box from "@mui/material/Box";
import Popover from "@mui/material/Popover";
import IconButton from "@mui/material/IconButton";
import Badge from "@mui/material/Badge";
import Tooltip from "@mui/material/Tooltip";
import AddIcon from "@mui/icons-material/Add";
import TuneIcon from "@mui/icons-material/Tune";
import ExportButtons from "./ExportButtons";
import KeyboardArrowDownIcon from "@mui/icons-material/KeyboardArrowDown";
import KeyboardArrowRightIcon from "@mui/icons-material/KeyboardArrowRight";
import TextField from "@mui/material/TextField";
import Button from "@mui/material/Button";
import Autocomplete from "@mui/material/Autocomplete";
import Select from "@mui/material/Select";
import MenuItem from "@mui/material/MenuItem";
import FormControl from "@mui/material/FormControl";
import InputLabel from "@mui/material/InputLabel";
import CircularProgress from "@mui/material/CircularProgress";
import FormGroup from "@mui/material/FormGroup";
import FormControlLabel from "@mui/material/FormControlLabel";
import Checkbox from "@mui/material/Checkbox";
import Divider from "@mui/material/Divider";
import { addDays, addWeeks, format, parseISO, isValid, startOfWeek } from "date-fns";
import { RoistatWeeklyRow } from "../hooks/useRoistatWeekly";
import { AdvertisingCompanyOption } from "../hooks/useAdvertisingCompanies";
import SyncedTableScroll from "./SyncedTableScroll";

interface WeeklyTableProps {
  rows: RoistatWeeklyRow[];
  loading: boolean;
  error?: string | null;
  selectedMonth?: string;
  onSelectedMonthChange?: (value: string) => void;
  companies?: AdvertisingCompanyOption[];
  onCreateBudget?: (weekStart: string, campaign: string, botKey: string | null, amount: number) => Promise<void>;
  userId?: number | null;
}

const STORAGE_KEY_PREFIX = "weekly_hidden_metrics_v1_";

const METRIC_COLUMN_KEYS = [
  "budget",
  "entered_all",
  "cpa_start",
  "almanah_starts",
  "direct_source_cnt",
  "cpa_almanah",
  "platform",
  "platform_cr",
  "cpa_platform",
  "started_learning",
  "started_course_cr",
  "cpa_learning",
  "completed_course",
  "course_cr",
  "cpa_course",
  "completed_mtt",
  "completed_spin",
  "completed_cash",
  "interview_reached",
  "interview_cr",
  "offer_received",
  "offer_cr",
  "contract_signed",
  "contract_cr",
  "cpa_contract",
  "contract_mtt",
  "contract_spin",
  "contract_cash",
  "distance_grinding",
  "learning",
  "base",
  "base_cr",
  "mtt",
  "spin",
  "cash",
  "not_started",
  "channel_subscribed",
  "saloon",
  "new_in_system",
  "old_in_system",
] as const;

const loadHiddenColumns = (userId?: number | null): Set<string> => {
  try {
    const key = STORAGE_KEY_PREFIX + (userId ?? "default");
    const stored = localStorage.getItem(key);
    if (stored) {
      const parsed = JSON.parse(stored);
      if (Array.isArray(parsed)) {
        return new Set<string>(parsed);
      }
    }
  } catch {}
  return new Set<string>();
};

const saveHiddenColumns = (userId: number | null | undefined, hidden: Set<string>) => {
  try {
    const key = STORAGE_KEY_PREFIX + (userId ?? "default");
    localStorage.setItem(key, JSON.stringify(Array.from(hidden)));
  } catch {}
};

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

const cpa = (budget: number, count: number) => {
  const b = toNumber(budget);
  const c = toNumber(count);
  if (!c || !b) return "—";
  return `$${(b / c).toFixed(2)}`;
};

const buildCr = (row: {
  almanah_starts: number; direct_source_cnt?: number; new_in_system: number; old_in_system: number;
  platform: number; learning: number; started_learning?: number;
  base?: number; mtt: number; spin: number; cash: number; not_started: number;
  channel_subscribed: number; saloon: number; completed_course: number;
  distance_grinding: number; contract_signed: number; budget: number;
  entered_all?: number; interview_reached?: number; offer_received?: number;
  completed_mtt?: number; completed_spin?: number; completed_cash?: number;
  contract_mtt?: number; contract_spin?: number; contract_cash?: number;
}) => ({
  platformCr: pct(toNumber(row.platform), toNumber(row.almanah_starts)),
  learningCr: pct(toNumber(row.learning), toNumber(row.platform)),
  startedCourseCr: pct(
    row.started_learning !== undefined
      ? toNumber(row.started_learning)
      : toNumber(row.base) + toNumber(row.mtt) + toNumber(row.spin) + toNumber(row.cash),
    toNumber(row.platform)
  ),
  baseCr: pct(toNumber(row.base), toNumber(row.learning)),
  mttCr: pct(toNumber(row.mtt), toNumber(row.learning)),
  spinCr: pct(toNumber(row.spin), toNumber(row.learning)),
  cashCr: pct(toNumber(row.cash), toNumber(row.learning)),
  notStartedCr: pct(toNumber(row.not_started), toNumber(row.platform)),
  channelCr: pct(toNumber(row.channel_subscribed), toNumber(row.almanah_starts)),
  saloonCr: pct(toNumber(row.saloon), toNumber(row.almanah_starts)),
  courseCr: pct(
    toNumber(row.completed_course),
    toNumber(row.started_learning ?? (toNumber(row.base) + toNumber(row.mtt) + toNumber(row.spin) + toNumber(row.cash)))
  ),
  distanceCr: pct(toNumber(row.distance_grinding), toNumber(row.completed_course)),
  contractCr: pct(toNumber(row.contract_signed), toNumber(row.completed_course)),
  interviewCr: pct(toNumber(row.interview_reached ?? 0), toNumber(row.started_learning ?? 0)),
  offerCr: pct(toNumber(row.offer_received ?? 0), toNumber(row.interview_reached ?? 0)),
  // CPA
  cpaStart: cpa(row.budget, row.entered_all ?? row.almanah_starts),
  cpaAlmanah: cpa(row.budget, row.almanah_starts),
  cpaPlatform: cpa(row.budget, row.platform),
  cpaLearning: cpa(row.budget, row.started_learning ?? 0),
  cpaCourse: cpa(row.budget, row.completed_course),
  cpaContract: cpa(row.budget, row.contract_signed),
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

const sumStartedCourse = (row: { base?: number; mtt: number; spin: number; cash: number }) =>
  toNumber(row.base) + toNumber(row.mtt) + toNumber(row.spin) + toNumber(row.cash);

const COMPACT_CELL_SX = {
  px: 0.5,
  py: 0.35,
  whiteSpace: "nowrap",
  fontSize: "0.78rem",
  borderBottom: "1px solid var(--app-table-divider)",
};

const getCompletedWeekEnd = () => addDays(startOfWeek(new Date(), { weekStartsOn: 1 }), -1);

type TotalsRow = {
  almanah_starts: number; direct_source_cnt: number; new_in_system: number; old_in_system: number;
  platform: number; learning: number; started_learning: number;
  base: number; mtt: number; spin: number; cash: number; not_started: number;
  channel_subscribed: number; saloon: number; completed_course: number;
  distance_grinding: number; contract_signed: number; budget: number;
  entered_all: number; interview_reached: number; offer_received: number;
  completed_mtt: number; completed_spin: number; completed_cash: number;
  contract_mtt: number; contract_spin: number; contract_cash: number;
};

const TOTALS_KEYS: (keyof TotalsRow)[] = [
  "almanah_starts","direct_source_cnt","new_in_system","old_in_system","platform","learning","started_learning",
  "base","mtt","spin","cash","not_started","channel_subscribed","saloon",
  "completed_course","distance_grinding","contract_signed","budget",
  "entered_all","interview_reached","offer_received",
  "completed_mtt","completed_spin","completed_cash",
  "contract_mtt","contract_spin","contract_cash",
];

const calcMean = (rows: RoistatWeeklyRow[]): TotalsRow => {
  if (!rows.length) return {} as TotalsRow;
  const sum = rows.reduce((acc, r) => {
    TOTALS_KEYS.forEach((k) => { (acc as any)[k] = ((acc as any)[k] || 0) + toNumber((r as any)[k]); });
    return acc;
  }, {} as TotalsRow);
  TOTALS_KEYS.forEach((k) => { (sum as any)[k] = (sum as any)[k] / rows.length; });
  return sum;
};

const calcMedian = (rows: RoistatWeeklyRow[]): TotalsRow => {
  if (!rows.length) return {} as TotalsRow;
  const result = {} as TotalsRow;
  TOTALS_KEYS.forEach((k) => {
    const vals = rows.map((r) => toNumber((r as any)[k])).sort((a, b) => a - b);
    const mid = Math.floor(vals.length / 2);
    (result as any)[k] = vals.length % 2 !== 0 ? vals[mid] : (vals[mid - 1] + vals[mid]) / 2;
  });
  return result;
};

const buildWeeklyRange = (rows: RoistatWeeklyRow[]) => {
  const parsed = rows
    .map((row) => safeParse(row.week_start))
    .filter((date): date is Date => date !== null)
    .sort((a, b) => a.getTime() - b.getTime());
  if (!parsed.length) {
    return [];
  }
  const start = startOfWeek(parsed[0], { weekStartsOn: 1 });
  const lastCompletedWeek = startOfWeek(getCompletedWeekEnd(), { weekStartsOn: 1 });
  const end = parsed[parsed.length - 1] > lastCompletedWeek ? lastCompletedWeek : startOfWeek(parsed[parsed.length - 1], { weekStartsOn: 1 });
  const weeks: Date[] = [];
  for (let cursor = start; cursor <= end; cursor = addWeeks(cursor, 1)) {
    weeks.push(cursor);
  }
  return weeks;
};

const safeParse = (value: string) => {
  try {
    const dt = parseISO(value);
    return isValid(dt) ? dt : null;
  } catch {
    return null;
  }
};

const renderStatusCount = (key: "new_in_system" | "old_in_system", value: unknown) => {
  const color = key === "new_in_system" ? "var(--app-chip-success)" : "var(--app-chip-warning)";
  return (
    <Box component="span" sx={{ color, fontWeight: 700 }}>
      {displayNumber(value)}
    </Box>
  );
};

const WeeklyTable: React.FC<WeeklyTableProps> = ({
  rows,
  loading,
  error,
  selectedMonth: controlledSelectedMonth,
  onSelectedMonthChange,
  companies = [],
  onCreateBudget,
  userId,
}) => {
  const [internalMonth, setInternalMonth] = useState<string>("all");
  const [expandedMonths, setExpandedMonths] = useState<Set<string>>(
    () => new Set([format(new Date(), "yyyy-MM")])
  );
  const [showStats, setShowStats] = useState(false);

  const toggleMonth = (monthKey: string) => {
    setExpandedMonths((prev) => {
      const next = new Set(prev);
      if (next.has(monthKey)) next.delete(monthKey);
      else next.add(monthKey);
      return next;
    });
  };

  const [popoverAnchor, setPopoverAnchor] = useState<HTMLElement | null>(null);
  const [popoverWeekStart, setPopoverWeekStart] = useState<string>("");
  const [popoverCampaign, setPopoverCampaign] = useState("");
  const [popoverBot, setPopoverBot] = useState("");
  const [popoverAmount, setPopoverAmount] = useState("");
  const [popoverSaving, setPopoverSaving] = useState(false);
  const [popoverError, setPopoverError] = useState<string | null>(null);
  const [columnsAnchor, setColumnsAnchor] = useState<HTMLElement | null>(null);
  const [hiddenColumns, setHiddenColumns] = useState<Set<string>>(() => loadHiddenColumns(userId));

  React.useEffect(() => {
    setHiddenColumns(loadHiddenColumns(userId));
  }, [userId]);

  const companyOptions = useMemo(() => companies.map((c) => c.company_name).filter(Boolean), [companies]);
  const selectedCompany = companies.find((c) => c.company_name === popoverCampaign);
  const botOptions = selectedCompany?.bot_keys || [];

  const handleOpenPopover = (el: HTMLElement, weekStart: string) => {
    setPopoverAnchor(el);
    setPopoverWeekStart(weekStart);
    setPopoverCampaign("");
    setPopoverBot("");
    setPopoverAmount("");
    setPopoverError(null);
  };

  const handleClosePopover = () => {
    setPopoverAnchor(null);
  };

  const handleSaveBudget = async () => {
    if (!popoverCampaign.trim() || !popoverAmount || !onCreateBudget) return;
    const amount = Number(popoverAmount.replace(",", ".").replace(/\s/g, ""));
    if (!Number.isFinite(amount) || amount <= 0) return;
    setPopoverSaving(true);
    setPopoverError(null);
    try {
      await onCreateBudget(popoverWeekStart, popoverCampaign.trim(), popoverBot || null, amount);
      handleClosePopover();
    } catch (err: any) {
      setPopoverError(err?.response?.data?.detail || err?.message || "Ошибка сохранения");
    } finally {
      setPopoverSaving(false);
    }
  };
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
    const sourceByWeek = new Map(sorted.map((row) => [row.week_start, row]));
    const bucket = new Map<string, RoistatWeeklyRow[]>();
    buildWeeklyRange(sorted).forEach((weekStart) => {
      const key = format(weekStart, "yyyy-MM");
      const weekKey = format(weekStart, "yyyy-MM-dd");
      const current = bucket.get(key) || [];
      current.push(
        sourceByWeek.get(weekKey) ?? {
          week_start: weekKey,
          almanah_starts: 0, direct_source_cnt: 0, new_in_system: 0, old_in_system: 0,
          platform: 0, learning: 0, started_learning: 0,
          base: 0, mtt: 0, spin: 0, cash: 0, not_started: 0,
          channel_subscribed: 0, saloon: 0, completed_course: 0, completed_base: 0,
          distance_grinding: 0, contract_signed: 0, budget: 0,
          entered_all: 0, interview_reached: 0, offer_received: 0,
          completed_mtt: 0, completed_spin: 0, completed_cash: 0,
          contract_mtt: 0, contract_spin: 0, contract_cash: 0,
        }
      );
      bucket.set(key, current);
    });
    return bucket;
  }, [rows]);

  const monthKeys = useMemo(() => Array.from(grouped.keys()).sort(), [grouped]);
  const visibleMonthKeys = useMemo(() => {
    if (selectedMonth === "all") return monthKeys;
    return monthKeys.filter((m) => m === selectedMonth);
  }, [monthKeys, selectedMonth]);

  const metricColumns = [
    { key: "budget", label: "Бюджет $" },
    { key: "entered_all", label: "Старт в бота" },
    { key: "cpa_start", label: "$ старта" },
    { key: "almanah_starts", label: "Рег. Альманах" },
    { key: "direct_source_cnt", label: "Прямой источник" },
    { key: "cpa_almanah", label: "$ Альманах" },
    { key: "platform", label: "Рег. на ПХ (ph)" },
    { key: "platform_cr", label: "% ПХ" },
    { key: "cpa_platform", label: "$ ПХ" },
    { key: "started_learning", label: "Старт обучения" },
    { key: "started_course_cr", label: "% обуч." },
    { key: "cpa_learning", label: "$ начала курса" },
    { key: "completed_course", label: "Прошли курс" },
    { key: "course_cr", label: "% курса" },
    { key: "cpa_course", label: "$ курса" },
    { key: "completed_mtt", label: "МТТ прошли" },
    { key: "completed_spin", label: "SPIN прошли" },
    { key: "completed_cash", label: "КЕШ прошли" },
    { key: "interview_reached", label: "Назначено собеседование" },
    { key: "interview_cr", label: "% предофер" },
    { key: "offer_received", label: "Офер лид" },
    { key: "offer_cr", label: "% офер" },
    { key: "contract_signed", label: "Контракт" },
    { key: "contract_cr", label: "% контракт" },
    { key: "cpa_contract", label: "$ контракт" },
    { key: "contract_mtt", label: "МТТ контракт" },
    { key: "contract_spin", label: "SPIN контракт" },
    { key: "contract_cash", label: "КЕШ контракт" },
    { key: "distance_grinding", label: "Наигрыш дист." },
    { key: "learning", label: "Рег. на курс" },
    { key: "base", label: "BASE рег." },
    { key: "base_cr", label: "% BASE" },
    { key: "mtt", label: "МТТ рег." },
    { key: "spin", label: "SPIN рег." },
    { key: "cash", label: "КЕШ рег." },
    { key: "not_started", label: "Не начали" },
    { key: "channel_subscribed", label: "Подписки КД" },
    { key: "saloon", label: "Салун" },
    { key: "new_in_system", label: "Новые" },
    { key: "old_in_system", label: "Старые" },
  ] as const;

  const isVisible = (key: typeof METRIC_COLUMN_KEYS[number]) => !hiddenColumns.has(key);

  const toggleMetricColumn = (key: typeof METRIC_COLUMN_KEYS[number]) => {
    setHiddenColumns((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      saveHiddenColumns(userId, next);
      return next;
    });
  };

  const renderMetricCells = (values: Record<string, React.ReactNode>, commonSx?: object) =>
    metricColumns.map((column) =>
      isVisible(column.key) ? (
        <TableCell key={column.key} align="right" sx={commonSx}>
          {values[column.key] ?? "—"}
        </TableCell>
      ) : null
    );

  const getExportData = (): (string | number)[][] => {
    const headers = [
      "Период","Бюджет $","Старт в бота","$ старта","Рег. Альманах","Прямой источник","$ Альманах",
      "Рег. ПХ","% ПХ","$ ПХ","Старт обучения","% обуч.","$ начала курса",
      "Прошли курс","% курса","$ курса","МТТ прошли","SPIN прошли","КЕШ прошли",
      "Назначено собеседование","% предофер","Офер лид","% офер",
      "Контракт","% контракт","$ контракт","МТТ контракт","SPIN контракт","КЕШ контракт",
      "Наигрыш дист.","Рег. на курс","BASE рег.","% BASE","МТТ рег.","SPIN рег.","КЕШ рег.",
      "Не начали","Подписки КД","Салун","Новые","Старые",
    ];
    const allRows: (string | number)[][] = [];
    visibleMonthKeys.forEach((monthKey) => {
      const weekRows = grouped.get(monthKey) || [];
      weekRows.forEach((row) => {
        const dt = safeParse(row.week_start);
        const label = dt ? `${format(dt, "dd.MM")}–${format(addDays(dt, 6), "dd.MM.yyyy")}` : row.week_start;
        const cr = buildCr(row);
        allRows.push([
          label,
          row.budget, row.entered_all, cr.cpaStart,
          row.almanah_starts, row.direct_source_cnt, cr.cpaAlmanah,
          row.platform, cr.platformCr, cr.cpaPlatform,
          row.started_learning, cr.startedCourseCr, cr.cpaLearning,
          row.completed_course, cr.courseCr, cr.cpaCourse,
          row.completed_mtt, row.completed_spin, row.completed_cash,
          row.interview_reached, cr.interviewCr,
          row.offer_received, cr.offerCr,
          row.contract_signed, cr.contractCr, cr.cpaContract,
          row.contract_mtt, row.contract_spin, row.contract_cash,
          row.distance_grinding, row.learning,
          row.base, cr.baseCr,
          row.mtt, row.spin, row.cash,
          row.not_started, row.channel_subscribed, row.saloon,
          row.new_in_system, row.old_in_system,
        ]);
      });
    });
    return [headers, ...allRows];
  };

  return (
    <Paper
      sx={{
        mt: 2,
        p: 2,
        borderRadius: "24px",
        border: "1px solid var(--app-shell-border)",
        background: "var(--app-panel-bg)",
        boxShadow: "var(--app-shell-shadow)",
      }}
    >
      <Stack direction="row" justifyContent="space-between" alignItems="center" mb={1}>
        <Stack direction="row" spacing={1} alignItems="center">
          <Typography variant="h6">Weekly</Typography>
          <ExportButtons
            getData={getExportData}
            baseName={`weekly_${selectedMonth}`}
            sheetName="Weekly"
            disabled={!rows.length}
          />
          <Tooltip title="Настройка столбцов">
            <Button
              size="small"
              variant={hiddenColumns.size > 0 ? "contained" : "outlined"}
              onClick={(event) => setColumnsAnchor(event.currentTarget)}
              startIcon={
                <Badge
                  badgeContent={hiddenColumns.size > 0 ? hiddenColumns.size : 0}
                  color="warning"
                  invisible={hiddenColumns.size === 0}
                >
                  <TuneIcon fontSize="small" />
                </Badge>
              }
              sx={{ textTransform: "none", fontSize: "0.75rem", px: 1.5 }}
            >
              Столбцы
            </Button>
          </Tooltip>
          <Box
            component="button"
            onClick={() => setShowStats((v) => !v)}
            sx={{
              px: 1.25,
              py: 0.55,
              borderRadius: "12px",
              border: "1px solid var(--app-table-divider)",
              background: showStats ? "linear-gradient(135deg, var(--c-blue-bg), rgba(37, 99, 235, 0.18))" : "var(--app-panel-muted)",
              color: "var(--c-ink)",
              cursor: "pointer",
              fontSize: "0.75rem",
              fontWeight: 700,
            }}
          >
            {showStats ? "Скрыть среднее/медиану" : "Показать среднее/медиану"}
          </Box>
        </Stack>
        <Box
          component="select"
          value={selectedMonth}
          onChange={(event) => setSelectedMonth(String(event.target.value))}
          className="app-native-select"
          style={{ minWidth: 220 }}
        >
          <option value="all">Все месяцы</option>
          {monthKeys.map((month) => (
            <option key={month} value={month}>
              {monthLabel(month)}
            </option>
          ))}
        </Box>
      </Stack>
      {loading && <LinearProgress sx={{ mb: 1 }} />}
      {error && (
        <Typography variant="body2" color="error" mb={1}>
          {error}
        </Typography>
      )}
      <Popover
        open={Boolean(columnsAnchor)}
        anchorEl={columnsAnchor}
        onClose={() => setColumnsAnchor(null)}
        anchorOrigin={{ vertical: "bottom", horizontal: "right" }}
        transformOrigin={{ vertical: "top", horizontal: "right" }}
      >
        <Stack sx={{ p: 1.5, maxHeight: 520, overflow: "auto", minWidth: 260 }}>
          <Stack direction="row" justifyContent="space-between" alignItems="center" mb={0.5}>
            <Typography variant="caption" color="text.secondary" fontWeight={600}>
              Метрики ({metricColumns.length - hiddenColumns.size}/{metricColumns.length})
            </Typography>
            <Stack direction="row" spacing={0.5}>
              <Typography
                variant="caption"
                color="primary"
                sx={{ cursor: "pointer" }}
                onClick={() => {
                  const none = new Set<string>();
                  setHiddenColumns(none);
                  saveHiddenColumns(userId, none);
                }}
              >
                Все
              </Typography>
              <Typography variant="caption" color="text.secondary">/</Typography>
              <Typography
                variant="caption"
                color="primary"
                sx={{ cursor: "pointer" }}
                onClick={() => {
                  const all = new Set<string>(METRIC_COLUMN_KEYS);
                  setHiddenColumns(all);
                  saveHiddenColumns(userId, all);
                }}
              >
                Ни одной
              </Typography>
            </Stack>
          </Stack>
          <Divider sx={{ mb: 0.5 }} />
          <FormGroup>
            {metricColumns.map((column) => (
              <FormControlLabel
                key={column.key}
                control={
                  <Checkbox
                    size="small"
                    checked={!hiddenColumns.has(column.key)}
                    onChange={() => toggleMetricColumn(column.key)}
                    sx={{ py: 0.25 }}
                  />
                }
                label={<Typography variant="body2">{column.label}</Typography>}
                sx={{ mx: 0 }}
              />
            ))}
          </FormGroup>
        </Stack>
      </Popover>
      <SyncedTableScroll maxHeight="calc(100vh - 280px)" topOffset={0}>
      <TableContainer>
        <Table size="small" sx={{
          "& .MuiTableCell-root": COMPACT_CELL_SX,
          "& .MuiTableHead-root .MuiTableCell-root": {
            backgroundColor: "var(--app-table-head-bg)",
            color: "var(--c-ink2)",
            whiteSpace: "normal",
            wordBreak: "break-word",
            lineHeight: 1.2,
            verticalAlign: "bottom",
            maxWidth: 80,
            fontWeight: 700,
          },
          "& .MuiTableBody-root .MuiTableRow-root:nth-of-type(even)": {
            backgroundColor: "var(--app-table-row-alt)",
          },
          "& .MuiTableBody-root .MuiTableRow-root:hover": {
            backgroundColor: "var(--app-table-row-hover)",
          },
        }}>
          <TableHead>
            <TableRow>
              <TableCell>Период</TableCell>
              {metricColumns.map((column) =>
                isVisible(column.key) ? (
                  <TableCell key={column.key} align="right">{column.label}</TableCell>
                ) : null
              )}
            </TableRow>
          </TableHead>
          <TableBody>
            {visibleMonthKeys.map((monthKey) => {
              const monthRows = grouped.get(monthKey) || [];
              const monthTotals = monthRows.reduce(
                (acc, row) => ({
                  almanah_starts: acc.almanah_starts + toNumber(row.almanah_starts),
                  direct_source_cnt: acc.direct_source_cnt + toNumber(row.direct_source_cnt),
                  new_in_system: acc.new_in_system + toNumber(row.new_in_system),
                  old_in_system: acc.old_in_system + toNumber(row.old_in_system),
                  platform: acc.platform + toNumber(row.platform),
                  learning: acc.learning + toNumber(row.learning),
                  started_learning: acc.started_learning + toNumber(row.started_learning),
                  base: acc.base + toNumber(row.base),
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
                  entered_all: acc.entered_all + toNumber(row.entered_all),
                  interview_reached: acc.interview_reached + toNumber(row.interview_reached),
                  offer_received: acc.offer_received + toNumber(row.offer_received),
                  completed_mtt: acc.completed_mtt + toNumber(row.completed_mtt),
                  completed_spin: acc.completed_spin + toNumber(row.completed_spin),
                  completed_cash: acc.completed_cash + toNumber(row.completed_cash),
                  contract_mtt: acc.contract_mtt + toNumber(row.contract_mtt),
                  contract_spin: acc.contract_spin + toNumber(row.contract_spin),
                  contract_cash: acc.contract_cash + toNumber(row.contract_cash),
                }),
                {
                  almanah_starts: 0, direct_source_cnt: 0, new_in_system: 0, old_in_system: 0,
                  platform: 0, learning: 0, started_learning: 0,
                  base: 0, mtt: 0, spin: 0, cash: 0, not_started: 0,
                  channel_subscribed: 0, saloon: 0, completed_course: 0,
                  distance_grinding: 0, contract_signed: 0, budget: 0,
                  entered_all: 0, interview_reached: 0, offer_received: 0,
                  completed_mtt: 0, completed_spin: 0, completed_cash: 0,
                  contract_mtt: 0, contract_spin: 0, contract_cash: 0,
                }
              );
              const isExpanded = expandedMonths.has(monthKey);
              const mean = showStats ? calcMean(monthRows) : null;
              const median = showStats ? calcMedian(monthRows) : null;

              const renderStatRow = (label: string, data: TotalsRow, bgColor: string) => {
                const cr = buildCr(data);
                const f1 = (v: number) => v.toFixed(1);
                return (
                    <TableRow sx={{ backgroundColor: bgColor }}>
                    <TableCell sx={{ fontStyle: "italic", pl: 3 }}>{label}</TableCell>
                    {renderMetricCells(
                      {
                        budget: f1(data.budget),
                        entered_all: f1(data.entered_all),
                        cpa_start: cr.cpaStart,
                        almanah_starts: f1(data.almanah_starts),
                        direct_source_cnt: f1(data.direct_source_cnt),
                        cpa_almanah: cr.cpaAlmanah,
                        platform: f1(data.platform),
                        platform_cr: cr.platformCr,
                        cpa_platform: cr.cpaPlatform,
                        started_learning: f1(data.started_learning),
                        started_course_cr: cr.startedCourseCr,
                        cpa_learning: cr.cpaLearning,
                        completed_course: f1(data.completed_course),
                        course_cr: cr.courseCr,
                        cpa_course: cr.cpaCourse,
                        completed_mtt: f1(data.completed_mtt),
                        completed_spin: f1(data.completed_spin),
                        completed_cash: f1(data.completed_cash),
                        interview_reached: f1(data.interview_reached),
                        interview_cr: cr.interviewCr,
                        offer_received: f1(data.offer_received),
                        offer_cr: cr.offerCr,
                        contract_signed: f1(data.contract_signed),
                        contract_cr: cr.contractCr,
                        cpa_contract: cr.cpaContract,
                        contract_mtt: f1(data.contract_mtt),
                        contract_spin: f1(data.contract_spin),
                        contract_cash: f1(data.contract_cash),
                        distance_grinding: f1(data.distance_grinding),
                        learning: f1(data.learning),
                        base: f1(data.base),
                        base_cr: cr.baseCr,
                        mtt: f1(data.mtt),
                        spin: f1(data.spin),
                        cash: f1(data.cash),
                        not_started: f1(data.not_started),
                        channel_subscribed: f1(data.channel_subscribed),
                        saloon: f1(data.saloon),
                        new_in_system: <Box component="span" sx={{ color: "var(--app-chip-success)" }}>{f1(data.new_in_system)}</Box>,
                        old_in_system: <Box component="span" sx={{ color: "var(--app-chip-warning)" }}>{f1(data.old_in_system)}</Box>,
                      },
                      { fontStyle: "italic" }
                    )}
                  </TableRow>
                );
              };

              return (
                <React.Fragment key={monthKey}>
                  {(() => {
                    const cr = buildCr(monthTotals);
                    const startedCourse = toNumber(
                      typeof monthTotals.started_learning === "number"
                        ? monthTotals.started_learning
                        : sumStartedCourse(monthTotals)
                    );
                    const B = 700;
                    return (
                      <TableRow
                        sx={{ backgroundColor: "var(--app-table-month-bg)", cursor: "pointer", userSelect: "none" }}
                        onClick={() => toggleMonth(monthKey)}
                      >
                        <TableCell sx={{ fontWeight: B }}>
                          <Stack direction="row" alignItems="center" spacing={0.5}>
                            {isExpanded ? <KeyboardArrowDownIcon fontSize="small" /> : <KeyboardArrowRightIcon fontSize="small" />}
                            <span>{monthLabel(monthKey)}</span>
                          </Stack>
                        </TableCell>
                        {renderMetricCells(
                          {
                            budget: Number(monthTotals.budget || 0).toFixed(2),
                            entered_all: displayNumber(monthTotals.entered_all),
                            cpa_start: cr.cpaStart,
                            almanah_starts: displayNumber(monthTotals.almanah_starts),
                            direct_source_cnt: displayNumber(monthTotals.direct_source_cnt),
                            cpa_almanah: cr.cpaAlmanah,
                            platform: displayNumber(monthTotals.platform),
                            platform_cr: cr.platformCr,
                            cpa_platform: cr.cpaPlatform,
                            started_learning: startedCourse,
                            started_course_cr: cr.startedCourseCr,
                            cpa_learning: cr.cpaLearning,
                            completed_course: displayNumber(monthTotals.completed_course),
                            course_cr: cr.courseCr,
                            cpa_course: cr.cpaCourse,
                            completed_mtt: displayNumber(monthTotals.completed_mtt),
                            completed_spin: displayNumber(monthTotals.completed_spin),
                            completed_cash: displayNumber(monthTotals.completed_cash),
                            interview_reached: displayNumber(monthTotals.interview_reached),
                            interview_cr: cr.interviewCr,
                            offer_received: displayNumber(monthTotals.offer_received),
                            offer_cr: cr.offerCr,
                            contract_signed: displayNumber(monthTotals.contract_signed),
                            contract_cr: cr.contractCr,
                            cpa_contract: cr.cpaContract,
                            contract_mtt: displayNumber(monthTotals.contract_mtt),
                            contract_spin: displayNumber(monthTotals.contract_spin),
                            contract_cash: displayNumber(monthTotals.contract_cash),
                            distance_grinding: displayNumber(monthTotals.distance_grinding),
                            learning: displayNumber(monthTotals.learning),
                            base: displayNumber(monthTotals.base),
                            base_cr: cr.baseCr,
                            mtt: displayNumber(monthTotals.mtt),
                            spin: displayNumber(monthTotals.spin),
                            cash: displayNumber(monthTotals.cash),
                            not_started: displayNumber(monthTotals.not_started),
                            channel_subscribed: displayNumber(monthTotals.channel_subscribed),
                            saloon: displayNumber(monthTotals.saloon),
                            new_in_system: renderStatusCount("new_in_system", monthTotals.new_in_system),
                            old_in_system: renderStatusCount("old_in_system", monthTotals.old_in_system),
                          },
                          { fontWeight: B }
                        )}
                      </TableRow>
                    );
                  })()}
                  {showStats && mean && renderStatRow("Среднее", mean, "var(--app-table-summary-bg)")}
                  {showStats && median && renderStatRow("Медиана", median, "var(--app-table-summary-bg)")}
                  {isExpanded && monthRows.map((row) => (
                    (() => {
                      const cr = buildCr(row);
                      const startedCourse = toNumber(
                        typeof row.started_learning === "number"
                          ? row.started_learning
                          : sumStartedCourse(row)
                      );
                      const start = safeParse(row.week_start);
                      if (!start) {
                        return null;
                      }
                      const end = addDays(start, 6);
                      return (
                        <TableRow key={row.week_start}>
                          <TableCell sx={{ pl: 3 }}>{`${format(start, "dd.MM")} - ${format(end, "dd.MM")}`}</TableCell>
                          {renderMetricCells({
                            budget:
                              toNumber(row.budget) > 0 ? (
                                Number(row.budget).toFixed(2)
                              ) : onCreateBudget ? (
                                <IconButton size="small" onClick={(e) => handleOpenPopover(e.currentTarget, row.week_start)}>
                                  <AddIcon fontSize="small" />
                                </IconButton>
                              ) : "—",
                            entered_all: displayNumber(row.entered_all),
                            cpa_start: cr.cpaStart,
                            almanah_starts: displayNumber(row.almanah_starts),
                            direct_source_cnt: displayNumber(row.direct_source_cnt),
                            cpa_almanah: cr.cpaAlmanah,
                            platform: displayNumber(row.platform),
                            platform_cr: cr.platformCr,
                            cpa_platform: cr.cpaPlatform,
                            started_learning: startedCourse,
                            started_course_cr: cr.startedCourseCr,
                            cpa_learning: cr.cpaLearning,
                            completed_course: displayNumber(row.completed_course),
                            course_cr: cr.courseCr,
                            cpa_course: cr.cpaCourse,
                            completed_mtt: displayNumber(row.completed_mtt),
                            completed_spin: displayNumber(row.completed_spin),
                            completed_cash: displayNumber(row.completed_cash),
                            interview_reached: displayNumber(row.interview_reached),
                            interview_cr: cr.interviewCr,
                            offer_received: displayNumber(row.offer_received),
                            offer_cr: cr.offerCr,
                            contract_signed: displayNumber(row.contract_signed),
                            contract_cr: cr.contractCr,
                            cpa_contract: cr.cpaContract,
                            contract_mtt: displayNumber(row.contract_mtt),
                            contract_spin: displayNumber(row.contract_spin),
                            contract_cash: displayNumber(row.contract_cash),
                            distance_grinding: displayNumber(row.distance_grinding),
                            learning: displayNumber(row.learning),
                            base: displayNumber(row.base),
                            base_cr: cr.baseCr,
                            mtt: displayNumber(row.mtt),
                            spin: displayNumber(row.spin),
                            cash: displayNumber(row.cash),
                            not_started: displayNumber(row.not_started),
                            channel_subscribed: displayNumber(row.channel_subscribed),
                            saloon: displayNumber(row.saloon),
                            new_in_system: renderStatusCount("new_in_system", row.new_in_system),
                            old_in_system: renderStatusCount("old_in_system", row.old_in_system),
                          })}
                        </TableRow>
                      );
                    })()
                  ))}
                </React.Fragment>
              );
            })}
            {!rows.length && !loading && (
              <TableRow>
                <TableCell colSpan={metricColumns.filter((column) => isVisible(column.key)).length + 1}>Нет данных</TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </TableContainer>
      </SyncedTableScroll>
      <Popover
        open={Boolean(popoverAnchor)}
        anchorEl={popoverAnchor}
        onClose={handleClosePopover}
        anchorOrigin={{ vertical: "bottom", horizontal: "right" }}
        transformOrigin={{ vertical: "top", horizontal: "right" }}
      >
        <Stack spacing={2} sx={{ p: 2, minWidth: 260 }}>
          <Typography variant="subtitle2">
            Бюджет за неделю{popoverWeekStart ? ` (${format(parseISO(popoverWeekStart), "dd.MM")} – ${format(addDays(parseISO(popoverWeekStart), 6), "dd.MM")})` : ""}
          </Typography>
          <Autocomplete
            freeSolo
            options={companyOptions}
            inputValue={popoverCampaign}
            onInputChange={(_, value) => { setPopoverCampaign(value); setPopoverBot(""); }}
            renderInput={(params) => <TextField {...params} label="РК" size="small" />}
          />
          {botOptions.length > 0 && (
            <FormControl size="small">
              <InputLabel id="pw-bot-label">Бот (опц.)</InputLabel>
              <Select
                labelId="pw-bot-label"
                label="Бот (опц.)"
                value={popoverBot}
                onChange={(e) => setPopoverBot(e.target.value)}
              >
                <MenuItem value=""><em>Все боты РК</em></MenuItem>
                {botOptions.map((b) => <MenuItem key={b} value={b}>{b}</MenuItem>)}
              </Select>
            </FormControl>
          )}
          <TextField
            label="Сумма, USD"
            size="small"
            value={popoverAmount}
            onChange={(e) => setPopoverAmount(e.target.value)}
            inputMode="decimal"
            helperText="За всю неделю (будет поделена на 7 дней)"
          />
          {popoverError && (
            <Typography variant="body2" color="error">{popoverError}</Typography>
          )}
          <Stack direction="row" spacing={1} justifyContent="flex-end">
            <Button size="small" onClick={handleClosePopover} disabled={popoverSaving}>
              Отмена
            </Button>
            <Button
              size="small"
              variant="contained"
              onClick={handleSaveBudget}
              disabled={popoverSaving || !popoverCampaign.trim() || !popoverAmount}
              startIcon={popoverSaving ? <CircularProgress size={14} /> : undefined}
            >
              Сохранить
            </Button>
          </Stack>
        </Stack>
      </Popover>
    </Paper>
  );
};

export default WeeklyTable;
