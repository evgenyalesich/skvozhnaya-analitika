// Хук сравнения подписок (GET /api/reports/funnel-start/subscriptions/compare).
// Поддерживает groupBy (campaign/bot/overall) и interval (day/week).
// Используется в TG SUBS вкладке и в overview (overviewSubsOverall для мини-графиков).
import { useCallback, useEffect, useState } from "react";
import axios from "axios";
import { format } from "date-fns";
import { FilterValues } from "./useReports";

const API_BASE = import.meta.env.VITE_API_BASE || "";

export interface SubscriptionCompareRow {
  date: string;
  campaign: string;
  bot_key?: string;
  bot_starts: number;
  almanah_starts: number;
  channel_subscribed: number;
  channel_unsubscribed: number;
  channel_total: number;
  saloon_subscribed: number;
  saloon_unsubscribed: number;
  saloon_total: number;
}

export interface SubscriptionCompareSummary {
  channel: { active: number; subscribed: number; unsubscribed: number; total_in_channel?: number; not_in_bot?: number };
  saloon: { active: number; subscribed: number; unsubscribed: number; total_in_channel?: number; not_in_bot?: number };
}

export interface ChannelFunnelRow {
  chat_id: string;
  label: string;
  total_in_channel: number;
  in_bot: number;
  registrations: number;
  started_learning: number;
  completed_course: number;
  contract_signed: number;
  budget?: number;
  start_in_bot_cost?: number | null;
  registration_cost?: number | null;
  started_learning_cost?: number | null;
  completed_course_cost?: number | null;
  contract_cost?: number | null;
  pct_in_bot: number;
  pct_registration: number;
  pct_learning: number;
  pct_completed: number;
  pct_contract: number;
}

export interface ChannelReportWeeklyRow {
  week_start: string;
  chat_id: string;
  channel_key?: string;
  label: string;
  in_bot: number;
  registrations: number;
  started_learning: number;
  completed_course: number;
  contract_signed: number;
  budget?: number;
  start_in_bot_cost?: number | null;
  registration_cost?: number | null;
  started_learning_cost?: number | null;
  completed_course_cost?: number | null;
  contract_cost?: number | null;
}

export interface SubscriptionCompareOverallRow {
  date: string;
  bot_starts: number;
  almanah_starts: number;
  channel_subscribed: number;
  channel_unsubscribed: number;
  saloon_subscribed: number;
  saloon_unsubscribed: number;
}

export type SubscriptionGroupBy = "campaign" | "bot" | "overall";
export type SubscriptionInterval = "day" | "week";

export const useSubscriptionsCompare = (
  filters: FilterValues,
  options: { groupBy: SubscriptionGroupBy; interval: SubscriptionInterval; enabled?: boolean; pollMs?: number }
) => {
  const [data, setData] = useState<SubscriptionCompareRow[]>([]);
  const [summary, setSummary] = useState<SubscriptionCompareSummary | null>(null);
  const [channelFunnel, setChannelFunnel] = useState<ChannelFunnelRow[]>([]);
  const [channelReportWeekly, setChannelReportWeekly] = useState<ChannelReportWeeklyRow[]>([]);
  const [overall, setOverall] = useState<SubscriptionCompareOverallRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    if (options.enabled === false) {
      return;
    }
    try {
      setLoading(true);
      setError(null);
      const params: Record<string, string | string[]> = {};
      if (filters.startDate instanceof Date && !Number.isNaN(filters.startDate.getTime())) {
        params.start_date = format(filters.startDate, "yyyy-MM-dd");
      }
      if (filters.endDate instanceof Date && !Number.isNaN(filters.endDate.getTime())) {
        params.end_date = format(filters.endDate, "yyyy-MM-dd");
      }
      params.group_by = options.groupBy;
      params.interval = options.interval;
      if (filters.bots.length) {
        params.bots = filters.bots;
      }
      if (filters.companies.length) {
        params.advertising_companies = filters.companies;
      }
      if (filters.utmSource.length) {
        params.utm_source = filters.utmSource;
      }
      if (filters.utmCampaign.length) {
        params.utm_campaign = filters.utmCampaign;
      }
      if (filters.utmMedium.length) {
        params.utm_medium = filters.utmMedium;
      }
      if (filters.utmContent.length) {
        params.utm_content = filters.utmContent;
      }
      if (filters.utmTerm.length) {
        params.utm_term = filters.utmTerm;
      }
      const res = await axios.get(`${API_BASE}/api/reports/subscriptions/compare`, { params, timeout: 60000 });
      setData(res.data?.data || []);
      setOverall(res.data?.overall || []);
      setSummary(res.data?.summary || null);
      setChannelFunnel(res.data?.channel_funnel || []);
      setChannelReportWeekly(res.data?.channel_report_weekly || []);
    } catch (err: any) {
      console.error(err);
      setError(err?.response?.data?.detail || err?.message || "Не удалось загрузить подписки");
      setData([]);
      setOverall([]);
      setSummary(null);
      setChannelFunnel([]);
      setChannelReportWeekly([]);
    } finally {
      setLoading(false);
    }
  }, [
    filters.startDate,
    filters.endDate,
    filters.bots,
    filters.companies,
    filters.utmSource,
    filters.utmCampaign,
    filters.utmMedium,
    filters.utmContent,
    filters.utmTerm,
    options.groupBy,
    options.interval,
    options.enabled,
  ]);

  useEffect(() => {
    if (options.enabled === false) {
      return;
    }
    fetchData();
  }, [fetchData, options.enabled]);

  useEffect(() => {
    if (options.enabled === false) return;
    const pollMs = options.pollMs ?? 30_000;
    if (pollMs <= 0) {
      return;
    }
    const id = setInterval(() => {
      if (document.visibilityState === "visible") {
        fetchData();
      }
    }, pollMs);
    return () => clearInterval(id);
  }, [fetchData, options.enabled, options.pollMs]);

  return { data, overall, summary, channelFunnel, channelReportWeekly, loading, error, refresh: fetchData };
};
