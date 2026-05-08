// Хук Roistat-дерева (GET /api/reports/roistat-weekly/tree): Platform → Company → Bot.
import { useCallback, useEffect, useState } from "react";
import axios from "axios";

const API_BASE = import.meta.env.VITE_API_BASE || "";

export interface RoistatTreeMetrics {
  almanah_starts: number;
  new_in_system: number;
  platform_cnt: number;
  started_learning: number;
  completed_course: number;
  completed_mtt: number;
  completed_spin: number;
  completed_cash: number;
  interview_reached: number;
  offer_received: number;
  contract_signed: number;
  contract_mtt: number;
  contract_spin: number;
  contract_cash: number;
  distance_grinding: number;
}

export interface RoistatTreeBot extends RoistatTreeMetrics {
  bot: string;
}

export interface RoistatTreeCompany extends RoistatTreeMetrics {
  company: string;
  bots: RoistatTreeBot[];
}

export interface RoistatTreeSource extends RoistatTreeMetrics {
  source: string;
  companies: RoistatTreeCompany[];
}

export const useRoistatWeeklyTree = (
  eventStart?: string,
  eventEnd?: string,
  enabled: boolean = true,
) => {
  const [tree, setTree] = useState<RoistatTreeSource[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchTree = useCallback(async () => {
    if (!enabled) return;
    setLoading(true);
    setError(null);
    try {
      const params: Record<string, string> = {};
      if (eventStart) params.event_start = eventStart;
      if (eventEnd) params.event_end = eventEnd;
      const response = await axios.get(`${API_BASE}/api/reports/roistat-weekly/tree`, { params });
      setTree(response.data?.tree || []);
    } catch (err: any) {
      setError(err?.response?.data?.detail || err?.message || "Не удалось загрузить дерево");
    } finally {
      setLoading(false);
    }
  }, [enabled, eventStart, eventEnd]);

  useEffect(() => {
    fetchTree();
  }, [fetchTree]);

  return { tree, loading, error, refresh: fetchTree };
};
