import { useCallback, useEffect, useState } from "react";
import axios from "axios";
import { format } from "date-fns";
import { FilterValues } from "./useReports";

const API_BASE = import.meta.env.VITE_API_BASE || "";

export interface BudgetWeeklyReportRow {
  week_start: string;
  campaign: string;
  bot_key: string | null;
  budget: number;
  currency: string;
  starts: number;
  lead: number;
  platform: number;
  learning: number;
  completed_course: number;
  interview: number;
  passed: number;
  offer: number;
  contract: number;
  impressions: number;
  clicks: number;
  spend: number;
  ctr: number | null;
  cpc_click: number | null;
  cpm: number | null;
  subscribed: number;
  unsubscribed: number;
  course_mtt: number;
  course_spin: number;
  course_cash: number;
  cpf: number | null;
  cpl: number | null;
  cpa: number | null;
  cpc: number | null;
}

export const useBudgetWeeklyReport = (filters: FilterValues, interval: "day" | "week" = "day") => {
  const [data, setData] = useState<BudgetWeeklyReportRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    const params: Record<string, string> = {};
    if (filters.startDate) {
      params.start_date = format(filters.startDate, "yyyy-MM-dd");
    }
    if (filters.endDate) {
      params.end_date = format(filters.endDate, "yyyy-MM-dd");
    }
    params.interval = interval;
    try {
      const res = await axios.get(`${API_BASE}/api/reports/budgets/weekly`, { params });
      setData(res.data?.data || []);
    } catch (err: any) {
      console.error(err);
      setError(err?.response?.data?.detail || err?.message || "Не удалось загрузить бюджеты");
    } finally {
      setLoading(false);
    }
  }, [filters.startDate, filters.endDate, interval]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  return { data, loading, error, refresh: fetchData };
};
