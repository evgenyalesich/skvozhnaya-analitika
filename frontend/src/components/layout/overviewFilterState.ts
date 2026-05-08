import { addDays, endOfMonth, startOfMonth } from "date-fns";
import { FilterValues, RawColumnFilters } from "../../hooks/useReports";

export const DEFAULT_FILTERS: FilterValues = {
  startDate: null,
  endDate: null,
  bots: [],
  companies: [],
  utmSource: [],
  utmCampaign: [],
  utmMedium: [],
  utmContent: [],
  utmTerm: [],
  userScope: "all",
  touchMode: "event",
  displayMode: "weekly",
};

export const DEFAULT_RAW_FILTERS: RawColumnFilters = {
  botKeys: [],
  tgUserId: "",
  utmSource: [],
  utmCampaign: [],
  utmMedium: [],
  utmContent: [],
  utmTerm: [],
  advertisingCompanies: [],
  convertedToLead: null,
  registeredPlatform: null,
  startedLearning: null,
  completedCourse: null,
  usedSimulator: null,
  interviewReached: null,
  interviewPassed: null,
  offerReceived: null,
  contractSigned: null,
  distanceGrinding: null,
  interviewReachedStatus: "",
  interviewPassedStatus: "",
  offerReceivedStatus: "",
  contractSignedStatus: "",
  channelSubscribed: null,
  communityMember: null,
  teamMember: null,
  communityMemberStatus: "",
  internalStatus: "",
  userBlock: null,
  userStatus: "",
  firstTouchPresent: null,
  lastTouchPresent: null,
};

export const buildPresetRange = (preset: "today" | "7d" | "month" | "prev_month", now = new Date()) => {
  if (preset === "today") {
    return { startDate: now, endDate: now };
  }
  if (preset === "7d") {
    return { startDate: addDays(now, -6), endDate: now };
  }
  if (preset === "month") {
    return { startDate: startOfMonth(now), endDate: endOfMonth(now) };
  }
  const prevMonth = addDays(startOfMonth(now), -1);
  return { startDate: startOfMonth(prevMonth), endDate: endOfMonth(prevMonth) };
};

