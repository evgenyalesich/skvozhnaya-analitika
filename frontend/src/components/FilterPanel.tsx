import React from "react";
import Box from "@mui/material/Box";
import Grid from "@mui/material/Grid";
import Button from "@mui/material/Button";
import TextField from "@mui/material/TextField";
import MenuItem from "@mui/material/MenuItem";
import { DatePicker } from "@mui/x-date-pickers/DatePicker";
import { LocalizationProvider } from "@mui/x-date-pickers/LocalizationProvider";
import { AdapterDateFns } from "@mui/x-date-pickers/AdapterDateFns";

export interface FilterPanelProps {
  bots: string[];
  filters: Record<string, any>;
  onChange: (key: string, value: any) => void;
  onApply: () => void;
}

const FilterPanel: React.FC<FilterPanelProps> = ({ bots, filters, onChange, onApply }) => (
  <Box mb={2} p={2} bgcolor="#fff" borderRadius={2} boxShadow={1}>
    <LocalizationProvider dateAdapter={AdapterDateFns}>
      <Grid container spacing={2} alignItems="center">
        <Grid item xs={12} sm={5} md={3}>
          <DatePicker
            label="Date from"
            value={filters.startDate}
            onChange={(value) => onChange("startDate", value)}
            slotProps={{ textField: { fullWidth: true } }}
          />
        </Grid>
        <Grid item xs={12} sm={5} md={3}>
          <DatePicker
            label="Date to"
            value={filters.endDate}
            onChange={(value) => onChange("endDate", value)}
            slotProps={{ textField: { fullWidth: true } }}
          />
        </Grid>
        <Grid item xs={12} sm={10} md={4}>
          <TextField
            select
            fullWidth
            label="Bot"
            value={filters.bot || ""}
            onChange={(event) => onChange("bot", event.target.value)}
          >
            <MenuItem value="">All bots</MenuItem>
            {bots.map((bot) => (
              <MenuItem key={bot} value={bot}>
                {bot}
              </MenuItem>
            ))}
          </TextField>
        </Grid>
        <Grid item xs={12} sm={2} md={2}>
          <Button variant="contained" fullWidth onClick={onApply}>
            APPLY
          </Button>
        </Grid>
      </Grid>
    </LocalizationProvider>
  </Box>
);

export default FilterPanel;
