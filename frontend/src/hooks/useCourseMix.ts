import { useCallback, useEffect, useState } from "react";
import axios from "axios";
import { format } from "date-fns";
import { FilterValues } from "./useReports";

const API_BASE = import.meta.env.VITE_API_BASE || "";

export interface CourseMixRow {
  course: string;
  users: number;
}

export const useCourseMix = (filters: FilterValues) => {
  const [data, setData] = useState<CourseMixRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    const params: Record<string, string> = {};
    if (filters.startDate) {
      params.start_date = format(filters.startDate, "yyyy-MM-dd");
    }
    if (filters.endDate) {
      params.end_date = format(filters.endDate, "yyyy-MM-dd");
    }
    try {
      const res = await axios.get(`${API_BASE}/api/reports/courses/mix`, { params });
      setData(res.data?.data || []);
    } catch (err: any) {
      console.error(err);
      setError(err?.response?.data?.detail || err?.message || "Не удалось загрузить курсы");
    } finally {
      setLoading(false);
    }
  }, [filters.startDate, filters.endDate]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  return { data, loading, error, refresh: fetchData };
};
