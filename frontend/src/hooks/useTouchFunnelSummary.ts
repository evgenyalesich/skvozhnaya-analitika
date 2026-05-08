// Хук touch-воронки (GET /api/reports/funnel-start/touch-summary) — разбивка по точкам касания.
import { useCallback, useEffect, useState } from "react";
import axios from "axios";
import { buildFilterParams, buildQueryParams, FilterValues } from "./useReports";

const API_BASE = import.meta.env.VITE_API_BASE || "";
const touchSummaryCache = new Map<string, TouchFunnelRow[]>();

export interface TouchFunnelRow {
  bot: string;
  entered: number;
  lead: number;
  platform: number;
  learning: number;
  course: number;
  interview: number;
  passed: number;
  offer: number;
  distance_grinding: number;
  contract: number;
  impressions?: number;
  clicks?: number;
  subscribed?: number;
  spend?: number;
  budget?: number;
}

export const useTouchFunnelSummary = (filters: FilterValues, mode: "first" | "last" = "last", enabled = true) => {
  const [rows, setRows] = useState<TouchFunnelRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const requestKey = JSON.stringify({
    mode,
    touchMode: filters.touchMode || "event",
    startDate: filters.startDate ? filters.startDate.toISOString() : null,
    endDate: filters.endDate ? filters.endDate.toISOString() : null,
    bots: filters.bots || [],
    companies: filters.companies || [],
    utmSource: filters.utmSource || [],
    utmCampaign: filters.utmCampaign || [],
    utmMedium: filters.utmMedium || [],
    utmContent: filters.utmContent || [],
    utmTerm: filters.utmTerm || [],
    userScope: filters.userScope || "all",
  });

  const fetchSummary = useCallback(async () => {
    if (!enabled) return;
    const params = {
      ...buildFilterParams(filters),
      mode,
    };
    const query = buildQueryParams(params);
    const cacheKey = query.toString();
    const cached = touchSummaryCache.get(cacheKey);
    if (cached) {
      setRows(cached);
      setError(null);
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const response = await axios.get(`${API_BASE}/api/reports/touch/funnel-summary`, {
        params: query,
      });
      const nextRows = response.data.summary || [];
      touchSummaryCache.set(cacheKey, nextRows);
      setRows(nextRows);
    } catch (err: any) {
      console.error(err);
      setError(err?.response?.data?.detail || err?.message || "Не удалось загрузить TotalC");
    } finally {
      setLoading(false);
    }
  }, [filters, mode, enabled]);

  useEffect(() => {
    if (!enabled) return;
    const params = {
      ...buildFilterParams(filters),
      mode,
    };
    const cacheKey = buildQueryParams(params).toString();
    const cached = touchSummaryCache.get(cacheKey);
    if (!cached) {
      setRows([]);
    }
    setError(null);
    fetchSummary();
  }, [enabled, fetchSummary, requestKey]);

  return { rows, loading, error, refresh: fetchSummary };
};
