// Альтернативная реализация главной страницы с боковой панелью (AppShell + Sidebar + Topbar).
// Это более новая версия по сравнению с pages/OverviewPage.tsx — используется как основной макет.
import React, { useEffect, useMemo, useState, useRef, useCallback } from "react";
import { AppShell } from "./AppShell";
import { Sidebar } from "./Sidebar";
import { Topbar } from "./Topbar";
import { addDays, format as formatDate, parseISO, startOfWeek, isValid, startOfMonth, endOfMonth } from "date-fns";
import {
  LineChart, Line, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip as RechartTooltip,
  Legend, ResponsiveContainer,
} from "recharts";
import Box from "@mui/material/Box";
import Grid from "@mui/material/Grid";
import Typography from "@mui/material/Typography";
import Button from "@mui/material/Button";
import Stack from "@mui/material/Stack";
import Chip from "@mui/material/Chip";
import ButtonGroup from "@mui/material/ButtonGroup";
import Alert from "@mui/material/Alert";
import Paper from "@mui/material/Paper";
import TextField from "@mui/material/TextField";
import RefreshIcon from "@mui/icons-material/Refresh";
import FilterPanel from "../FilterPanel";
import OverviewTabs from "../OverviewTabs";
import MetricCard from "../MetricCard";
import LineChartCard from "../LineChartCard";
import RawUsersTable from "../RawUsersTable";
import BreakdownTable from "../BreakdownTable";
import FunnelView from "../FunnelView";
import BotRegistryDialog from "../BotRegistryDialog";
import AdvertisingCompaniesDialog from "../AdvertisingCompaniesDialog";
import AccessManagerDialog from "../AccessManagerDialog";
import EmployeeRegistryDialog from "../EmployeeRegistryDialog";
import FunnelSummaryTable from "../FunnelSummaryTable";
import SubscriptionsComparePanel from "../SubscriptionsComparePanel";
import BudgetDialog from "../BudgetDialog";
import AdMetricsDialog from "../AdMetricsDialog";
import SystemSettingsDialog from "../SystemSettingsDialog";
import WeeklyTable from "../WeeklyTable";
import RoistatLessonsTable from "../RoistatLessonsTable";
import UserSearchPanel from "../UserSearchPanel";
import FunnelTreeTable from "../FunnelTreeTable";
import MainReportTable from "../MainReportTable";
import FaqPanel from "../FaqPanel";
import { KpiCard, KpiGrid } from "../ui/KpiCard";
import { Pill } from "../ui/Pill";
import {
  useReports,
  FilterValues,
  RawReportParams,
  RawColumnFilters,
  buildFilterParams,
  buildRawFilterParams,
  buildQueryParams,
} from "../../hooks/useReports";
import { useFilterOptions } from "../../hooks/useFilterOptions";
import axios from "axios";
import { useBotRegistry, BotOption } from "../../hooks/useBotRegistry";
import { BotSelectOption } from "../FilterPanel";
import { useFunnelSummary } from "../../hooks/useFunnelSummary";
import { useAdvertisingCompanies } from "../../hooks/useAdvertisingCompanies";
import { useTelegramAccess } from "../../hooks/useTelegramAccess";
import { useEmployeeRegistry } from "../../hooks/useEmployeeRegistry";
import { useSubscriptionsCompare } from "../../hooks/useSubscriptionsCompare";
import { useBudgets } from "../../hooks/useBudgets";
import { useBudgetWeeklyReport } from "../../hooks/useBudgetWeeklyReport";
import { useAdMetrics } from "../../hooks/useAdMetrics";
import { useSystemSettings } from "../../hooks/useSystemSettings";
import { useRoistatWeekly } from "../../hooks/useRoistatWeekly";
import { useRoistatLessons } from "../../hooks/useRoistatLessons";
import { useMainReport } from "../../hooks/useMainReport";
import { useFunnelTree } from "../../hooks/useFunnelTree";
import { useRoistatWeeklyTree } from "../../hooks/useRoistatWeeklyTree";
import RoistatWeeklyTreeTable from "../RoistatWeeklyTreeTable";
import { buildPresetRange, DEFAULT_FILTERS, DEFAULT_RAW_FILTERS } from "./overviewFilterState";
import { buildActiveFilterChips } from "./overviewFilterChips";

interface SyncStatus {
  ts: number;
  status: "ok" | "error";
  error?: string | null;
}

const API_BASE = import.meta.env.VITE_API_BASE || "";

const TABS: Array<
  "overview" | "funnel" | "totalb" | "totala" | "tgsubs" | "weekly" | "lessons" | "raw" | "rawutm" | "usersearch"
> = [
  "overview",
  "funnel",
  "totalb",
  "totala",
  "tgsubs",
  "weekly",
  "lessons",
  "raw",
  "rawutm",
  "usersearch",
];

const sumBy = <T,>(items: T[], getValue: (item: T) => number) =>
  items.reduce((acc, item) => acc + (Number(getValue(item)) || 0), 0);

const formatCompact = (value: number) => value.toLocaleString("ru-RU");
const formatMoneyCompact = (value: number) => (value > 0 ? `$${value.toLocaleString("ru-RU", { maximumFractionDigits: 0 })}` : "—");
const formatPctCompact = (value: number) => `${value.toFixed(1)}%`;

const calcDelta = (current: number, previous: number) => {
  if (!previous) return 0;
  return ((current - previous) / previous) * 100;
};

interface OverviewPageProps {
  userId?: string | null;
  currentUsername?: string | null;
  onLogout?: () => void;
  darkMode?: boolean;
  onToggleDark?: () => void;
}

const OverviewPage: React.FC<OverviewPageProps> = ({
  darkMode = false,
  onToggleDark,
}) => {
  const [draftFilters, setDraftFilters] = useState<FilterValues>(DEFAULT_FILTERS);
  const [activeFilters, setActiveFilters] = useState<FilterValues>(DEFAULT_FILTERS);
  const [tab, setTab] = useState<
    "overview" | "funnel" | "main" | "totalb" | "totala" | "tgsubs" | "weekly" | "lessons" | "raw" | "rawutm" | "usersearch" | "faq"
  >(
    "overview"
  );
  const [breakdownGroup, setBreakdownGroup] = useState("utm_source");
  const [rawPage, setRawPage] = useState(0);
  const [rawPageSize, setRawPageSize] = useState(50);
  const [rawSortBy, setRawSortBy] = useState("created_at");
  const [rawSortDirection, setRawSortDirection] = useState<"asc" | "desc">("desc");
  const [exporting, setExporting] = useState(false);
  const [subscriptionsGroupBy, setSubscriptionsGroupBy] = useState<"campaign" | "overall">("campaign");
  const [subscriptionsInterval, setSubscriptionsInterval] = useState<"day" | "week">("week");
  const initialWeeklyMonth = formatDate(new Date(), "yyyy-MM");
  const [weeklyMonth, setWeeklyMonth] = useState<string>(initialWeeklyMonth);
  const [selectedBotKey, setSelectedBotKey] = useState<string | null>(null);
  const [funnelUserScope, setFunnelUserScope] = useState<"all" | "new" | "old">("all");
  const [rawFilters, setRawFilters] = useState<RawColumnFilters>(DEFAULT_RAW_FILTERS);
  const [syncing, setSyncing] = useState(false);
  const [syncMessage, setSyncMessage] = useState<string | null>(null);
  const [lastIngestionStatus, setLastIngestionStatus] = useState<SyncStatus | null>(null);
  const [lastIngestionSuccess, setLastIngestionSuccess] = useState<SyncStatus | null>(null);
  const [lastSmStatus, setLastSmStatus] = useState<SyncStatus | null>(null);
  const [replStatus, setReplStatus] = useState<{streams_ok: number; streams_error: string[]; total: number} | null>(null);
  const [periodPreset, setPeriodPreset] = useState<"7d" | "14d" | "30d" | "all">("7d");
  const [chartPeriods, setChartPeriods] = useState<Record<string, number>>({});
  const setChartPeriod = (key: string, days: number) =>
    setChartPeriods((prev) => ({ ...prev, [key]: days }));
  const getChartPeriod = (key: string) => chartPeriods[key] ?? 0;
  const [periodEndDate, setPeriodEndDate] = useState<Date | null>(null);
  const {
    bots: registryBots,
    loading: loadingDatabases,
    error: databasesError,
    refresh: refreshDatabases,
  } = useBotRegistry();

  const [botDialogOpen, setBotDialogOpen] = useState(false);
  const [companyDialogOpen, setCompanyDialogOpen] = useState(false);
  const [accessDialogOpen, setAccessDialogOpen] = useState(false);
  const [employeeDialogOpen, setEmployeeDialogOpen] = useState(false);
  const [budgetDialogOpen, setBudgetDialogOpen] = useState(false);
  const [adMetricsDialogOpen, setAdMetricsDialogOpen] = useState(false);
  const [settingsDialogOpen, setSettingsDialogOpen] = useState(false);

  const botOptions: BotSelectOption[] = useMemo(
    () =>
      registryBots
        .filter((bot) => bot.is_active)
        .map((bot) => ({
          value: bot.bot_key,
          label: bot.display_name || bot.bot_key,
        })),
    [registryBots]
  );

  const activeBotKeys = useMemo(() => botOptions.map((bot) => bot.value), [botOptions]);
  const botNameMap = useMemo(() => {
    const map = new Map<string, string>();
    botOptions.forEach((bot) => map.set(bot.value, bot.label));
    return map;
  }, [botOptions]);
  const resolveBotLabel = useMemo(
    () => (key: string) => {
      const normalized = String(key || "").trim().toLowerCase();
      if (normalized === "lead" || normalized.startsWith("lead")) {
        return "Альманах";
      }
      return botNameMap.get(key) || key;
    },
    [botNameMap]
  );

  const selectedDatabases = useMemo(() => {
    if (draftFilters.bots.length) {
      return draftFilters.bots;
    }
    return [];
  }, [draftFilters.bots]);

  const {
    companies,
    utmSource,
    utmCampaign,
    utmMedium,
    utmContent,
    utmTerm,
    loading: loadingOptions,
    error: filtersError,
  } = useFilterOptions(activeBotKeys, selectedDatabases);

  const {
    companies: advertisingCompanies,
    loading: loadingCompanies,
    error: companiesError,
    upsert: upsertCompany,
    remove: deleteCompany,
  } = useAdvertisingCompanies();

  const { entries: accessEntries, loading: accessLoading, error: accessError, add: grantAccess, remove: revokeAccess } =
    useTelegramAccess();
  const {
    entries: employeeEntries,
    loading: employeeLoading,
    error: employeeError,
    replaceAll: saveEmployees,
  } = useEmployeeRegistry();
  // Removed overview widgets: keep hooks out to avoid extra requests.
  const {
    data: subscriptionsData,
    overall: subscriptionsOverall,
    summary: subscriptionsSummary,
    loading: subscriptionsLoading,
    error: subscriptionsError,
  } = useSubscriptionsCompare(activeFilters, {
    groupBy: subscriptionsGroupBy,
    interval: subscriptionsInterval,
    enabled: tab === "tgsubs",
  });
  const overviewFilters = useMemo(
    () => ({
      ...activeFilters,
      startDate: null,
      endDate: null,
    }),
    [activeFilters]
  );
  const { overall: overviewSubsOverall } = useSubscriptionsCompare(overviewFilters, {
    groupBy: "overall",
    interval: "day",
    enabled: tab === "overview",
    pollMs: 30000,
  });
  const needsCoreReports = tab === "overview" || tab === "raw" || tab === "rawutm" || tab === "funnel";
  const needsBudgetReport = tab === "overview" || tab === "totalb" || tab === "totala" || tab === "main";
  const needsAdminData = budgetDialogOpen || adMetricsDialogOpen || settingsDialogOpen;
  const {
    budgets,
    loading: budgetsLoading,
    error: budgetsError,
    refresh: refreshBudgets,
    createBudget,
    updateBudget,
    deleteBudget,
  } = useBudgets({ enabled: needsAdminData });

  useEffect(() => {
    if (adMetricsDialogOpen) {
      refreshBudgets();
    }
  }, [adMetricsDialogOpen, refreshBudgets]);
  const {
    rows: adMetricsRows,
    loading: adMetricsLoading,
    error: adMetricsError,
    createRow: createAdMetrics,
    updateRow: updateAdMetrics,
    deleteRow: deleteAdMetrics,
  } = useAdMetrics({ enabled: needsAdminData });
  const {
    settings: systemSettings,
    logs: systemLogs,
    marketingDailySettings,
    marketingDailyPreview,
    marketingDailyHistory,
    loading: systemLoading,
    error: systemError,
    refresh: refreshSystemSettings,
    update: updateSystemSettings,
    rebuildCompanies,
    updateMarketingDaily,
    refreshMarketingDailyPreview,
    sendMarketingDailyTest,
    resendMarketingDaily,
  } = useSystemSettings({ enabled: needsAdminData });
  const {
    data: budgetWeeklyData,
    error: budgetWeeklyError,
  } = useBudgetWeeklyReport(activeFilters, "day", { enabled: needsBudgetReport });
  const firstTouchStart = useMemo(
    () =>
      activeFilters.startDate && isValid(activeFilters.startDate)
        ? formatDate(activeFilters.startDate, "yyyy-MM-dd")
        : undefined,
    [activeFilters.startDate]
  );
  const firstTouchEnd = useMemo(
    () =>
      activeFilters.endDate && isValid(activeFilters.endDate)
        ? formatDate(activeFilters.endDate, "yyyy-MM-dd")
        : undefined,
    [activeFilters.endDate]
  );
  const weeklyMonthRange = useMemo(() => {
    if (weeklyMonth === "all") {
      return { start: undefined, end: undefined };
    }
    const dt = parseISO(`${weeklyMonth}-01`);
    if (!isValid(dt)) {
      return { start: undefined, end: undefined };
    }
    return {
      start: formatDate(startOfMonth(dt), "yyyy-MM-dd"),
      end: formatDate(endOfMonth(dt), "yyyy-MM-dd"),
    };
  }, [weeklyMonth]);

  const weeklyEventStart = firstTouchStart || weeklyMonthRange.start;
  const weeklyEventEnd = firstTouchEnd || weeklyMonthRange.end;
  const weeklyFirstTouchStart = firstTouchStart || weeklyMonthRange.start;
  const weeklyFirstTouchEnd = firstTouchEnd || weeklyMonthRange.end;

  const {
    rows: roistatWeeklyRows,
    loading: roistatWeeklyLoading,
    error: roistatWeeklyError,
    refresh: refreshRoistatWeekly,
  } = useRoistatWeekly(
    weeklyEventStart,
    weeklyEventEnd,
    activeFilters.touchMode,
    tab === "weekly",
    weeklyFirstTouchStart,
    weeklyFirstTouchEnd
  );
  const { rows: overviewWeeklyRows } = useRoistatWeekly(
    undefined,
    undefined,
    "event",
    tab === "overview",
    undefined,
    undefined,
    activeFilters.bots.length > 0 ? activeFilters.bots : undefined,
  );
  const {
    tree: roistatWeeklyTree,
    loading: roistatWeeklyTreeLoading,
    error: roistatWeeklyTreeError,
  } = useRoistatWeeklyTree(weeklyEventStart, weeklyEventEnd, tab === "weekly");

  const mainReportFilters = useMemo(
    () => ({
      bots: activeFilters.bots,
      companies: activeFilters.companies,
      utmSource: activeFilters.utmSource,
      utmCampaign: activeFilters.utmCampaign,
      utmMedium: activeFilters.utmMedium,
      utmContent: activeFilters.utmContent,
      utmTerm: activeFilters.utmTerm,
    }),
    [activeFilters.bots, activeFilters.companies, activeFilters.utmSource, activeFilters.utmCampaign, activeFilters.utmMedium, activeFilters.utmContent, activeFilters.utmTerm]
  );
  const useMonthScopedMainReport = tab === "main";
  const mainReportEventStart = useMonthScopedMainReport ? weeklyEventStart : firstTouchStart;
  const mainReportEventEnd = useMonthScopedMainReport ? weeklyEventEnd : firstTouchEnd;
  const mainReportFirstTouchStart = useMonthScopedMainReport ? weeklyFirstTouchStart : firstTouchStart;
  const mainReportFirstTouchEnd = useMonthScopedMainReport ? weeklyFirstTouchEnd : firstTouchEnd;

  const {
    rows: mainReportRows,
    botRows: mainReportBotRows,
    weekTotals: mainReportWeekTotals,
    loading: mainReportLoading,
    error: mainReportError,
    refresh: refreshMainReport,
  } = useMainReport(
    mainReportEventStart,
    mainReportEventEnd,
    tab === "main" || tab === "totala",
    activeFilters.touchMode,
    mainReportFirstTouchStart,
    mainReportFirstTouchEnd,
    activeFilters.displayMode,
    mainReportFilters,
    { pollMs: 30000 },
  );

  const {
    courses: roistatLessonCourses,
    loading: roistatLessonsLoading,
    error: roistatLessonsError,
    pokerhubUserId,
    setPokerhubUserId,
    learnStartDateFrom,
    setLearnStartDateFrom,
    learnStartDateTo,
    setLearnStartDateTo,
  } = useRoistatLessons(activeFilters, tab === "lessons");

  const budgetAggregates = useMemo(() => {
    type Agg = {
      budget: number;
      spend: number;
      impressions: number;
      clicks: number;
      subscribed: number;
    };
    const emptyAgg = (): Agg => ({
      budget: 0,
      spend: 0,
      impressions: 0,
      clicks: 0,
      subscribed: 0,
    });
    const byBot = new Map<string, Agg>();
    const byCampaign = new Map<string, Agg>();
    const add = (map: Map<string, Agg>, key: string | null | undefined, row: (typeof budgetWeeklyData)[number]) => {
      if (!key) {
        return;
      }
      const agg = map.get(key) ?? emptyAgg();
      agg.budget += row.budget || 0;
      agg.spend += row.spend || 0;
      agg.impressions += row.impressions || 0;
      agg.clicks += row.clicks || 0;
      agg.subscribed += row.subscribed || 0;
      map.set(key, agg);
    };
    budgetWeeklyData.forEach((row) => {
      add(byCampaign, row.campaign, row);
      add(byBot, row.bot_key, row);
    });
    return { byBot, byCampaign };
  }, [budgetWeeklyData]);

  const totalACompanyMeta = useMemo(() => {
    const map: Record<string, { bots: string[] }> = {};
    advertisingCompanies.forEach((company) => {
      if (company.company_name) {
        map[company.company_name] = { bots: company.bot_keys || [] };
      }
    });
    return map;
  }, [advertisingCompanies]);


  const rawParams = useMemo(
    () => ({
      limit: rawPageSize,
      offset: rawPage * rawPageSize,
      sortBy: rawSortBy,
      sortDirection: rawSortDirection,
    }),
    [rawPage, rawPageSize, rawSortBy, rawSortDirection]
  );

  const {
    total,
    daily,
    breakdown,
    stages,
    raw,
    rawTotal,
    loading,
    error,
    refresh,
  } = useReports(activeFilters, rawParams, rawFilters, breakdownGroup, { enabled: needsCoreReports });

  const scopedFunnelFilters = useMemo(
    () => ({ ...activeFilters, userScope: funnelUserScope }),
    [activeFilters, funnelUserScope]
  );
  const summaryBotsForFunnel = useFunnelSummary(scopedFunnelFilters, "bot_key", {
    enabled: tab === "totalb",
  });
  const summaryCompanies = useFunnelSummary(activeFilters, "advertising_company", { enabled: tab === "totala" });
  const sourceTreeFilters = useMemo(
    () => ({
      ...activeFilters,
      bots: [],
      companies: [],
      utmSource: [],
      utmCampaign: [],
      utmMedium: [],
      utmContent: [],
      utmTerm: [],
    }),
    [activeFilters]
  );
  const funnelTree = useFunnelTree(sourceTreeFilters, tab === "rawutm");

  const handleFilterChange = (key: string, value: any) => {
    if (key === "startDate" || key === "endDate") {
      const normalizedDate =
        value instanceof Date && isValid(value) ? value : null;
      setDraftFilters((prev) => ({ ...prev, [key]: normalizedDate }));
      return;
    }
    if (key === "touchMode") {
      setDraftFilters((prev) => ({ ...prev, touchMode: value }));
      setActiveFilters((prev) => ({ ...prev, touchMode: value }));
      setRawPage(0);
      return;
    }
    if (key === "displayMode") {
      setDraftFilters((prev) => ({ ...prev, displayMode: value }));
      setActiveFilters((prev) => ({ ...prev, displayMode: value }));
      return;
    }
    setDraftFilters((prev) => ({ ...prev, [key]: value }));
  };

  const handleApplyFilters = () => {
    setActiveFilters({ ...draftFilters });
    setRawPage(0);
  };

  const applyPresetFilters = (preset: "today" | "7d" | "month" | "prev_month") => {
    const { startDate: nextStart, endDate: nextEnd } = buildPresetRange(preset);
    const nextFilters = { ...draftFilters, startDate: nextStart, endDate: nextEnd };
    setDraftFilters(nextFilters);
    setActiveFilters(nextFilters);
    setRawPage(0);
  };

  const resetAllFilters = () => {
    setDraftFilters(DEFAULT_FILTERS);
    setActiveFilters(DEFAULT_FILTERS);
    setRawPage(0);
  };

  const removeActiveFilter = (key: keyof FilterValues, value?: string) => {
    const next = { ...activeFilters };
    if (key === "startDate" || key === "endDate") {
      (next as any)[key] = null;
    } else if (Array.isArray((next as any)[key])) {
      (next as any)[key] = value ? ((next as any)[key] as string[]).filter((item) => item !== value) : [];
    } else if (key === "touchMode") {
      next.touchMode = "event";
    } else if (key === "displayMode") {
      next.displayMode = "weekly";
    }
    setDraftFilters(next);
    setActiveFilters(next);
    setRawPage(0);
  };



  const handleSort = (field: string) => {
    if (rawSortBy === field) {
      setRawSortDirection(rawSortDirection === "asc" ? "desc" : "asc");
    } else {
      setRawSortBy(field);
      setRawSortDirection("desc");
    }
    setRawPage(0);
  };

  const handlePageChange = (_event: unknown, page: number) => {
    setRawPage(page);
  };

  const handleRowsPerPageChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    setRawPageSize(Number(event.target.value));
    setRawPage(0);
  };

  const handleRawFilterChange = (key: keyof RawColumnFilters, value: any) => {
    setRawFilters((prev) => ({ ...prev, [key]: value }));
    setRawPage(0);
  };

  const handleExport = async () => {
    setExporting(true);
    try {
      const params = {
        ...buildFilterParams(activeFilters),
        ...buildRawFilterParams(rawFilters),
        sort_by: rawSortBy,
        sort_direction: rawSortDirection,
      };
      const response = await axios.get(`${API_BASE}/api/reports/funnel-start/export`, {
        params: buildQueryParams(params),
        responseType: "blob",
      });
      const blob = new Blob([response.data], { type: "text/csv" });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = "raw_users.csv";
      link.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      console.error(err);
    } finally {
      setExporting(false);
    }
  };

  const normalizeSyncStatus = (value: SyncStatus | number | null | undefined) => {
    if (!value) return null;
    if (typeof value === "number") {
      return { ts: value, status: "ok" as const, error: null };
    }
    if (typeof value === "object" && typeof value.ts === "number") {
      return value as SyncStatus;
    }
    return null;
  };

  const fetchSyncStatus = async () => {
    try {
      const response = await axios.get(`${API_BASE}/api/admin/sync-status`);
      setLastIngestionStatus(normalizeSyncStatus(response.data?.last_ingestion));
      if (response.data?.replication) setReplStatus(response.data.replication);
      setLastIngestionSuccess(normalizeSyncStatus(response.data?.last_ingestion_success));
      setLastSmStatus(normalizeSyncStatus(response.data?.last_sm));
    } catch (err) {
      console.error(err);
    }
  };

  useEffect(() => {
    fetchSyncStatus();
    const timer = window.setInterval(fetchSyncStatus, 30000);
    return () => window.clearInterval(timer);
  }, []);

  const handleCreateMainReportBudget = async (
    weekStart: string,
    campaign: string,
    botKey: string | null,
    amount: number,
  ) => {
    await createBudget({ week_start: weekStart, campaign, bot_key: botKey, amount, currency: "USD" });
    refreshBudgets();
    refreshMainReport();
  };

  const handleSyncAll = async () => {
    setSyncing(true);
    setSyncMessage(null);
    try {
      await axios.post(`${API_BASE}/api/admin/sync-all`);
      setSyncMessage("Синхронизация всех источников запущена");
      fetchSyncStatus();
    } catch (err) {
      console.error(err);
      setSyncMessage("Ошибка запуска синхронизации");
    } finally {
      setSyncing(false);
    }
  };

  const handleSyncSm = async () => {
    setSyncing(true);
    setSyncMessage(null);
    try {
      await axios.post(`${API_BASE}/api/admin/sync-google-sheets`);
      setSyncMessage("Синхронизация SM запущена");
      fetchSyncStatus();
    } catch (err) {
      console.error(err);
      setSyncMessage("Ошибка запуска синхронизации SM");
    } finally {
      setSyncing(false);
    }
  };

  const handleSaveBots = async (botsToSave: BotOption[]) => {
    try {
      await Promise.all(
        botsToSave.map((bot) =>
          axios.post(`${API_BASE}/api/bots/registry`, {
            bot_key: bot.bot_key,
            display_name: bot.display_name || null,
            canonical_base: bot.canonical_base || null,
            is_active: bot.is_active,
          })
        )
      );
      await refreshDatabases();
    } catch (err) {
      console.error(err);
    }
  };

  const formatMsk = (ts: number | null | undefined) => {
    if (!ts) {
      return "—";
    }
    const date = new Date(ts * 1000);
    return new Intl.DateTimeFormat("ru-RU", {
      timeZone: "Europe/Moscow",
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    }).format(date);
  };

  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, []);

  // Dark mode handled via App.tsx ThemeProvider

  const nowMsk = new Date(now + 3 * 3600 * 1000)
    .toISOString()
    .replace("T", " ")
    .slice(11, 19);

  const syncColor = (status: SyncStatus | null, checkRepl = false): "success.main" | "warning.main" | "error.main" | "grey.400" => {
    if (!status?.ts) return "grey.400";
    if (status.status === "error") return "error.main";
    if (checkRepl && replStatus?.total) {
      return replStatus.streams_error.length > 0 ? "warning.main" : "success.main";
    }
    const age = now / 1000 - status.ts;
    if (age < 1800) return "success.main";
    if (age < 21600) return "warning.main";
    return "error.main";
  };

  const renderSyncInfo = (label: string, status: SyncStatus | null, checkRepl = false) => {
    const color = syncColor(status, checkRepl);
    const errorStreams = checkRepl && replStatus?.streams_error.length ? replStatus.streams_error : [];
    const replHealthy = checkRepl && !!replStatus?.total && replStatus.streams_error.length === 0;
    const isGreen = color === "success.main";
    const ageSec = status?.ts ? now / 1000 - status.ts : null;
    const timeDisplay = isGreen ? <strong>{nowMsk}</strong> : formatMsk(status?.ts ?? null);
    const hint = status?.status === "error"
      ? " (ошибка)"
      : errorStreams.length > 0
        ? ` (сбой: ${errorStreams.join(", ")})`
        : replHealthy
          ? null
        : ageSec !== null && ageSec > 1800
          ? ` (обн. ${Math.floor(ageSec / 60)} мин назад)`
          : null;

    return (
      <Typography variant="caption" sx={{ display: "flex", alignItems: "center", gap: 0.5 }}>
        <Box
          component="span"
          sx={{
            display: "inline-block", width: 7, height: 7,
            borderRadius: "50%", bgcolor: color, flexShrink: 0,
            ...(isGreen ? {
              "@keyframes pulse": { "0%, 100%": { opacity: 1 }, "50%": { opacity: 0.25 } },
              animation: "pulse 1.2s ease-in-out infinite",
            } : {}),
          }}
        />
        {label}: {timeDisplay}
        {hint && (
          <Typography component="span" variant="caption" color={color === "error.main" ? "error" : "text.secondary"}>
            {hint}
          </Typography>
        )}
      </Typography>
    );
  };

  const toErrorMessage = (value: unknown) => {
    if (!value) return null;
    if (typeof value === "string") return value;
    if (value instanceof Error) return value.message;
    try {
      return JSON.stringify(value);
    } catch {
      return "Ошибка";
    }
  };

  const alertMessage = toErrorMessage(
    filtersError ||
      error ||
      databasesError ||
      companiesError ||
      subscriptionsError ||
      budgetWeeklyError ||
      adMetricsError
      || roistatLessonsError
  );

  const fullDailySeries = useMemo(() => {
    if (!daily.length) {
      return [];
    }
    const rawDates = daily.map((point) => parseISO(point.date)).filter(isValid);
    if (!rawDates.length) {
      return [];
    }
    const dataMinDate = new Date(Math.min(...rawDates.map((d) => d.getTime())));
    const dataMaxDate = new Date(Math.max(...rawDates.map((d) => d.getTime())));
    const requestedStart = activeFilters.startDate ?? dataMinDate;
    const requestedEnd = activeFilters.endDate ?? dataMaxDate;
    const minDate = requestedStart > dataMinDate ? requestedStart : dataMinDate;
    const maxDate = requestedEnd < dataMaxDate ? requestedEnd : dataMaxDate;
    if (maxDate < minDate) {
      return [];
    }
    const usersByDate = new Map(daily.map((point) => [point.date, point.users]));
    const series: { date: string; users: number }[] = [];
    let cursor = minDate;
    while (cursor <= maxDate) {
      const key = formatDate(cursor, "yyyy-MM-dd");
      series.push({ date: key, users: usersByDate.get(key) ?? 0 });
      cursor = addDays(cursor, 1);
    }
    return series;
  }, [daily, activeFilters.startDate, activeFilters.endDate]);

  const periodRange = useMemo(() => {
    if (!fullDailySeries.length) {
      return { start: null as Date | null, end: null as Date | null };
    }
    const lastPoint = fullDailySeries[fullDailySeries.length - 1];
    const maxEnd = parseISO(lastPoint.date);
    const requestedEnd = periodEndDate && isValid(periodEndDate) ? periodEndDate : maxEnd;
    const end = requestedEnd > maxEnd ? maxEnd : requestedEnd;
    if (periodPreset === "all") {
      return { start: parseISO(fullDailySeries[0].date), end };
    }
    const days =
      periodPreset === "7d" ? 7 : periodPreset === "14d" ? 14 : 30;
    return { start: addDays(end, -(days - 1)), end };
  }, [fullDailySeries, periodEndDate, periodPreset]);

  const periodSeries = useMemo(() => {
    if (!fullDailySeries.length || !periodRange.start || !periodRange.end) {
      return [];
    }
    return fullDailySeries.filter((point) => {
      const date = parseISO(point.date);
      return date >= periodRange.start! && date <= periodRange.end!;
    });
  }, [fullDailySeries, periodRange.start, periodRange.end]);

  const hasSelectedBots = activeFilters.bots.length > 0;
  const totalbRows = useMemo(() => {
    const summaryMap = new Map<string, any>(
      summaryBotsForFunnel.rows.map((row) => [row.group, row])
    );
    const botKeys = new Set<string>();
    const selectedBots = activeFilters.bots ?? [];
    summaryMap.forEach((_value, key) => {
      if (key) {
        botKeys.add(key);
      }
    });
    budgetAggregates.byBot.forEach((_value, key) => {
      if (key) {
        botKeys.add(key);
      }
    });
    selectedBots.forEach((key) => {
      if (key) {
        botKeys.add(key);
      }
    });
    const filteredBotKeys =
      selectedBots.length > 0 ? Array.from(botKeys).filter((key) => selectedBots.includes(key)) : Array.from(botKeys);
    return filteredBotKeys.map((botKey) => {
      const summaryRow = summaryMap.get(botKey);
      const base = summaryRow ?? {
        group: botKey,
        entered: 0,
        new_in_system: 0,
        old_in_system: 0,
        lead: 0,
        platform: 0,
        learning: 0,
        course: 0,
        simulator: 0,
        interview: 0,
        passed: 0,
        offer: 0,
        contract: 0,
        distance_grinding: 0,
      };
      const agg = budgetAggregates.byBot.get(botKey);
      return {
        ...base,
        impressions: agg?.impressions ?? 0,
        clicks: agg?.clicks ?? 0,
        spend: agg?.spend ?? 0,
        budget: agg?.budget ?? 0,
      };
    });
  }, [summaryBotsForFunnel.rows, budgetAggregates, activeFilters.bots]);
  const totalbFunnelRows = useMemo(
    () => {
      return totalbRows.map((row) => ({
        group: row.group,
        entered: row.entered ?? 0,
        new_in_system: row.new_in_system ?? 0,
        old_in_system: row.old_in_system ?? 0,
        lead: row.lead ?? 0,
        platform: row.platform ?? 0,
        learning: row.learning ?? 0,
        course: row.course ?? 0,
        simulator: row.simulator ?? 0,
        interview: row.interview ?? 0,
        passed: row.passed ?? 0,
        offer: row.offer ?? 0,
        contract: row.contract ?? 0,
        distance_grinding: row.distance_grinding ?? 0,
      }));
    },
    [totalbRows]
  );

  const totalaRows = useMemo(() => {
    const companySet = new Set(companies.map((item) => item.name));
    const mainReportCompanyMap = new Map<string, any>();
    mainReportRows.forEach((row) => {
      const key = row.company || "";
      if (!key) return;
      const current = mainReportCompanyMap.get(key) ?? {
        group: key,
        entered: 0,
        new_in_system: 0,
        old_in_system: 0,
        lead: 0,
        platform: 0,
        learning: 0,
        course: 0,
        simulator: 0,
        interview: 0,
        passed: 0,
        offer: 0,
        contract: 0,
        distance_grinding: 0,
      };
      current.entered += row.entered_all ?? 0;
      current.new_in_system += row.new_in_system ?? 0;
      current.old_in_system += row.old_in_system ?? 0;
      current.lead += row.almanah_starts ?? 0;
      current.platform += row.platform_cnt ?? 0;
      current.learning += row.started_learning ?? 0;
      current.course += row.completed_course ?? 0;
      current.interview += row.interview_reached ?? 0;
      current.offer += row.offer_received ?? 0;
      current.contract += row.contract_signed ?? 0;
      current.distance_grinding += row.distance_grinding ?? 0;
      mainReportCompanyMap.set(key, current);
    });
    const merged: typeof summaryCompanies.rows = [];
    for (const name of companySet) {
      merged.push(
        mainReportCompanyMap.get(name) ?? {
          group: name,
          entered: 0,
          new_in_system: 0,
          old_in_system: 0,
          lead: 0,
          platform: 0,
          learning: 0,
          course: 0,
          simulator: 0,
          interview: 0,
          passed: 0,
          offer: 0,
          contract: 0,
          distance_grinding: 0,
        }
      );
    }
    for (const [group, row] of mainReportCompanyMap.entries()) {
      if (!companySet.has(group)) {
        merged.push(row);
      }
    }
    budgetAggregates.byCampaign.forEach((_value, key) => {
      if (key && !companySet.has(key) && !mainReportCompanyMap.has(key)) {
        merged.push({
          group: key,
          entered: 0,
          new_in_system: 0,
          old_in_system: 0,
          lead: 0,
          platform: 0,
          learning: 0,
          course: 0,
          simulator: 0,
          interview: 0,
          passed: 0,
          offer: 0,
          contract: 0,
          distance_grinding: 0,
        });
      }
    });
    const isEmptyGroup = (value: string) => {
      const normalized = value.trim().toLowerCase();
      return (
        normalized === "-" ||
        normalized === "—" ||
        normalized === "(none)" ||
        normalized === "none" ||
        normalized === "null" ||
        normalized === "нет метки"
      );
    };
    return merged
      .filter((row) => row.group && !isEmptyGroup(row.group))
      .map((row) => {
        const agg = budgetAggregates.byCampaign.get(row.group);
        return {
          ...row,
          impressions: agg?.impressions ?? 0,
          clicks: agg?.clicks ?? 0,
          spend: agg?.spend ?? 0,
          budget: agg?.budget ?? 0,
        };
      });
  }, [companies, mainReportRows, budgetAggregates]);

  const activeFilterChips = useMemo(() => {
    return buildActiveFilterChips(activeFilters, resolveBotLabel);
  }, [activeFilters, resolveBotLabel]);

  const totalbSummary = useMemo(() => {
    const starts = sumBy(totalbRows, (row) => row.entered);
    const leads = sumBy(totalbRows, (row) => row.lead);
    const contracts = sumBy(totalbRows, (row) => row.contract);
    const spend = sumBy(totalbRows, (row) => row.spend ?? row.budget ?? 0);
    const bestBot = [...totalbRows].sort((a, b) => b.contract - a.contract || b.lead - a.lead)[0];
    return {
      starts,
      leads,
      contracts,
      spend,
      leadCr: starts ? (leads / starts) * 100 : 0,
      contractCr: leads ? (contracts / leads) * 100 : 0,
      bestBot,
    };
  }, [totalbRows]);

  const mainSummary = useMemo(() => {
    const budget = sumBy(mainReportRows, (row) => row.budget);
    const starts = sumBy(mainReportRows, (row) => (row.almanah_starts ?? 0) + (row.direct_source_cnt ?? 0));
    const platform = sumBy(mainReportRows, (row) => row.platform_cnt);
    const startedLearning = sumBy(mainReportRows, (row) => row.started_learning);
    const contracts = sumBy(mainReportRows, (row) => row.contract_signed);
    const course = sumBy(mainReportRows, (row) => row.completed_course);
    return {
      budget,
      starts,
      platform,
      startedLearning,
      contracts,
      course,
      cpaStart: starts ? budget / starts : 0,
      cpaContract: contracts ? budget / contracts : 0,
      platformCr: starts ? (platform / starts) * 100 : 0,
      learningCr: platform ? (startedLearning / platform) * 100 : 0,
      contractCr: course ? (contracts / course) * 100 : 0,
    };
  }, [mainReportRows]);

  const tgsubsSummary = useMemo(() => {
    const current = subscriptionsOverall?.[subscriptionsOverall.length - 1];
    const previous = subscriptionsOverall?.[subscriptionsOverall.length - 2];
    const currentBotStarts = current?.bot_starts ?? 0;
    const currentChannelSubs = current?.channel_subscribed ?? 0;
    const currentSaloonSubs = current?.saloon_subscribed ?? 0;
    return {
      activeChannel: subscriptionsSummary?.channel.active ?? 0,
      activeSaloon: subscriptionsSummary?.saloon.active ?? 0,
      totalChannel: subscriptionsSummary?.channel.total_in_channel ?? 0,
      totalSaloon: subscriptionsSummary?.saloon.total_in_channel ?? 0,
      currentBotStarts,
      currentChannelSubs,
      currentSaloonSubs,
      startsDelta: previous ? calcDelta(currentBotStarts, previous.bot_starts ?? 0) : 0,
      channelDelta: previous ? calcDelta(currentChannelSubs, previous.channel_subscribed ?? 0) : 0,
      saloonDelta: previous ? calcDelta(currentSaloonSubs, previous.saloon_subscribed ?? 0) : 0,
    };
  }, [subscriptionsOverall, subscriptionsSummary]);


  const renderTabContent = () => {
    if (
      !hasSelectedBots &&
      tab !== "totalb" &&
      tab !== "totala" &&
      tab !== "tgsubs" &&
      tab !== "weekly" &&
      tab !== "lessons" &&
      tab !== "rawutm" &&
      tab !== "usersearch" &&
      tab !== "raw" &&
      tab !== "faq" &&
      tab !== "overview" &&
      tab !== "main"
    ) {
      return (
        <Alert severity="info" sx={{ mt: 2 }}>
          Выберите хотя бы одну базу и нажмите «ПРИМЕНИТЬ», чтобы увидеть данные.
        </Alert>
      );
    }
    switch (tab) {
      case "funnel":
        return (
          <FunnelView
            stages={stages}
            userScope={draftFilters.userScope}
            onUserScopeChange={(value) => {
              setDraftFilters((prev) => ({ ...prev, userScope: value }));
              setActiveFilters((prev) => ({ ...prev, userScope: value }));
            }}
            touchMode={activeFilters.touchMode}
          />
        );
      case "usersearch":
        return <UserSearchPanel registryBotKeys={activeBotKeys} />;
      case "rawutm":
        return (
          <Box>
            <Alert severity="info" sx={{ mt: 2, mb: 2 }}>
              Вкладка источников строится по всей системе. Выбор баз, РК и UTM сверху на неё не влияет; используется только выбранный диапазон дат.
            </Alert>
            <FunnelTreeTable
              tree={funnelTree.tree}
              loading={funnelTree.loading}
              error={funnelTree.error}
            />
          </Box>
        );
      case "totalb":
        {
          const selectedBotRow = selectedBotKey
            ? totalbRows.find((r) => r.group === selectedBotKey) ?? null
            : null;
          const selectedFunnelBotRow = selectedBotKey
            ? totalbFunnelRows.find((r) => r.group === selectedBotKey) ?? null
            : null;
          const funnelTotal = ["entered", "lead", "platform", "learning", "course", "simulator", "interview", "passed", "offer", "contract", "distance_grinding"]
            .reduce((acc, key) => {
              acc[key] = totalbFunnelRows.reduce((sum, row) => sum + ((row as any)[key] || 0), 0);
              return acc;
            }, {} as Record<string, number>);
          const funnelStages: Record<string, number> = selectedFunnelBotRow
            ? {
                entered: selectedFunnelBotRow.entered,
                lead: selectedFunnelBotRow.lead,
                platform: selectedFunnelBotRow.platform,
                learning: selectedFunnelBotRow.learning,
                course: selectedFunnelBotRow.course,
                simulator: (selectedFunnelBotRow as any).simulator ?? 0,
                interview: selectedFunnelBotRow.interview,
                passed: selectedFunnelBotRow.passed,
                offer: selectedFunnelBotRow.offer,
                contract: selectedFunnelBotRow.contract,
                distance_grinding: (selectedFunnelBotRow as any).distance_grinding ?? 0,
              }
            : funnelTotal;
          return (
            <Box className="app-page">
            <FunnelSummaryTable
              title="TotalB: Воронка по ботам"
              nameLabel="Бот"
              rows={totalbRows}
              nameResolver={(value) => botNameMap.get(value) || value}
              botLabelResolver={resolveBotLabel}
              startDate={activeFilters.startDate}
              endDate={activeFilters.endDate}
              selectedGroup={selectedBotKey}
              onGroupSelect={setSelectedBotKey}
              columnSettingsKey="bots"
              activeFilters={activeFilters}
              weeklySource="main_report"
            />
            <Box sx={{ display: "flex", alignItems: "center", gap: 1, mt: 1.5, mb: 0.5, flexWrap: "wrap" }}>
              <Typography variant="body2" color="text.secondary" sx={{ fontWeight: 600 }}>
                Воронка:
              </Typography>
              {selectedBotRow ? (
                <>
                  <Chip
                    label={botNameMap.get(selectedBotKey!) || selectedBotKey}
                    size="small"
                    color="primary"
                    onDelete={() => setSelectedBotKey(null)}
                  />
                  <Typography variant="caption" color="text.secondary">
                    (нажмите x чтобы показать Total)
                  </Typography>
                </>
              ) : (
                <Chip label="Total (все боты)" size="small" variant="outlined" />
              )}
            </Box>
            <FunnelView
              stages={funnelStages}
              userScope={funnelUserScope}
              onUserScopeChange={(value) => {
                setFunnelUserScope(value);
              }}
              touchMode={activeFilters.touchMode}
            />
          </Box>
          );
        }
      case "totala":
        return (
          <Box className="app-page">
            <FunnelSummaryTable
              title="TotalA: Воронка по РК"
              nameLabel="Рекламная компания"
              rows={totalaRows}
              groupType="company"
              groupMeta={totalACompanyMeta}
              botLabelResolver={resolveBotLabel}
              startDate={activeFilters.startDate}
              endDate={activeFilters.endDate}
              activeFilters={activeFilters}
              weeklySource="main_report"
            />
          </Box>
        );
      case "tgsubs":
        return (
          <Box className="app-page">
        <SubscriptionsComparePanel
          data={subscriptionsData}
          overall={subscriptionsOverall}
          summary={subscriptionsSummary}
          loading={subscriptionsLoading}
          groupBy={subscriptionsGroupBy}
          onGroupByChange={setSubscriptionsGroupBy}
          interval={subscriptionsInterval}
              onIntervalChange={setSubscriptionsInterval}
            />
          </Box>
        );
      case "weekly":
        return (
          <Box className="app-page">
            <WeeklyTable
              rows={roistatWeeklyRows}
              loading={roistatWeeklyLoading}
              error={roistatWeeklyError}
              selectedMonth={weeklyMonth}
              onSelectedMonthChange={setWeeklyMonth}
              companies={advertisingCompanies}
              onCreateBudget={async (weekStart, campaign, botKey, amount) => {
                const [y, m, d] = weekStart.split("-").map(Number);
                const start = new Date(y, m - 1, d);
                const perDay = amount / 7;
                for (let i = 0; i < 7; i++) {
                  const cur = new Date(start);
                  cur.setDate(start.getDate() + i);
                  const dayStr = `${cur.getFullYear()}-${String(cur.getMonth() + 1).padStart(2, "0")}-${String(cur.getDate()).padStart(2, "0")}`;
                  await createBudget({ week_start: dayStr, campaign, bot_key: botKey, amount: perDay, currency: "USD" });
                }
                refreshRoistatWeekly();
              }}
            />
            <RoistatWeeklyTreeTable
              tree={roistatWeeklyTree}
              loading={roistatWeeklyTreeLoading}
              error={roistatWeeklyTreeError}
            />
          </Box>
        );
      case "lessons":
        return (
          <Box className="app-page">
            <Alert severity="info" sx={{ mt: 2, mb: 2 }}>
              Во вкладке PokerHub Lessons база фиксирована на <strong>lead</strong>. Период сверху фильтрует по <strong>дате регистрации в боте</strong>. Для фильтрации по дате начала обучения используйте отдельный фильтр внутри таблицы.
            </Alert>
            <RoistatLessonsTable
              courses={roistatLessonCourses}
              loading={roistatLessonsLoading}
              error={roistatLessonsError}
              pokerhubUserId={pokerhubUserId}
              onPokerhubUserIdChange={setPokerhubUserId}
              learnStartDateFrom={learnStartDateFrom}
              learnStartDateTo={learnStartDateTo}
              onLearnStartDateFromChange={setLearnStartDateFrom}
              onLearnStartDateToChange={setLearnStartDateTo}
            />
          </Box>
        );
      case "raw":
        return (
          <Box className="app-page">
            <Stack direction="row" spacing={2} alignItems="center" className="app-actions-row">
              <Button variant="outlined" startIcon={<RefreshIcon />} onClick={refresh}>
                Обновить
              </Button>
              <Button variant="contained" onClick={handleExport} disabled={exporting}>
                {exporting ? "Экспорт..." : "Экспорт CSV"}
              </Button>
            </Stack>
            <RawUsersTable
              users={raw}
              total={rawTotal}
              loading={loading}
              page={rawPage}
              pageSize={rawPageSize}
              sortBy={rawSortBy}
              sortDirection={rawSortDirection}
              onSort={handleSort}
              onPageChange={handlePageChange}
              onRowsPerPageChange={handleRowsPerPageChange}
              filters={rawFilters}
              onFilterChange={handleRawFilterChange}
              botOptions={botOptions}
              companyOptions={companies}
              utmSourceOptions={utmSource}
              utmCampaignOptions={utmCampaign}
              utmMediumOptions={utmMedium}
              utmContentOptions={utmContent}
              utmTermOptions={utmTerm}
            />
          </Box>
        );
      case "main":
        return (
          <Box className="app-page">
            <MainReportTable
              rows={mainReportRows}
              botRows={mainReportBotRows}
              weekTotals={mainReportWeekTotals}
              loading={mainReportLoading}
              error={mainReportError}
              botNameResolver={resolveBotLabel}
              selectedMonth={weeklyMonth}
              onSelectedMonthChange={setWeeklyMonth}
              companies={advertisingCompanies}
              onCreateBudget={handleCreateMainReportBudget}
            />
          </Box>
        );
      case "faq":
        return (
          <Box sx={{ p: 3 }}>
            <FaqPanel />
          </Box>
        );
      default:
        return (
          <Box className="app-page">
            <Grid container spacing={2} mt={2}>
              <Grid item xs={12} md={4}>
                <MetricCard label="Users at Funnel Start" value={total?.total_users ?? "—"} />
              </Grid>
              <Grid item xs={12} md={4}>
                <MetricCard label="Total Budget" value={total?.total_budget ?? "—"} />
              </Grid>
              <Grid item xs={12} md={4}>
                <MetricCard
                  label="CAC"
                  value={total?.cac ? total.cac.toFixed(2) : "—"}
                  caption="Cost per acquisition"
                />
              </Grid>
              <Grid item xs={12}>
                <Stack direction="row" spacing={2} alignItems="center" sx={{ mt: 1, flexWrap: "wrap" }}>
                  <Typography variant="subtitle2">Период:</Typography>
                  <ButtonGroup size="small">
                    <Button
                      variant={periodPreset === "7d" ? "contained" : "outlined"}
                      onClick={() => setPeriodPreset("7d")}
                    >
                      7 дней
                    </Button>
                    <Button
                      variant={periodPreset === "14d" ? "contained" : "outlined"}
                      onClick={() => setPeriodPreset("14d")}
                    >
                      14 дней
                    </Button>
                    <Button
                      variant={periodPreset === "30d" ? "contained" : "outlined"}
                      onClick={() => setPeriodPreset("30d")}
                    >
                      Месяц
                    </Button>
                    <Button
                      variant={periodPreset === "all" ? "contained" : "outlined"}
                      onClick={() => setPeriodPreset("all")}
                    >
                      Все время
                    </Button>
                  </ButtonGroup>
                  <TextField
                    size="small"
                    label="Дата по"
                    type="date"
                    value={
                      periodRange.end && isValid(periodRange.end)
                        ? formatDate(periodRange.end, "yyyy-MM-dd")
                        : ""
                    }
                    onChange={(event) =>
                      setPeriodEndDate(event.target.value ? new Date(event.target.value) : null)
                    }
                    InputLabelProps={{ shrink: true }}
                  />
                </Stack>
              <LineChartCard
                title="Daily New Users"
                data={periodSeries}
              />
            </Grid>
            </Grid>
            {overviewSubsOverall.length > 0 && (() => {
              const options = [
                { label: "7д", days: 7 },
                { label: "30д", days: 30 },
                { label: "3м", days: 90 },
                { label: "6м", days: 180 },
                { label: "1г", days: 365 },
                { label: "Всё", days: 0 },
              ];
              const cutoff = (days: number) => {
                if (!days) return "";
                const d = new Date();
                d.setDate(d.getDate() - days);
                return d.toISOString().slice(0, 10);
              };
              const filterDaily = (data: { date: string; users: number }[], key: string) => {
                const c = cutoff(getChartPeriod(key));
                return c ? data.filter((r) => r.date >= c) : data;
              };
              const PeriodBar = ({ chartKey }: { chartKey: string }) => (
                <Stack direction="row" spacing={0.5}>
                  {options.map((option) => (
                    <Button
                      key={option.label}
                      size="small"
                      variant={getChartPeriod(chartKey) === option.days ? "contained" : "text"}
                      onClick={() => setChartPeriod(chartKey, option.days)}
                      sx={{ minWidth: 0, px: 1, py: 0.2, fontSize: "0.68rem", lineHeight: 1.4 }}
                    >
                      {option.label}
                    </Button>
                  ))}
                </Stack>
              );
              const allSeries = {
                kostyli: overviewSubsOverall.map((r) => ({ date: r.date, users: Math.max(0, (r.bot_starts || 0) - (r.almanah_starts || 0)) })),
                almanah: overviewSubsOverall.map((r) => ({ date: r.date, users: r.almanah_starts || 0 })),
                kanal: overviewSubsOverall.map((r) => ({ date: r.date, users: r.channel_subscribed || 0 })),
                saloon: overviewSubsOverall.map((r) => ({ date: r.date, users: r.saloon_subscribed || 0 })),
              };
              return (
                <Grid container spacing={2} mt={0}>
                  {([
                    ["Daily New Users — Костыли", "kostyli", allSeries.kostyli, "#1565c0"],
                    ["Daily New Users — Альманах", "almanah", allSeries.almanah, "#6a1b9a"],
                    ["Daily New Users — Канал (КД)", "kanal", allSeries.kanal, "#2e7d32"],
                    ["Daily New Users — Салун", "saloon", allSeries.saloon, "#00695c"],
                  ] as [string, string, { date: string; users: number }[], string][]).map(([title, key, data, color]) => (
                    <Grid item xs={12} md={6} key={key}>
                      <Paper sx={{ p: 2 }}>
                        <Stack direction="row" justifyContent="space-between" alignItems="center" mb={1}>
                          <Typography variant="subtitle1" fontWeight={700}>{title}</Typography>
                          <PeriodBar chartKey={key} />
                        </Stack>
                        <ResponsiveContainer width="100%" height={200}>
                          <LineChart data={filterDaily(data, key)} margin={{ top: 4, right: 16, bottom: 4, left: 0 }}>
                            <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                            <XAxis dataKey="date" tick={{ fontSize: 10 }} />
                            <YAxis allowDecimals={false} tick={{ fontSize: 10 }} width={35} />
                            <RechartTooltip />
                            <Line type="monotone" dataKey="users" stroke={color} strokeWidth={2} dot={false} />
                          </LineChart>
                        </ResponsiveContainer>
                      </Paper>
                    </Grid>
                  ))}
                </Grid>
              );
            })()}
            {overviewWeeklyRows.length > 0 && (() => {
              const options = [
                { label: "4н", days: 28 },
                { label: "3м", days: 90 },
                { label: "6м", days: 180 },
                { label: "1г", days: 365 },
                { label: "Всё", days: 0 },
              ];
              const cutoff = (days: number) => {
                if (!days) return "";
                const d = new Date();
                d.setDate(d.getDate() - days);
                return d.toISOString().slice(0, 10);
              };
              const filterWeekly = (key: string) => {
                const c = cutoff(getChartPeriod(key));
                return c ? overviewWeeklyRows.filter((r) => (r.week_start || "") >= c) : overviewWeeklyRows;
              };
              const PeriodBar = ({ chartKey }: { chartKey: string }) => (
                <Stack direction="row" spacing={0.5}>
                  {options.map((option) => (
                    <Button
                      key={option.label}
                      size="small"
                      variant={getChartPeriod(chartKey) === option.days ? "contained" : "text"}
                      onClick={() => setChartPeriod(chartKey, option.days)}
                      sx={{ minWidth: 0, px: 1, py: 0.2, fontSize: "0.68rem", lineHeight: 1.4 }}
                    >
                      {option.label}
                    </Button>
                  ))}
                </Stack>
              );
              return (
                <Box mt={2}>
                  <Paper sx={{ p: 2, mb: 2 }}>
                    <Stack direction="row" justifyContent="space-between" alignItems="center" mb={1}>
                      <Typography variant="subtitle1" fontWeight={700}>Регистрации на PokerHub (по неделям)</Typography>
                      <PeriodBar chartKey="platform" />
                    </Stack>
                    <ResponsiveContainer width="100%" height={200}>
                      <LineChart data={filterWeekly("platform")} margin={{ top: 4, right: 16, bottom: 4, left: 0 }}>
                        <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                        <XAxis dataKey="week_start" tick={{ fontSize: 10 }} />
                        <YAxis allowDecimals={false} tick={{ fontSize: 10 }} width={35} />
                        <RechartTooltip />
                        <Line type="monotone" dataKey="platform" name="Регистрации" stroke="#0277bd" strokeWidth={2} dot={false} />
                      </LineChart>
                    </ResponsiveContainer>
                  </Paper>

                  <Paper sx={{ p: 2, mb: 2 }}>
                    <Stack direction="row" justifyContent="space-between" alignItems="center" mb={1}>
                      <Typography variant="subtitle1" fontWeight={700}>Старт обучения по направлениям (по неделям)</Typography>
                      <PeriodBar chartKey="learning" />
                    </Stack>
                    <ResponsiveContainer width="100%" height={220}>
                      <LineChart data={filterWeekly("learning")} margin={{ top: 4, right: 16, bottom: 4, left: 0 }}>
                        <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                        <XAxis dataKey="week_start" tick={{ fontSize: 10 }} />
                        <YAxis allowDecimals={false} tick={{ fontSize: 10 }} width={35} />
                        <RechartTooltip />
                        <Legend iconType="circle" iconSize={8} wrapperStyle={{ fontSize: 12 }} />
                        <Line type="monotone" dataKey="started_learning" name="ТОТАЛ" stroke="#37474f" strokeWidth={2} dot={false} />
                        <Line type="monotone" dataKey="mtt" name="МТТ" stroke="#1565c0" strokeWidth={2} dot={false} />
                        <Line type="monotone" dataKey="spin" name="СПИН" stroke="#6a1b9a" strokeWidth={2} dot={false} />
                        <Line type="monotone" dataKey="cash" name="КЕШ" stroke="#e65100" strokeWidth={2} dot={false} />
                      </LineChart>
                    </ResponsiveContainer>
                  </Paper>

                  <Paper sx={{ p: 2, mb: 2 }}>
                    <Stack direction="row" justifyContent="space-between" alignItems="center" mb={1}>
                      <Typography variant="subtitle1" fontWeight={700}>Окончили курс по направлениям (по неделям)</Typography>
                      <PeriodBar chartKey="completed" />
                    </Stack>
                    <ResponsiveContainer width="100%" height={220}>
                      <BarChart data={filterWeekly("completed")} margin={{ top: 4, right: 16, bottom: 4, left: 0 }}>
                        <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                        <XAxis dataKey="week_start" tick={{ fontSize: 10 }} />
                        <YAxis allowDecimals={false} tick={{ fontSize: 10 }} width={35} />
                        <RechartTooltip />
                        <Legend iconType="circle" iconSize={8} wrapperStyle={{ fontSize: 12 }} />
                        <Bar dataKey="completed_mtt" name="МТТ" fill="#1565c0" stackId="a" />
                        <Bar dataKey="completed_spin" name="СПИН" fill="#6a1b9a" stackId="a" />
                        <Bar dataKey="completed_cash" name="КЕШ" fill="#e65100" stackId="a" />
                      </BarChart>
                    </ResponsiveContainer>
                  </Paper>

                  <Paper sx={{ p: 2, mb: 2 }}>
                    <Stack direction="row" justifyContent="space-between" alignItems="center" mb={1}>
                      <Typography variant="subtitle1" fontWeight={700}>Оффер Лиды (по неделям)</Typography>
                      <PeriodBar chartKey="offer" />
                    </Stack>
                    <ResponsiveContainer width="100%" height={200}>
                      <BarChart data={filterWeekly("offer")} margin={{ top: 4, right: 16, bottom: 4, left: 0 }}>
                        <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                        <XAxis dataKey="week_start" tick={{ fontSize: 10 }} />
                        <YAxis allowDecimals={false} tick={{ fontSize: 10 }} width={35} />
                        <RechartTooltip />
                        <Bar dataKey="offer_received" name="Оффер лиды" fill="#2e7d32" />
                      </BarChart>
                    </ResponsiveContainer>
                  </Paper>

                  <Paper sx={{ p: 2, mb: 2 }}>
                    <Stack direction="row" justifyContent="space-between" alignItems="center" mb={1}>
                      <Typography variant="subtitle1" fontWeight={700}>Контракт Лиды (по неделям)</Typography>
                      <PeriodBar chartKey="contract" />
                    </Stack>
                    <ResponsiveContainer width="100%" height={200}>
                      <BarChart data={filterWeekly("contract")} margin={{ top: 4, right: 16, bottom: 4, left: 0 }}>
                        <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                        <XAxis dataKey="week_start" tick={{ fontSize: 10 }} />
                        <YAxis allowDecimals={false} tick={{ fontSize: 10 }} width={35} />
                        <RechartTooltip />
                        <Bar dataKey="contract_signed" name="Контракт лиды" fill="#00695c" />
                      </BarChart>
                    </ResponsiveContainer>
                  </Paper>
                </Box>
              );
            })()}
            <Paper sx={{ mt: 2, p: 2 }}>
              <Typography variant="h6" mb={1}>
                Breakdown
              </Typography>
              <BreakdownTable data={breakdown} loading={loading} groupBy={breakdownGroup} />
            </Paper>
          </Box>
        );
    }
  };

  const renderActiveFiltersBar = () => {
    if (!activeFilterChips.length) {
      return null;
    }
    return (
      <Box
        sx={{
          px: 2.5,
          py: 1.2,
          borderBottom: "1px solid var(--app-shell-border)",
          background: "linear-gradient(180deg, rgba(37,99,235,0.03), transparent)",
        }}
      >
        <Stack direction={{ xs: "column", md: "row" }} spacing={1} alignItems={{ xs: "flex-start", md: "center" }} justifyContent="space-between">
          <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
            <Typography sx={{ fontSize: 11.5, fontWeight: 800, color: "var(--c-ink2)", textTransform: "uppercase", letterSpacing: "0.08em" }}>
              Active Filters
            </Typography>
            {activeFilterChips.map((chip) => (
              <Chip
                key={`${chip.key}-${chip.value || chip.label}`}
                label={chip.label}
                onDelete={() => removeActiveFilter(chip.key, chip.value)}
                size="small"
                variant="outlined"
                sx={{ background: "var(--app-panel-muted)" }}
              />
            ))}
          </Stack>
          <Button size="small" onClick={resetAllFilters}>Сбросить все</Button>
        </Stack>
      </Box>
    );
  };

  const renderSummaryHero = () => {
    if (tab === "totalb") {
      return (
        <Box className="app-page" sx={{ pt: 0 }}>
          <KpiGrid>
            <KpiCard label="Starts" value={formatCompact(totalbSummary.starts)} stripe="var(--c-blue)" foot={<span>Лиды: {formatCompact(totalbSummary.leads)}</span>} pill={<Pill variant="blue">{formatPctCompact(totalbSummary.leadCr)} CR в лид</Pill>} />
            <KpiCard label="Contracts" value={formatCompact(totalbSummary.contracts)} stripe="var(--c-green)" foot={<span>Spend: {formatMoneyCompact(totalbSummary.spend)}</span>} pill={<Pill variant="green">{formatPctCompact(totalbSummary.contractCr)} CR в контракт</Pill>} />
            <KpiCard label="Best Bot" value={totalbSummary.bestBot ? resolveBotLabel(totalbSummary.bestBot.group) : "—"} stripe="var(--c-amber)" foot={<span>Контрактов: {formatCompact(totalbSummary.bestBot?.contract ?? 0)}</span>} pill={<Pill variant="amber">Топ по выходу</Pill>} />
          </KpiGrid>
        </Box>
      );
    }
    if (tab === "main") {
      return (
        <Box className="app-page" sx={{ pt: 0 }}>
          <KpiGrid>
            <KpiCard label="Budget" value={formatMoneyCompact(mainSummary.budget)} stripe="var(--c-blue)" foot={<span>Starts: {formatCompact(mainSummary.starts)}</span>} pill={<Pill variant="blue">{mainSummary.cpaStart ? `${mainSummary.cpaStart.toFixed(2)} $/start` : "—"}</Pill>} />
            <KpiCard label="Platform" value={formatCompact(mainSummary.platform)} stripe="var(--c-purple)" foot={<span>Обучение: {formatCompact(mainSummary.startedLearning)}</span>} pill={<Pill variant="purple">{formatPctCompact(mainSummary.platformCr)} CR в ПХ</Pill>} />
            <KpiCard label="Contracts" value={formatCompact(mainSummary.contracts)} stripe="var(--c-green)" foot={<span>Курс: {formatCompact(mainSummary.course)}</span>} pill={<Pill variant="green">{formatPctCompact(mainSummary.contractCr)} CR курса</Pill>} />
            <KpiCard label="Contract Cost" value={mainSummary.cpaContract ? `$${mainSummary.cpaContract.toFixed(2)}` : "—"} stripe="var(--c-amber)" foot={<span>CR в обучение: {formatPctCompact(mainSummary.learningCr)}</span>} pill={<Pill variant="amber">unit economics</Pill>} />
          </KpiGrid>
        </Box>
      );
    }
    if (tab === "tgsubs") {
      return (
        <Box className="app-page" sx={{ pt: 0 }}>
          <KpiGrid>
            <KpiCard label="Card House" value={formatCompact(tgsubsSummary.activeChannel)} stripe="var(--c-green)" foot={<span>Всего в канале: {formatCompact(tgsubsSummary.totalChannel)}</span>} pill={<Pill variant={tgsubsSummary.channelDelta >= 0 ? "green" : "red"}>{tgsubsSummary.channelDelta.toFixed(1)}%</Pill>} />
            <KpiCard label="Saloon" value={formatCompact(tgsubsSummary.activeSaloon)} stripe="var(--c-purple)" foot={<span>Всего в салуне: {formatCompact(tgsubsSummary.totalSaloon)}</span>} pill={<Pill variant={tgsubsSummary.saloonDelta >= 0 ? "green" : "red"}>{tgsubsSummary.saloonDelta.toFixed(1)}%</Pill>} />
            <KpiCard label="Latest Bot Starts" value={formatCompact(tgsubsSummary.currentBotStarts)} stripe="var(--c-blue)" foot={<span>Подписок КД: {formatCompact(tgsubsSummary.currentChannelSubs)}</span>} pill={<Pill variant={tgsubsSummary.startsDelta >= 0 ? "green" : "red"}>{tgsubsSummary.startsDelta.toFixed(1)}%</Pill>} />
          </KpiGrid>
        </Box>
      );
    }
    return null;
  };

  const TAB_TITLES: Record<string, string> = {
    overview:   "Сводка",
    funnel:     "Воронка конверсий",
    main:       "Основной отчёт",
    totalb:     "Боты — TotalB",
    totala:     "Кампании — TotalA",
    tgsubs:     "TG Подписки",
    weekly:     "Weekly",
    lessons:    "Уроки PokerHub",
    raw:        "RAW Users",
    rawutm:     "Источники",
    usersearch: "Поиск пользователей",
    faq:        "FAQ",
  };
  const TAB_SUBTITLES: Record<string, string> = {
    overview: "Общая картина по продукту, бюджету и динамике пользователей",
    totalb: "Воронка по ботам с основными этапами и стоимостью",
    main: "Главный перформанс-отчет по неделям, РК и ботам",
    tgsubs: "Стартовые метрики и подписки по каналам и салуну",
    raw: "Сырые пользователи и детальная фильтрация источников",
  };

  const liveColorRaw = syncColor(lastIngestionStatus, true);
  const liveColor: "green" | "yellow" | "red" =
    liveColorRaw === "success.main" ? "green" :
    liveColorRaw === "warning.main" ? "yellow" : "red";

  const liveDisplay = liveColor === "green" ? nowMsk : formatMsk(lastIngestionStatus?.ts ?? null);

  return (
    <AppShell
      sidebar={
        <Sidebar
          tab={tab as "overview" | "totalb" | "funnel" | "main" | "tgsubs" | "lessons" | "raw" | "usersearch" | "faq"}
          onTabChange={(t) => setTab(t as typeof tab)}
          admin={{
            onBots:       () => setBotDialogOpen(true),
            onCompanies:  () => setCompanyDialogOpen(true),
            onBudgets:    () => setBudgetDialogOpen(true),
            onAdMetrics:  () => setAdMetricsDialogOpen(true),
            onAccess:     () => setAccessDialogOpen(true),
            onEmployees:  () => setEmployeeDialogOpen(true),
            onSettings:   () => setSettingsDialogOpen(true),
            onRefresh:    refreshDatabases,
            refreshing:   loadingDatabases,
          }}
        />
      }
      topbar={
        <Topbar
          title={TAB_TITLES[tab] || "Dashboard"}
          subtitle={TAB_SUBTITLES[tab] || ""}
          breadcrumb="Analytics / Reports"
          liveTime={liveDisplay}
          liveColor={liveColor}
          darkMode={darkMode}
          onToggleDark={onToggleDark}
          onRefresh={handleSyncAll}
          refreshing={syncing}
        />
      }
      filterbar={
        tab !== "usersearch" ? (
          <div style={{
            background: "var(--c-surface)",
            borderBottom: "1px solid var(--c-border)",
            padding: "0 20px",
            flexShrink: 0,
            overflowX: "auto",
          }}>
            <FilterPanel
              filters={draftFilters}
              botOptions={botOptions}
              companies={companies}
              utmSource={utmSource}
              utmCampaign={utmCampaign}
              utmMedium={utmMedium}
              utmContent={utmContent}
              utmTerm={utmTerm}
              onChange={handleFilterChange}
              onApply={handleApplyFilters}
              onPresetSelect={applyPresetFilters}
              onResetFilters={resetAllFilters}
              loading={loadingOptions}
              showDisplayMode={tab === "main"}
            />
          </div>
        ) : undefined
      }
    >
      {tab !== "usersearch" && renderActiveFiltersBar()}
      {alertMessage && (
        <Alert severity="error" sx={{ mb: 2, borderRadius: "var(--r-md)" }}>
          {alertMessage}
        </Alert>
      )}
      {syncMessage && (
        <Alert severity="info" sx={{ mb: 1, borderRadius: "var(--r-md)" }}>
          {syncMessage}
        </Alert>
      )}
      {renderSummaryHero()}
      {renderTabContent()}
      <BotRegistryDialog
        open={botDialogOpen}
        bots={registryBots}
        onClose={() => setBotDialogOpen(false)}
        onSave={handleSaveBots}
      />
      <AdvertisingCompaniesDialog
        open={companyDialogOpen}
        companies={advertisingCompanies}
        bots={registryBots}
        onClose={() => setCompanyDialogOpen(false)}
        onSave={async (updatedCompanies) => {
          for (const company of updatedCompanies) {
            await upsertCompany(company);
          }
        }}
        onDelete={deleteCompany}
      />
      <AccessManagerDialog
        open={accessDialogOpen}
        onClose={() => setAccessDialogOpen(false)}
        entries={accessEntries}
        loading={accessLoading}
        error={accessError}
        onAdd={grantAccess}
        onRemove={revokeAccess}
      />
      <EmployeeRegistryDialog
        open={employeeDialogOpen}
        onClose={() => setEmployeeDialogOpen(false)}
        entries={employeeEntries}
        loading={employeeLoading}
        error={employeeError}
        onSave={saveEmployees}
      />
      <BudgetDialog
        open={budgetDialogOpen}
        budgets={budgets}
        loading={budgetsLoading}
        companies={advertisingCompanies}
        onClose={() => setBudgetDialogOpen(false)}
        onCreate={createBudget}
        onUpdate={updateBudget}
        onDelete={deleteBudget}
      />
      <AdMetricsDialog
        open={adMetricsDialogOpen}
        rows={adMetricsRows}
        loading={adMetricsLoading}
        budgets={budgets}
        companies={advertisingCompanies}
        onClose={() => setAdMetricsDialogOpen(false)}
        onCreate={createAdMetrics}
        onUpdate={updateAdMetrics}
        onDelete={deleteAdMetrics}
      />
      <SystemSettingsDialog
        open={settingsDialogOpen}
        settings={systemSettings}
        logs={systemLogs}
        marketingDailySettings={marketingDailySettings}
        marketingDailyPreview={marketingDailyPreview}
        marketingDailyHistory={marketingDailyHistory}
        marketingDailyEnabledForUser={Boolean(marketingDailySettings)}
        loading={systemLoading}
        error={systemError}
        onClose={() => setSettingsDialogOpen(false)}
        onSave={updateSystemSettings}
        onSaveMarketingDaily={updateMarketingDaily}
        onRefreshMarketingDailyPreview={refreshMarketingDailyPreview}
        onSendMarketingDailyTest={sendMarketingDailyTest}
        onResendMarketingDaily={resendMarketingDaily}
        onRefresh={refreshSystemSettings}
        onRebuildCompanies={rebuildCompanies}
        onSyncAll={handleSyncAll}
        onSyncSm={handleSyncSm}
      />
    </AppShell>
  );
};

export default OverviewPage;
