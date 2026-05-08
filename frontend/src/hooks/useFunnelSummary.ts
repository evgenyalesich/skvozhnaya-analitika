// Хук сводной таблицы воронки (GET /api/reports/funnel-start/summary).
// Возвращает rows: FunnelSummaryRow[] — каждая строка = одна группа (bot_key или company).
import { useCallback, useEffect, useState } from "react";
import axios from "axios";
import { buildFilterParams, buildQueryParams, FilterValues } from "./useReports";

const API_BASE = import.meta.env.VITE_API_BASE || "";

export interface FunnelSummaryRow {
  group: string;
  entered: number;
  new_in_system: number;
  old_in_system: number;
  lead: number;
  platform: number;
  learning: number;
  course: number;
  simulator: number;
  interview: number;
  passed: number;
  offer: number;
  contract: number;
  distance_grinding: number;
  impressions?: number;
  clicks?: number;
  subscribed?: number;
  spend?: number;
  budget?: number;
}

export const useFunnelSummary = (
  filters: FilterValues,
  groupBy: "bot_key" | "advertising_company",
  options?: { enabled?: boolean; pollMs?: number },
) => {
  const [rows, setRows] = useState<FunnelSummaryRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const enabled = options?.enabled ?? true;
  const pollMs = options?.pollMs ?? 0;
  const requestKey = JSON.stringify({
    groupBy,
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
    if (!enabled) {
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const params = {
        ...buildFilterParams(filters),
        group_by: groupBy,
        touch_mode: filters.touchMode || "event",
      };
      const response = await axios.get(`${API_BASE}/api/reports/funnel-start/summary`, {
        params: buildQueryParams(params),
      });
      setRows(response.data.summary || []);
    } catch (err: any) {
      console.error(err);
      setError(err?.response?.data?.detail || err?.message || "Не удалось загрузить сводку");
    } finally {
      setLoading(false);
    }
  }, [enabled, filters, groupBy]);

  useEffect(() => {
    if (!enabled) {
      return;
    }
    setRows([]);
    setError(null);
    fetchSummary();
  }, [enabled, fetchSummary, requestKey]);

  useEffect(() => {
    if (!enabled || pollMs <= 0) {
      return;
    }
    const id = window.setInterval(() => {
      if (document.visibilityState === "visible") {
        fetchSummary();
      }
    }, pollMs);
    return () => window.clearInterval(id);
  }, [enabled, fetchSummary, pollMs]);

  return { rows, loading, error, refresh: fetchSummary };
};
