import React, { useEffect, useMemo, useState } from "react";
import Dialog from "@mui/material/Dialog";
import DialogTitle from "@mui/material/DialogTitle";
import DialogContent from "@mui/material/DialogContent";
import DialogActions from "@mui/material/DialogActions";
import Button from "@mui/material/Button";
import TextField from "@mui/material/TextField";
import Stack from "@mui/material/Stack";
import FormControl from "@mui/material/FormControl";
import InputLabel from "@mui/material/InputLabel";
import Select from "@mui/material/Select";
import MenuItem from "@mui/material/MenuItem";
import Autocomplete from "@mui/material/Autocomplete";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import TableContainer from "@mui/material/TableContainer";
import LinearProgress from "@mui/material/LinearProgress";
import IconButton from "@mui/material/IconButton";
import DeleteIcon from "@mui/icons-material/Delete";
import Paper from "@mui/material/Paper";
import Typography from "@mui/material/Typography";
import Tabs from "@mui/material/Tabs";
import Tab from "@mui/material/Tab";
import Chip from "@mui/material/Chip";
import Accordion from "@mui/material/Accordion";
import AccordionSummary from "@mui/material/AccordionSummary";
import AccordionDetails from "@mui/material/AccordionDetails";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import Divider from "@mui/material/Divider";

import { BudgetWeeklyRow } from "../hooks/useBudgets";
import { AdvertisingCompanyOption } from "../hooks/useAdvertisingCompanies";

interface BudgetDialogProps {
  open: boolean;
  budgets: BudgetWeeklyRow[];
  loading: boolean;
  companies: AdvertisingCompanyOption[];
  onClose: () => void;
  onCreate: (payload: Omit<BudgetWeeklyRow, "id">) => Promise<void>;
  onUpdate: (id: number, patch: Partial<BudgetWeeklyRow>) => Promise<void>;
  onDelete: (id: number) => Promise<void>;
}

const BudgetDialog: React.FC<BudgetDialogProps> = ({
  open,
  budgets,
  loading,
  companies,
  onClose,
  onCreate,
  onUpdate: _onUpdate,
  onDelete,
}) => {
  const [drafts, setDrafts] = useState<BudgetWeeklyRow[]>([]);
  const [newRangeStart, setNewRangeStart] = useState("");
  const [newRangeEnd, setNewRangeEnd] = useState("");
  const [newCampaign, setNewCampaign] = useState("");
  const [newBot, setNewBot] = useState("");
  const [newAmount, setNewAmount] = useState("");
  const [saving, setSaving] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<BudgetWeeklyRow | null>(null);
  const [selectedMonth, setSelectedMonth] = useState<string>("all");
  const [budgetTab, setBudgetTab] = useState<"entries" | "gaps">("entries");
  const isHiddenTgSubsBudget = (row: Pick<BudgetWeeklyRow, "campaign" | "channel_key">) => {
    const campaign = (row.campaign || "").trim().toLowerCase();
    const channel = (row.channel_key || "").trim().toLowerCase();
    return (
      campaign === "tgsubs_card_house" ||
      campaign === "tgsubs_saloon" ||
      channel === "card_house" ||
      channel === "saloon"
    );
  };
  const visibleBudgets = useMemo(
    () => budgets.filter((row) => !isHiddenTgSubsBudget(row)),
    [budgets]
  );

  const parseLocalDate = (value: string) => {
    if (!value) return null;
    const [year, month, day] = value.split("-").map(Number);
    if (!year || !month || !day) return null;
    return new Date(year, month - 1, day);
  };

  const toDayKey = (value: Date) =>
    `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, "0")}-${String(value.getDate()).padStart(2, "0")}`;

  const startOfWeek = (value: Date) => {
    const date = new Date(value.getFullYear(), value.getMonth(), value.getDate());
    const diff = (date.getDay() + 6) % 7;
    date.setDate(date.getDate() - diff);
    return date;
  };

  const toWeekLabel = (value: string) => {
    const dt = parseLocalDate(value);
    if (!dt) return "";
    const start = startOfWeek(dt);
    const end = new Date(start);
    end.setDate(start.getDate() + 6);
    const fmt = (d: Date) =>
      `${String(d.getDate()).padStart(2, "0")}.${String(d.getMonth() + 1).padStart(2, "0")}.${d.getFullYear()}`;
    return `${fmt(start)} - ${fmt(end)}`;
  };

  const parseDecimal = (value: string) => {
    const normalized = value.replace(/\s+/g, "").replace(",", ".");
    if (!normalized) return Number.NaN;
    return Number(normalized);
  };

  useEffect(() => {
    if (open) {
      setDrafts(visibleBudgets);
      setNewRangeStart("");
      setNewRangeEnd("");
      setNewCampaign("");
      setNewBot("");
      setNewAmount("");
      const latestMonth = visibleBudgets
        .map((row) => (row.week_start && /^\d{4}-\d{2}/.test(row.week_start) ? row.week_start.slice(0, 7) : ""))
        .filter(Boolean)
        .sort()
        .pop();
      setSelectedMonth(latestMonth || "all");
      setBudgetTab("entries");
    }
  }, [open, visibleBudgets]);


  const companyOptions = React.useMemo(
    () => companies.map((company) => company.company_name).filter(Boolean),
    [companies]
  );
  const selectedCompany = companies.find((c) => c.company_name === newCampaign);
  const botOptions = selectedCompany?.bot_keys || [];

  const toDisplay = (value?: string) => (value ? value.split("-").reverse().join(".") : "");

  const monthOptions = useMemo(() => {
    const set = new Set<string>();
    drafts.forEach((row) => {
      if (row.week_start && /^\d{4}-\d{2}/.test(row.week_start)) {
        set.add(row.week_start.slice(0, 7));
      }
    });
    return Array.from(set).sort();
  }, [drafts]);

  const monthLabel = (value: string) => {
    if (value === "all") return "Все месяцы";
    const [y, m] = value.split("-");
    const names = [
      "Январь",
      "Февраль",
      "Март",
      "Апрель",
      "Май",
      "Июнь",
      "Июль",
      "Август",
      "Сентябрь",
      "Октябрь",
      "Ноябрь",
      "Декабрь",
    ];
    const idx = Number(m) - 1;
    return `${names[idx] || m} ${y}`;
  };

  const filteredDrafts = useMemo(() => {
    if (selectedMonth === "all") return drafts;
    return drafts.filter((row) => row.week_start?.startsWith(selectedMonth));
  }, [drafts, selectedMonth]);

  const handleCreate = async () => {
    if (!newRangeStart || !newRangeEnd || !newCampaign.trim()) return;
    const amount = parseDecimal(newAmount);
    if (Number.isNaN(amount)) return;

    const startDate = parseLocalDate(newRangeStart);
    const endDate = parseLocalDate(newRangeEnd);
    if (!startDate || !endDate) return;
    if (endDate < startDate) return;

    const days: string[] = [];
    const cursor = new Date(startDate.getFullYear(), startDate.getMonth(), startDate.getDate());
    const last = new Date(endDate.getFullYear(), endDate.getMonth(), endDate.getDate());
    while (cursor <= last) {
      days.push(toDayKey(cursor));
      cursor.setDate(cursor.getDate() + 1);
    }
    if (!days.length) return;
    const perDay = amount / days.length;

    setSaving(true);
    try {
      for (const day of days) {
        await onCreate({
          week_start: day,
          campaign: newCampaign.trim(),
          bot_key: newBot || null,
          amount: perDay,
          currency: "USD",
        });
      }
      setNewRangeStart("");
      setNewRangeEnd("");
      setNewCampaign("");
      setNewBot("");
      setNewAmount("");
    } finally {
      setSaving(false);
    }
  };

  const confirmDelete = async () => {
    if (!deleteTarget) return;
    await onDelete(deleteTarget.id);
    setDeleteTarget(null);
  };

  const filterStartDate = newRangeStart ? parseLocalDate(newRangeStart) : null;
  const filterEndDate = newRangeEnd ? parseLocalDate(newRangeEnd) : null;

  const coverage = useMemo(() => {
    if (!filterStartDate || !filterEndDate || !newCampaign.trim()) return [];
    const start = new Date(filterStartDate.getFullYear(), filterStartDate.getMonth(), filterStartDate.getDate());
    const end = new Date(filterEndDate.getFullYear(), filterEndDate.getMonth(), filterEndDate.getDate());
    if (end < start) return [];
    const days: string[] = [];
    const cursor = new Date(start);
    while (cursor <= end) {
      days.push(toDayKey(cursor));
      cursor.setDate(cursor.getDate() + 1);
    }
    const keyCampaign = newCampaign.trim().toLowerCase();
    const keyBot = (newBot || "").trim().toLowerCase();
    const existing = new Set(
      visibleBudgets
        .filter((row) => (row.campaign || "").trim().toLowerCase() === keyCampaign)
        .filter((row) => (row.bot_key || "").trim().toLowerCase() === keyBot)
        .map((row) => row.week_start)
    );
    return days.filter((day) => !existing.has(day));
  }, [visibleBudgets, filterStartDate, filterEndDate, newCampaign, newBot]);

  const sortedDrafts = useMemo(() => {
    return [...filteredDrafts].sort((a, b) => {
      const d1 = a.week_start || "";
      const d2 = b.week_start || "";
      if (d1 !== d2) return d1.localeCompare(d2);
      const c1 = (a.campaign || "").toLowerCase();
      const c2 = (b.campaign || "").toLowerCase();
      if (c1 !== c2) return c1.localeCompare(c2);
      const b1 = (a.bot_key || "").toLowerCase();
      const b2 = (b.bot_key || "").toLowerCase();
      return b1.localeCompare(b2);
    });
  }, [filteredDrafts]);

  const weeklyGroups = useMemo(() => {
    const map = new Map<string, BudgetWeeklyRow[]>();
    sortedDrafts.forEach((row) => {
      if (!row.week_start) return;
      const dt = parseLocalDate(row.week_start);
      if (!dt) return;
      const key = toDayKey(startOfWeek(dt));
      const arr = map.get(key) || [];
      arr.push(row);
      map.set(key, arr);
    });
    return Array.from(map.entries())
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([key, rows]) => ({ key, rows }));
  }, [sortedDrafts]);

  const missingDatesSummary = useMemo(() => {
    const source = filteredDrafts.filter((row) => Boolean(row.week_start) && Boolean((row.campaign || "").trim()));
    if (!source.length) {
      return {
        dateRange: null as { start: string; end: string } | null,
        combos: 0,
        totalMissing: 0,
        top: [] as Array<{ campaign: string; bot: string; missing: number }>,
      };
    }
    const days = source
      .map((row) => row.week_start as string)
      .sort();
    const start = days[0];
    const end = days[days.length - 1];
    const startDate = parseLocalDate(start);
    const endDate = parseLocalDate(end);
    if (!startDate || !endDate || endDate < startDate) {
      return {
        dateRange: null as { start: string; end: string } | null,
        combos: 0,
        totalMissing: 0,
        top: [] as Array<{ campaign: string; bot: string; missing: number }>,
      };
    }

    const totalDays = Math.floor(
      (new Date(endDate.getFullYear(), endDate.getMonth(), endDate.getDate()).getTime() -
        new Date(startDate.getFullYear(), startDate.getMonth(), startDate.getDate()).getTime()) /
        86_400_000
    ) + 1;
    if (totalDays <= 0) {
      return {
        dateRange: null as { start: string; end: string } | null,
        combos: 0,
        totalMissing: 0,
        top: [] as Array<{ campaign: string; bot: string; missing: number }>,
      };
    }

    const comboMap = new Map<string, { campaign: string; bot: string; days: Set<string> }>();
    source.forEach((row) => {
      const campaign = (row.campaign || "").trim();
      if (!campaign) return;
      const bot = (row.bot_key || "").trim() || "—";
      const key = `${campaign}||${bot}`;
      const entry = comboMap.get(key) || { campaign, bot, days: new Set<string>() };
      entry.days.add(row.week_start as string);
      comboMap.set(key, entry);
    });

    const details = Array.from(comboMap.values()).map((entry) => ({
      campaign: entry.campaign,
      bot: entry.bot,
      missing: Math.max(0, totalDays - entry.days.size),
    }));
    const totalMissing = details.reduce((sum, row) => sum + row.missing, 0);
    const top = details
      .filter((row) => row.missing > 0)
      .sort((a, b) => b.missing - a.missing || a.campaign.localeCompare(b.campaign))
      .slice(0, 8);

    return {
      dateRange: { start, end },
      combos: comboMap.size,
      totalMissing,
      top,
    };
  }, [filteredDrafts]);

  const globalCoverage = useMemo(() => {
    if (budgetTab !== "gaps") {
      return { days: [], rows: [] as Array<{ key: string; campaign: string; bot: string; missing: string[] }> };
    }
    const source = selectedMonth === "all"
      ? visibleBudgets
      : visibleBudgets.filter((row) => row.week_start?.startsWith(selectedMonth));
    const dayValues = source
      .map((row) => row.week_start)
      .filter((value): value is string => Boolean(value))
      .sort();
    if (!dayValues.length) {
      return { days: [], rows: [] as Array<{ key: string; campaign: string; bot: string; missing: string[] }> };
    }
    const minDay = dayValues[0];
    const maxDay = dayValues[dayValues.length - 1];
    const minDate = parseLocalDate(minDay);
    const maxDate = parseLocalDate(maxDay);
    if (!minDate || !maxDate) {
      return { days: [], rows: [] as Array<{ key: string; campaign: string; bot: string; missing: string[] }> };
    }
    const days: string[] = [];
    const cursor = new Date(minDate.getFullYear(), minDate.getMonth(), minDate.getDate());
    const last = new Date(maxDate.getFullYear(), maxDate.getMonth(), maxDate.getDate());
    while (cursor <= last) {
      days.push(toDayKey(cursor));
      cursor.setDate(cursor.getDate() + 1);
    }
    if (!days.length) {
      return { days: [], rows: [] as Array<{ key: string; campaign: string; bot: string; missing: string[] }> };
    }
    const combos = new Map<string, { campaign: string; bot: string }>();
    source.forEach((row) => {
      const campaign = (row.campaign || "").trim();
      const bot = (row.bot_key || "").trim() || "—";
      if (!campaign) return;
      const key = `${campaign}||${bot}`;
      if (!combos.has(key)) {
        combos.set(key, { campaign, bot });
      }
    });
    const rows: Array<{ key: string; campaign: string; bot: string; missing: string[] }> = Array.from(combos.entries()).map(
      ([key, meta]) => {
        const existing = new Set(
          source
            .filter((row) => (row.campaign || "").trim() === meta.campaign)
            .filter((row) => ((row.bot_key || "").trim() || "—") === meta.bot)
            .map((row) => row.week_start)
        );
        const missing = days.filter((day) => !existing.has(day));
        return { key, missing, campaign: meta.campaign, bot: meta.bot };
      }
    );
    return { days, rows };
  }, [visibleBudgets, selectedMonth, budgetTab]);

  const treeCoverage = useMemo(() => {
    if (budgetTab !== "gaps") {
      return [] as Array<{
        campaign: string;
        bots: Array<{ bot: string; weeks: Array<{ week: string; days: string[] }> }>;
        totalMissingDays: number;
      }>;
    }
    const rows = globalCoverage.rows.filter((row) => row.missing.length);
    const byCampaign = new Map<
      string,
      Array<{ bot: string; weeks: Array<{ week: string; days: string[] }> }>
    >();
    rows.forEach((row) => {
      const weekMap = new Map<string, string[]>();
      row.missing.forEach((d) => {
        const dt = parseLocalDate(d);
        if (!dt) return;
        const wk = toDayKey(startOfWeek(dt));
        const list = weekMap.get(wk) || [];
        list.push(d);
        weekMap.set(wk, list);
      });
      const weeks = Array.from(weekMap.entries())
        .sort(([a], [b]) => a.localeCompare(b))
        .map(([week, days]) => ({
          week,
          days: days.sort(),
        }));
      if (!weeks.length) return;
      const list = byCampaign.get(row.campaign) || [];
      list.push({ bot: row.bot, weeks });
      byCampaign.set(row.campaign, list);
    });
    return Array.from(byCampaign.entries())
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([campaign, bots]) => ({
        campaign,
        bots: bots.sort((a, b) => a.bot.localeCompare(b.bot)),
        totalMissingDays: bots.reduce(
          (sum, bot) => sum + bot.weeks.reduce((acc, wk) => acc + wk.days.length, 0),
          0
        ),
      }));
  }, [globalCoverage.rows, budgetTab]);

  return (
    <Dialog
      open={open}
      onClose={onClose}
      maxWidth="lg"
      fullWidth
      PaperProps={{
        sx: {
          borderRadius: "24px",
          border: "1px solid var(--app-shell-border)",
          background: "var(--app-panel-bg)",
          boxShadow: "var(--app-shell-shadow)",
        },
      }}
    >
      <DialogTitle>Бюджеты</DialogTitle>
      <DialogContent dividers>
        <Stack spacing={2}>
          <Stack spacing={2}>
            <Paper
              variant="outlined"
              sx={{
                p: 2,
                borderRadius: "20px",
                borderColor: "var(--app-table-divider)",
                background: "var(--app-panel-muted)",
              }}
            >
              <Typography variant="subtitle2" gutterBottom>
                Добавить расходы
              </Typography>
              <Stack direction={{ xs: "column", md: "row" }} spacing={2} alignItems="center" flexWrap="wrap">
                <TextField
                  label="Период с"
                  type="date"
                  value={newRangeStart}
                  onChange={(event) => setNewRangeStart(event.target.value)}
                  size="small"
                  InputLabelProps={{ shrink: true }}
                  sx={{ minWidth: 160 }}
                />
              <TextField
                label="Период по"
                type="date"
                value={newRangeEnd}
                onChange={(event) => setNewRangeEnd(event.target.value)}
                size="small"
                InputLabelProps={{ shrink: true }}
                sx={{ minWidth: 160 }}
              />
              <FormControl size="small" sx={{ minWidth: 240 }}>
                <Autocomplete
                  freeSolo
                  options={companyOptions}
                  inputValue={newCampaign}
                  onInputChange={(_, value) => {
                    setNewCampaign(value);
                    setNewBot("");
                  }}
                  renderInput={(params) => (
                    <TextField {...params} label="РК" size="small" />
                  )}
                />
              </FormControl>
              <FormControl size="small" sx={{ minWidth: 180 }}>
                <InputLabel id="budget-bot-label">Бот (опц.)</InputLabel>
                <Select
                  labelId="budget-bot-label"
                  label="Бот (опц.)"
                  value={newBot}
                  onChange={(event) => setNewBot(event.target.value)}
                >
                  <MenuItem value="">
                    <em>Все боты РК</em>
                  </MenuItem>
                  {botOptions.map((bot) => (
                    <MenuItem key={bot} value={bot}>
                      {bot}
                    </MenuItem>
                  ))}
                </Select>
                </FormControl>
              </Stack>
              <Stack direction={{ xs: "column", md: "row" }} spacing={2} alignItems="center" flexWrap="wrap" sx={{ mt: 2 }}>
                <TextField
                  label="Расходы, USD"
                  value={newAmount}
                  onChange={(event) => setNewAmount(event.target.value)}
                  size="small"
                  inputMode="decimal"
                  sx={{ minWidth: 220 }}
                  helperText="Сумма за период (будет поделена на дни)"
                />
                <Button variant="contained" onClick={handleCreate} disabled={saving} sx={{ minWidth: 140, whiteSpace: "nowrap" }}>
                  Добавить
                </Button>
              </Stack>
            </Paper>
            <Paper
              variant="outlined"
              sx={{
                p: 2,
                borderRadius: "20px",
                borderColor: "var(--app-table-divider)",
                background: "var(--app-panel-muted)",
              }}
            >
              <Typography variant="subtitle2" gutterBottom>
                Фильтры просмотра
              </Typography>
              <Stack direction={{ xs: "column", md: "row" }} spacing={2} alignItems="center" flexWrap="wrap">
                <FormControl size="small" sx={{ minWidth: 200 }}>
                  <InputLabel id="budget-month-filter">Месяц</InputLabel>
                  <Select
                    labelId="budget-month-filter"
                    label="Месяц"
                    value={selectedMonth}
                    onChange={(event) => setSelectedMonth(event.target.value)}
                  >
                    <MenuItem value="all">Все месяцы</MenuItem>
                    {monthOptions.map((month) => (
                      <MenuItem key={month} value={month}>
                        {monthLabel(month)}
                      </MenuItem>
                    ))}
                  </Select>
                </FormControl>
              </Stack>
            </Paper>
          </Stack>
          {filterStartDate && filterEndDate && newCampaign.trim() && (
            <TextField
              label="Проверка заполнения"
              value={
                coverage.length
                  ? `Не заполнены: ${coverage.map((d) => d.split("-").reverse().join(".")).join(", ")}`
                  : "Все дни заполнены"
              }
              size="small"
              InputProps={{ readOnly: true }}
            />
          )}
          {loading && <LinearProgress />}
          <Tabs
            value={budgetTab}
            onChange={(_e, value) => setBudgetTab(value)}
            sx={{ mt: 0.5 }}
          >
            <Tab value="entries" label="Записи бюджета" />
            <Tab value="gaps" label="Пропуски дат" />
          </Tabs>
          {budgetTab === "entries" && <Paper variant="outlined" sx={{ p: 2, borderRadius: "20px", borderColor: "var(--app-table-divider)", background: "var(--app-panel-muted)" }}>
            <Typography variant="subtitle2" gutterBottom>
              Пропуски дат (месяц: {monthLabel(selectedMonth)})
            </Typography>
            <Typography variant="body2" color="text.secondary">
              Комбинаций РК/бот: {missingDatesSummary.combos}. Пропущено дат: {missingDatesSummary.totalMissing}.
              {missingDatesSummary.dateRange
                ? ` Диапазон: ${toDisplay(missingDatesSummary.dateRange.start)} — ${toDisplay(missingDatesSummary.dateRange.end)}.`
                : ""}
            </Typography>
            {missingDatesSummary.top.length > 0 ? (
              <Stack spacing={0.5} sx={{ mt: 1 }}>
                {missingDatesSummary.top.map((row) => (
                  <Typography key={`${row.campaign}-${row.bot}`} variant="caption" color="text.secondary">
                    {row.campaign} / {row.bot}: {row.missing} дн.
                  </Typography>
                ))}
              </Stack>
            ) : (
              <Typography variant="caption" color="success.main" sx={{ mt: 1, display: "block" }}>
                Пропусков по выбранному месяцу нет.
              </Typography>
            )}
          </Paper>}
          {budgetTab === "entries" && <TableContainer sx={{ borderRadius: "18px", border: "1px solid var(--app-table-divider)", overflow: "hidden" }}>
            <Table
              size="small"
              sx={{
                "& .MuiTableCell-root": {
                  borderBottom: "1px solid var(--app-table-divider)",
                },
                "& .MuiTableHead-root .MuiTableCell-root": {
                  backgroundColor: "var(--app-table-head-bg)",
                  color: "var(--c-ink2)",
                  fontWeight: 700,
                },
                "& .MuiTableBody-root .MuiTableRow-root:nth-of-type(even)": {
                  backgroundColor: "var(--app-table-row-alt)",
                },
              }}
            >
            <TableHead>
              <TableRow>
                <TableCell>Неделя</TableCell>
                <TableCell>Дата</TableCell>
                <TableCell>РК</TableCell>
                <TableCell>Бот</TableCell>
                <TableCell align="right">Расход, USD</TableCell>
                <TableCell />
              </TableRow>
            </TableHead>
            <TableBody>
              {weeklyGroups.map((group) => (
                <React.Fragment key={group.key}>
                  <TableRow sx={{ backgroundColor: "var(--app-table-month-bg)" }}>
                    <TableCell colSpan={6} sx={{ fontWeight: 600 }}>
                      {toWeekLabel(group.key)}
                    </TableCell>
                  </TableRow>
                  {group.rows.map((row) => (
                    <TableRow key={row.id}>
                      <TableCell />
                      <TableCell>{toDisplay(row.week_start)}</TableCell>
                      <TableCell>{row.campaign}</TableCell>
                      <TableCell>{row.bot_key || "—"}</TableCell>
                      <TableCell align="right">{Number(row.amount || 0).toFixed(2)}</TableCell>
                      <TableCell align="right">
                        <IconButton onClick={() => setDeleteTarget(row)} size="small">
                          <DeleteIcon fontSize="small" />
                        </IconButton>
                      </TableCell>
                    </TableRow>
                  ))}
                </React.Fragment>
              ))}
              {!weeklyGroups.length && (
                <TableRow>
                  <TableCell colSpan={6}>Нет данных</TableCell>
                </TableRow>
              )}
            </TableBody>
            </Table>
          </TableContainer>}
          {budgetTab === "gaps" && (
            <Paper variant="outlined" sx={{ p: 2, borderRadius: "20px", borderColor: "var(--app-table-divider)", background: "var(--app-panel-muted)" }}>
              <Typography variant="subtitle2" gutterBottom>
                Детализация пропусков (месяц: {monthLabel(selectedMonth)})
              </Typography>
              <Stack direction={{ xs: "column", md: "row" }} spacing={2} alignItems="center" sx={{ mb: 2 }}>
                <Stack direction="row" spacing={1} alignItems="center">
                  <Chip label="3-4д" color="warning" size="small" />
                  <Chip label="5+д" color="error" size="small" />
                </Stack>
                {!!globalCoverage.days.length && (
                  <Typography variant="caption" color="text.secondary">
                    Период: {toDisplay(globalCoverage.days[0])} — {toDisplay(globalCoverage.days[globalCoverage.days.length - 1])}
                  </Typography>
                )}
              </Stack>
              {treeCoverage.length ? (
                <Stack spacing={1}>
                  {treeCoverage.map((group) => (
                    <Accordion
                      key={group.campaign}
                      defaultExpanded={false}
                      sx={{
                        background: "transparent",
                        border: "1px solid var(--app-table-divider)",
                        borderRadius: "16px !important",
                        boxShadow: "none",
                        "&:before": { display: "none" },
                      }}
                    >
                      <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                        <Stack direction="row" spacing={1} alignItems="center">
                          <Typography sx={{ fontWeight: 600 }}>{group.campaign}</Typography>
                          <Chip label={`${group.totalMissingDays} дн.`} size="small" />
                        </Stack>
                      </AccordionSummary>
                      <AccordionDetails>
                        <Stack spacing={1} divider={<Divider flexItem />}>
                          {group.bots.map((bot) => (
                            <Accordion
                              key={bot.bot}
                              defaultExpanded={false}
                              sx={{
                                background: "transparent",
                                border: "1px solid var(--app-table-divider)",
                                borderRadius: "14px !important",
                                boxShadow: "none",
                                "&:before": { display: "none" },
                              }}
                            >
                              <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                                <Stack direction="row" spacing={1} alignItems="center">
                                  <Typography variant="body2">{bot.bot}</Typography>
                                  <Chip
                                    label={`${bot.weeks.reduce((acc, w) => acc + w.days.length, 0)} дн.`}
                                    size="small"
                                  />
                                </Stack>
                              </AccordionSummary>
                              <AccordionDetails>
                                <Stack spacing={1}>
                                  {bot.weeks.map((wk) => {
                                    const count = wk.days.length;
                                    let color: "default" | "warning" | "error" = "default";
                                    if (count >= 5) color = "error";
                                    else if (count >= 3) color = "warning";
                                    return (
                                      <Accordion
                                        key={`${bot.bot}-${wk.week}`}
                                        defaultExpanded={false}
                                        sx={{
                                          background: "transparent",
                                          border: "1px solid var(--app-table-divider)",
                                          borderRadius: "12px !important",
                                          boxShadow: "none",
                                          "&:before": { display: "none" },
                                        }}
                                      >
                                        <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                                          <Stack direction="row" spacing={1} alignItems="center">
                                            <Typography variant="body2">{toWeekLabel(wk.week)}</Typography>
                                            <Chip label={`${count} дн.`} size="small" color={color} />
                                          </Stack>
                                        </AccordionSummary>
                                        <AccordionDetails>
                                          <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
                                            {wk.days.map((d) => (
                                              <Chip
                                                key={`${bot.bot}-${wk.week}-${d}`}
                                                label={toDisplay(d)}
                                                size="small"
                                                variant="outlined"
                                              />
                                            ))}
                                          </Stack>
                                        </AccordionDetails>
                                      </Accordion>
                                    );
                                  })}
                                </Stack>
                              </AccordionDetails>
                            </Accordion>
                          ))}
                        </Stack>
                      </AccordionDetails>
                    </Accordion>
                  ))}
                </Stack>
              ) : (
                <Typography variant="body2" color="text.secondary">
                  Пропусков нет
                </Typography>
              )}
            </Paper>
          )}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} disabled={saving}>
          Отмена
        </Button>
      </DialogActions>
      <Dialog
        open={Boolean(deleteTarget)}
        onClose={() => setDeleteTarget(null)}
        PaperProps={{
          sx: {
            borderRadius: "20px",
            border: "1px solid var(--app-shell-border)",
            background: "var(--app-panel-bg)",
          },
        }}
      >
        <DialogTitle>Удалить запись?</DialogTitle>
        <DialogContent dividers>
          Запись будет удалена без возможности восстановления.
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDeleteTarget(null)}>Отмена</Button>
          <Button color="error" variant="contained" onClick={confirmDelete}>
            Удалить
          </Button>
        </DialogActions>
      </Dialog>
    </Dialog>
  );
};

export default BudgetDialog;
