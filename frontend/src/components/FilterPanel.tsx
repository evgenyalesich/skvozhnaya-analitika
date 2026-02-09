import React from "react";
import Box from "@mui/material/Box";
import Grid from "@mui/material/Grid";
import Button from "@mui/material/Button";
import TextField from "@mui/material/TextField";
import Stack from "@mui/material/Stack";
import LinearProgress from "@mui/material/LinearProgress";
import Autocomplete from "@mui/material/Autocomplete";
import Chip from "@mui/material/Chip";
import { DatePicker } from "@mui/x-date-pickers/DatePicker";
import { LocalizationProvider } from "@mui/x-date-pickers/LocalizationProvider";
import { AdapterDateFns } from "@mui/x-date-pickers/AdapterDateFns";
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
  loading: boolean;
}

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
  loading,
}) => {
  const selectedBotOptions = botOptions.filter((option) => filters.bots.includes(option.value));

  const renderBotSelect = () => (
    <Grid item xs={12} md={4} lg={3}>
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
      <Stack direction="row" spacing={1} mt={0.5}>
        <Button
          size="small"
          onClick={() => onChange("bots", botOptions.map((option) => option.value))}
          disabled={!botOptions.length}
        >
          Все
        </Button>
        <Button
          size="small"
          onClick={() => onChange("bots", [])}
          disabled={!filters.bots.length}
        >
          Очистить
        </Button>
      </Stack>
    </Grid>
  );

  const renderMultiSelect = (
    label: string,
    value: string[],
    options: string[],
    key: string,
    placeholder?: string
  ) => (
    <Grid item xs={12} md={4} lg={3}>
      <Autocomplete
        multiple
        options={options}
        value={value}
        onChange={(_, newValue) => onChange(key, newValue)}
        size="small"
        disableCloseOnSelect
        getOptionLabel={(option) => option}
        renderTags={(tagValue, getTagProps) =>
          tagValue.map((option, index) => (
            (() => {
              const tagProps = getTagProps({ index });
              const { key: _key, ...rest } = tagProps;
              return <Chip key={option} label={option} {...rest} size="small" />;
            })()
          ))
        }
        renderInput={(params) => (
          <TextField {...params} label={label} placeholder={placeholder || label} fullWidth />
        )}
      />
      <Stack direction="row" spacing={1} mt={0.5}>
        <Button
          size="small"
          onClick={() => onChange(key, options)}
          disabled={!options.length}
        >
          Все
        </Button>
        <Button size="small" onClick={() => onChange(key, [])} disabled={!value.length}>
          Очистить
        </Button>
      </Stack>
    </Grid>
  );

  return (
    <Box mb={2} p={2} bgcolor="#fff" borderRadius={2} boxShadow={1}>
      <LocalizationProvider dateAdapter={AdapterDateFns}>
        <Grid container spacing={2}>
          <Grid item xs={12} sm={6} md={3}>
            <DatePicker
              label="Дата с"
              value={filters.startDate}
              onChange={(value) => onChange("startDate", value)}
              slotProps={{ textField: { fullWidth: true, size: "small" } }}
            />
          </Grid>
          <Grid item xs={12} sm={6} md={3}>
            <DatePicker
              label="Дата по"
              value={filters.endDate}
              onChange={(value) => onChange("endDate", value)}
              slotProps={{ textField: { fullWidth: true, size: "small" } }}
            />
          </Grid>
          {renderBotSelect()}
          {renderMultiSelect("Компания", filters.companies, companies, "companies")}
          {renderMultiSelect("UTM Source", filters.utmSource, utmSource, "utmSource")}
          {renderMultiSelect("UTM Campaign", filters.utmCampaign, utmCampaign, "utmCampaign")}
          {renderMultiSelect("UTM Medium", filters.utmMedium, utmMedium, "utmMedium")}
          {renderMultiSelect("UTM Content", filters.utmContent, utmContent, "utmContent")}
          {renderMultiSelect("UTM Term", filters.utmTerm, utmTerm, "utmTerm")}
          <Grid item xs={12} sm={6} md={3} alignSelf="center">
            <Button variant="contained" fullWidth onClick={onApply} disabled={loading}>
              {loading ? "Применение..." : "ПРИМЕНИТЬ"}
            </Button>
          </Grid>
        </Grid>
        {loading && <LinearProgress sx={{ mt: 1 }} />}
      </LocalizationProvider>
    </Box>
  );
};

export default FilterPanel;
