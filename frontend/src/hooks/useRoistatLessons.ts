import { useCallback, useEffect, useState } from "react";
import axios from "axios";
import { format, isValid } from "date-fns";
import { FilterValues, buildFilterParams, buildQueryParams } from "./useReports";

const API_BASE = import.meta.env.VITE_API_BASE || "";

export interface RoistatLessonColumn {
  key: string;
  label: string;
  module?: number | null;
  lesson?: number | null;
}

export interface RoistatLessonUserRow {
  tg_user_id: number;
  username?: string | null;
  pokerhub_user_id?: string | null;
  completed_lessons: number;
  lessons: Record<string, string | null>;
}

export interface RoistatLessonCourse {
  course: string;
  total_lessons: number;
  columns: RoistatLessonColumn[];
  rows: RoistatLessonUserRow[];
}

export const useRoistatLessons = (filters: FilterValues, enabled: boolean = true) => {
  const [courses, setCourses] = useState<RoistatLessonCourse[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pokerhubUserId, setPokerhubUserId] = useState("");
  const [debouncedPokerhubUserId, setDebouncedPokerhubUserId] = useState("");
  const [learnStartDateFrom, setLearnStartDateFrom] = useState("");
  const [learnStartDateTo, setLearnStartDateTo] = useState("");

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setDebouncedPokerhubUserId(pokerhubUserId);
    }, 350);
    return () => window.clearTimeout(timer);
  }, [pokerhubUserId]);

  const fetchCourses = useCallback(async () => {
    if (!enabled) return;
    setLoading(true);
    setError(null);
    try {
      const params: Record<string, any> = buildFilterParams(filters);
      if (debouncedPokerhubUserId.trim()) {
        params.pokerhub_user_id = debouncedPokerhubUserId.trim();
      }
      if (learnStartDateFrom) {
        params.learn_start_date_from = learnStartDateFrom;
      }
      if (learnStartDateTo) {
        params.learn_start_date_to = learnStartDateTo;
      }
      const response = await axios.get(`${API_BASE}/api/reports/roistat-lessons`, {
        params: buildQueryParams(params),
      });
      setCourses(response.data?.courses || []);
    } catch (err: any) {
      setError(err?.response?.data?.detail || err?.message || "Не удалось загрузить матрицу уроков");
    } finally {
      setLoading(false);
    }
  }, [debouncedPokerhubUserId, enabled, filters, learnStartDateFrom, learnStartDateTo]);

  useEffect(() => {
    fetchCourses();
  }, [fetchCourses]);

  return {
    courses,
    loading,
    error,
    refresh: fetchCourses,
    pokerhubUserId,
    setPokerhubUserId,
    learnStartDateFrom,
    setLearnStartDateFrom,
    learnStartDateTo,
    setLearnStartDateTo,
  };
};
