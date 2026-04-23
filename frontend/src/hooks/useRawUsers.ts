import { useCallback, useEffect, useState } from "react";
import axios from "axios";
import {
  FilterValues,
  RawColumnFilters,
  RawReportParams,
  RawUserModel,
  buildFilterParams,
  buildRawFilterParams,
  buildQueryParams,
} from "./useReports";

const API_BASE = import.meta.env.VITE_API_BASE || "";

export const useRawUsers = (
  rawParams: RawReportParams,
  rawFilters: RawColumnFilters,
  topFilters?: FilterValues,
  touchMode: "event" | "first_touch" | "last_touch" = "event",
  enabled: boolean = true,
) => {
  const [raw, setRaw] = useState<RawUserModel[]>([]);
  const [rawTotal, setRawTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchRaw = useCallback(async () => {
    if (!enabled) {
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const rawFilterParams = buildRawFilterParams(rawFilters);
      // RAW users should respect the same top filters (including selected bot),
      // while touch mode is passed explicitly via touch_mode below.
      const topParams = buildFilterParams({
        startDate: topFilters?.startDate ?? null,
        endDate: topFilters?.endDate ?? null,
        bots: topFilters?.bots ?? [],
        companies: topFilters?.companies ?? [],
        utmSource: topFilters?.utmSource ?? [],
        utmCampaign: topFilters?.utmCampaign ?? [],
        utmMedium: topFilters?.utmMedium ?? [],
        utmContent: topFilters?.utmContent ?? [],
        utmTerm: topFilters?.utmTerm ?? [],
        userScope: "all",
        touchMode: "event",
      });
      const res = await axios.get(`${API_BASE}/api/reports/funnel-start/raw`, {
        params: buildQueryParams({
          ...topParams,
          ...rawFilterParams,
          touch_mode: touchMode === "first_touch" ? "first" : touchMode === "last_touch" ? "last" : "event",
          limit: rawParams.limit,
          offset: rawParams.offset,
          sort_by: rawParams.sortBy,
          sort_direction: rawParams.sortDirection,
        }),
      });
      setRaw(res.data.users || []);
      setRawTotal(res.data.total || 0);
    } catch (err: any) {
      setError(err?.response?.data?.detail || err?.message || "Не удалось загрузить данные");
    } finally {
      setLoading(false);
    }
  }, [enabled, rawParams, rawFilters, topFilters, touchMode]);

  useEffect(() => {
    if (!enabled) {
      return;
    }
    fetchRaw();
  }, [enabled, fetchRaw]);

  return { raw, rawTotal, loading, error, refresh: fetchRaw };
};
