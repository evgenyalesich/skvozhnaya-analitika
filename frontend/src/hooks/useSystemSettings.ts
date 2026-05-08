// Хук системных настроек, Marketing Daily и логов синхронизации.
// GET/PUT /api/admin/settings, /marketing-daily/settings, /marketing-daily/preview, history.
// rebuildCompanies — POST /api/advertising-companies/rebuild (пересчёт attribution).
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

export interface MarketingDailySettings {
  enabled: boolean;
  send_hour_msk: number;
  show_top_growth: number;
  show_top_decline: number;
  allowed_subscriber_ids: number[];
  anomaly_drop_threshold_pct: number;
  downward_streak_days: number;
}

export interface MarketingDailyPreview {
  report_date: string | null;
  previous_date: string | null;
  summary: Record<string, any>;
  leaders_growth: Array<Record<string, any>>;
  leaders_decline: Array<Record<string, any>>;
  anomalies: string[];
  all_bots: Array<Record<string, any>>;
  text: string;
}

export interface MarketingDailyHistoryItem {
  id: number;
  report_date: string;
  source: string;
  initiated_by?: number | null;
  total_recipients: number;
  success_count: number;
  failure_count: number;
  status: string;
  created_at: string;
  message_text: string;
}

export interface SyncEventLog {
  id: number;
  source: string;
  level: string;
  message: string;
  created_at: string;
}

export const useSystemSettings = (options?: { enabled?: boolean }) => {
  const [settings, setSettings] = useState<SystemSettings | null>(null);
  const [logs, setLogs] = useState<SyncEventLog[]>([]);
  const [marketingDailySettings, setMarketingDailySettings] = useState<MarketingDailySettings | null>(null);
  const [marketingDailyPreview, setMarketingDailyPreview] = useState<MarketingDailyPreview | null>(null);
  const [marketingDailyHistory, setMarketingDailyHistory] = useState<MarketingDailyHistoryItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const enabled = options?.enabled ?? true;

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
      try {
        const [marketingSettingsRes, marketingPreviewRes] = await Promise.all([
          axios.get(`${API_BASE}/api/admin/marketing-daily/settings`),
          axios.get(`${API_BASE}/api/admin/marketing-daily/preview`),
        ]);
        setMarketingDailySettings(marketingSettingsRes.data);
        setMarketingDailyPreview(marketingPreviewRes.data);
        const historyRes = await axios.get(`${API_BASE}/api/admin/marketing-daily/history`);
        setMarketingDailyHistory(historyRes.data?.items || []);
      } catch (marketingErr: any) {
        if (marketingErr?.response?.status !== 403) {
          throw marketingErr;
        }
        setMarketingDailySettings(null);
        setMarketingDailyPreview(null);
        setMarketingDailyHistory([]);
      }
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

  const updateMarketingDaily = useCallback(async (payload: MarketingDailySettings) => {
    setLoading(true);
    setError(null);
    try {
      const res = await axios.put(`${API_BASE}/api/admin/marketing-daily/settings`, {
        marketing_daily: payload,
      });
      setMarketingDailySettings(res.data);
    } catch (err: any) {
      console.error(err);
      setError(err?.response?.data?.detail || err?.message || "Не удалось сохранить Marketing Daily");
      throw err;
    } finally {
      setLoading(false);
    }
  }, []);

  const refreshMarketingDailyPreview = useCallback(async () => {
    const res = await axios.get(`${API_BASE}/api/admin/marketing-daily/preview`);
    setMarketingDailyPreview(res.data);
    return res.data as MarketingDailyPreview;
  }, []);

  const sendMarketingDailyTest = useCallback(async () => {
    const res = await axios.post(`${API_BASE}/api/admin/marketing-daily/send-test`);
    return res.data;
  }, []);

  const resendMarketingDaily = useCallback(async () => {
    const res = await axios.post(`${API_BASE}/api/admin/marketing-daily/resend`);
    return res.data;
  }, []);

  useEffect(() => {
    if (!enabled) {
      return;
    }
    refresh();
  }, [enabled, refresh]);

  return {
    settings,
    logs,
    marketingDailySettings,
    marketingDailyPreview,
    marketingDailyHistory,
    loading,
    error,
    refresh,
    update,
    rebuildCompanies,
    updateMarketingDaily,
    refreshMarketingDailyPreview,
    sendMarketingDailyTest,
    resendMarketingDaily,
  };
};
