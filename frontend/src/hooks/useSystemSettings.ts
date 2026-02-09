import { useCallback, useEffect, useState } from "react";
import axios from "axios";

const API_BASE = import.meta.env.VITE_API_BASE || "";

export interface SchedulerSettings {
  periodic_enabled: boolean;
  run_on_start: boolean;
  warm_cache_on_start: boolean;
  ingestion_interval_minutes: number;
  google_sheets_interval_minutes: number;
  pokerhub_interval_hours: number;
  telegram_interval_minutes: number;
  telegram_daily_hour: number;
  telegram_batch_size: number;
  telegram_job_timeout_seconds: number;
}

export interface SystemSettings {
  scheduler: SchedulerSettings;
}

export interface SyncEventLog {
  id: number;
  source: string;
  level: string;
  message: string;
  created_at: string;
}

export const useSystemSettings = () => {
  const [settings, setSettings] = useState<SystemSettings | null>(null);
  const [logs, setLogs] = useState<SyncEventLog[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [settingsRes, logsRes] = await Promise.all([
        axios.get(`${API_BASE}/api/admin/settings`),
        axios.get(`${API_BASE}/api/admin/sync-logs`),
      ]);
      setSettings(settingsRes.data);
      setLogs(logsRes.data || []);
    } catch (err: any) {
      console.error(err);
      setError(err?.response?.data?.detail || err?.message || "Не удалось загрузить настройки");
    } finally {
      setLoading(false);
    }
  }, []);

  const update = useCallback(async (payload: SystemSettings) => {
    setLoading(true);
    setError(null);
    try {
      const res = await axios.put(`${API_BASE}/api/admin/settings`, payload);
      setSettings(res.data);
    } catch (err: any) {
      console.error(err);
      setError(err?.response?.data?.detail || err?.message || "Не удалось сохранить настройки");
      throw err;
    } finally {
      setLoading(false);
    }
  }, []);

  const rebuildCompanies = useCallback(async () => {
    await axios.post(`${API_BASE}/api/advertising-companies/rebuild`);
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return { settings, logs, loading, error, refresh, update, rebuildCompanies };
};
