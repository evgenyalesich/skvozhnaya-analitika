import { useCallback, useEffect, useState } from "react";
import axios from "axios";

const API_BASE = import.meta.env.VITE_API_BASE || "";

export interface BotOption {
  bot_key: string;
  display_name?: string | null;
  canonical_base?: string | null;
  is_active: boolean;
  replicate: boolean;
  exists?: boolean;
}

export const useBotRegistry = () => {
  const [bots, setBots] = useState<BotOption[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await axios.get(`${API_BASE}/api/bots`);
      setBots(res.data.bots || []);
    } catch (err: any) {
      console.error(err);
      setError(err?.response?.data?.detail || err?.message || "Не удалось получить список баз");
    } finally {
      setLoading(false);
    }
  }, []);

  const upsert = useCallback(async (bot: BotOption) => {
    await axios.post(`${API_BASE}/api/bots/registry`, {
      bot_key: bot.bot_key,
      display_name: bot.display_name || null,
      canonical_base: bot.canonical_base || null,
      is_active: bot.is_active,
      replicate: bot.replicate,
    });
    await refresh();
  }, [refresh]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return { bots, loading, error, refresh, upsert };
};
