import React, { useEffect, useMemo, useRef, useState } from "react";
import { addDays, format as formatDate, parseISO, startOfWeek, isValid, startOfMonth, endOfMonth } from "date-fns";
import Box from "@mui/material/Box";
import Grid from "@mui/material/Grid";
import Typography from "@mui/material/Typography";
import Button from "@mui/material/Button";
import Stack from "@mui/material/Stack";
import ButtonGroup from "@mui/material/ButtonGroup";
import Alert from "@mui/material/Alert";
import Paper from "@mui/material/Paper";
import TextField from "@mui/material/TextField";
import Switch from "@mui/material/Switch";
import FormControlLabel from "@mui/material/FormControlLabel";
import RefreshIcon from "@mui/icons-material/Refresh";
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
import FunnelSummaryTable from "../components/FunnelSummaryTable";
import TouchFunnelTable from "../components/TouchFunnelTable";
import SubscriptionsComparePanel from "../components/SubscriptionsComparePanel";
import BudgetDialog from "../components/BudgetDialog";
import AdMetricsDialog from "../components/AdMetricsDialog";
import SystemSettingsDialog from "../components/SystemSettingsDialog";
import WeeklyTable from "../components/WeeklyTable";
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
import { useFunnelSummary } from "../hooks/useFunnelSummary";
import { useAdvertisingCompanies } from "../hooks/useAdvertisingCompanies";
import { useTelegramAccess } from "../hooks/useTelegramAccess";
import { useTouchFunnelSummary } from "../hooks/useTouchFunnelSummary";
import { useSubscriptionsCompare } from "../hooks/useSubscriptionsCompare";
import { useBudgets } from "../hooks/useBudgets";
import { useBudgetWeeklyReport } from "../hooks/useBudgetWeeklyReport";
import { useAdMetrics } from "../hooks/useAdMetrics";
import { useSystemSettings } from "../hooks/useSystemSettings";
import { useRoistatWeekly } from "../hooks/useRoistatWeekly";

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
  "overview" | "funnel" | "totalb" | "totala" | "totalc" | "tgsubs" | "weekly" | "raw" | "rawutm"
> = [
  "overview",
  "funnel",
  "totalb",
  "totala",
  "totalc",
  "tgsubs",
  "weekly",
  "raw",
  "rawutm",
];

const DETAILS_GROUPS = ["utm_source", "utm_campaign", "source_campaign", "advertising_company"];

const OverviewPage: React.FC = () => {
  const [draftFilters, setDraftFilters] = useState<FilterValues>(DEFAULT_FILTERS);
  const [activeFilters, setActiveFilters] = useState<FilterValues>(DEFAULT_FILTERS);
  const [tab, setTab] = useState<
    "overview" | "funnel" | "totalb" | "totala" | "totalc" | "tgsubs" | "weekly" | "raw" | "rawutm"
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
  const [touchMode, setTouchMode] = useState<"first" | "last">("last");
  const [weeklyUseFirstTouch, setWeeklyUseFirstTouch] = useState(false);
  const [weeklyMonth, setWeeklyMonth] = useState<string>("all");
  const [rawFilters, setRawFilters] = useState<RawColumnFilters>(DEFAULT_RAW_FILTERS);
  const [syncing, setSyncing] = useState(false);
  const [syncMessage, setSyncMessage] = useState<string | null>(null);
  const [lastIngestionStatus, setLastIngestionStatus] = useState<SyncStatus | null>(null);
  const [lastIngestionSuccess, setLastIngestionSuccess] = useState<SyncStatus | null>(null);
  const [lastSmStatus, setLastSmStatus] = useState<SyncStatus | null>(null);
  const [periodPreset, setPeriodPreset] = useState<"7d" | "14d" | "30d" | "all">("7d");
  const [periodEndDate, setPeriodEndDate] = useState<Date | null>(null);
  const prevDateFilters = useRef<{ start: Date | null; end: Date | null }>({
    start: DEFAULT_FILTERS.startDate,
    end: DEFAULT_FILTERS.endDate,
  });
  const {
    bots: registryBots,
    loading: loadingDatabases,
    error: databasesError,
    refresh: refreshDatabases,
  } = useBotRegistry();

  const [botDialogOpen, setBotDialogOpen] = useState(false);
  const [companyDialogOpen, setCompanyDialogOpen] = useState(false);
  const [accessDialogOpen, setAccessDialogOpen] = useState(false);
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
  } = useAdvertisingCompanies();

  const { entries: accessEntries, loading: accessLoading, error: accessError, add: grantAccess, remove: revokeAccess } =
    useTelegramAccess();
  // Removed overview widgets: keep hooks out to avoid extra requests.
  const {
    rows: touchFunnelRows,
    loading: touchFunnelLoading,
    error: touchFunnelError,
  } = useTouchFunnelSummary(activeFilters, touchMode);
  const {
    data: subscriptionsData,
    loading: subscriptionsLoading,
    error: subscriptionsError,
  } = useSubscriptionsCompare(activeFilters, {
    groupBy: subscriptionsGroupBy,
    interval: subscriptionsInterval,
    enabled: tab === "tgsubs",
  });
  const {
    budgets,
    loading: budgetsLoading,
    error: budgetsError,
    createBudget,
    updateBudget,
    deleteBudget,
  } = useBudgets();
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
    loading: systemLoading,
    error: systemError,
    refresh: refreshSystemSettings,
    update: updateSystemSettings,
    rebuildCompanies,
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

  const weeklyEventStart = firstTouchStart;
  const weeklyEventEnd = firstTouchEnd;
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
    weeklyUseFirstTouch,
    tab === "weekly",
    weeklyFirstTouchStart,
    weeklyFirstTouchEnd
  );

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
  } = useReports(activeFilters, rawParams, rawFilters, breakdownGroup);

  const summaryBots = useFunnelSummary(activeFilters, "bot_key");
  const summaryCompanies = useFunnelSummary(activeFilters, "advertising_company");

  const handleFilterChange = (key: string, value: any) => {
    setDraftFilters((prev) => ({ ...prev, [key]: value }));
  };

  const handleApplyFilters = () => {
    setActiveFilters({ ...draftFilters });
    setRawPage(0);
  };

  useEffect(() => {
    const prev = prevDateFilters.current;
    if (prev.start !== draftFilters.startDate || prev.end !== draftFilters.endDate) {
      setActiveFilters((current) => ({
        ...current,
        startDate: draftFilters.startDate,
        endDate: draftFilters.endDate,
      }));
      setRawPage(0);
      prevDateFilters.current = {
        start: draftFilters.startDate,
        end: draftFilters.endDate,
      };
    }
  }, [draftFilters.startDate, draftFilters.endDate]);


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

  const renderSyncInfo = (label: string, status: SyncStatus | null) => (
    <Typography variant="caption">
      {label}: {formatMsk(status?.ts ?? null)}
      {status?.status === "error" && (
        <Typography component="span" variant="caption" color="error">
          {" "}
          (при последнем обновлении была ошибка)
        </Typography>
      )}
    </Typography>
  );

  const alertMessage =
    filtersError ||
    error ||
    databasesError ||
    companiesError ||
    subscriptionsError ||
    touchFunnelError ||
    budgetWeeklyError ||
    adMetricsError;

  const fullDailySeries = useMemo(() => {
    if (!daily.length) {
      return [];
    }
    const rawDates = daily.map((point) => parseISO(point.date));
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
    const matchesPattern = (value: string) =>
      value.startsWith("tgads") || /bot$/i.test(value);
    const summaryMap = new Map(summaryBots.rows.map((row) => [row.group, row]));
    const botKeys = new Set<string>();
    summaryBots.rows.forEach((row) => {
      if (row.group && matchesPattern(row.group)) {
        botKeys.add(row.group);
      }
    });
    budgetAggregates.byBot.forEach((_value, key) => {
      if (key && matchesPattern(key)) {
        botKeys.add(key);
      }
    });
    return Array.from(botKeys).map((botKey) => {
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
        subscribed: agg?.subscribed ?? 0,
        spend: agg?.spend ?? 0,
        budget: agg?.budget ?? 0,
      };
    });
  }, [summaryBots.rows, budgetAggregates]);
  const totalaRows = useMemo(() => {
    const companySet = new Set(companies.map((item) => item.name));
    const rowsByName = new Map(summaryCompanies.rows.map((row) => [row.group, row]));
    const merged: typeof summaryCompanies.rows = [];
    for (const name of companySet) {
      merged.push(
        rowsByName.get(name) ?? {
          group: name,
          entered: 0,
          lead: 0,
          platform: 0,
          learning: 0,
          course: 0,
          interview: 0,
          passed: 0,
          offer: 0,
          contract: 0,
        }
      );
    }
    for (const row of summaryCompanies.rows) {
      if (!companySet.has(row.group) && row.group) {
        merged.push(row);
      }
    }
    budgetAggregates.byCampaign.forEach((_value, key) => {
      if (key && !companySet.has(key) && !rowsByName.has(key)) {
        merged.push({
          group: key,
          entered: 0,
          lead: 0,
          platform: 0,
          learning: 0,
          course: 0,
          interview: 0,
          passed: 0,
          offer: 0,
          contract: 0,
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
        normalized === "null"
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
          subscribed: agg?.subscribed ?? 0,
          spend: agg?.spend ?? 0,
          budget: agg?.budget ?? 0,
        };
      });
  }, [companies, summaryCompanies.rows, budgetAggregates]);

  const touchRowsWithBudget = useMemo(() => {
    return touchFunnelRows.map((row) => {
      const agg = budgetAggregates.byBot.get(row.bot || "");
      return {
        ...row,
        impressions: agg?.impressions ?? 0,
        clicks: agg?.clicks ?? 0,
        subscribed: agg?.subscribed ?? 0,
        spend: agg?.spend ?? 0,
        budget: agg?.budget ?? 0,
      };
    });
  }, [touchFunnelRows, budgetAggregates]);

  const renderTabContent = () => {
    if (
      !hasSelectedBots &&
      tab !== "totalb" &&
      tab !== "totala" &&
      tab !== "totalc" &&
      tab !== "tgsubs" &&
      tab !== "weekly"
    ) {
      return (
        <Alert severity="info" sx={{ mt: 2 }}>
          Выберите хотя бы одну базу и нажмите «ПРИМЕНИТЬ», чтобы увидеть данные.
        </Alert>
      );
    }
    switch (tab) {
      case "funnel":
        return <FunnelView stages={stages} />;
      case "rawutm":
        return (
          <Box>
            <ButtonGroup size="small" sx={{ mt: 2 }}>
              {DETAILS_GROUPS.map((group) => (
                <Button
                  key={group}
                  variant={breakdownGroup === group ? "contained" : "outlined"}
                  onClick={() => setBreakdownGroup(group)}
                >
                  {group === "source_campaign" ? "Source / Campaign" : group.replace("_", " ")}
                </Button>
              ))}
            </ButtonGroup>
            <BreakdownTable data={breakdown} loading={loading} groupBy={breakdownGroup} />
          </Box>
        );
      case "totalb":
        return (
          <Box>
            <FunnelSummaryTable
              title="TotalB: Воронка по ботам"
              nameLabel="Бот"
              rows={totalbRows}
              nameResolver={(value) => botNameMap.get(value) || value}
              botLabelResolver={resolveBotLabel}
            />
          </Box>
        );
      case "totala":
        return (
          <Box>
            <FunnelSummaryTable
              title="TotalA: Воронка по РК"
              nameLabel="Рекламная компания"
              rows={totalaRows}
              groupType="company"
              groupMeta={totalACompanyMeta}
              botLabelResolver={resolveBotLabel}
            />
          </Box>
        );
      case "totalc":
        return (
          <Box>
            <TouchFunnelTable
              title="Total C"
              rows={touchRowsWithBudget}
              loading={touchFunnelLoading}
              botLabel="Touch Bot"
              mode={touchMode}
              onModeChange={setTouchMode}
            />
          </Box>
        );
      case "tgsubs":
        return (
          <Box>
            <SubscriptionsComparePanel
              data={subscriptionsData}
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
          <Box>
            <Stack direction={{ xs: "column", sm: "row" }} spacing={2} alignItems="center" sx={{ mt: 1 }}>
              <FormControlLabel
                control={
                  <Switch
                    checked={weeklyUseFirstTouch}
                    onChange={(e) => setWeeklyUseFirstTouch(e.target.checked)}
                  />
                }
                label="Фильтр first_touch"
              />
            </Stack>
            <WeeklyTable
              rows={roistatWeeklyRows}
              loading={roistatWeeklyLoading}
              error={roistatWeeklyError}
              selectedMonth={weeklyMonth}
              onSelectedMonthChange={setWeeklyMonth}
            />
          </Box>
        );
      case "raw":
        return (
          <Box>
            <Stack direction="row" spacing={2} alignItems="center" mt={2}>
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
                title="Daily New Users"
                data={periodSeries}
              />
            </Grid>
            </Grid>
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

  return (
    <section>
      <Typography variant="h4" mt={2} mb={1}>
        Analytics Dashboard
      </Typography>
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
          {loadingDatabases && <Typography variant="caption">Обновляю...</Typography>}
          {syncMessage && <Typography variant="caption">{syncMessage}</Typography>}
        </Stack>
        <Stack direction="row" spacing={2} alignItems="center">
          {renderSyncInfo("Обновление баз (MSK)", lastIngestionStatus)}
          {renderSyncInfo("Обновление SM (MSK)", lastSmStatus)}
        </Stack>
        {lastIngestionSuccess && (
          <Typography variant="caption" color="text.secondary">
            Последнее успешное обновление: {formatMsk(lastIngestionSuccess.ts)}
          </Typography>
        )}
      </Box>
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
        />
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
        onSave={async (updatedCompanies) => {
          for (const company of updatedCompanies) {
            await upsertCompany(company);
          }
        }}
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
        loading={systemLoading}
        error={systemError}
        onClose={() => setSettingsDialogOpen(false)}
        onSave={updateSystemSettings}
        onRefresh={refreshSystemSettings}
        onRebuildCompanies={rebuildCompanies}
        onSyncAll={handleSyncAll}
        onSyncSm={handleSyncSm}
      />
    </section>
  );
};

export default OverviewPage;
