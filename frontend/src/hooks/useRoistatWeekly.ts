import { useCallback, useEffect, useState } from "react";
import axios from "axios";

const API_BASE = import.meta.env.VITE_API_BASE || "";

export interface RoistatWeeklyRow {
  week_start: string;
  almanah_starts: number;
  platform: number;
  learning: number;
  mtt: number;
  spin: number;
  cash: number;
  not_started: number;
  channel_subscribed: number;
  saloon: number;
  completed_course: number;
  distance_grinding: number;
  contract_signed: number;
  budget: number;
}

export const useRoistatWeekly = (
  eventStart?: string,
  eventEnd?: string,
  useFirstTouch: boolean = false,
  enabled: boolean = true,
  firstTouchStart?: string,
  firstTouchEnd?: string
) => {
  const [rows, setRows] = useState<RoistatWeeklyRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchRows = useCallback(async () => {
    if (!enabled) return;
    setLoading(true);
    setError(null);
    try {
      const params: Record<string, string> = {};
      params.mode = useFirstTouch ? "first_touch" : "event";
      if (eventStart) params.event_start = eventStart;
      if (eventEnd) params.event_end = eventEnd;
      if (useFirstTouch) {
        const ftStart = firstTouchStart || eventStart;
        const ftEnd = firstTouchEnd || eventEnd;
        if (ftStart) params.first_touch_start = ftStart;
        if (ftEnd) params.first_touch_end = ftEnd;
      }
      const response = await axios.get(`${API_BASE}/api/reports/roistat-weekly`, { params });
      setRows(response.data?.rows || []);
    } catch (err: any) {
      setError(err?.response?.data?.detail || err?.message || "Не удалось загрузить Weekly");
    } finally {
      setLoading(false);
    }
  }, [enabled, eventStart, eventEnd, firstTouchStart, firstTouchEnd, useFirstTouch]);

  useEffect(() => {
    fetchRows();
  }, [fetchRows]);

  return { rows, loading, error, refresh: fetchRows };
};
