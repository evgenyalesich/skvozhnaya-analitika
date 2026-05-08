// Диалог рекламных метрик: impressions/clicks/spend по кампании и боту за неделю.
import React, { useEffect, useMemo, useState } from "react";
import axios from "axios";
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
import Alert from "@mui/material/Alert";
import DeleteIcon from "@mui/icons-material/Delete";
import Paper from "@mui/material/Paper";
import Typography from "@mui/material/Typography";
import DialogContentText from "@mui/material/DialogContentText";

import { AdMetricsWeeklyRow } from "../hooks/useAdMetrics";
import { BudgetWeeklyRow } from "../hooks/useBudgets";
import { AdvertisingCompanyOption } from "../hooks/useAdvertisingCompanies";

const API_BASE = import.meta.env.VITE_API_BASE || "https://roistat.pokerhub.pro";

interface AdMetricsDialogProps {
  open: boolean;
  rows: AdMetricsWeeklyRow[];
  loading: boolean;
  budgets: BudgetWeeklyRow[];
  companies: AdvertisingCompanyOption[];
  onClose: () => void;
  onCreate: (payload: Omit<AdMetricsWeeklyRow, "id">) => Promise<void>;
  onUpdate: (id: number, patch: Partial<AdMetricsWeeklyRow>) => Promise<void>;
  onDelete: (id: number) => Promise<void>;
}

const AdMetricsDialog: React.FC<AdMetricsDialogProps> = ({
  open,
  rows,
  loading,
  budgets = [],
  companies,
  onClose,
  onCreate,
  onUpdate: _onUpdate,
  onDelete,
}) => {
  const [drafts, setDrafts] = useState<AdMetricsWeeklyRow[]>([]);
  const [newRangeStart, setNewRangeStart] = useState("");
  const [newRangeEnd, setNewRangeEnd] = useState("");
  const [newCampaign, setNewCampaign] = useState("");
  const [newBot, setNewBot] = useState("");
  const [newImpr, setNewImpr] = useState("");
  const [newClicks, setNewClicks] = useState("");
  const [saving, setSaving] = useState(false);
  const [selectedMonth, setSelectedMonth] = useState("all");
  const [formError, setFormError] = useState<string | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<AdMetricsWeeklyRow | null>(null);
  const [localBudgets, setLocalBudgets] = useState<BudgetWeeklyRow[]>([]);
  const [loadingBudgets, setLoadingBudgets] = useState(false);
  const [useFilteredBudgets, setUseFilteredBudgets] = useState(false);

  const parseDecimal = (value: string) => {
    const normalized = value.replace(/\s+/g, "").replace(",", ".");
    if (!normalized) return Number.NaN;
    return Number(normalized);
  };

  const toErrorMessage = (err: any, fallback: string) => {
    const detail = err?.response?.data?.detail;
    if (typeof detail === "string") return detail;
    if (detail && typeof detail === "object") {
      try {
        return JSON.stringify(detail);
      } catch {
        return fallback;
      }
    }
    if (typeof err?.message === "string") return err.message;
    return fallback;
  };

  const normalizeKey = (value?: string | null) => {
    const raw = (value || "")
      .toString()
      .normalize("NFKC")
      .replace(/\u00A0/g, " ")
      .replace(/[\u200B-\u200D\uFEFF]/g, "")
      .replace(/\s+/g, " ")
      .trim()
      .toLowerCase();
    if (!raw) return "";
    const cyrToLat: Record<string, string> = {
      а: "a",
      б: "b",
      в: "v",
      г: "g",
      д: "d",
      е: "e",
      ё: "e",
      ж: "zh",
      з: "z",
      и: "i",
      й: "i",
      к: "k",
      л: "l",
      м: "m",
      н: "n",
      о: "o",
      п: "p",
      р: "r",
      с: "s",
      т: "t",
      у: "u",
      ф: "f",
      х: "x",
      ц: "c",
      ч: "ch",
      ш: "sh",
      щ: "shch",
      ы: "y",
      э: "e",
      ю: "yu",
      я: "ya",
      ь: "",
      ъ: "",
    };
    return raw
      .split("")
      .map((ch) => cyrToLat[ch] ?? ch)
      .join("");
  };

  const normalizeDayKey = (value?: string | null) => {
    if (!value) return "";
    const trimmed = value.trim();
    if (/^\d{4}-\d{2}-\d{2}$/.test(trimmed)) return trimmed;
    if (trimmed.length >= 10 && /^\d{4}-\d{2}-\d{2}/.test(trimmed)) {
      return trimmed.slice(0, 10);
    }
    return trimmed;
  };

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

  const toDisplay = (value?: string) => (value ? value.split("-").reverse().join(".") : "");

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

  useEffect(() => {
    if (open) {
      setDrafts(rows);
      setNewRangeStart("");
      setNewRangeEnd("");
      setNewCampaign("");
      setNewBot("");
      setNewImpr("");
      setNewClicks("");
      setSelectedMonth("all");
      setFormError(null);
      setLocalBudgets([]);
      setUseFilteredBudgets(false);
    }
  }, [open, rows]);

  useEffect(() => {
    if (!open) return;
    if (!newRangeStart || !newRangeEnd || !newCampaign.trim() || !newBot) {
      setUseFilteredBudgets(false);
      return;
    }
    let active = true;
    const controller = new AbortController();
    setLoadingBudgets(true);
    setLocalBudgets([]);
    setUseFilteredBudgets(true);
    const timer = window.setTimeout(() => {
      axios
        .get(`${API_BASE}/api/budgets`, {
          params: { start_date: newRangeStart, end_date: newRangeEnd },
          signal: controller.signal,
        })
        .then((res) => {
          if (active) setLocalBudgets(res.data || []);
        })
        .catch((err) => {
          if (err?.name !== "CanceledError") console.error(err);
        })
        .finally(() => {
          if (active) setLoadingBudgets(false);
        });
    }, 200);
    return () => {
      active = false;
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [open, newRangeStart, newRangeEnd, newCampaign, newBot]);

  const monthOptions = useMemo(() => {
    const set = new Set<string>();
    drafts.forEach((row) => {
      const key = row.week_start?.slice(0, 7);
      if (key && /^\d{4}-\d{2}$/.test(key)) {
        set.add(key);
      }
    });
    return Array.from(set).sort();
  }, [drafts]);

  const formatMonthLabel = (monthKey: string) => {
    if (monthKey === "all") return "Все месяцы";
    const [year, month] = monthKey.split("-");
    const monthIndex = Number(month) - 1;
    const monthNames = [
      "январь",
      "февраль",
      "март",
      "апрель",
      "май",
      "июнь",
      "июль",
      "август",
      "сентябрь",
      "октябрь",
      "ноябрь",
      "декабрь",
    ];
    return `${monthNames[monthIndex] || month} ${year}`;
  };

  const companyOptions = useMemo(
    () => companies.map((company) => company.company_name).filter(Boolean),
    [companies]
  );
  const selectedCompany = companies.find((c) => c.company_name === newCampaign);
  const botOptions = selectedCompany?.bot_keys || [];

  const budgetsSource = useFilteredBudgets ? localBudgets : budgets;

  const buildBudgetMaps = useMemo(() => {
    const map = new Map<string, number>();
    const campaignDayTotals = new Map<string, number>();
    budgetsSource.forEach((row) => {
      const day = normalizeDayKey(row.week_start);
      if (!day) return;
      const keyCampaign = normalizeKey(row.campaign);
      const keyBot = normalizeKey(row.bot_key);
      map.set(`${day}::${keyCampaign}::${keyBot}`, Number(row.amount || 0));
      const campaignKey = `${day}::${keyCampaign}`;
      campaignDayTotals.set(campaignKey, (campaignDayTotals.get(campaignKey) || 0) + Number(row.amount || 0));
    });
    return { byBot: map, byCampaign: campaignDayTotals };
  }, [budgetsSource]);

  const budgetInfo = useMemo(() => {
    if (!newRangeStart || !newRangeEnd || !newCampaign.trim() || !newBot) {
      return { total: null as number | null, missing: 0, days: 0, source: "" as "bot" | "campaign" | "" };
    }
    const startDate = parseLocalDate(newRangeStart);
    const endDate = parseLocalDate(newRangeEnd);
    if (!startDate || !endDate || endDate < startDate) {
      return { total: null as number | null, missing: 0, days: 0, source: "" as "bot" | "campaign" | "" };
    }
    const days: string[] = [];
    const cursor = new Date(startDate.getFullYear(), startDate.getMonth(), startDate.getDate());
    const last = new Date(endDate.getFullYear(), endDate.getMonth(), endDate.getDate());
    while (cursor <= last) {
      days.push(toDayKey(cursor));
      cursor.setDate(cursor.getDate() + 1);
    }
    const keyCampaign = normalizeKey(newCampaign);
    const keyBot = normalizeKey(newBot);
    const byBotMissing = days.filter((d) => !buildBudgetMaps.byBot.has(`${d}::${keyCampaign}::${keyBot}`)).length;
    const byBotTotal = days.reduce(
      (sum, d) => sum + (buildBudgetMaps.byBot.get(`${d}::${keyCampaign}::${keyBot}`) || 0),
      0
    );
    return {
      total: byBotTotal,
      missing: byBotMissing,
      days: days.length,
      source: "bot" as const,
    };
  }, [buildBudgetMaps, newRangeStart, newRangeEnd, newCampaign, newBot]);

  const handleCreate = async () => {
    if (!newRangeStart || !newRangeEnd || !newCampaign.trim()) {
      setFormError("Заполните период и РК.");
      return;
    }
    const impressions = parseDecimal(newImpr);
    const clicks = parseDecimal(newClicks);
    if (Number.isNaN(impressions) || Number.isNaN(clicks)) {
      setFormError("Показы и клики должны быть числами.");
      return;
    }
    const startDate = parseLocalDate(newRangeStart);
    const endDate = parseLocalDate(newRangeEnd);
    if (!startDate || !endDate) {
      setFormError("Некорректный период.");
      return;
    }
    if (endDate < startDate) {
      setFormError("Дата окончания раньше даты начала.");
      return;
    }
    const days: string[] = [];
    const cursor = new Date(startDate.getFullYear(), startDate.getMonth(), startDate.getDate());
    const last = new Date(endDate.getFullYear(), endDate.getMonth(), endDate.getDate());
    while (cursor <= last) {
      days.push(toDayKey(cursor));
      cursor.setDate(cursor.getDate() + 1);
    }
    if (!days.length) {
      setFormError("Период не дал ни одного дня.");
      return;
    }

    const keyCampaign = normalizeKey(newCampaign);
    const keyBot = normalizeKey(newBot);
    if (!newBot) {
      setFormError("Выберите бота.");
      return;
    }
    const missingByBot = days.filter((d) => !buildBudgetMaps.byBot.has(`${d}::${keyCampaign}::${keyBot}`));
    const missingByCampaign = days.filter((d) => !buildBudgetMaps.byBot.has(`${d}::${keyCampaign}::`));
    const missingByCampaignAny = days.filter((d) => !buildBudgetMaps.byCampaign.has(`${d}::${keyCampaign}`));
    const missingBudgets = missingByBot;
    if (missingBudgets.length) {
      setFormError("Нельзя добавить: нет бюджета для выбранной РК/бота на все дни периода.");
      return;
    }

    const totalImpr = Math.round(Number(impressions));
    const totalClicks = Math.round(Number(clicks));
    const baseImpr = Math.floor(totalImpr / days.length);
    const baseClicks = Math.floor(totalClicks / days.length);
    const remImpr = totalImpr - baseImpr * days.length;
    const remClicks = totalClicks - baseClicks * days.length;

    setFormError(null);
    setSaving(true);
    try {
      for (let i = 0; i < days.length; i += 1) {
        const day = days[i];
        const perDayImpr = baseImpr + (i < remImpr ? 1 : 0);
        const perDayClicks = baseClicks + (i < remClicks ? 1 : 0);
        const spend = buildBudgetMaps.byBot.get(`${day}::${keyCampaign}::${keyBot}`) ?? 0;
        await onCreate({
          week_start: day,
          campaign: newCampaign.trim(),
          bot_key: newBot || null,
          impressions: perDayImpr,
          clicks: perDayClicks,
          spend,
        });
      }
      setNewRangeStart("");
      setNewRangeEnd("");
      setNewCampaign("");
      setNewBot("");
      setNewImpr("");
      setNewClicks("");
    } catch (err: any) {
      setFormError(toErrorMessage(err, "Не удалось добавить метрики"));
    } finally {
      setSaving(false);
    }
  };

  const confirmDelete = async () => {
    if (!deleteTarget) return;
    await onDelete(deleteTarget.id);
    setDeleteTarget(null);
  };

  const filteredDrafts = useMemo(() => {
    if (selectedMonth === "all") return drafts;
    return drafts.filter((row) => row.week_start?.startsWith(selectedMonth));
  }, [drafts, selectedMonth]);

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
    const map = new Map<string, AdMetricsWeeklyRow[]>();
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
      <DialogTitle>Рекламные метрики</DialogTitle>
      <DialogContent dividers>
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
              Добавить метрики
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
                  renderInput={(params) => <TextField {...params} label="РК" size="small" />}
                />
              </FormControl>
              <FormControl size="small" sx={{ minWidth: 180 }}>
                <InputLabel id="ad-metrics-bot-label">Бот (опц.)</InputLabel>
                <Select
                  labelId="ad-metrics-bot-label"
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
                label="Показы"
                value={newImpr}
                onChange={(event) => setNewImpr(event.target.value)}
                size="small"
                inputMode="numeric"
                sx={{ minWidth: 160 }}
                helperText="Сумма за период (будет поделена на дни)"
              />
              <TextField
                label="Клики"
                value={newClicks}
                onChange={(event) => setNewClicks(event.target.value)}
                size="small"
                inputMode="numeric"
                sx={{ minWidth: 160 }}
                helperText="Сумма за период (будет поделена на дни)"
              />
              <TextField
                label="Spend"
                value={budgetInfo.total !== null ? budgetInfo.total.toFixed(2) : ""}
                size="small"
                sx={{ minWidth: 220 }}
                InputProps={{ readOnly: true }}
                helperText={
                  !newBot
                    ? "Выберите бота"
                    : budgetInfo.missing > 0
                      ? `Нет бюджета на ${budgetInfo.missing} дн.`
                      : "Сумма за период из бюджета РК/бота"
                }
              />
              <Button
                variant="contained"
                onClick={handleCreate}
                disabled={saving || loadingBudgets || budgetInfo.total === null || budgetInfo.missing > 0 || !newBot}
                sx={{ minWidth: 140, whiteSpace: "nowrap" }}
              >
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
                <InputLabel id="ad-metrics-month-label">Месяц</InputLabel>
                <Select
                  labelId="ad-metrics-month-label"
                  label="Месяц"
                  value={selectedMonth}
                  onChange={(event) => setSelectedMonth(event.target.value)}
                >
                  <MenuItem value="all">Все месяцы</MenuItem>
                  {monthOptions.map((month) => (
                    <MenuItem key={month} value={month}>
                      {formatMonthLabel(month)}
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>
            </Stack>
          </Paper>

          {formError && <Alert severity="error">{formError}</Alert>}
          {loading && <LinearProgress />}

          <TableContainer sx={{ borderRadius: "18px", border: "1px solid var(--app-table-divider)", overflow: "hidden" }}>
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
                  <TableCell align="right">Показы</TableCell>
                  <TableCell align="right">Клики</TableCell>
                  <TableCell align="right">Spend</TableCell>
                  <TableCell />
                </TableRow>
              </TableHead>
              <TableBody>
                {weeklyGroups.map((group) => (
                  <React.Fragment key={group.key}>
                    <TableRow sx={{ backgroundColor: "var(--app-table-month-bg)" }}>
                      <TableCell colSpan={8} sx={{ fontWeight: 600 }}>
                        {toWeekLabel(group.key)}
                      </TableCell>
                    </TableRow>
                    {group.rows.map((row) => (
                      <TableRow key={row.id}>
                        <TableCell />
                        <TableCell>{toDisplay(row.week_start)}</TableCell>
                        <TableCell>{row.campaign}</TableCell>
                        <TableCell>{row.bot_key || "—"}</TableCell>
                        <TableCell align="right">{Math.round(Number(row.impressions || 0))}</TableCell>
                        <TableCell align="right">{Math.round(Number(row.clicks || 0))}</TableCell>
                        <TableCell align="right">{Number(row.spend || 0).toFixed(2)}</TableCell>
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
                    <TableCell colSpan={8}>Нет данных</TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </TableContainer>
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
          <DialogContentText>
            Запись будет удалена без возможности восстановления.
          </DialogContentText>
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

export default AdMetricsDialog;
