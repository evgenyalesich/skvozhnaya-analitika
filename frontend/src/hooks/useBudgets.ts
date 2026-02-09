import { useCallback, useEffect, useState } from "react";
import axios from "axios";

const API_BASE = import.meta.env.VITE_API_BASE || "";

export interface BudgetWeeklyRow {
  id: number;
  week_start: string;
  campaign: string;
  bot_key: string | null;
  amount: number;
  currency: string;
}

export const useBudgets = () => {
  const [budgets, setBudgets] = useState<BudgetWeeklyRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchBudgets = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await axios.get(`${API_BASE}/api/budgets`);
      setBudgets(res.data || []);
    } catch (err: any) {
      console.error(err);
      setError(err?.response?.data?.detail || err?.message || "Не удалось загрузить бюджеты");
    } finally {
      setLoading(false);
    }
  }, []);

  const createBudget = useCallback(async (payload: Omit<BudgetWeeklyRow, "id">) => {
    try {
      setError(null);
      const res = await axios.post(`${API_BASE}/api/budgets`, payload);
      setBudgets((prev) => [res.data, ...prev]);
    } catch (err: any) {
      setError(err?.response?.data?.detail || err?.message || "Не удалось создать бюджет");
      throw err;
    }
  }, []);

  const updateBudget = useCallback(async (id: number, patch: Partial<BudgetWeeklyRow>) => {
    try {
      setError(null);
      const res = await axios.put(`${API_BASE}/api/budgets/${id}`, patch);
      setBudgets((prev) => prev.map((row) => (row.id === id ? res.data : row)));
    } catch (err: any) {
      setError(err?.response?.data?.detail || err?.message || "Не удалось обновить бюджет");
      throw err;
    }
  }, []);

  const deleteBudget = useCallback(async (id: number) => {
    try {
      setError(null);
      await axios.delete(`${API_BASE}/api/budgets/${id}`);
      setBudgets((prev) => prev.filter((row) => row.id !== id));
    } catch (err: any) {
      setError(err?.response?.data?.detail || err?.message || "Не удалось удалить бюджет");
      throw err;
    }
  }, []);

  useEffect(() => {
    fetchBudgets();
  }, [fetchBudgets]);

  return { budgets, loading, error, refresh: fetchBudgets, createBudget, updateBudget, deleteBudget };
};
