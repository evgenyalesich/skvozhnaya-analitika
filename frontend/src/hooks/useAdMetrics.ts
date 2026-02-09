import { useCallback, useEffect, useState } from "react";
import axios from "axios";

const API_BASE = import.meta.env.VITE_API_BASE || "";

export interface AdMetricsWeeklyRow {
  id: number;
  week_start: string;
  campaign: string;
  bot_key: string | null;
  impressions: number;
  clicks: number;
  spend: number;
}

export const useAdMetrics = () => {
  const [rows, setRows] = useState<AdMetricsWeeklyRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchRows = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await axios.get(`${API_BASE}/api/ad-metrics`);
      setRows(res.data || []);
    } catch (err: any) {
      console.error(err);
      setError(err?.response?.data?.detail || err?.message || "Не удалось загрузить метрики");
    } finally {
      setLoading(false);
    }
  }, []);

  const createRow = useCallback(async (payload: Omit<AdMetricsWeeklyRow, "id">) => {
    try {
      setError(null);
      const res = await axios.post(`${API_BASE}/api/ad-metrics`, payload);
      setRows((prev) => [res.data, ...prev]);
    } catch (err: any) {
      setError(err?.response?.data?.detail || err?.message || "Не удалось создать рекламные метрики");
      throw err;
    }
  }, []);

  const updateRow = useCallback(async (id: number, patch: Partial<AdMetricsWeeklyRow>) => {
    try {
      setError(null);
      const res = await axios.put(`${API_BASE}/api/ad-metrics/${id}`, patch);
      setRows((prev) => prev.map((row) => (row.id === id ? res.data : row)));
    } catch (err: any) {
      setError(err?.response?.data?.detail || err?.message || "Не удалось обновить рекламные метрики");
      throw err;
    }
  }, []);

  const deleteRow = useCallback(async (id: number) => {
    try {
      setError(null);
      await axios.delete(`${API_BASE}/api/ad-metrics/${id}`);
      setRows((prev) => prev.filter((row) => row.id !== id));
    } catch (err: any) {
      setError(err?.response?.data?.detail || err?.message || "Не удалось удалить рекламные метрики");
      throw err;
    }
  }, []);

  useEffect(() => {
    fetchRows();
  }, [fetchRows]);

  return { rows, loading, error, refresh: fetchRows, createRow, updateRow, deleteRow };
};
