import { useCallback, useEffect, useState } from "react";
import axios from "axios";

const API_BASE = import.meta.env.VITE_API_BASE || "";

export interface RoistatWeeklyRow {
  week_start: string;
  almanah_starts: number;
  direct_source_cnt: number;
  new_in_system: number;
  old_in_system: number;
  platform: number;
  learning: number;
  started_learning: number;
  mtt: number;
  spin: number;
  cash: number;
  base: number;
  not_started: number;
  channel_subscribed: number;
  saloon: number;
  completed_course: number;
  completed_base: number;
  distance_grinding: number;
  contract_signed: number;
  budget: number;
  // Extended
  entered_all: number;
  interview_reached: number;
  offer_received: number;
  completed_mtt: number;
  completed_spin: number;
  completed_cash: number;
  contract_mtt: number;
  contract_spin: number;
  contract_cash: number;
}

export const useRoistatWeekly = (
  eventStart?: string,
  eventEnd?: string,
  touchMode: "event" | "first_touch" | "last_touch" = "event",
  enabled: boolean = true,
  firstTouchStart?: string,
  firstTouchEnd?: string,
  bots?: string[],
) => {
  const [rows, setRows] = useState<RoistatWeeklyRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchRows = useCallback(async () => {
    if (!enabled) return;
    setLoading(true);
    setError(null);
    try {
      const params: Record<string, string | string[]> = {};
      params.mode = touchMode;
      if (eventStart) params.event_start = eventStart;
      if (eventEnd) params.event_end = eventEnd;
      if (touchMode !== "event") {
        const ftStart = firstTouchStart || eventStart;
        const ftEnd = firstTouchEnd || eventEnd;
        if (ftStart) params.first_touch_start = ftStart;
        if (ftEnd) params.first_touch_end = ftEnd;
      }
      if (bots && bots.length > 0) params.bots = bots;
      const response = await axios.get(`${API_BASE}/api/reports/roistat-weekly`, { params });
      setRows(response.data?.rows || []);
    } catch (err: any) {
      setError(err?.response?.data?.detail || err?.message || "Не удалось загрузить Weekly");
    } finally {
      setLoading(false);
    }
  }, [enabled, eventStart, eventEnd, firstTouchStart, firstTouchEnd, touchMode, bots]);

  useEffect(() => {
    fetchRows();
  }, [fetchRows]);

  return { rows, loading, error, refresh: fetchRows };
};
