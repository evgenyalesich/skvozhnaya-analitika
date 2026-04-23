import React, { useEffect, useMemo, useState, useRef } from "react";
import { addDays, format as formatDate, parseISO, startOfWeek, isValid } from "date-fns";
import {
  LineChart, Line, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip as RechartTooltip,
  Legend, ResponsiveContainer,
} from "recharts";
import Box from "@mui/material/Box";
import Grid from "@mui/material/Grid";
import Typography from "@mui/material/Typography";
import Button from "@mui/material/Button";
import Stack from "@mui/material/Stack";
import ButtonGroup from "@mui/material/ButtonGroup";
import Alert from "@mui/material/Alert";
import Paper from "@mui/material/Paper";
import TextField from "@mui/material/TextField";
import Chip from "@mui/material/Chip";
import Tooltip from "@mui/material/Tooltip";
import RefreshIcon from "@mui/icons-material/Refresh";
import LogoutIcon from "@mui/icons-material/Logout";
import FilterPanel from "../components/FilterPanel";
import OverviewTabs from "../components/OverviewTabs";
import MetricCard from "../components/MetricCard";
import LineChartCard from "../components/LineChartCard";
import RawUsersTable from "../components/RawUsersTable";
import BreakdownTable from "../components/BreakdownTable";
import FunnelView from "../components/FunnelView";
import BotRegistryDialog from "../components/BotRegistryDialog";
import AdvertisingCompaniesDialog from "../components/AdvertisingCompaniesDialog";
import AccessManagerDialog from "../components/AccessManagerDialog";
import EmployeeRegistryDialog from "../components/EmployeeRegistryDialog";
import FunnelSummaryTable from "../components/FunnelSummaryTable";
import SubscriptionsComparePanel from "../components/SubscriptionsComparePanel";
import BudgetDialog from "../components/BudgetDialog";
import AdMetricsDialog from "../components/AdMetricsDialog";
import SystemSettingsDialog from "../components/SystemSettingsDialog";
import MainReportTable from "../components/MainReportTable";
import RoistatLessonsTable from "../components/RoistatLessonsTable";
import UserSearchPanel from "../components/UserSearchPanel";
import FaqPanel from "../components/FaqPanel";
import {
  useReports,
  FilterValues,
  RawReportParams,
  RawColumnFilters,
  buildFilterParams,
  buildRawFilterParams,
  buildQueryParams,
} from "../hooks/useReports";
import { useFilterOptions } from "../hooks/useFilterOptions";
import axios from "axios";
import { useBotRegistry, BotOption } from "../hooks/useBotRegistry";
import { BotSelectOption } from "../components/FilterPanel";
import { useFunnelSummary, FunnelSummaryRow } from "../hooks/useFunnelSummary";
import { useAdvertisingCompanies } from "../hooks/useAdvertisingCompanies";
import { useTelegramAccess } from "../hooks/useTelegramAccess";
import { useEmployeeRegistry } from "../hooks/useEmployeeRegistry";
import { useSubscriptionsCompare } from "../hooks/useSubscriptionsCompare";
import { useBudgets } from "../hooks/useBudgets";
import { useBudgetWeeklyReport } from "../hooks/useBudgetWeeklyReport";
import { useAdMetrics } from "../hooks/useAdMetrics";
import { useSystemSettings } from "../hooks/useSystemSettings";
import { useRoistatLessons } from "../hooks/useRoistatLessons";
import { useMainReport } from "../hooks/useMainReport";
import { useRoistatWeekly } from "../hooks/useRoistatWeekly";
import { useRawUsers } from "../hooks/useRawUsers";

const DEFAULT_FILTERS: FilterValues = {
  startDate: null,
  endDate: null,
  bots: [],
  companies: [],
  utmSource: [],
  utmCampaign: [],
  utmMedium: [],
  utmContent: [],
  utmTerm: [],
  userScope: "all",
  touchMode: "event",
  displayMode: "weekly",
};

const DEFAULT_RAW_FILTERS: RawColumnFilters = {
  botKeys: [],
  tgUserId: "",
  utmSource: [],
  utmCampaign: [],
  utmMedium: [],
  utmContent: [],
  utmTerm: [],
  advertisingCompanies: [],
  convertedToLead: null,
  registeredPlatform: null,
  startedLearning: null,
  completedCourse: null,
  usedSimulator: null,
  interviewReached: null,
  interviewPassed: null,
  offerReceived: null,
  contractSigned: null,
  distanceGrinding: null,
  interviewReachedStatus: "",
  interviewPassedStatus: "",
  offerReceivedStatus: "",
  contractSignedStatus: "",
  channelSubscribed: null,
  communityMember: null,
  teamMember: null,
  communityMemberStatus: "",
  internalStatus: "",
  userBlock: null,
  userStatus: "",
  firstTouchPresent: null,
  lastTouchPresent: null,
};

interface SyncStatus {
  ts: number;
  status: "ok" | "error";
  error?: string | null;
}

const API_BASE = import.meta.env.VITE_API_BASE || "";

const TABS: Array<
  "overview" | "totalb" | "main" | "tgsubs" | "lessons" | "raw" | "usersearch" | "faq"
> = [
  "overview",
  "totalb",
  "main",
  "tgsubs",
  "lessons",
  "raw",
  "usersearch",
  "faq",
];

const OverviewPage: React.FC<{ userId?: number | null; currentUsername?: string | null; onLogout?: () => void }> = ({
  userId,
  currentUsername,
  onLogout,
}) => {
  const [draftFilters, setDraftFilters] = useState<FilterValues>(DEFAULT_FILTERS);
  const [activeFilters, setActiveFilters] = useState<FilterValues>(DEFAULT_FILTERS);
  const [tab, setTab] = useState<
    "overview" | "totalb" | "main" | "tgsubs" | "lessons" | "raw" | "usersearch" | "faq"
  >(
    "overview"
  );
  const [breakdownGroup, setBreakdownGroup] = useState("utm_source");
  const [rawPage, setRawPage] = useState(0);
  const [rawPageSize, setRawPageSize] = useState(50);
  const [rawSortBy, setRawSortBy] = useState("created_at");
  const [rawSortDirection, setRawSortDirection] = useState<"asc" | "desc">("desc");
  const [exporting, setExporting] = useState(false);
  const [subscriptionsGroupBy, setSubscriptionsGroupBy] = useState<"campaign" | "bot" | "overall">("bot");
  const [subscriptionsInterval, setSubscriptionsInterval] = useState<"day" | "week">("week");
  const initialWeeklyMonth = "all";
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
          label: bot.display_name || bot.canonical_base || bot.bot_key,
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
    () => (key: string) => botNameMap.get(key) || key,
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
    saveAll: saveAllCompanies,
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
  // TG SUBS shows all bots regardless of global bot/company filter,
  // but keeps selected period to support period-based CPA calculations.
  const tgsubsFilters = useMemo(() => ({ ...activeFilters, bots: [], companies: [] }), [activeFilters]);
  const {
    data: subscriptionsData,
    overall: subscriptionsOverall,
    summary: subscriptionsSummary,
    loading: subscriptionsLoading,
    error: subscriptionsError,
  } = useSubscriptionsCompare(tgsubsFilters, {
    groupBy: subscriptionsGroupBy,
    interval: subscriptionsInterval,
    enabled: tab === "tgsubs",
    pollMs: 30000,
  });

  const overviewFilters = useMemo(() => ({
    ...activeFilters,
    startDate: null,
    endDate: null,
  }), [activeFilters]);

  const {
    overall: overviewSubsOverall,
  } = useSubscriptionsCompare(overviewFilters, {
    groupBy: "overall",
    interval: "day",
    enabled: tab === "overview",
    pollMs: 30000,
  });
  const {
    budgets,
    loading: budgetsLoading,
    error: budgetsError,
    refresh: refreshBudgets,
    createBudget,
    updateBudget,
    deleteBudget,
  } = useBudgets();

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
  } = useAdMetrics();
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
  } = useSystemSettings();
  const {
    data: budgetWeeklyData,
    error: budgetWeeklyError,
  } = useBudgetWeeklyReport(activeFilters, "day");
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
  const weeklyEventStart = firstTouchStart;
  const weeklyEventEnd = firstTouchEnd;
  const weeklyFirstTouchStart = firstTouchStart;
  const weeklyFirstTouchEnd = firstTouchEnd;
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
    [
      activeFilters.bots,
      activeFilters.companies,
      activeFilters.utmSource,
      activeFilters.utmCampaign,
      activeFilters.utmMedium,
      activeFilters.utmContent,
      activeFilters.utmTerm,
    ],
  );

  const {
    rows: overviewWeeklyRows,
  } = useRoistatWeekly(
    undefined,
    undefined,
    "event",
    tab === "overview",
    undefined,
    undefined,
    activeFilters.bots.length > 0 ? activeFilters.bots : undefined,
  );

  const {
    rows: mainReportRows,
    botRows: mainReportBotRows,
    weekTotals: mainReportWeekTotals,
    loading: mainReportLoading,
    error: mainReportError,
    refresh: refreshMainReport,
  } = useMainReport(
    weeklyEventStart,
    weeklyEventEnd,
    tab === "main",
    activeFilters.touchMode,
    weeklyFirstTouchStart,
    weeklyFirstTouchEnd,
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
    loading,
    error,
    refresh,
  } = useReports(activeFilters, rawParams, rawFilters, breakdownGroup, {
    enabled: tab === "overview",
    pollMs: 30000,
  });

  const {
    raw,
    rawTotal,
    loading: rawLoading,
    error: rawError,
    refresh: refreshRaw,
  } = useRawUsers(rawParams, rawFilters, activeFilters, activeFilters.touchMode, tab === "raw");

  // Derive bot summary from main report data — guarantees identical numbers
  const summaryBots = useMemo<FunnelSummaryRow[]>(() => {
    const map = new Map<string, FunnelSummaryRow>();
    for (const row of mainReportBotRows) {
      const key = row.bot_key ?? "Без бота";
      const prev = map.get(key) ?? {
        group: key,
        entered: 0, lead: 0, new_in_system: 0, old_in_system: 0,
        platform: 0, learning: 0, course: 0, simulator: 0,
        interview: 0, passed: 0, offer: 0, contract: 0,
        distance_grinding: 0,
      };
      map.set(key, {
        ...prev,
        entered: prev.entered + (row.entered_all ?? 0),
        lead: prev.lead + (row.almanah_starts ?? 0),
        new_in_system: prev.new_in_system + (row.new_in_system ?? 0),
        old_in_system: prev.old_in_system + Math.max(0, (row.entered_all ?? 0) - (row.new_in_system ?? 0)),
        platform: prev.platform + (row.platform_cnt ?? 0),
        learning: prev.learning + (row.started_learning ?? 0),
        course: prev.course + (row.completed_course ?? 0),
        interview: prev.interview + (row.interview_reached ?? 0),
        offer: prev.offer + (row.offer_received ?? 0),
        contract: prev.contract + (row.contract_signed ?? 0),
        distance_grinding: prev.distance_grinding + (row.distance_grinding ?? 0),
      });
    }
    return Array.from(map.values());
  }, [mainReportBotRows]);
  const scopedFunnelFilters = useMemo(
    () => ({ ...activeFilters, userScope: funnelUserScope }),
    [activeFilters, funnelUserScope]
  );
  const summaryBotsForFunnel = useFunnelSummary(scopedFunnelFilters, "bot_key", {
    enabled: tab === "totalb",
    pollMs: 30000,
  });

  const [botsStagesTotal, setBotsStagesTotal] = useState<Record<string, number> | undefined>(undefined);
  useEffect(() => {
    if (tab !== "totalb" || activeFilters.touchMode !== "event") {
      setBotsStagesTotal(undefined);
      return;
    }
    const params = buildQueryParams(buildFilterParams(activeFilters));
    axios.get(`${API_BASE}/api/reports/funnel-start/stages`, { params })
      .then((res) => setBotsStagesTotal(res.data.stages || undefined))
      .catch(() => setBotsStagesTotal(undefined));
  }, [tab, activeFilters]);

  const handleFilterChange = (key: string, value: any) => {
    setDraftFilters((prev) => ({ ...prev, [key]: value }));
    // Touch mode should apply immediately to avoid stale table/funnel state
    // when switching back and forth between event/first/last touch.
    if (key === "touchMode") {
      setActiveFilters((prev) => ({ ...prev, touchMode: value }));
      setRawPage(0);
    }
    if (key === "displayMode") {
      setActiveFilters((prev) => ({ ...prev, displayMode: value }));
    }
  };

  const handleApplyFilters = () => {
    setActiveFilters({ ...draftFilters });
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
        ...buildFilterParams({
          ...activeFilters,
          bots: [],
          companies: [],
          utmSource: [],
          utmCampaign: [],
          utmMedium: [],
          utmContent: [],
          utmTerm: [],
          userScope: "all",
          touchMode: "event",
        }),
        ...buildRawFilterParams(rawFilters),
        touch_mode: activeFilters.touchMode === "first_touch" ? "first" : activeFilters.touchMode === "last_touch" ? "last" : "event",
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

  const handleCreateMainReportBudget = async (
    weekStart: string,
    campaign: string,
    botKey: string | null,
    amount: number,
  ) => {
    await createBudget({
      week_start: weekStart,
      campaign,
      bot_key: botKey,
      amount,
      currency: "USD",
    });
    refreshBudgets();
    refreshMainReport();
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

  const nowMsk = new Date(now + 3 * 3600 * 1000)
    .toISOString()
    .replace("T", " ")
    .slice(11, 19);

  const syncColor = (status: SyncStatus | null, checkRepl = false): "success.main" | "warning.main" | "error.main" | "grey.400" => {
    if (!status?.ts) return "grey.400";
    if (status.status === "error") return "error.main";
    const age = now / 1000 - status.ts;
    if (checkRepl && replStatus && replStatus.streams_error.length > 0) return "warning.main";
    if (age < 1800) return "success.main";
    if (age < 21600) return "warning.main";
    return "error.main";
  };

  const renderSyncInfo = (label: string, status: SyncStatus | null, checkRepl = false) => {
    const color = syncColor(status, checkRepl);
    const errorStreams = checkRepl && replStatus?.streams_error.length ? replStatus.streams_error : [];
    const isGreen = color === "success.main";
    const ageSec = status?.ts ? now / 1000 - status.ts : null;
    const timeDisplay = isGreen ? <strong>{nowMsk}</strong> : formatMsk(status?.ts ?? null);
    const hint = status?.status === "error"
      ? " (ошибка)"
      : errorStreams.length > 0
        ? ` (сбой: ${errorStreams.join(", ")})`
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
    const minDate = activeFilters.startDate ?? new Date(Math.min(...rawDates.map((d) => d.getTime())));
    const maxDate = activeFilters.endDate ?? new Date(Math.max(...rawDates.map((d) => d.getTime())));
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
    const end = periodEndDate ?? parseISO(lastPoint.date);
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
    // BOTs has its own source-bot -> lead transition semantics.
    const sourceRows = summaryBotsForFunnel.rows;
    const summaryMap = new Map(sourceRows.map((row) => [row.group, row]));
    const selectedBots = activeFilters.bots ?? [];
    // Use only bots from the registry; apply bot filter if selected
    const baseKeys = selectedBots.length > 0
      ? activeBotKeys.filter((key) => selectedBots.includes(key))
      : activeBotKeys;
    return baseKeys.map((botKey) => {
      const base = summaryMap.get(botKey) ?? {
        group: botKey,
        entered: 0,
        lead: 0,
        platform: 0,
        learning: 0,
        course: 0,
        interview: 0,
        passed: 0,
        offer: 0,
        contract: 0,
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
  }, [summaryBotsForFunnel.rows, budgetAggregates, activeBotKeys, activeFilters.bots]);
  const totalbFunnelRows = useMemo(() => {
    const summaryMap = new Map(summaryBotsForFunnel.rows.map((row) => [row.group, row]));
    const selectedBots = activeFilters.bots ?? [];
    const baseKeys = selectedBots.length > 0
      ? activeBotKeys.filter((key) => selectedBots.includes(key))
      : activeBotKeys;
    return baseKeys.map((botKey) => (
      summaryMap.get(botKey) ?? {
        group: botKey,
        entered: 0,
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
    ));
  }, [summaryBotsForFunnel.rows, activeBotKeys, activeFilters.bots]);
  const totalbTotal = useMemo<Record<string, number>>(() => {
    const keys = ["entered", "lead", "platform", "learning", "course", "simulator", "interview", "passed", "offer", "contract", "distance_grinding"];
    return keys.reduce((acc, k) => {
      acc[k] = totalbRows.reduce((s, r) => s + ((r as any)[k] || 0), 0);
      return acc;
    }, {} as Record<string, number>);
  }, [totalbRows]);

  const attributionModeLabel = useMemo(() => {
    if (activeFilters.touchMode === "first_touch") {
      return "First Touch";
    }
    if (activeFilters.touchMode === "last_touch") {
      return "Last Touch (before learning)";
    }
    return "Event";
  }, [activeFilters.touchMode]);

  const renderTabContent = () => {
    if (
      !hasSelectedBots &&
      tab !== "totalb" &&
      tab !== "main" &&
      tab !== "tgsubs" &&
      tab !== "lessons" &&
      tab !== "usersearch" &&
      tab !== "faq" &&
      tab !== "raw"
    ) {
      return (
        <Alert severity="info" sx={{ mt: 2 }}>
          Выберите хотя бы одну базу и нажмите «ПРИМЕНИТЬ», чтобы увидеть данные.
        </Alert>
      );
    }
    switch (tab) {
      case "usersearch":
        return <UserSearchPanel registryBotKeys={activeBotKeys} />;
      case "faq":
        return <FaqPanel />;
      case "totalb": {
        const selectedBotRow = selectedBotKey
          ? totalbRows.find((r) => r.group === selectedBotKey) ?? null
          : null;
        const selectedFunnelBotRow = selectedBotKey
          ? totalbFunnelRows.find((r) => r.group === selectedBotKey) ?? null
          : null;
        const funnelTotal = ["entered", "lead", "platform", "learning", "course", "simulator", "interview", "passed", "offer", "contract", "distance_grinding"]
          .reduce((acc, k) => {
            acc[k] = totalbFunnelRows.reduce((s, r) => s + ((r as any)[k] || 0), 0);
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
          : (activeFilters.touchMode === "event" && botsStagesTotal)
            ? botsStagesTotal
            : funnelTotal;
        return (
          <Box>
            <FunnelSummaryTable
              title="BOTs: Воронка по ботам"
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
            />
            <Box sx={{ display: "flex", alignItems: "center", gap: 1, mt: 1.5, mb: 0.5 }}>
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
                    (нажмите × чтобы показать Total)
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
            />
          </Box>
        );
      }
      case "main":
        return (
          <Box>
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
      case "tgsubs":
        return (
          <Box>
            <SubscriptionsComparePanel
              data={subscriptionsData}
              overall={subscriptionsOverall}
              summary={subscriptionsSummary}
              loading={subscriptionsLoading}
              groupBy={subscriptionsGroupBy}
              onGroupByChange={setSubscriptionsGroupBy}
              interval={subscriptionsInterval}
              onIntervalChange={setSubscriptionsInterval}
              resolveName={resolveBotLabel}
            />
          </Box>
        );
      case "lessons":
        return (
          <Box>
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
          <Box>
            <Stack direction="row" spacing={2} alignItems="center" mt={2}>
              <Button variant="outlined" startIcon={<RefreshIcon />} onClick={refreshRaw}>
                Обновить
              </Button>
              <Button variant="contained" onClick={handleExport} disabled={exporting}>
                {exporting ? "Экспорт..." : "Экспорт CSV"}
              </Button>
            </Stack>
            {rawError && (
              <Alert severity="error" sx={{ mt: 1 }}>{rawError}</Alert>
            )}
            <RawUsersTable
              users={raw}
              total={rawTotal}
              loading={rawLoading}
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
              userId={userId}
            />
          </Box>
        );
      default:
        return (
          <Box>
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
                title="Daily New Users (все источники)"
                data={periodSeries}
              />
            </Grid>
            </Grid>

            {/* ── Per-source daily charts ─────────────────────────────── */}
            {overviewSubsOverall.length > 0 && (() => {
              const OPTS = [{ l: "7д", d: 7 }, { l: "30д", d: 30 }, { l: "3м", d: 90 }, { l: "6м", d: 180 }, { l: "1г", d: 365 }, { l: "Всё", d: 0 }];
              const cutoff = (days: number) => {
                if (!days) return "";
                const d = new Date(); d.setDate(d.getDate() - days);
                return d.toISOString().slice(0, 10);
              };
              const filterDaily = (data: {date:string;users:number}[], key: string) => {
                const c = cutoff(getChartPeriod(key));
                return c ? data.filter(r => r.date >= c) : data;
              };
              const PeriodBar = ({ chartKey }: { chartKey: string }) => (
                <Stack direction="row" spacing={0.5}>
                  {OPTS.map(o => (
                    <Button key={o.l} size="small"
                      variant={getChartPeriod(chartKey) === o.d ? "contained" : "text"}
                      onClick={() => setChartPeriod(chartKey, o.d)}
                      sx={{ minWidth: 0, px: 1, py: 0.2, fontSize: "0.68rem", lineHeight: 1.4 }}
                    >{o.l}</Button>
                  ))}
                </Stack>
              );
              const allSeries = {
                kostyli: overviewSubsOverall.map(r => ({ date: r.date, users: Math.max(0, (r.bot_starts||0)-(r.almanah_starts||0)) })),
                almanah: overviewSubsOverall.map(r => ({ date: r.date, users: r.almanah_starts||0 })),
                kanal:   overviewSubsOverall.map(r => ({ date: r.date, users: r.channel_subscribed||0 })),
                saloon:  overviewSubsOverall.map(r => ({ date: r.date, users: r.saloon_subscribed||0 })),
              };
              return (
                <Grid container spacing={2} mt={0}>
                  {([
                    ["Daily New Users — Костыли", "kostyli", allSeries.kostyli, "#1565c0"],
                    ["Daily New Users — Альманах", "almanah", allSeries.almanah, "#6a1b9a"],
                    ["Daily New Users — Канал (КД)", "kanal",  allSeries.kanal,   "#2e7d32"],
                    ["Daily New Users — Салун",     "saloon", allSeries.saloon,  "#00695c"],
                  ] as [string, string, {date:string;users:number}[], string][]).map(([title, key, data, color]) => (
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

            {/* ── Weekly funnel charts ─────────────────────────────────── */}
            {overviewWeeklyRows.length > 0 && (() => {
              const OPTS = [{ l: "4н", d: 28 }, { l: "3м", d: 90 }, { l: "6м", d: 180 }, { l: "1г", d: 365 }, { l: "Всё", d: 0 }];
              const cutoff = (days: number) => {
                if (!days) return "";
                const d = new Date(); d.setDate(d.getDate() - days);
                return d.toISOString().slice(0, 10);
              };
              const filterWeekly = (key: string) => {
                const c = cutoff(getChartPeriod(key));
                return c ? overviewWeeklyRows.filter(r => (r.week_start||"") >= c) : overviewWeeklyRows;
              };
              const PeriodBar = ({ chartKey }: { chartKey: string }) => (
                <Stack direction="row" spacing={0.5}>
                  {OPTS.map(o => (
                    <Button key={o.l} size="small"
                      variant={getChartPeriod(chartKey) === o.d ? "contained" : "text"}
                      onClick={() => setChartPeriod(chartKey, o.d)}
                      sx={{ minWidth: 0, px: 1, py: 0.2, fontSize: "0.68rem", lineHeight: 1.4 }}
                    >{o.l}</Button>
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
                        <Line type="monotone" dataKey="mtt"  name="МТТ"  stroke="#1565c0" strokeWidth={2} dot={false} />
                        <Line type="monotone" dataKey="spin" name="СПИН" stroke="#6a1b9a" strokeWidth={2} dot={false} />
                        <Line type="monotone" dataKey="cash" name="КЕШ"  stroke="#e65100" strokeWidth={2} dot={false} />
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
                        <Bar dataKey="completed_mtt"  name="МТТ"  fill="#1565c0" stackId="a" />
                        <Bar dataKey="completed_spin" name="СПИН" fill="#6a1b9a" stackId="a" />
                        <Bar dataKey="completed_cash" name="КЕШ"  fill="#e65100" stackId="a" />
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
          </Box>
        );
    }
  };

  return (
    <section>
      <Box display="flex" alignItems="center" justifyContent="space-between" mt={2} mb={1}>
        <Typography variant="h4">Analytics Dashboard</Typography>
        {(currentUsername || userId) && (
          <Stack direction="row" spacing={1} alignItems="center">
            <Chip
              icon={
                <Box
                  component="span"
                  sx={{
                    width: 20,
                    height: 20,
                    borderRadius: "50%",
                    background: "linear-gradient(135deg, #1c5cff 0%, #3f7bff 100%)",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    color: "#fff",
                    fontSize: 11,
                    fontWeight: 700,
                    flexShrink: 0,
                  }}
                >
                  {(currentUsername?.[0] ?? "?").toUpperCase()}
                </Box>
              }
              label={currentUsername ? `@${currentUsername}` : `#${userId}`}
              variant="outlined"
              size="small"
              sx={{ fontWeight: 600 }}
            />
            <Tooltip title="Выйти">
              <Button
                size="small"
                variant="outlined"
                color="error"
                startIcon={<LogoutIcon fontSize="small" />}
                onClick={onLogout}
                sx={{ textTransform: "none" }}
              >
                Выйти
              </Button>
            </Tooltip>
          </Stack>
        )}
      </Box>
      <Box mb={1} mt={2} display="flex" alignItems="center" justifyContent="space-between" flexWrap="wrap">
        <Stack direction="row" spacing={1} alignItems="center">
          <Button size="small" onClick={refreshDatabases} startIcon={<RefreshIcon />} disabled={loadingDatabases}>
            Обновить список баз
          </Button>
          <Button size="small" variant="outlined" onClick={() => setBotDialogOpen(true)}>
            Настроить базы
          </Button>
          <Button
            size="small"
            variant="outlined"
            onClick={() => setCompanyDialogOpen(true)}
            disabled={loadingCompanies}
          >
            Настроить РК
          </Button>
          <Button size="small" variant="outlined" onClick={() => setBudgetDialogOpen(true)}>
            Бюджеты
          </Button>
          <Button size="small" variant="outlined" onClick={() => setAdMetricsDialogOpen(true)}>
            Рекламные метрики
          </Button>
          <Button size="small" variant="outlined" onClick={() => setSettingsDialogOpen(true)}>
            Настройки обновлений
          </Button>
          <Button
            size="small"
            variant="outlined"
            onClick={() => setAccessDialogOpen(true)}
            sx={{ textTransform: "none" }}
          >
            Доступы
          </Button>
          <Button
            size="small"
            variant="outlined"
            onClick={() => setEmployeeDialogOpen(true)}
            sx={{ textTransform: "none" }}
          >
            Сотрудники
          </Button>
          {loadingDatabases && <Typography variant="caption">Обновляю...</Typography>}
          {syncMessage && <Typography variant="caption">{syncMessage}</Typography>}
        </Stack>
        <Stack direction="row" spacing={2} alignItems="center">
          {renderSyncInfo("Обновление баз (MSK)", lastIngestionStatus, true)}
          {renderSyncInfo("Обновление SM (MSK)", lastSmStatus)}
        </Stack>
      </Box>
      {tab !== "usersearch" && tab !== "faq" && (
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
          loading={loadingOptions}
          showDisplayMode={tab === "main"}
        />
      )}
      {alertMessage && (
        <Alert severity="error" sx={{ mb: 2 }}>
          {alertMessage}
        </Alert>
      )}
      <OverviewTabs value={tab} onChange={setTab} />
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
        onSave={saveAllCompanies}
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
        marketingDailyEnabledForUser={userId === 542149705 || userId === 6717031233}
        loading={systemLoading}
        error={systemError}
        onClose={() => setSettingsDialogOpen(false)}
        onSave={updateSystemSettings}
        onSaveMarketingDaily={updateMarketingDaily}
        onRefreshMarketingDailyPreview={async () => {
          await refreshMarketingDailyPreview();
        }}
        onSendMarketingDailyTest={async () => {
          await sendMarketingDailyTest();
        }}
        onResendMarketingDaily={async () => {
          await resendMarketingDaily();
        }}
        onRefresh={refreshSystemSettings}
        onRebuildCompanies={rebuildCompanies}
        onSyncAll={handleSyncAll}
        onSyncSm={handleSyncSm}
      />
    </section>
  );
};

export default OverviewPage;
