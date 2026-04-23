import { useCallback, useEffect, useState } from "react";
import axios from "axios";

const API_BASE = import.meta.env.VITE_API_BASE || "";

export interface TelegramAccessEntry {
  tg_user_id: number;
  created_at: string;
  created_by?: string | null;
}

export const useTelegramAccess = () => {
  const [entries, setEntries] = useState<TelegramAccessEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await axios.get(`${API_BASE}/api/admin/telegram-access`);
      setEntries(response.data || []);
    } catch (err: any) {
      console.error(err);
      setError(err?.response?.data?.detail || err?.message || "Не удалось получить доступы");
    } finally {
      setLoading(false);
    }
  }, []);

  const add = useCallback(
    async (tgUserId: number) => {
      const payload = { tg_user_id: tgUserId };
      await axios.post(`${API_BASE}/api/admin/telegram-access`, payload);
      await refresh();
    },
    [refresh]
  );

  const remove = useCallback(
    async (tgUserId: number) => {
      await axios.delete(`${API_BASE}/api/admin/telegram-access/${tgUserId}`);
      await refresh();
    },
    [refresh]
  );

  useEffect(() => {
    refresh();
  }, [refresh]);

  return { entries, loading, error, refresh, add, remove };
};
