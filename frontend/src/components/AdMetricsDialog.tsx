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
import Alert from "@mui/material/Alert";
import DeleteIcon from "@mui/icons-material/Delete";

import { AdMetricsWeeklyRow } from "../hooks/useAdMetrics";
import { AdvertisingCompanyOption } from "../hooks/useAdvertisingCompanies";

interface AdMetricsDialogProps {
  open: boolean;
  rows: AdMetricsWeeklyRow[];
  loading: boolean;
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
  companies,
  onClose,
  onCreate,
  onUpdate,
  onDelete,
}) => {
  const [drafts, setDrafts] = useState<AdMetricsWeeklyRow[]>([]);
  const [newRangeStart, setNewRangeStart] = useState("");
  const [newRangeEnd, setNewRangeEnd] = useState("");
  const [newCampaign, setNewCampaign] = useState("");
  const [newBot, setNewBot] = useState("");
  const [newImpr, setNewImpr] = useState("");
  const [newClicks, setNewClicks] = useState("");
  const [newSpend, setNewSpend] = useState("");
  const [saving, setSaving] = useState(false);
  const [selectedMonth, setSelectedMonth] = useState("");
  const [formError, setFormError] = useState<string | null>(null);

  useEffect(() => {
    if (open) {
      setDrafts(rows);
      setNewRangeStart("");
      setNewRangeEnd("");
      setNewCampaign("");
      setNewBot("");
      setNewImpr("");
      setNewClicks("");
      setNewSpend("");
      setSelectedMonth("");
      setFormError(null);
    }
  }, [open, rows]);

  const monthOptions = React.useMemo(() => {
    const set = new Set<string>();
    rows.forEach((row) => {
      const key = row.week_start?.slice(0, 7);
      if (key && /^\d{4}-\d{2}$/.test(key)) {
        set.add(key);
      }
    });
    return Array.from(set).sort();
  }, [rows]);

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

  const handleDraftChange = (id: number, patch: Partial<AdMetricsWeeklyRow>) => {
    setDrafts((prev) => prev.map((row) => (row.id === id ? { ...row, ...patch } : row)));
  };

  const handleCreate = async () => {
    if (!newRangeStart || !newRangeEnd || !newCampaign.trim()) {
      setFormError("Заполните период и РК.");
      return;
    }
    const impressions = Number(newImpr);
    const clicks = Number(newClicks);
    const spend = Number(newSpend || 0);
    if (Number.isNaN(impressions) || Number.isNaN(clicks) || Number.isNaN(spend)) {
      setFormError("Показы, клики и spend должны быть числами.");
      return;
    }
    const startDate = new Date(`${newRangeStart}T00:00:00`);
    const endDate = new Date(`${newRangeEnd}T00:00:00`);
    if (Number.isNaN(startDate.getTime()) || Number.isNaN(endDate.getTime())) {
      setFormError("Некорректный период.");
      return;
    }
    const weeks: string[] = [];
    const cursor = new Date(startDate);
    while (cursor <= endDate) {
      weeks.push(cursor.toISOString().slice(0, 10));
      cursor.setDate(cursor.getDate() + 7);
    }
    if (!weeks.length) {
      setFormError("Период не дал ни одной недели.");
      return;
    }
    setFormError(null);
    setSaving(true);
    try {
      for (const weekStart of weeks) {
        await onCreate({
          week_start: weekStart,
          campaign: newCampaign.trim(),
          bot_key: newBot || null,
          impressions,
          clicks,
          spend,
        });
      }
      setNewRangeStart("");
      setNewRangeEnd("");
      setNewCampaign("");
      setNewBot("");
      setNewImpr("");
      setNewClicks("");
      setNewSpend("");
    } catch (err: any) {
      setFormError(err?.response?.data?.detail || err?.message || "Не удалось добавить метрики");
    } finally {
      setSaving(false);
    }
  };

  const handleSaveAll = async () => {
    setSaving(true);
    try {
      for (const row of drafts) {
        const original = rows.find((item) => item.id === row.id);
        if (!original) continue;
        const patch: Partial<AdMetricsWeeklyRow> = {};
        if (row.week_start !== original.week_start) patch.week_start = row.week_start;
        if (row.campaign !== original.campaign) patch.campaign = row.campaign;
        if (row.bot_key !== original.bot_key) patch.bot_key = row.bot_key;
        if (row.impressions !== original.impressions) patch.impressions = row.impressions;
        if (row.clicks !== original.clicks) patch.clicks = row.clicks;
        if (row.spend !== original.spend) patch.spend = row.spend;
        if (Object.keys(patch).length) {
          await onUpdate(row.id, patch);
        }
      }
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
      <DialogTitle>Недельные рекламные метрики</DialogTitle>
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
            {companies.length ? (
              <>
                <FormControl size="small" sx={{ minWidth: 240 }}>
                  <InputLabel id="admetrics-company-label">РК</InputLabel>
                  <Select
                    labelId="admetrics-company-label"
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
                  <InputLabel id="admetrics-bot-label">Бот (опц.)</InputLabel>
                  <Select
                    labelId="admetrics-bot-label"
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
              </>
            ) : (
              <>
                <TextField
                  label="РК"
                  value={newCampaign}
                  onChange={(event) => setNewCampaign(event.target.value)}
                  size="small"
                  sx={{ minWidth: 240 }}
                />
                <TextField
                  label="Бот (опц.)"
                  value={newBot}
                  onChange={(event) => setNewBot(event.target.value)}
                  size="small"
                  sx={{ minWidth: 180 }}
                />
              </>
            )}
            <FormControl size="small" sx={{ minWidth: 180 }}>
              <InputLabel id="admetrics-month-label">Месяц</InputLabel>
              <Select
                labelId="admetrics-month-label"
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
              label="Показы"
              value={newImpr}
              onChange={(event) => setNewImpr(event.target.value)}
              size="small"
              sx={{ minWidth: 140 }}
            />
            <TextField
              label="Клики"
              value={newClicks}
              onChange={(event) => setNewClicks(event.target.value)}
              size="small"
              sx={{ minWidth: 140 }}
            />
            <TextField
              label="Spend"
              value={newSpend}
              onChange={(event) => setNewSpend(event.target.value)}
              size="small"
              sx={{ minWidth: 140 }}
            />
          </Stack>
          {formError && <Alert severity="error">{formError}</Alert>}
          {loading && <LinearProgress />}
          <TableContainer>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>Неделя</TableCell>
                  <TableCell>Период</TableCell>
                  <TableCell>РК</TableCell>
                  <TableCell>Бот</TableCell>
                  <TableCell>Показы</TableCell>
                  <TableCell>Клики</TableCell>
                  <TableCell>Spend</TableCell>
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
                        value={row.impressions}
                        onChange={(event) =>
                          handleDraftChange(row.id, { impressions: Number(event.target.value) || 0 })
                        }
                      />
                    </TableCell>
                    <TableCell>
                      <TextField
                        size="small"
                        value={row.clicks}
                        onChange={(event) =>
                          handleDraftChange(row.id, { clicks: Number(event.target.value) || 0 })
                        }
                      />
                    </TableCell>
                    <TableCell>
                      <TextField
                        size="small"
                        value={row.spend}
                        onChange={(event) =>
                          handleDraftChange(row.id, { spend: Number(event.target.value) || 0 })
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
        <Button onClick={handleSaveAll} variant="contained" disabled={saving}>
          Сохранить
        </Button>
      </DialogActions>
    </Dialog>
  );
};

export default AdMetricsDialog;
