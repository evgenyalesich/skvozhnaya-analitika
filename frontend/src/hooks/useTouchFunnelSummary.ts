import { useCallback, useEffect, useState } from "react";
import axios from "axios";
import { buildFilterParams, buildQueryParams, FilterValues } from "./useReports";

const API_BASE = import.meta.env.VITE_API_BASE || "";

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

export const useTouchFunnelSummary = (filters: FilterValues, mode: "first" | "last" = "last") => {
  const [rows, setRows] = useState<TouchFunnelRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchSummary = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = {
        ...buildFilterParams(filters),
        mode,
      };
      const response = await axios.get(`${API_BASE}/api/reports/touch/funnel-summary`, {
        params: buildQueryParams(params),
      });
      setRows(response.data.summary || []);
    } catch (err: any) {
      console.error(err);
      setError(err?.response?.data?.detail || err?.message || "Не удалось загрузить TotalC");
    } finally {
      setLoading(false);
    }
  }, [filters, mode]);

  useEffect(() => {
    fetchSummary();
  }, [fetchSummary]);

  return { rows, loading, error, refresh: fetchSummary };
};
