import { format as formatDate, isValid } from "date-fns";
import { FilterValues } from "../../hooks/useReports";

export type ActiveFilterChip = { key: keyof FilterValues; label: string; value?: string };

export const buildActiveFilterChips = (
  activeFilters: FilterValues,
  resolveBotLabel: (botKey: string) => string,
): ActiveFilterChip[] => {
  const chips: ActiveFilterChip[] = [];
  if (activeFilters.startDate && isValid(activeFilters.startDate)) {
    chips.push({ key: "startDate", label: `C ${formatDate(activeFilters.startDate, "dd.MM.yyyy")}` });
  }
  if (activeFilters.endDate && isValid(activeFilters.endDate)) {
    chips.push({ key: "endDate", label: `По ${formatDate(activeFilters.endDate, "dd.MM.yyyy")}` });
  }
  activeFilters.bots.forEach((bot) => chips.push({ key: "bots", value: bot, label: resolveBotLabel(bot) }));
  activeFilters.companies.forEach((company) => chips.push({ key: "companies", value: company, label: company }));
  activeFilters.utmSource.forEach((utm) => chips.push({ key: "utmSource", value: utm, label: `src: ${utm}` }));
  activeFilters.utmCampaign.forEach((utm) => chips.push({ key: "utmCampaign", value: utm, label: `cmp: ${utm}` }));
  activeFilters.utmMedium.forEach((utm) => chips.push({ key: "utmMedium", value: utm, label: `med: ${utm}` }));
  activeFilters.utmContent.forEach((utm) => chips.push({ key: "utmContent", value: utm, label: `cnt: ${utm}` }));
  activeFilters.utmTerm.forEach((utm) => chips.push({ key: "utmTerm", value: utm, label: `term: ${utm}` }));
  if (activeFilters.touchMode !== "event") {
    chips.push({
      key: "touchMode",
      label: activeFilters.touchMode === "first_touch" ? "First Touch" : "Last Touch",
    });
  }
  if (activeFilters.displayMode !== "weekly") {
    chips.push({ key: "displayMode", label: "Событийное" });
  }
  return chips;
};

