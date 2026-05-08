// Хук сводки first/last touch (GET /api/reports/funnel-start/touch/summary).
// Показывает распределение пользователей по источникам touch атрибуции.
import { useCallback, useEffect, useState } from "react";
import axios from "axios";
import { format } from "date-fns";
import { FilterValues } from "./useReports";

const API_BASE = import.meta.env.VITE_API_BASE || "";

export interface TouchSummaryRow {
  bot: string;
  campaign: string;
  users: number;
}

export const useTouchSummary = (filters: FilterValues, mode: "first" | "last") => {
  const [data, setData] = useState<TouchSummaryRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    const params: Record<string, string> = { mode };
    if (filters.startDate) {
      params.start_date = format(filters.startDate, "yyyy-MM-dd");
    }
    if (filters.endDate) {
      params.end_date = format(filters.endDate, "yyyy-MM-dd");
    }
    try {
      const res = await axios.get(`${API_BASE}/api/reports/touch/summary`, { params });
      setData(res.data?.data || []);
    } catch (err: any) {
      console.error(err);
      setError(err?.response?.data?.detail || err?.message || "Не удалось загрузить атрибуцию");
    } finally {
      setLoading(false);
    }
  }, [filters.startDate, filters.endDate, mode]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  return { data, loading, error, refresh: fetchData };
};
