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

export type SubscriptionGroupBy = "campaign" | "overall";
export type SubscriptionInterval = "day" | "week";

export const useSubscriptionsCompare = (
  filters: FilterValues,
  options: { groupBy: SubscriptionGroupBy; interval: SubscriptionInterval; enabled?: boolean }
) => {
  const [data, setData] = useState<SubscriptionCompareRow[]>([]);
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
    } catch (err: any) {
      console.error(err);
      setError(err?.response?.data?.detail || err?.message || "Не удалось загрузить подписки");
      setData([]);
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

  return { data, loading, error, refresh: fetchData };
};
