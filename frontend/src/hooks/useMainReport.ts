// Хук основного Roistat-отчёта (companies-weekly).
// Кеш в localStorage (ключ v13 по всем параметрам, TTL 12 ч) — данные доступны мгновенно при открытии вкладки.
// При включении (enabled=true) делает GET /api/reports/roistat-weekly/companies-weekly.
// Поддерживает polling (pollMs) — только при document.visibilityState=visible.
// Возвращает rows (по company), botRows (по bot_key), weekTotals (total по неделям).

import { useCallback, useEffect, useRef, useState } from "react";
import axios from "axios";

const API_BASE = import.meta.env.VITE_API_BASE || "";
const MAIN_REPORT_CACHE_PREFIX = "main-report-cache:v19:";
const MAIN_REPORT_CACHE_TTL_MS = 12 * 60 * 60 * 1000;
const MAIN_REPORT_SYNC_VERSION_KEY = "main-report-sync-version:v1";

export interface MainReportRow {
  week_start: string;
  company: string;
  bot_key?: string | null;
  entered_all: number;
  budget: number;
  almanah_starts: number;
  direct_source_cnt: number;
  new_in_system: number;
  old_in_system: number;
  platform_cnt: number;
  learning: number;
  started_learning: number;
  started_base?: number;
  started_mtt?: number;
  started_spin?: number;
  started_cash?: number;
  advanced_started_uniq?: number;
  advanced_started_total?: number;
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
  advanced_completed_uniq?: number;
  advanced_completed_total?: number;
  interview_reached: number;
  offer_received: number;
  contract_signed: number;
  refused_interview: number;
  no_response_interview: number;
  contract_mtt: number;
  contract_spin: number;
  contract_cash: number;
  distance_grinding: number;
}

export interface MainReportWeekTotalRow {
  week_start: string;
  entered_all: number;
  budget: number;
  almanah_starts: number;
  direct_source_cnt: number;
  new_in_system: number;
  old_in_system: number;
  platform_cnt: number;
  learning: number;
  started_learning: number;
  started_base?: number;
  started_mtt?: number;
  started_spin?: number;
  started_cash?: number;
  advanced_started_uniq?: number;
  advanced_started_total?: number;
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
  advanced_completed_uniq?: number;
  advanced_completed_total?: number;
  interview_reached: number;
  offer_received: number;
  contract_signed: number;
  refused_interview: number;
  no_response_interview: number;
  contract_mtt: number;
  contract_spin: number;
  contract_cash: number;
  distance_grinding: number;
}

export interface MainReportFilters {
  bots?: string[];
  companies?: string[];
  utmSource?: string[];
  utmCampaign?: string[];
  utmMedium?: string[];
  utmContent?: string[];
  utmTerm?: string[];
}

interface MainReportCachePayload {
  ts: number;
  rows: MainReportRow[];
  botRows: MainReportRow[];
  weekTotals: MainReportWeekTotalRow[];
}

const buildCacheKey = (
  eventStart?: string | null,
  eventEnd?: string | null,
  touchMode: string = "event",
  firstTouchStart?: string | null,
  firstTouchEnd?: string | null,
  displayMode: "weekly" | "cohort" = "weekly",
  filters?: MainReportFilters,
  syncVersion?: string,
) =>
  `${MAIN_REPORT_CACHE_PREFIX}${JSON.stringify({
    eventStart: eventStart || null,
    eventEnd: eventEnd || null,
    touchMode,
    firstTouchStart: firstTouchStart || null,
    firstTouchEnd: firstTouchEnd || null,
    displayMode,
    bots: filters?.bots || [],
    companies: filters?.companies || [],
    utmSource: filters?.utmSource || [],
    utmCampaign: filters?.utmCampaign || [],
    utmMedium: filters?.utmMedium || [],
    utmContent: filters?.utmContent || [],
    utmTerm: filters?.utmTerm || [],
    syncVersion: syncVersion || "0:0",
  })}`;

const readMainReportSyncVersion = (): string => {
  if (typeof window === "undefined") return "0:0";
  try {
    return window.localStorage.getItem(MAIN_REPORT_SYNC_VERSION_KEY) || "0:0";
  } catch {
    return "0:0";
  }
};

const readCachedReport = (cacheKey: string): MainReportCachePayload | null => {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(cacheKey);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as MainReportCachePayload;
    if (!parsed?.ts || Date.now() - parsed.ts > MAIN_REPORT_CACHE_TTL_MS) {
      window.localStorage.removeItem(cacheKey);
      return null;
    }
    return parsed;
  } catch {
    return null;
  }
};

const writeCachedReport = (
  cacheKey: string,
  rows: MainReportRow[],
  botRows: MainReportRow[],
  weekTotals: MainReportWeekTotalRow[],
) => {
  if (typeof window === "undefined") return;
  try {
    const payload: MainReportCachePayload = { ts: Date.now(), rows, botRows, weekTotals };
    window.localStorage.setItem(cacheKey, JSON.stringify(payload));
  } catch {
    // Ignore quota/storage issues and continue with network data.
  }
};

export const useMainReport = (
  eventStart?: string | null,
  eventEnd?: string | null,
  enabled = true,
  touchMode: string = "event",
  firstTouchStart?: string | null,
  firstTouchEnd?: string | null,
  displayMode: "weekly" | "cohort" = "weekly",
  filters?: MainReportFilters,
  options?: { pollMs?: number },
) => {
  const pollMs = options?.pollMs ?? 0;
  const apiDisplayMode: "weekly" | "cohort" = displayMode === "cohort" ? "weekly" : displayMode;
  const syncVersion = readMainReportSyncVersion();
  const cacheKey = buildCacheKey(
    eventStart,
    eventEnd,
    touchMode,
    firstTouchStart,
    firstTouchEnd,
    apiDisplayMode,
    filters,
    syncVersion,
  );
  const cached = readCachedReport(cacheKey);
  const [rows, setRows] = useState<MainReportRow[]>(() => cached?.rows || []);
  const [botRows, setBotRows] = useState<MainReportRow[]>(() => cached?.botRows || []);
  const [weekTotals, setWeekTotals] = useState<MainReportWeekTotalRow[]>(() => cached?.weekTotals || []);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inFlightRef = useRef(false);

  const fetchData = useCallback(async () => {
    if (!enabled) return;
    if (inFlightRef.current) return;
    try {
      inFlightRef.current = true;
      setLoading(true);
      setError(null);
      const params = new URLSearchParams();
      if (eventStart) params.append("event_start", eventStart);
      if (eventEnd) params.append("event_end", eventEnd);
      if (touchMode && touchMode !== "event") params.append("mode", touchMode);
      if (firstTouchStart) params.append("first_touch_start", firstTouchStart);
      if (firstTouchEnd) params.append("first_touch_end", firstTouchEnd);
      if (apiDisplayMode && apiDisplayMode !== "weekly") params.append("display_mode", apiDisplayMode);
      filters?.bots?.forEach((value) => params.append("bots", value));
      filters?.companies?.forEach((value) => params.append("advertising_companies", value));
      filters?.utmSource?.forEach((value) => params.append("utm_source", value));
      filters?.utmCampaign?.forEach((value) => params.append("utm_campaign", value));
      filters?.utmMedium?.forEach((value) => params.append("utm_medium", value));
      filters?.utmContent?.forEach((value) => params.append("utm_content", value));
      filters?.utmTerm?.forEach((value) => params.append("utm_term", value));
      const res = await axios.get(`${API_BASE}/api/reports/roistat-weekly/companies-weekly`, {
        params,
        timeout: 90000,
      });
      const nextRows = res.data?.rows || [];
      const nextBotRows = res.data?.bot_rows || [];
      const nextWeekTotals = res.data?.week_totals || [];
      setRows(nextRows);
      setBotRows(nextBotRows);
      setWeekTotals(nextWeekTotals);
      writeCachedReport(cacheKey, nextRows, nextBotRows, nextWeekTotals);
    } catch (err: any) {
      setError(err?.response?.data?.detail || err?.message || "Ошибка загрузки основного отчёта");
    } finally {
      inFlightRef.current = false;
      setLoading(false);
    }
  }, [
    eventStart,
    eventEnd,
    enabled,
    touchMode,
    firstTouchStart,
    firstTouchEnd,
    apiDisplayMode,
    cacheKey,
    filters?.bots,
    filters?.companies,
    filters?.utmSource,
    filters?.utmCampaign,
    filters?.utmMedium,
    filters?.utmContent,
    filters?.utmTerm,
  ]);

  useEffect(() => {
    const cachedReport = readCachedReport(cacheKey);
    if (cachedReport) {
      setRows(cachedReport.rows || []);
      setBotRows(cachedReport.botRows || []);
      setWeekTotals(cachedReport.weekTotals || []);
    } else {
      setRows([]);
      setBotRows([]);
      setWeekTotals([]);
    }
    setError(null);
    fetchData();
  }, [cacheKey, fetchData]);

  useEffect(() => {
    if (!enabled || pollMs <= 0) {
      return;
    }
    const id = window.setInterval(() => {
      if (document.visibilityState === "visible") {
        fetchData();
      }
    }, pollMs);
    return () => window.clearInterval(id);
  }, [enabled, fetchData, pollMs]);

  return { rows, botRows, weekTotals, loading, error, refresh: fetchData };
};
