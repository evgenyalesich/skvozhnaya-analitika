// Панель фильтров: период, боты, рекламные компании, UTM (source/campaign/medium/content/term),
// user_scope (new/old/all), touch_mode (event/first/last), display_mode (weekly/cohort).
// Два режима: черновик (draft) в OverviewPage — применяется кнопкой "ПРИМЕНИТЬ".
import React, { useMemo, useState } from "react";
import Box from "@mui/material/Box";
import Grid from "@mui/material/Grid";
import Button from "@mui/material/Button";
import TextField from "@mui/material/TextField";
import Stack from "@mui/material/Stack";
import LinearProgress from "@mui/material/LinearProgress";
import Autocomplete from "@mui/material/Autocomplete";
import Chip from "@mui/material/Chip";
import ToggleButton from "@mui/material/ToggleButton";
import ToggleButtonGroup from "@mui/material/ToggleButtonGroup";
import FilterListIcon from "@mui/icons-material/FilterList";
import FormControl from "@mui/material/FormControl";
import InputLabel from "@mui/material/InputLabel";
import MenuItem from "@mui/material/MenuItem";
import Select from "@mui/material/Select";
import Typography from "@mui/material/Typography";
import Popover from "@mui/material/Popover";
import Divider from "@mui/material/Divider";
import TuneIcon from "@mui/icons-material/Tune";
import KeyboardArrowDownIcon from "@mui/icons-material/KeyboardArrowDown";
import { DatePicker } from "@mui/x-date-pickers/DatePicker";
import { LocalizationProvider } from "@mui/x-date-pickers/LocalizationProvider";
import { AdapterDateFns } from "@mui/x-date-pickers/AdapterDateFns";
import { endOfMonth, format, isValid, startOfMonth, subDays, subMonths } from "date-fns";
import { FilterValues } from "../hooks/useReports";

export interface BotSelectOption {
  value: string;
  label: string;
}

export interface FilterPanelProps {
  filters: FilterValues;
  botOptions: BotSelectOption[];
  companies: string[];
  utmSource: string[];
  utmCampaign: string[];
  utmMedium: string[];
  utmContent: string[];
  utmTerm: string[];
  onChange: (key: string, value: any) => void;
  onApply: () => void;
  onPresetSelect?: (preset: "today" | "7d" | "month" | "prev_month") => void;
  onResetFilters?: () => void;
  loading: boolean;
  hideTouch?: boolean;
  showDisplayMode?: boolean;
}

const popoverPaperSx = {
  borderRadius: "22px",
  border: "1px solid var(--app-shell-border)",
  background: "var(--app-panel-bg)",
  boxShadow: "var(--app-shell-shadow)",
  backdropFilter: "blur(18px)",
};

const FilterPanel: React.FC<FilterPanelProps> = ({
  filters,
  botOptions,
  companies,
  utmSource,
  utmCampaign,
  utmMedium,
  utmContent,
  utmTerm,
  onChange,
  onApply,
  onPresetSelect,
  onResetFilters,
  loading,
  hideTouch = false,
  showDisplayMode = false,
}) => {
  const safeStartDate = filters.startDate && isValid(filters.startDate) ? filters.startDate : null;
  const safeEndDate = filters.endDate && isValid(filters.endDate) ? filters.endDate : null;
  const [anchorEl, setAnchorEl] = useState<HTMLButtonElement | null>(null);
  const [advancedCategory, setAdvancedCategory] = useState("all");
  const selectedBotOptions = botOptions.filter((option) => filters.bots.includes(option.value));

  const touchLabel = useMemo(() => {
    switch (filters.touchMode) {
      case "first_touch":
        return "First Touch";
      case "last_touch":
        return "Last Touch";
      default:
        return "Без атрибуции";
    }
  }, [filters.touchMode]);

  const displaySummary = useMemo(() => {
    const parts: string[] = [];
    if (safeStartDate) {
      parts.push(`с ${format(safeStartDate, "dd.MM.yyyy")}`);
    }
    if (safeEndDate) {
      parts.push(`по ${format(safeEndDate, "dd.MM.yyyy")}`);
    }
    if (filters.bots.length) {
      parts.push(`базы: ${filters.bots.length}`);
    }
    if (filters.companies.length) {
      parts.push(`РК: ${filters.companies.length}`);
    }
    return parts.length ? parts.join(" • ") : "Период и атрибуция";
  }, [filters.bots.length, filters.companies.length, safeEndDate, safeStartDate]);

  const renderBotSelect = () => (
    <Grid item xs={12} md={6}>
      <Autocomplete
        multiple
        options={botOptions}
        value={selectedBotOptions}
        onChange={(_, newValue) => onChange("bots", newValue.map((option) => option.value))}
        size="small"
        disableCloseOnSelect
        getOptionLabel={(option) => option.label}
        isOptionEqualToValue={(option, value) => option.value === value.value}
        renderTags={(tagValue, getTagProps) =>
          tagValue.map((option, index) => {
            const tagProps = getTagProps({ index });
            const { key: _key, ...rest } = tagProps;
            return <Chip key={option.value} label={option.label} {...rest} size="small" />;
          })
        }
        renderInput={(params) => <TextField {...params} label="Базы" placeholder="Базы" fullWidth />}
      />
    </Grid>
  );

  const renderMultiSelect = (
    label: string,
    value: string[],
    options: string[],
    key: string,
    placeholder?: string
  ) => (
    <Grid item xs={12} md={6}>
      <Autocomplete
        multiple
        options={options}
        value={value}
        onChange={(_, newValue) => onChange(key, newValue)}
        size="small"
        disableCloseOnSelect
        getOptionLabel={(option) => option}
        renderTags={(tagValue, getTagProps) =>
          tagValue.map((option, index) => {
            const tagProps = getTagProps({ index });
            const { key: _key, ...rest } = tagProps;
            return <Chip key={option} label={option} {...rest} size="small" />;
          })
        }
        renderInput={(params) => (
          <TextField {...params} label={label} placeholder={placeholder || label} fullWidth />
        )}
      />
    </Grid>
  );

  const filterBlocks: Array<{ key: string; node: React.ReactNode }> = [
    { key: "bots", node: renderBotSelect() },
    { key: "companies", node: renderMultiSelect("Компания", filters.companies, companies, "companies") },
    { key: "utmSource", node: renderMultiSelect("UTM Source", filters.utmSource, utmSource, "utmSource") },
    { key: "utmCampaign", node: renderMultiSelect("UTM Campaign", filters.utmCampaign, utmCampaign, "utmCampaign") },
    { key: "utmMedium", node: renderMultiSelect("UTM Medium", filters.utmMedium, utmMedium, "utmMedium") },
    { key: "utmContent", node: renderMultiSelect("UTM Content", filters.utmContent, utmContent, "utmContent") },
    { key: "utmTerm", node: renderMultiSelect("UTM Term", filters.utmTerm, utmTerm, "utmTerm") },
  ];

  const visibleBlocks =
    advancedCategory === "all"
      ? filterBlocks
      : filterBlocks.filter((block) => block.key === advancedCategory);

  const handleApply = () => {
    onApply();
    setAnchorEl(null);
  };

  return (
    <LocalizationProvider dateAdapter={AdapterDateFns}>
      <Box
        sx={{
          my: 1.5,
          p: 1.25,
          borderRadius: "20px",
          border: "1px solid var(--app-shell-border)",
          background: "var(--app-panel-bg)",
          boxShadow: "var(--app-shell-shadow)",
          backdropFilter: "blur(16px)",
        }}
      >
        <Stack
          direction={{ xs: "column", md: "row" }}
          spacing={1.25}
          alignItems={{ xs: "stretch", md: "center" }}
          justifyContent="space-between"
        >
          <Stack direction={{ xs: "column", sm: "row" }} spacing={1} alignItems={{ xs: "stretch", sm: "center" }} flexWrap="wrap">
            <Button
              variant="outlined"
              startIcon={<FilterListIcon />}
              endIcon={<KeyboardArrowDownIcon />}
              onClick={(event) => setAnchorEl(event.currentTarget)}
              sx={{ minHeight: 42, px: 1.6, borderRadius: "14px", justifyContent: "space-between" }}
            >
              Фильтры
            </Button>
            <Chip
              label={displaySummary}
              variant="outlined"
              sx={{
                maxWidth: { xs: "100%", md: 360 },
                "& .MuiChip-label": {
                  display: "block",
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                },
              }}
            />
            {!hideTouch && (
              <Chip label={touchLabel} sx={{ background: "var(--c-blue-bg)", color: "var(--c-blue)", fontWeight: 800 }} />
            )}
          </Stack>

          <Stack direction="row" spacing={1} alignItems="center" justifyContent={{ xs: "space-between", md: "flex-end" }}>
            <Button
              variant="contained"
              onClick={handleApply}
              disabled={loading}
              sx={{
                minHeight: 42,
                minWidth: 158,
                background: "linear-gradient(135deg, var(--c-blue), #1d4ed8)",
              }}
            >
              {loading ? "Применение..." : "Применить"}
            </Button>
          </Stack>
        </Stack>
        {loading && <LinearProgress sx={{ mt: 1.2 }} />}
      </Box>

      <Popover
        open={Boolean(anchorEl)}
        anchorEl={anchorEl}
        onClose={() => setAnchorEl(null)}
        anchorOrigin={{ vertical: "bottom", horizontal: "left" }}
        transformOrigin={{ vertical: "top", horizontal: "left" }}
        PaperProps={{
          sx: {
            ...popoverPaperSx,
            width: "min(1120px, calc(100vw - 32px))",
            mt: 1,
          },
        }}
      >
        <Box sx={{ p: 2 }}>
          <Stack direction="row" justifyContent="space-between" alignItems="center" mb={1.5}>
            <Stack direction="row" spacing={1} alignItems="center">
              <TuneIcon sx={{ color: "var(--c-blue)" }} />
              <Typography variant="subtitle1" sx={{ fontWeight: 800, color: "var(--c-ink)" }}>
                Фильтры отчета
              </Typography>
            </Stack>
            <Button size="small" onClick={() => setAnchorEl(null)}>
              Скрыть
            </Button>
          </Stack>

          <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap mb={2}>
            {([
              ["today", "Сегодня"],
              ["7d", "7 дней"],
              ["month", "Этот месяц"],
              ["prev_month", "Прошлый месяц"],
            ] as const).map(([key, label]) => (
              <Button
                key={key}
                size="small"
                variant="outlined"
                onClick={() => {
                  if (onPresetSelect) {
                    onPresetSelect(key);
                  } else {
                    const today = new Date();
                    if (key === "today") {
                      onChange("startDate", today);
                      onChange("endDate", today);
                    }
                    if (key === "7d") {
                      onChange("startDate", subDays(today, 6));
                      onChange("endDate", today);
                    }
                    if (key === "month") {
                      onChange("startDate", startOfMonth(today));
                      onChange("endDate", endOfMonth(today));
                    }
                    if (key === "prev_month") {
                      const prev = subMonths(today, 1);
                      onChange("startDate", startOfMonth(prev));
                      onChange("endDate", endOfMonth(prev));
                    }
                  }
                }}
              >
                {label}
              </Button>
            ))}
            {onResetFilters && (
              <Button size="small" color="inherit" onClick={onResetFilters}>
                Сбросить все
              </Button>
            )}
          </Stack>

          <Grid container spacing={2}>
            <Grid item xs={12} md={3}>
              <DatePicker
                label="Дата с"
                value={safeStartDate}
                onChange={(value) => onChange("startDate", value)}
                format="dd.MM.yyyy"
                slotProps={{ textField: { fullWidth: true, size: "small" } }}
              />
            </Grid>
            <Grid item xs={12} md={3}>
              <DatePicker
                label="Дата по"
                value={safeEndDate}
                onChange={(value) => onChange("endDate", value)}
                format="dd.MM.yyyy"
                slotProps={{ textField: { fullWidth: true, size: "small" } }}
              />
            </Grid>
            {!hideTouch && (
              <Grid item xs={12} md={6}>
                <ToggleButtonGroup
                  value={filters.touchMode}
                  exclusive
                  size="small"
                  fullWidth
                  sx={{
                    minHeight: 40,
                    "& .MuiToggleButton-root": {
                      border: "1px solid var(--app-table-divider)",
                      color: "var(--c-ink2)",
                      fontWeight: 700,
                      "&.Mui-selected": {
                        color: "#fff",
                        background: "linear-gradient(135deg, var(--c-blue), #1d4ed8)",
                      },
                    },
                  }}
                  onChange={(_, val) => { if (val) { onChange("touchMode", val); } }}
                >
                  <ToggleButton value="event">Без атрибуции</ToggleButton>
                  <ToggleButton value="first_touch">First Touch</ToggleButton>
                  <ToggleButton value="last_touch">Last Touch</ToggleButton>
                </ToggleButtonGroup>
              </Grid>
            )}
            {showDisplayMode && (
              <Grid item xs={12} md={6}>
                <ToggleButtonGroup
                  value={filters.displayMode}
                  exclusive
                  size="small"
                  fullWidth
                  sx={{
                    minHeight: 40,
                    "& .MuiToggleButton-root": {
                      border: "1px solid var(--app-table-divider)",
                      color: "var(--c-ink2)",
                      fontWeight: 700,
                      "&.Mui-selected": {
                        color: "#fff",
                        background: "linear-gradient(135deg, var(--c-blue), #1d4ed8)",
                      },
                    },
                  }}
                  onChange={(_, val) => { if (val) { onChange("displayMode", val); } }}
                >
                  <ToggleButton value="weekly">Weekly</ToggleButton>
                  <ToggleButton value="cohort">Событийное</ToggleButton>
                </ToggleButtonGroup>
              </Grid>
            )}
          </Grid>

          <Divider sx={{ my: 2 }} />

          <Grid container spacing={2} alignItems="flex-start">
            <Grid item xs={12} md={4}>
              <FormControl size="small" fullWidth>
                <InputLabel id="advanced-filter-category-label">Показать категорию</InputLabel>
                <Select
                  labelId="advanced-filter-category-label"
                  label="Показать категорию"
                  value={advancedCategory}
                  onChange={(event) => setAdvancedCategory(String(event.target.value))}
                >
                  <MenuItem value="all">Все категории</MenuItem>
                  <MenuItem value="bots">Базы</MenuItem>
                  <MenuItem value="companies">Рекламные кабинеты</MenuItem>
                  <MenuItem value="utmSource">UTM Source</MenuItem>
                  <MenuItem value="utmCampaign">UTM Campaign</MenuItem>
                  <MenuItem value="utmMedium">UTM Medium</MenuItem>
                  <MenuItem value="utmContent">UTM Content</MenuItem>
                  <MenuItem value="utmTerm">UTM Term</MenuItem>
                </Select>
              </FormControl>
            </Grid>
          </Grid>

          <Grid container spacing={2} mt={0.25}>
            {visibleBlocks.map((block) => (
              <React.Fragment key={block.key}>{block.node}</React.Fragment>
            ))}
          </Grid>

          <Stack direction="row" justifyContent="flex-end" spacing={1.25} mt={2}>
            <Button onClick={() => setAnchorEl(null)}>Скрыть</Button>
            <Button
              variant="contained"
              onClick={handleApply}
              disabled={loading}
              sx={{ background: "linear-gradient(135deg, var(--c-blue), #1d4ed8)" }}
            >
              Применить
            </Button>
          </Stack>
        </Box>
      </Popover>
    </LocalizationProvider>
  );
};

export default FilterPanel;
