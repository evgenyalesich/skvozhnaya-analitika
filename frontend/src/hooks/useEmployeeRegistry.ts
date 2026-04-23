import { useCallback, useEffect, useState } from "react";
import axios from "axios";

const API_BASE = import.meta.env.VITE_API_BASE || "";

export interface EmployeeRegistryEntry {
  tg_user_id: number;
  username?: string | null;
  created_at: string;
  created_by?: string | null;
}

export const useEmployeeRegistry = () => {
  const [entries, setEntries] = useState<EmployeeRegistryEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await axios.get(`${API_BASE}/api/admin/employee-registry`);
      setEntries(response.data || []);
    } catch (err: any) {
      console.error(err);
      setError(err?.response?.data?.detail || err?.message || "Не удалось загрузить реестр сотрудников");
    } finally {
      setLoading(false);
    }
  }, []);

  const replaceAll = useCallback(
    async (tgUserIds: number[]) => {
      await axios.put(`${API_BASE}/api/admin/employee-registry`, { tg_user_ids: tgUserIds });
      await refresh();
    },
    [refresh]
  );

  useEffect(() => {
    refresh();
  }, [refresh]);

  return { entries, loading, error, refresh, replaceAll };
};
