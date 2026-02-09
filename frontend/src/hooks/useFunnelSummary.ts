import { useCallback, useEffect, useState } from "react";
import axios from "axios";
import { buildFilterParams, buildQueryParams, FilterValues } from "./useReports";

const API_BASE = import.meta.env.VITE_API_BASE || "";

export interface FunnelSummaryRow {
  group: string;
  entered: number;
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

export const useFunnelSummary = (filters: FilterValues, groupBy: "bot_key" | "advertising_company") => {
  const [rows, setRows] = useState<FunnelSummaryRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchSummary = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = {
        ...buildFilterParams(filters),
        group_by: groupBy,
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
  }, [filters, groupBy]);

  useEffect(() => {
    fetchSummary();
  }, [fetchSummary]);

  return { rows, loading, error, refresh: fetchSummary };
};
