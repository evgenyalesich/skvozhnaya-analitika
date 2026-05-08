// Хук иерархического дерева воронки (GET /api/reports/roistat-weekly/tree).
// Возвращает tree: Platform → Company → Bot с метриками на каждом уровне.
import { useCallback, useEffect, useState } from "react";
import axios from "axios";
import { FilterValues, buildFilterParams, buildQueryParams } from "./useReports";

const API_BASE = import.meta.env.VITE_API_BASE || "";

export interface FunnelTreeMetrics {
  entered: number;
  lead: number;
  platform: number;
  learning: number;
  course: number;
  simulator: number;
  interview: number;
  passed: number;
  offer: number;
  contract: number;
  distance: number;
}

export interface FunnelTreeBot extends FunnelTreeMetrics {
  bot: string;
}

export interface FunnelTreeCompany extends FunnelTreeMetrics {
  company: string;
  bots: FunnelTreeBot[];
}

export interface FunnelTreeSource extends FunnelTreeMetrics {
  source: string;
  companies: FunnelTreeCompany[];
}

export const useFunnelTree = (filters: FilterValues, enabled: boolean = true) => {
  const [tree, setTree] = useState<FunnelTreeSource[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetch = useCallback(async () => {
    if (!enabled) return;
    setLoading(true);
    setError(null);
    try {
      const params = buildQueryParams(buildFilterParams(filters));
      const res = await axios.get(`${API_BASE}/api/reports/funnel-start/tree`, { params });
      setTree(res.data.tree || []);
    } catch (err: any) {
      setError(err?.response?.data?.detail || err?.message || "Ошибка загрузки дерева");
    } finally {
      setLoading(false);
    }
  }, [filters, enabled]);

  useEffect(() => {
    fetch();
  }, [fetch]);

  return { tree, loading, error, refresh: fetch };
};
