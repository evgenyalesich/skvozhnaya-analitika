// Таблица сырых пользователей (raw_bot_users).
// Колонки: все поля воронки + UTM + first/last touch. Пагинация + сортировка + 30+ column-фильтров.
// Экспорт в CSV через handleExport в OverviewPage (не внутри компонента).
import React from "react";
import Box from "@mui/material/Box";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableContainer from "@mui/material/TableContainer";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import Paper from "@mui/material/Paper";
import Typography from "@mui/material/Typography";
import Stack from "@mui/material/Stack";
import Chip from "@mui/material/Chip";
import TablePagination from "@mui/material/TablePagination";
import TableSortLabel from "@mui/material/TableSortLabel";
import TextField from "@mui/material/TextField";
import ToggleButton from "@mui/material/ToggleButton";
import ToggleButtonGroup from "@mui/material/ToggleButtonGroup";
import Autocomplete from "@mui/material/Autocomplete";
import Select from "@mui/material/Select";
import MenuItem from "@mui/material/MenuItem";
import IconButton from "@mui/material/IconButton";
import Badge from "@mui/material/Badge";
import Button from "@mui/material/Button";
import Tooltip from "@mui/material/Tooltip";
import Popover from "@mui/material/Popover";
import Link from "@mui/material/Link";
import FormGroup from "@mui/material/FormGroup";
import FormControlLabel from "@mui/material/FormControlLabel";
import Checkbox from "@mui/material/Checkbox";
import Divider from "@mui/material/Divider";
import TuneIcon from "@mui/icons-material/Tune";
import { RawColumnFilters } from "../hooks/useReports";
import { BotSelectOption } from "./FilterPanel";
import SyncedTableScroll from "./SyncedTableScroll";
import ExportButtons from "./ExportButtons";
import { useColumnResize } from "../hooks/useColumnResize";
import EmptyState from "./ui/EmptyState";
import TableSkeleton from "./ui/TableSkeleton";

export interface RawUsersTableProps {
  users: Array<Record<string, any>>;
  total: number;
  loading: boolean;
  page: number;
  pageSize: number;
  sortBy: string;
  sortDirection: "asc" | "desc";
  onSort: (field: string) => void;
  onPageChange: (event: unknown, page: number) => void;
  onRowsPerPageChange: (event: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => void;
  filters: RawColumnFilters;
  onFilterChange: (key: keyof RawColumnFilters, value: any) => void;
  botOptions: BotSelectOption[];
  companyOptions: string[];
  utmSourceOptions: string[];
  utmCampaignOptions: string[];
  utmMediumOptions: string[];
  utmContentOptions: string[];
  utmTermOptions: string[];
  userId?: number | null;
}

// v2: храним СКРЫТЫЕ колонки (а не видимые) — новые колонки всегда показываются по умолчанию
const STORAGE_KEY_PREFIX = "raw_hidden_cols_v2_";
const COL_WIDTHS_KEY_PREFIX = "raw_col_widths_v1_";

// Legacy helpers kept only for hidden columns; resize logic is handled by useColumnResize hook.

const ALL_COLUMN_KEYS = [
  "id", "bot_key", "tg_user_id", "username", "pokerhub_user_id", "created_at", "freshness_status",
  "first_seen_at_system", "first_seen_at_bot", "user_block",
  "utm_source", "utm_campaign", "platform_utm_source", "platform_utm_campaign", "first_touch_bot", "first_touch_campaign",
  "last_touch_bot", "last_touch_campaign", "utm_medium", "utm_content", "utm_term",
  "platform_utm_medium", "platform_utm_content", "platform_utm_term",
  "referer", "raw_link", "bot_raw", "ph_raw", "last_activity", "ph_group",
  "advertising_company", "budget", "ingested_at",
  "converted_to_lead", "registered_platform", "platform_registered_at",
  "started_learning", "learn_start_date", "completed_course", "completed_course_at", "course_duration_days",
  "interview_reached", "interview_reached_status", "interview_passed", "interview_passed_status",
  "offer_received", "offer_received_status", "contract_signed", "contract_signed_status",
  "interview_reached_at", "interview_passed_at", "offer_received_at", "contract_signed_at",
  "distance_grinding", "channel_subscribed", "community_member", "community_member_status",
  "team_member", "internal_status",
];

// Загружаем множество СКРЫТЫХ колонок. По умолчанию — ничего не скрыто.
const loadHiddenColumns = (userId?: number | null): Set<string> => {
  try {
    const key = STORAGE_KEY_PREFIX + (userId ?? "default");
    const stored = localStorage.getItem(key);
    if (stored) {
      const parsed = JSON.parse(stored);
      if (Array.isArray(parsed)) return new Set<string>(parsed);
    }
  } catch {}
  return new Set<string>(); // ничего не скрыто
};

const saveHiddenColumns = (userId: number | null | undefined, hidden: Set<string>) => {
  try {
    const key = STORAGE_KEY_PREFIX + (userId ?? "default");
    localStorage.setItem(key, JSON.stringify(Array.from(hidden)));
  } catch {}
};

type ColAlign = "left" | "right" | "center" | "inherit" | "justify";

const sortableColumns = new Set([
  "created_at",
  "tg_user_id",
  "bot_key",
  "budget",
  "utm_source",
  "utm_campaign",
  "utm_medium",
  "utm_content",
  "utm_term",
  "advertising_company",
  "ingested_at",
]);

const HEADER_ROW_HEIGHT = 44;
const stickyHeaderCellSx = (top: number, zIndex: number, backgroundColor = "var(--app-table-head-bg)") => ({
  position: "sticky",
  top,
  backgroundColor,
  zIndex,
  borderBottom: "1px solid var(--app-table-divider)",
});

const formatBool = (value: boolean | null | undefined) => {
  if (value === null || value === undefined) {
    return (
      <Chip
        label="—"
        size="small"
        color="default"
        variant="outlined"
        sx={{ minWidth: 28, fontWeight: 700 }}
      />
    );
  }
  return value ? (
    <Chip
      label="✓"
      size="small"
      color="success"
      variant="filled"
      sx={{ minWidth: 28, fontWeight: 700 }}
    />
  ) : (
    <Chip
      label="✗"
      size="small"
      color="error"
      variant="filled"
      sx={{ minWidth: 28, fontWeight: 700 }}
    />
  );
};

const formatDate = (value: string | null | undefined) => {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  const pad = (v: number) => String(v).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(
    date.getHours()
  )}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`;
};

const prettifyLinkLabel = (value: string) => {
  try {
    const parsed = new URL(value);
    const params = Array.from(parsed.searchParams.keys());
    const path = parsed.pathname && parsed.pathname !== "/" ? parsed.pathname : "";
    const summary = params.length ? `?${params.slice(0, 2).join("&")}${params.length > 2 ? "&…" : ""}` : "";
    return `${parsed.hostname}${path}${summary}`;
  } catch {
    return value.length > 48 ? `${value.slice(0, 48)}…` : value;
  }
};

const renderLinkValue = (value: string | null | undefined) => {
  if (!value) {
    return "—";
  }
  const normalized = value.trim();
  if (!normalized || normalized.toLowerCase() === "none") {
    return "—";
  }
  const label = prettifyLinkLabel(normalized);
  return (
    <Tooltip title={normalized} placement="top-start">
      <Link
        href={normalized}
        target="_blank"
        rel="noopener noreferrer"
        underline="hover"
        color="info.light"
        sx={{
          display: "inline-block",
          maxWidth: "100%",
          overflow: "hidden",
          textOverflow: "ellipsis",
          whiteSpace: "nowrap",
          verticalAlign: "bottom",
          fontSize: "0.78rem",
        }}
      >
        {label}
      </Link>
    </Tooltip>
  );
};

const renderUserFreshness = (user: Record<string, any>) => {
  if (user.new_in_system) {
    return (
      <Chip
        label="Новый"
        size="small"
        color="success"
        variant="filled"
        sx={{ fontWeight: 700 }}
      />
    );
  }
  if (user.new_in_bot && user.old_in_system) {
    return (
      <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
        <Chip
          label="Новый в боте"
          size="small"
          color="info"
          variant="filled"
          sx={{ fontWeight: 700 }}
        />
        <Chip
          label="Старый в системе"
          size="small"
          color="warning"
          variant="filled"
          sx={{ fontWeight: 700 }}
        />
      </Stack>
    );
  }
  if (user.new_in_bot) {
    return (
      <Chip
        label="Новый в боте"
        size="small"
        color="info"
        variant="filled"
        sx={{ fontWeight: 700 }}
      />
    );
  }
  if (user.old_in_system) {
    return (
      <Chip
        label="Старый в системе"
        size="small"
        color="warning"
        variant="filled"
        sx={{ fontWeight: 700 }}
      />
    );
  }
  return "—";
};

const renderTriState = (
  value: boolean | null,
  onChange: (next: boolean | null) => void
) => (
  <ToggleButtonGroup
    size="small"
    exclusive
    value={value === null ? "all" : value ? "yes" : "no"}
    onChange={(_e, next) => {
      if (next === "yes") onChange(true);
      else if (next === "no") onChange(false);
      else onChange(null);
    }}
  >
    <ToggleButton value="all">Все</ToggleButton>
    <ToggleButton value="yes">✓</ToggleButton>
    <ToggleButton value="no">✗</ToggleButton>
  </ToggleButtonGroup>
);

const RawUsersTable: React.FC<RawUsersTableProps> = ({
  users,
  total,
  loading,
  page,
  pageSize,
  sortBy,
  sortDirection,
  onSort,
  onPageChange,
  onRowsPerPageChange,
  filters,
  onFilterChange,
  botOptions,
  companyOptions,
  utmSourceOptions,
  utmCampaignOptions,
  utmMediumOptions,
  utmContentOptions,
  utmTermOptions,
  userId,
}) => {
  const botLabelMap = React.useMemo(() => {
    const map = new Map<string, string>();
    botOptions.forEach((option) => map.set(option.value, option.label));
    return map;
  }, [botOptions]);
  const getBaseLabel = React.useCallback((user: RawUserModel) => {
    if (user.source_category === "direct_source") {
      return "Прямой источник";
    }
    if (user.source_category === "almanah" && user.bot_key === "lead") {
      return "Альманах";
    }
    return botLabelMap.get(user.bot_key) || user.bot_key;
  }, [botLabelMap]);
  const [hiddenColumns, setHiddenColumns] = React.useState<Set<string>>(() => loadHiddenColumns(userId));
  const [colAnchorEl, setColAnchorEl] = React.useState<HTMLButtonElement | null>(null);

  const resizeStorageKey = COL_WIDTHS_KEY_PREFIX + (userId ?? "default");
  const { colWidths, getColWidth, handleResizeMouseDown, resetColWidths, hasCustomWidths } = useColumnResize(resizeStorageKey);

  // Перезагружаем настройки если userId стал известен после первого рендера
  const prevUserIdRef = React.useRef(userId);
  React.useEffect(() => {
    if (userId !== prevUserIdRef.current) {
      prevUserIdRef.current = userId;
      setHiddenColumns(loadHiddenColumns(userId));
    }
  }, [userId]);

  const handleToggleColumn = (key: string) => {
    setHiddenColumns((prev) => {
      const next = new Set(prev);
      if (next.has(key)) {
        next.delete(key); // был скрыт → показываем
      } else {
        next.add(key);    // был виден → скрываем
      }
      saveHiddenColumns(userId, next);
      return next;
    });
  };

  const rawBotFilterOptions = React.useMemo(() => {
    const hasLead = botOptions.some((option) => option.value === "lead");
    if (!hasLead) {
      return botOptions;
    }
    return [
      ...botOptions,
      { value: "__direct_source__", label: "Прямой источник" },
    ];
  }, [botOptions]);
  const allColumns: Array<{ key: string; label: string; align?: ColAlign; defaultWidth: number }> = [
    { key: "id",                        label: "ID",                               defaultWidth: 60 },
    { key: "bot_key",                   label: "База",                             defaultWidth: 150 },
    { key: "tg_user_id",               label: "TG ID",                            defaultWidth: 100 },
    { key: "username",                  label: "Username",                         defaultWidth: 130 },
    { key: "pokerhub_user_id",          label: "PokerHub ID",                      defaultWidth: 100 },
    { key: "created_at",               label: "Дата регистрации",                 defaultWidth: 150 },
    { key: "freshness_status",          label: "Статус пользователя",              defaultWidth: 200 },
    { key: "first_seen_at_system",      label: "Первый вход в системе",            defaultWidth: 150 },
    { key: "first_seen_at_bot",         label: "Первый вход в боте",               defaultWidth: 150 },
    { key: "user_block",               label: "User Block",                       defaultWidth: 80 },
    { key: "utm_source",               label: "UTM Source",                       defaultWidth: 130 },
    { key: "utm_campaign",             label: "UTM Campaign",                     defaultWidth: 150 },
    { key: "platform_utm_source",      label: "Platform UTM Source",              defaultWidth: 140 },
    { key: "platform_utm_campaign",    label: "Platform UTM Campaign",            defaultWidth: 160 },
    { key: "first_touch_bot",          label: "First Touch Bot",                  defaultWidth: 150 },
    { key: "first_touch_campaign",     label: "First Touch Campaign",             defaultWidth: 160 },
    { key: "last_touch_bot",           label: "Last Touch Bot",                   defaultWidth: 150 },
    { key: "last_touch_campaign",      label: "Last Touch Campaign",              defaultWidth: 160 },
    { key: "utm_medium",               label: "UTM Medium",                       defaultWidth: 120 },
    { key: "utm_content",              label: "UTM Content",                      defaultWidth: 120 },
    { key: "utm_term",                 label: "UTM Term",                         defaultWidth: 120 },
    { key: "platform_utm_medium",      label: "Platform UTM Medium",              defaultWidth: 140 },
    { key: "platform_utm_content",     label: "Platform UTM Content",             defaultWidth: 150 },
    { key: "platform_utm_term",        label: "Platform UTM Term",                defaultWidth: 140 },
    { key: "referer",                  label: "Referer",                          defaultWidth: 220 },
    { key: "raw_link",                 label: "Raw Link",                         defaultWidth: 220 },
    { key: "bot_raw",                  label: "Bot Raw",                          defaultWidth: 220 },
    { key: "ph_raw",                   label: "PH Raw",                           defaultWidth: 220 },
    { key: "last_activity",            label: "Последняя активность",             defaultWidth: 160 },
    { key: "ph_group",                 label: "Группа PH",                        defaultWidth: 140 },
    { key: "advertising_company",      label: "Компания",                         defaultWidth: 150 },
    { key: "budget",                   label: "Бюджет",          align: "right",  defaultWidth: 80 },
    { key: "ingested_at",              label: "Загружено",                        defaultWidth: 150 },
    { key: "converted_to_lead",        label: "Альманах",                         defaultWidth: 80 },
    { key: "registered_platform",      label: "Платформа",                        defaultWidth: 80 },
    { key: "platform_registered_at",   label: "Дата регистрации на платформе",    defaultWidth: 200 },
    { key: "started_learning",         label: "Начал обучение",                   defaultWidth: 80 },
    { key: "learn_start_date",         label: "Дата начала обучения",             defaultWidth: 160 },
    { key: "completed_course",         label: "Прошел курс",                      defaultWidth: 80 },
    { key: "completed_course_at",      label: "Дата окончания курса",             defaultWidth: 160 },
    { key: "course_duration_days",     label: "Дней на прохождение", align: "right", defaultWidth: 100 },
    { key: "interview_reached",        label: "Дошел до собеседования",           defaultWidth: 80 },
    { key: "interview_reached_at",     label: "Дата передачи направлению",        defaultWidth: 170 },
    { key: "interview_reached_status", label: "Статус собеседования",             defaultWidth: 160 },
    { key: "interview_passed",         label: "Прошел собеседование",             defaultWidth: 80 },
    { key: "interview_passed_at",      label: "Дата выхода на собес",             defaultWidth: 160 },
    { key: "interview_passed_status",  label: "Статус прохождения",               defaultWidth: 150 },
    { key: "offer_received",           label: "Оффер",                            defaultWidth: 70 },
    { key: "offer_received_at",        label: "Дата оффера",                      defaultWidth: 140 },
    { key: "offer_received_status",    label: "Статус оффера",                    defaultWidth: 140 },
    { key: "contract_signed",          label: "Контракт",                         defaultWidth: 80 },
    { key: "contract_signed_at",       label: "Дата подписания контракта",        defaultWidth: 180 },
    { key: "contract_signed_status",   label: "Статус контракта",                 defaultWidth: 150 },
    { key: "distance_grinding",        label: "Наигрывают дистанцию",             defaultWidth: 80 },
    { key: "channel_subscribed",       label: "Канал",                            defaultWidth: 70 },
    { key: "community_member",         label: "Салун",                            defaultWidth: 70 },
    { key: "community_member_status",  label: "Статус салуна",                    defaultWidth: 140 },
    { key: "team_member",              label: "Команда",                          defaultWidth: 70 },
    { key: "internal_status",          label: "Внутренний статус",                defaultWidth: 140 },
  ];

  const columns = allColumns.filter((c) => !hiddenColumns.has(c.key));

  const resetColumnFilters = () => {
    onFilterChange("botKeys", []);
    onFilterChange("tgUserId", "");
    onFilterChange("utmSource", []);
    onFilterChange("utmCampaign", []);
    onFilterChange("utmMedium", []);
    onFilterChange("utmContent", []);
    onFilterChange("utmTerm", []);
    onFilterChange("advertisingCompanies", []);
    onFilterChange("convertedToLead", null);
    onFilterChange("registeredPlatform", null);
    onFilterChange("startedLearning", null);
    onFilterChange("completedCourse", null);
    onFilterChange("usedSimulator", null);
    onFilterChange("interviewReached", null);
    onFilterChange("interviewPassed", null);
    onFilterChange("offerReceived", null);
    onFilterChange("contractSigned", null);
    onFilterChange("distanceGrinding", null);
    onFilterChange("interviewReachedStatus", "");
    onFilterChange("interviewPassedStatus", "");
    onFilterChange("offerReceivedStatus", "");
    onFilterChange("contractSignedStatus", "");
    onFilterChange("channelSubscribed", null);
    onFilterChange("communityMember", null);
    onFilterChange("teamMember", null);
    onFilterChange("communityMemberStatus", "");
    onFilterChange("internalStatus", "");
    onFilterChange("userBlock", null);
    onFilterChange("userStatus", "");
    onFilterChange("firstTouchPresent", null);
    onFilterChange("lastTouchPresent", null);
  };

  const getExportData = (): (string | number)[][] => {
    const headers = allColumns.map((c) => c.label);
    const lines = users.map((u) => allColumns.map((c) => {
      if (c.key === "bot_key") {
        return getBaseLabel(u);
      }
      const v = u[c.key];
      if (v === null || v === undefined) return "";
      if (typeof v === "boolean") return v ? "✓" : "✗";
      if (
        c.key === "learn_start_date" ||
        c.key === "completed_course_at" ||
        c.key === "platform_registered_at" ||
        c.key === "created_at" ||
        c.key === "ingested_at" ||
        c.key === "first_seen_at_system" ||
        c.key === "first_seen_at_bot" ||
        c.key === "last_activity" ||
        c.key === "interview_reached_at" ||
        c.key === "interview_passed_at" ||
        c.key === "offer_received_at" ||
        c.key === "contract_signed_at"
      ) return formatDate(v);
      return v;
    }));
    return [headers, ...lines];
  };

  return (
    <Paper
      sx={{
        mt: 2,
        borderRadius: "24px",
        border: "1px solid var(--app-shell-border)",
        background: "var(--app-panel-bg)",
        boxShadow: "var(--app-shell-shadow)",
        overflow: "hidden",
      }}
    >
      <Stack direction="row" alignItems="center" justifyContent="space-between" px={2} pt={2}>
        <Stack direction="row" spacing={1} alignItems="center">
          <Typography variant="h6">RAW Users ({total.toLocaleString()})</Typography>
          <ExportButtons getData={getExportData} baseName="raw_users" sheetName="Raw Users" disabled={!users.length} />
        </Stack>
        <Stack direction="row" spacing={1} alignItems="center">
          <TextField
            size="small"
            placeholder="USERNAME / TG ID"
            value={filters.tgUserId}
            onChange={(event) => onFilterChange("tgUserId", event.target.value)}
            sx={{ minWidth: 260 }}
          />
          <Button
            size="small"
            variant="outlined"
            color="warning"
            onClick={resetColumnFilters}
            sx={{ textTransform: "none", fontSize: "0.75rem", px: 1.5 }}
          >
            Сбросить фильтры
          </Button>
          {loading && (
            <Typography variant="body2" color="textSecondary">
              Загружаем...
            </Typography>
          )}
          <Tooltip title="Настройка столбцов">
            <Button
              size="small"
              variant={hiddenColumns.size > 0 ? "contained" : "outlined"}
              onClick={(e) => setColAnchorEl(e.currentTarget)}
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
        </Stack>
      </Stack>
      {loading && !users.length && <TableSkeleton columns={8} rows={8} />}
      <Popover
        open={Boolean(colAnchorEl)}
        anchorEl={colAnchorEl}
        onClose={() => setColAnchorEl(null)}
        anchorOrigin={{ vertical: "bottom", horizontal: "right" }}
        transformOrigin={{ vertical: "top", horizontal: "right" }}
      >
        <Stack sx={{ p: 1.5, maxHeight: 480, overflow: "auto", minWidth: 220 }}>
          <Stack direction="row" justifyContent="space-between" alignItems="center" mb={0.5}>
            <Typography variant="caption" color="text.secondary" fontWeight={600}>
              Столбцы ({allColumns.length - hiddenColumns.size}/{allColumns.length})
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
                  const all = new Set<string>(ALL_COLUMN_KEYS);
                  setHiddenColumns(all);
                  saveHiddenColumns(userId, all);
                }}
              >
                Ни одного
              </Typography>
            </Stack>
          </Stack>
          <Divider sx={{ mb: 0.5 }} />
          {hasCustomWidths && (
            <Typography
              variant="caption"
              color="error"
              sx={{ cursor: "pointer", mb: 0.5 }}
              onClick={resetColWidths}
            >
              Сбросить ширины столбцов
            </Typography>
          )}
          <FormGroup>
            {allColumns.map((col) => (
              <FormControlLabel
                key={col.key}
                control={
                  <Checkbox
                    size="small"
                    checked={!hiddenColumns.has(col.key)}
                    onChange={() => handleToggleColumn(col.key)}
                    sx={{ py: 0.25 }}
                  />
                }
                label={<Typography variant="body2">{col.label}</Typography>}
                sx={{ mx: 0 }}
              />
            ))}
          </FormGroup>
        </Stack>
      </Popover>
      <SyncedTableScroll maxHeight="calc(100vh - 280px)" topOffset={0}>
      <TableContainer sx={{ overflow: "visible" }}>
        <Table
          size="small"
          stickyHeader
          sx={{
            tableLayout: "fixed",
            "& .MuiTableCell-root": {
              borderBottom: "1px solid var(--app-table-divider)",
              py: 1.05,
              fontSize: "0.78rem",
            },
            "& .MuiTableBody-root .MuiTableRow-root:nth-of-type(even)": {
              backgroundColor: "var(--app-table-row-alt)",
            },
            "& .MuiTableBody-root .MuiTableRow-root:hover": {
              backgroundColor: "var(--app-table-row-hover)",
            },
          }}
        >
          <colgroup>
            {columns.map((column) => {
              const w = getColWidth(column.key, column.defaultWidth);
              return <col key={column.key} style={{ width: w, minWidth: w }} />;
            })}
          </colgroup>
          <TableHead>
            <TableRow>
              {columns.map((column) => (
                <TableCell
                  key={column.key}
                  align={column.align || "left"}
                  sortDirection={sortBy === column.key ? sortDirection : false}
                  sx={{
                    ...stickyHeaderCellSx(0, 6, "var(--app-table-head-bg)"),
                    position: "relative",
                    userSelect: "none",
                    overflow: "hidden",
                    whiteSpace: "nowrap",
                    textOverflow: "ellipsis",
                  }}
                >
                  {sortableColumns.has(column.key) ? (
                    <TableSortLabel
                      active={sortBy === column.key}
                      direction={sortBy === column.key ? sortDirection : "asc"}
                      onClick={() => onSort(column.key)}
                    >
                      {column.label}
                    </TableSortLabel>
                  ) : (
                    column.label
                  )}
                  {/* Ручка для ресайза столбца */}
                  <span
                    onMouseDown={(e) =>
                      handleResizeMouseDown(
                        e,
                        column.key,
                        e.currentTarget.parentElement?.getBoundingClientRect().width ?? getColWidth(column.key, column.defaultWidth)
                      )
                    }
                    style={{
                      position: "absolute",
                      right: 0,
                      top: 0,
                      height: "100%",
                      width: 6,
                      cursor: "col-resize",
                      zIndex: 1,
                      background: "transparent",
                    }}
                    title="Потяните чтобы изменить ширину"
                  />
                </TableCell>
              ))}
            </TableRow>
            <TableRow>
              {columns.map((column) => (
                <TableCell
                  key={column.key}
                  align={column.align || "left"}
                  sx={stickyHeaderCellSx(HEADER_ROW_HEIGHT, 5, "var(--app-table-summary-bg)")}
                >
                  {column.key === "bot_key" && (
                    <Autocomplete
                      multiple
                      size="small"
                      options={rawBotFilterOptions}
                      value={rawBotFilterOptions.filter((option) => filters.botKeys.includes(option.value))}
                      onChange={(_e, value) => onFilterChange("botKeys", value.map((o) => o.value))}
                      getOptionLabel={(option) => option.label}
                      isOptionEqualToValue={(option, value) => option.value === value.value}
                      renderInput={(params) => <TextField {...params} placeholder="База" />}
                    />
                  )}
                  {(column.key === "tg_user_id" || column.key === "username") && (
                    <TextField
                      size="small"
                      fullWidth
                      placeholder="TG ID / Username"
                      value={filters.tgUserId}
                      onChange={(event) => onFilterChange("tgUserId", event.target.value)}
                    />
                  )}
                  {column.key === "freshness_status" && (
                    <Select
                      size="small"
                      displayEmpty
                      value={filters.userStatus}
                      onChange={(event) => onFilterChange("userStatus", String(event.target.value))}
                      sx={{ minWidth: 190 }}
                    >
                      <MenuItem value="">Все статусы</MenuItem>
                      <MenuItem value="new_in_bot">Новый в боте</MenuItem>
                      <MenuItem value="old_in_system">Старый в системе</MenuItem>
                    </Select>
                  )}
                  {column.key === "user_block" && renderTriState(filters.userBlock, (v) => onFilterChange("userBlock", v))}
                  {column.key === "utm_source" && (
                    <Autocomplete
                      multiple size="small" options={utmSourceOptions} value={filters.utmSource}
                      onChange={(_e, value) => onFilterChange("utmSource", value)}
                      renderInput={(params) => <TextField {...params} placeholder="UTM Source" />}
                    />
                  )}
                  {column.key === "utm_campaign" && (
                    <Autocomplete
                      multiple size="small" options={utmCampaignOptions} value={filters.utmCampaign}
                      onChange={(_e, value) => onFilterChange("utmCampaign", value)}
                      renderInput={(params) => <TextField {...params} placeholder="UTM Campaign" />}
                    />
                  )}
                  {column.key === "utm_medium" && (
                    <Autocomplete
                      multiple size="small" options={utmMediumOptions} value={filters.utmMedium}
                      onChange={(_e, value) => onFilterChange("utmMedium", value)}
                      renderInput={(params) => <TextField {...params} placeholder="UTM Medium" />}
                    />
                  )}
                  {column.key === "utm_content" && (
                    <Autocomplete
                      multiple size="small" options={utmContentOptions} value={filters.utmContent}
                      onChange={(_e, value) => onFilterChange("utmContent", value)}
                      renderInput={(params) => <TextField {...params} placeholder="UTM Content" />}
                    />
                  )}
                  {column.key === "utm_term" && (
                    <Autocomplete
                      multiple size="small" options={utmTermOptions} value={filters.utmTerm}
                      onChange={(_e, value) => onFilterChange("utmTerm", value)}
                      renderInput={(params) => <TextField {...params} placeholder="UTM Term" />}
                    />
                  )}
                  {column.key === "advertising_company" && (
                    <Autocomplete
                      multiple size="small" options={companyOptions} value={filters.advertisingCompanies}
                      onChange={(_e, value) => onFilterChange("advertisingCompanies", value)}
                      renderInput={(params) => <TextField {...params} placeholder="Company" />}
                    />
                  )}
                  {column.key === "converted_to_lead" && renderTriState(filters.convertedToLead, (v) => onFilterChange("convertedToLead", v))}
                  {column.key === "registered_platform" && renderTriState(filters.registeredPlatform, (v) => onFilterChange("registeredPlatform", v))}
                  {column.key === "started_learning" && renderTriState(filters.startedLearning, (v) => onFilterChange("startedLearning", v))}
                  {column.key === "completed_course" && renderTriState(filters.completedCourse, (v) => onFilterChange("completedCourse", v))}
                  {column.key === "interview_reached" && renderTriState(filters.interviewReached, (v) => onFilterChange("interviewReached", v))}
                  {column.key === "interview_reached_status" && (
                    <TextField size="small" placeholder="Статус собеседования"
                      value={filters.interviewReachedStatus}
                      onChange={(e) => onFilterChange("interviewReachedStatus", e.target.value)} />
                  )}
                  {column.key === "interview_passed" && renderTriState(filters.interviewPassed, (v) => onFilterChange("interviewPassed", v))}
                  {column.key === "interview_passed_status" && (
                    <TextField size="small" placeholder="Статус прохождения"
                      value={filters.interviewPassedStatus}
                      onChange={(e) => onFilterChange("interviewPassedStatus", e.target.value)} />
                  )}
                  {column.key === "offer_received" && renderTriState(filters.offerReceived, (v) => onFilterChange("offerReceived", v))}
                  {column.key === "offer_received_status" && (
                    <TextField size="small" placeholder="Статус оффера"
                      value={filters.offerReceivedStatus}
                      onChange={(e) => onFilterChange("offerReceivedStatus", e.target.value)} />
                  )}
                  {column.key === "contract_signed" && renderTriState(filters.contractSigned, (v) => onFilterChange("contractSigned", v))}
                  {column.key === "contract_signed_status" && (
                    <TextField size="small" placeholder="Статус контракта"
                      value={filters.contractSignedStatus}
                      onChange={(e) => onFilterChange("contractSignedStatus", e.target.value)} />
                  )}
                  {column.key === "distance_grinding" && renderTriState(filters.distanceGrinding, (v) => onFilterChange("distanceGrinding", v))}
                  {column.key === "channel_subscribed" && renderTriState(filters.channelSubscribed, (v) => onFilterChange("channelSubscribed", v))}
                  {column.key === "community_member" && renderTriState(filters.communityMember, (v) => onFilterChange("communityMember", v))}
                  {column.key === "community_member_status" && (
                    <TextField size="small" placeholder="Статус салуна"
                      value={filters.communityMemberStatus}
                      onChange={(e) => onFilterChange("communityMemberStatus", e.target.value)} />
                  )}
                  {column.key === "team_member" && renderTriState(filters.teamMember, (v) => onFilterChange("teamMember", v))}
                  {column.key === "internal_status" && (
                    <TextField size="small" placeholder="Внутренний статус"
                      value={filters.internalStatus}
                      onChange={(e) => onFilterChange("internalStatus", e.target.value)} />
                  )}
                </TableCell>
              ))}
            </TableRow>
          </TableHead>
          <TableBody>
            {users.map((user) => (
              <TableRow key={user.id} hover>
                {columns.map((column) => (
                  <TableCell key={column.key} align={column.align || "left"}>
                    {column.key === "id" && user.id}
                    {column.key === "bot_key" && getBaseLabel(user)}
                    {column.key === "tg_user_id" && user.tg_user_id}
                    {column.key === "username" && (user.username ? `@${user.username}` : "—")}
                    {column.key === "pokerhub_user_id" && (user.pokerhub_user_id || "—")}
                    {column.key === "created_at" && formatDate(user.created_at)}
                    {column.key === "freshness_status" && renderUserFreshness(user)}
                    {column.key === "first_seen_at_system" && formatDate(user.first_seen_at_system)}
                    {column.key === "first_seen_at_bot" && formatDate(user.first_seen_at_bot)}
                    {column.key === "user_block" && formatBool(user.user_block)}
                    {column.key === "utm_source" && (user.utm_source || "(none)")}
                    {column.key === "utm_campaign" && (user.utm_campaign || "(none)")}
                    {column.key === "platform_utm_source" && (user.platform_utm_source || "—")}
                    {column.key === "platform_utm_campaign" && (user.platform_utm_campaign || "—")}
                    {column.key === "first_touch_bot" && (user.first_touch_bot || "нет метки")}
                    {column.key === "first_touch_campaign" && (user.first_touch_campaign || "нет метки")}
                    {column.key === "last_touch_bot" && (user.last_touch_bot || "нет метки")}
                    {column.key === "last_touch_campaign" && (user.last_touch_campaign || "нет метки")}
                    {column.key === "utm_medium" && (user.utm_medium || "(none)")}
                    {column.key === "utm_content" && (user.utm_content || "(none)")}
                    {column.key === "utm_term" && (user.utm_term || "(none)")}
                    {column.key === "platform_utm_medium" && (user.platform_utm_medium || "—")}
                    {column.key === "platform_utm_content" && (user.platform_utm_content || "—")}
                    {column.key === "platform_utm_term" && (user.platform_utm_term || "—")}
                    {column.key === "referer" && renderLinkValue(user.referer)}
                    {column.key === "raw_link" && renderLinkValue(user.raw_link)}
                    {column.key === "bot_raw" && renderLinkValue(user.bot_raw)}
                    {column.key === "ph_raw" && renderLinkValue(user.ph_raw)}
                    {column.key === "last_activity" && formatDate(user.last_activity)}
                    {column.key === "ph_group" && (user.ph_group || "—")}
                    {column.key === "advertising_company" && (user.advertising_company || "—")}
                    {column.key === "budget" && (user.budget ? Number(user.budget).toFixed(2) : "0.00")}
                    {column.key === "ingested_at" && formatDate(user.ingested_at)}
                    {column.key === "converted_to_lead" && formatBool(user.converted_to_lead)}
                    {column.key === "registered_platform" && formatBool(user.registered_platform)}
                    {column.key === "platform_registered_at" && formatDate(user.platform_registered_at)}
                    {column.key === "started_learning" && formatBool(user.started_learning)}
                    {column.key === "learn_start_date" && formatDate(user.learn_start_date)}
                    {column.key === "completed_course" && formatBool(user.completed_course)}
                    {column.key === "completed_course_at" && formatDate(user.completed_course_at)}
                    {column.key === "course_duration_days" && (user.course_duration_days ?? "—")}
                    {column.key === "interview_reached" && formatBool(user.interview_reached)}
                    {column.key === "interview_reached_at" && formatDate(user.interview_reached_at)}
                    {column.key === "interview_reached_status" && (user.interview_reached_status || "—")}
                    {column.key === "interview_passed" && formatBool(user.interview_passed)}
                    {column.key === "interview_passed_at" && formatDate(user.interview_passed_at)}
                    {column.key === "interview_passed_status" && (user.interview_passed_status || "—")}
                    {column.key === "offer_received" && formatBool(user.offer_received)}
                    {column.key === "offer_received_at" && formatDate(user.offer_received_at)}
                    {column.key === "offer_received_status" && (user.offer_received_status || "—")}
                    {column.key === "contract_signed" && formatBool(user.contract_signed)}
                    {column.key === "contract_signed_at" && formatDate(user.contract_signed_at)}
                    {column.key === "contract_signed_status" && (user.contract_signed_status || "—")}
                    {column.key === "distance_grinding" && formatBool(user.distance_grinding)}
                    {column.key === "channel_subscribed" && formatBool(user.channel_subscribed)}
                    {column.key === "community_member" && formatBool(user.community_member)}
                    {column.key === "community_member_status" && (user.community_member_status || "—")}
                    {column.key === "team_member" && formatBool(user.team_member)}
                    {column.key === "internal_status" && (user.internal_status || "—")}
                  </TableCell>
                ))}
              </TableRow>
            ))}
            {!loading && !users.length && (
              <TableRow>
                <TableCell colSpan={columns.length} sx={{ py: 0 }}>
                  <EmptyState
                    compact
                    title="RAW Users пока пуст"
                    description="По текущим фильтрам записи не найдены. Попробуй расширить период или убрать часть ограничений."
                  />
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </TableContainer>
      </SyncedTableScroll>
      <TablePagination
        component="div"
        count={total}
        page={page}
        onPageChange={onPageChange}
        rowsPerPage={pageSize}
        onRowsPerPageChange={onRowsPerPageChange}
        rowsPerPageOptions={[50, 100, 200, 500, 1000]}
        sx={{ borderTop: "1px solid var(--app-table-divider)" }}
      />
    </Paper>
  );
};

export default RawUsersTable;
