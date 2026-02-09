import React, { useEffect, useState } from "react";
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
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import TableContainer from "@mui/material/TableContainer";
import LinearProgress from "@mui/material/LinearProgress";
import IconButton from "@mui/material/IconButton";
import DeleteIcon from "@mui/icons-material/Delete";

import { BudgetWeeklyRow } from "../hooks/useBudgets";
import { useAdMetrics } from "../hooks/useAdMetrics";
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
  onUpdate,
  onDelete,
}) => {
  const [drafts, setDrafts] = useState<BudgetWeeklyRow[]>([]);
  const [newRangeStart, setNewRangeStart] = useState("");
  const [newRangeEnd, setNewRangeEnd] = useState("");
  const [newCampaign, setNewCampaign] = useState("");
  const [newBot, setNewBot] = useState("");
  const [newAmount, setNewAmount] = useState("");
  const [saving, setSaving] = useState(false);
  const [selectedMonth, setSelectedMonth] = useState("");
  const { rows: adMetrics, refresh: refreshAdMetrics } = useAdMetrics();

  useEffect(() => {
    if (open) {
      setDrafts(budgets);
      setNewRangeStart("");
      setNewRangeEnd("");
      setNewCampaign("");
      setNewBot("");
      setNewAmount("");
      setSelectedMonth("");
    }
  }, [open, budgets]);

  const monthOptions = React.useMemo(() => {
    const set = new Set<string>();
    budgets.forEach((row) => {
      const key = row.week_start?.slice(0, 7);
      if (key && /^\d{4}-\d{2}$/.test(key)) {
        set.add(key);
      }
    });
    return Array.from(set).sort();
  }, [budgets]);

  useEffect(() => {
    if (!selectedMonth && monthOptions.length) {
      setSelectedMonth(monthOptions[monthOptions.length - 1]);
    }
  }, [monthOptions, selectedMonth]);

  const formatMonthLabel = (monthKey: string) => {
    if (!monthKey) return "Все месяцы";
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

  const formatWeekRange = (weekStart: string) => {
    if (!weekStart) return "";
    const start = new Date(`${weekStart}T00:00:00`);
    if (Number.isNaN(start.getTime())) return weekStart;
    const end = new Date(start);
    end.setDate(start.getDate() + 6);
    const fmt = (d: Date) =>
      `${String(d.getDate()).padStart(2, "0")}.${String(d.getMonth() + 1).padStart(2, "0")}.${d.getFullYear()}`;
    return `${fmt(start)} – ${fmt(end)}`;
  };

  const selectedCompany = companies.find((c) => c.company_name === newCampaign);
  const botOptions = selectedCompany?.bot_keys || [];

  const computedSpend = React.useMemo(() => {
    if (!newCampaign.trim()) return null;
    const start = newRangeStart;
    const end = newRangeEnd;
    if (!start || !end) return null;
    const startDate = new Date(`${start}T00:00:00`);
    const endDate = new Date(`${end}T23:59:59`);
    if (Number.isNaN(startDate.getTime()) || Number.isNaN(endDate.getTime())) return null;
    const campaignKey = newCampaign.trim().toLowerCase();
    const botKey = (newBot || "").trim().toLowerCase();
    let total = 0;
    adMetrics.forEach((row) => {
      if (!row.week_start) return;
      const rowStart = new Date(`${row.week_start}T00:00:00`);
      if (Number.isNaN(rowStart.getTime())) return;
      const rowEnd = new Date(rowStart);
      rowEnd.setDate(rowStart.getDate() + 6);
      if (rowStart > endDate || rowEnd < startDate) return;
      if ((row.campaign || "").trim().toLowerCase() !== campaignKey) return;
      if (botKey) {
        if ((row.bot_key || "").trim().toLowerCase() !== botKey) return;
      }
      total += Number(row.spend || 0);
    });
    return total;
  }, [adMetrics, newCampaign, newBot, newRangeStart, newRangeEnd]);

  const handleDraftChange = (id: number, patch: Partial<BudgetWeeklyRow>) => {
    setDrafts((prev) => prev.map((row) => (row.id === id ? { ...row, ...patch } : row)));
  };

  const handleCreate = async () => {
    if (!newRangeStart || !newRangeEnd || !newCampaign.trim()) return;
    const amount = Number(newAmount);
    if (Number.isNaN(amount)) return;

    const startDate = new Date(`${newRangeStart}T00:00:00`);
    const endDate = new Date(`${newRangeEnd}T00:00:00`);
    if (Number.isNaN(startDate.getTime()) || Number.isNaN(endDate.getTime())) return;

    const weeks: string[] = [];
    const cursor = new Date(startDate);
    while (cursor <= endDate) {
      weeks.push(cursor.toISOString().slice(0, 10));
      cursor.setDate(cursor.getDate() + 7);
    }

    if (!weeks.length) return;

    setSaving(true);
    try {
      for (const weekStart of weeks) {
        await onCreate({
          week_start: weekStart,
          campaign: newCampaign.trim(),
          bot_key: newBot || null,
          amount,
          currency: "USD",
        });
      }
      await refreshAdMetrics();
      setNewRangeStart("");
      setNewRangeEnd("");
      setNewCampaign("");
      setNewBot("");
      setNewAmount("");
    } finally {
      setSaving(false);
    }
  };

  const handleSaveAll = async () => {
    setSaving(true);
    try {
      for (const row of drafts) {
        const original = budgets.find((item) => item.id === row.id);
        if (!original) continue;
        const patch: Partial<BudgetWeeklyRow> = {};
        if (row.week_start !== original.week_start) patch.week_start = row.week_start;
        if (row.campaign !== original.campaign) patch.campaign = row.campaign;
        if (row.bot_key !== original.bot_key) patch.bot_key = row.bot_key;
        if (row.amount !== original.amount) patch.amount = row.amount;
        if (Object.keys(patch).length) {
          await onUpdate(row.id, patch);
        }
      }
      await refreshAdMetrics();
      onClose();
    } finally {
      setSaving(false);
    }
  };

  const filteredDrafts = drafts.filter((row) => {
    if (selectedMonth) {
      if (!(typeof row.week_start === "string" && row.week_start.startsWith(selectedMonth))) {
        return false;
      }
    }
    if (newRangeStart && row.week_start < newRangeStart) return false;
    if (newRangeEnd && row.week_start > newRangeEnd) return false;
    return true;
  });

  return (
    <Dialog open={open} onClose={onClose} maxWidth="lg" fullWidth>
      <DialogTitle>Недельные бюджеты</DialogTitle>
      <DialogContent dividers>
        <Stack spacing={2}>
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
              <InputLabel id="budget-company-label">РК</InputLabel>
              <Select
                labelId="budget-company-label"
                label="РК"
                value={newCampaign}
                onChange={(event) => {
                  setNewCampaign(event.target.value);
                  setNewBot("");
                }}
              >
                {companies.map((company) => (
                  <MenuItem key={company.company_id || company.company_name} value={company.company_name}>
                    {company.company_name}
                  </MenuItem>
                ))}
              </Select>
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
            <FormControl size="small" sx={{ minWidth: 180 }}>
              <InputLabel id="budget-month-label">Месяц</InputLabel>
              <Select
                labelId="budget-month-label"
                label="Месяц"
                value={selectedMonth}
                onChange={(event) => setSelectedMonth(event.target.value)}
              >
                <MenuItem value="">Все месяцы</MenuItem>
                {monthOptions.map((month) => (
                  <MenuItem key={month} value={month}>
                    {formatMonthLabel(month)}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
            <Button variant="outlined" onClick={handleCreate} disabled={saving} sx={{ minWidth: 120, whiteSpace: "nowrap" }}>
              Добавить
            </Button>
          </Stack>
          <Stack direction={{ xs: "column", md: "row" }} spacing={2} alignItems="center" flexWrap="wrap">
            <TextField
              label="Бюджет, USD"
              value={newAmount}
              onChange={(event) => setNewAmount(event.target.value)}
              size="small"
              sx={{ minWidth: 160 }}
            />
            <TextField
              label="Spend (по метрикам)"
              value={computedSpend !== null ? computedSpend.toFixed(2) : ""}
              size="small"
              sx={{ minWidth: 200 }}
              InputProps={{ readOnly: true }}
            />
          </Stack>
          {loading && <LinearProgress />}
          <TableContainer>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>Неделя</TableCell>
                  <TableCell>Период</TableCell>
                  <TableCell>РК</TableCell>
                  <TableCell>Бот</TableCell>
                  <TableCell>Бюджет, USD</TableCell>
                  <TableCell />
                </TableRow>
              </TableHead>
              <TableBody>
                {filteredDrafts.map((row) => (
                  <TableRow key={row.id}>
                    <TableCell>
                      <TextField
                        type="date"
                        size="small"
                        value={row.week_start}
                        onChange={(event) => handleDraftChange(row.id, { week_start: event.target.value })}
                        InputLabelProps={{ shrink: true }}
                      />
                    </TableCell>
                    <TableCell>{formatWeekRange(row.week_start)}</TableCell>
                    <TableCell>
                      <TextField
                        size="small"
                        value={row.campaign}
                        onChange={(event) => handleDraftChange(row.id, { campaign: event.target.value })}
                      />
                    </TableCell>
                    <TableCell>
                      <TextField
                        size="small"
                        value={row.bot_key || ""}
                        onChange={(event) => handleDraftChange(row.id, { bot_key: event.target.value || null })}
                        placeholder="bot_key"
                      />
                    </TableCell>
                    <TableCell>
                      <TextField
                        size="small"
                        value={row.amount}
                        onChange={(event) =>
                          handleDraftChange(row.id, { amount: Number(event.target.value) || 0 })
                        }
                      />
                    </TableCell>
                    <TableCell align="right">
                      <IconButton onClick={() => onDelete(row.id)} size="small">
                        <DeleteIcon fontSize="small" />
                      </IconButton>
                    </TableCell>
                  </TableRow>
                ))}
                {!filteredDrafts.length && (
                  <TableRow>
                    <TableCell colSpan={6}>Нет данных</TableCell>
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
        <Button onClick={handleSaveAll} variant="contained" disabled={saving}>
          Сохранить
        </Button>
      </DialogActions>
    </Dialog>
  );
};

export default BudgetDialog;
