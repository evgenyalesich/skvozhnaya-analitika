import { useCallback, useEffect, useState } from "react";
import axios from "axios";
import { format, isValid } from "date-fns";

const API_BASE = import.meta.env.VITE_API_BASE || "";

export interface FilterValues {
  startDate: Date | null;
  endDate: Date | null;
  bots: string[];
  companies: string[];
  utmSource: string[];
  utmCampaign: string[];
  utmMedium: string[];
  utmContent: string[];
  utmTerm: string[];
  userScope: "all" | "new" | "old";
  touchMode: "event" | "first_touch" | "last_touch";
  displayMode: "weekly" | "cohort";
}

export interface RawReportParams {
  limit: number;
  offset: number;
  sortBy: string;
  sortDirection: "asc" | "desc";
}

export interface RawColumnFilters {
  botKeys: string[];
  tgUserId: string;
  utmSource: string[];
  utmCampaign: string[];
  utmMedium: string[];
  utmContent: string[];
  utmTerm: string[];
  advertisingCompanies: string[];
  convertedToLead: boolean | null;
  registeredPlatform: boolean | null;
  startedLearning: boolean | null;
  completedCourse: boolean | null;
  usedSimulator: boolean | null;
  interviewReached: boolean | null;
  interviewPassed: boolean | null;
  offerReceived: boolean | null;
  contractSigned: boolean | null;
  distanceGrinding: boolean | null;
  interviewReachedStatus: string;
  interviewPassedStatus: string;
  offerReceivedStatus: string;
  contractSignedStatus: string;
  channelSubscribed: boolean | null;
  communityMember: boolean | null;
  teamMember: boolean | null;
  communityMemberStatus: string;
  internalStatus: string;
  userBlock: boolean | null;
  userStatus: string;
  firstTouchPresent: boolean | null;
  lastTouchPresent: boolean | null;
}

export interface RawUserModel {
  id: number;
  bot_key: string;
  tg_user_id: number;
  created_at: string;
  first_seen_at_system: string | null;
  first_seen_at_bot: string | null;
  new_in_system: boolean;
  new_in_bot: boolean;
  old_in_system: boolean;
  ingested_at: string;
  user_block: boolean | null;
  utm_source: string;
  utm_campaign: string;
  utm_medium: string | null;
  utm_content: string | null;
  utm_term: string | null;
  platform_utm_source?: string | null;
  platform_utm_campaign?: string | null;
  platform_utm_medium?: string | null;
  platform_utm_content?: string | null;
  platform_utm_term?: string | null;
  first_touch_bot: string | null;
  first_touch_campaign: string | null;
  last_touch_bot: string | null;
  last_touch_campaign: string | null;
  advertising_company: string | null;
  budget: number;
  converted_to_lead: boolean;
  registered_platform: boolean;
  started_learning: boolean;
  learn_start_date?: string | null;
  completed_course: boolean;
  completed_course_at?: string | null;
  course_duration_days?: number | null;
  used_simulator: boolean;
  interview_reached: boolean;
  interview_passed: boolean;
  offer_received: boolean;
  contract_signed: boolean;
  distance_grinding: boolean;
  interview_reached_status: string | null;
  interview_passed_status: string | null;
  offer_received_status: string | null;
  contract_signed_status: string | null;
  channel_subscribed: boolean;
  community_member: boolean;
  team_member: boolean;
  community_member_status: string | null;
  internal_status: string | null;
  source_category?: string | null;
}

export interface ConversionRow {
  bot_key: string;
  entered: number;
  converted: number;
  conversion_rate: number;
}

export const buildFilterParams = (filters: FilterValues) => {
  const params: Record<string, any> = {};
  if (filters.startDate && isValid(filters.startDate)) {
    params.start_date = format(filters.startDate, "yyyy-MM-dd");
  }
  if (filters.endDate && isValid(filters.endDate)) {
    params.end_date = format(filters.endDate, "yyyy-MM-dd");
  }
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
  if (filters.userScope && filters.userScope !== "all") {
    params.user_scope = filters.userScope;
  }
  if (filters.touchMode && filters.touchMode !== "event") {
    params.touch_mode = filters.touchMode;
  }
  return params;
};

export const buildRawFilterParams = (filters: RawColumnFilters) => {
  const params: Record<string, any> = {};
  const rawBotKeys = Array.isArray((filters as any)?.botKeys) ? (filters as any).botKeys : [];
  const segmentCategories: string[] = [];
  const regularBotKeys: string[] = [];

  rawBotKeys.forEach((key: string) => {
    if (key === "lead") {
      regularBotKeys.push("lead");
      segmentCategories.push("almanah");
      return;
    }
    if (key === "__direct_source__") {
      regularBotKeys.push("lead");
      segmentCategories.push("direct_source");
      return;
    }
    regularBotKeys.push(key);
  });

  const uniqueBotKeys = Array.from(new Set(regularBotKeys));
  if (uniqueBotKeys.length) {
    params.raw_bot_key = uniqueBotKeys;
  }
  if (filters.tgUserId.trim()) {
    params.raw_tg_user_id = filters.tgUserId.trim();
  }
  if (filters.utmSource.length) {
    params.raw_utm_source = filters.utmSource;
  }
  if (filters.utmCampaign.length) {
    params.raw_utm_campaign = filters.utmCampaign;
  }
  if (filters.utmMedium.length) {
    params.raw_utm_medium = filters.utmMedium;
  }
  if (filters.utmContent.length) {
    params.raw_utm_content = filters.utmContent;
  }
  if (filters.utmTerm.length) {
    params.raw_utm_term = filters.utmTerm;
  }
  if (filters.advertisingCompanies.length) {
    params.raw_advertising_company = filters.advertisingCompanies;
  }
  if (filters.convertedToLead !== null) {
    params.raw_converted_to_lead = filters.convertedToLead;
  }
  if (filters.registeredPlatform !== null) {
    params.raw_registered_platform = filters.registeredPlatform;
  }
  if (filters.startedLearning !== null) {
    params.raw_started_learning = filters.startedLearning;
  }
  if (filters.completedCourse !== null) {
    params.raw_completed_course = filters.completedCourse;
  }
  if (filters.usedSimulator !== null) {
    params.raw_used_simulator = filters.usedSimulator;
  }
  if (filters.interviewReached !== null) {
    params.raw_interview_reached = filters.interviewReached;
  }
  if (filters.interviewPassed !== null) {
    params.raw_interview_passed = filters.interviewPassed;
  }
  if (filters.offerReceived !== null) {
    params.raw_offer_received = filters.offerReceived;
  }
  if (filters.contractSigned !== null) {
    params.raw_contract_signed = filters.contractSigned;
  }
  if (filters.distanceGrinding !== null) {
    params.raw_distance_grinding = filters.distanceGrinding;
  }
  if (filters.interviewReachedStatus.trim()) {
    params.raw_interview_reached_status = filters.interviewReachedStatus.trim();
  }
  if (filters.interviewPassedStatus.trim()) {
    params.raw_interview_passed_status = filters.interviewPassedStatus.trim();
  }
  if (filters.offerReceivedStatus.trim()) {
    params.raw_offer_received_status = filters.offerReceivedStatus.trim();
  }
  if (filters.contractSignedStatus.trim()) {
    params.raw_contract_signed_status = filters.contractSignedStatus.trim();
  }
  if (filters.channelSubscribed !== null) {
    params.raw_channel_subscribed = filters.channelSubscribed;
  }
  if (filters.communityMember !== null) {
    params.raw_community_member = filters.communityMember;
  }
  if (filters.teamMember !== null) {
    params.raw_team_member = filters.teamMember;
  }
  if (filters.communityMemberStatus.trim()) {
    params.raw_community_member_status = filters.communityMemberStatus.trim();
  }
  if (filters.internalStatus.trim()) {
    params.raw_internal_status = filters.internalStatus.trim();
  }
  if (filters.userBlock !== null) {
    params.raw_user_block = filters.userBlock;
  }
  if (filters.userStatus.trim()) {
    params.raw_user_status = filters.userStatus.trim();
  }
  if (segmentCategories.length) {
    params.raw_source_category = Array.from(new Set(segmentCategories));
  }
  return params;
};

export const buildQueryParams = (params: Record<string, any>) => {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value === undefined || value === null) {
      return;
    }
    if (Array.isArray(value)) {
      value.forEach((item) => {
        if (item !== undefined && item !== null) {
          search.append(key, String(item));
        }
      });
      return;
    }
    search.append(key, String(value));
  });
  return search;
};

export const useReports = (
  filters: FilterValues,
  rawParams: RawReportParams,
  rawFilters: RawColumnFilters,
  breakdownGroup: string = "utm_source",
  options?: { enabled?: boolean; pollMs?: number }
) => {
  const [total, setTotal] = useState<any>(null);
  const [daily, setDaily] = useState<Array<{ date: string; users: number }>>([]);
  const [breakdown, setBreakdown] = useState<any[]>([]);
  const [conversions, setConversions] = useState<ConversionRow[]>([]);
  const [stages, setStages] = useState<Record<string, number>>({});
  const [raw, setRaw] = useState<any[]>([]);
  const [rawTotal, setRawTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const enabled = options?.enabled ?? true;
  const pollMs = options?.pollMs ?? 0;

  const fetchReports = useCallback(async () => {
    if (!enabled) {
      return;
    }
    setLoading(true);
    setError(null);
    if (!filters.bots.length) {
      setTotal(null);
      setDaily([]);
      setBreakdown([]);
      setConversions([]);
      setStages({});
      setLoading(false);
      return;
    }
    const params = buildFilterParams(filters);
    try {
      const [
        totalRes,
        dailyRes,
        breakdownRes,
        conversionsRes,
        stagesRes,
      ] = await Promise.all([
        axios.get(`${API_BASE}/api/reports/funnel-start/total`, {
          params: buildQueryParams(params),
        }),
        axios.get(`${API_BASE}/api/reports/funnel-start/daily`, {
          params: buildQueryParams({ ...params }),
        }),
        axios.get(`${API_BASE}/api/reports/funnel-start/breakdown`, {
          params: buildQueryParams({ ...params, group_by: breakdownGroup, limit: 20 }),
        }),
        axios.get(`${API_BASE}/api/reports/funnel-start/conversions`, {
          params: buildQueryParams(params),
        }),
        axios.get(`${API_BASE}/api/reports/funnel-start/stages`, {
          params: buildQueryParams(params),
        }),
      ]);
      setTotal(totalRes.data);
      setDaily(dailyRes.data.data || []);
      setBreakdown(breakdownRes.data.breakdown || []);
      setConversions(conversionsRes.data.conversions || []);
      setStages(stagesRes.data.stages || {});
    } catch (err: any) {
      console.error(err);
      setError(err?.response?.data?.detail || err?.message || "Не удалось загрузить данные");
    } finally {
      setLoading(false);
    }
  }, [breakdownGroup, enabled, filters]);

  useEffect(() => {
    if (!enabled) {
      return;
    }
    fetchReports();
  }, [enabled, fetchReports]);

  useEffect(() => {
    if (!enabled || pollMs <= 0) {
      return;
    }
    const id = window.setInterval(() => {
      if (document.visibilityState === "visible") {
        fetchReports();
      }
    }, pollMs);
    return () => window.clearInterval(id);
  }, [enabled, fetchReports, pollMs]);

  const fetchRaw = useCallback(async () => {
    if (!enabled) return;
    const mainParams = buildFilterParams(filters);
    if (mainParams.touch_mode === "first_touch") {
      mainParams.touch_mode = "first";
    } else if (mainParams.touch_mode === "last_touch") {
      mainParams.touch_mode = "last";
    }
    const rawP = buildRawFilterParams(rawFilters);
    const combined = {
      ...mainParams,
      ...rawP,
      limit: rawParams.limit,
      offset: rawParams.offset,
      sort_by: rawParams.sortBy,
      sort_direction: rawParams.sortDirection,
    };
    try {
      const res = await axios.get(`${API_BASE}/api/reports/funnel-start/raw`, {
        params: buildQueryParams(combined),
      });
      setRaw(res.data.users || []);
      setRawTotal(res.data.total || 0);
    } catch (err: any) {
      console.error("fetchRaw error:", err);
      setRaw([]);
      setRawTotal(0);
    }
  }, [enabled, filters, rawFilters, rawParams]);

  useEffect(() => {
    if (!enabled) return;
    fetchRaw();
  }, [enabled, fetchRaw]);

  return {
    total,
    daily,
    breakdown,
    conversions,
    stages,
    raw,
    rawTotal,
    loading,
    error,
    refresh: fetchReports,
  };
};
