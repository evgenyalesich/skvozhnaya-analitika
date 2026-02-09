import React, { useEffect, useState } from "react";
import Dialog from "@mui/material/Dialog";
import DialogTitle from "@mui/material/DialogTitle";
import DialogContent from "@mui/material/DialogContent";
import DialogActions from "@mui/material/DialogActions";
import Button from "@mui/material/Button";
import TextField from "@mui/material/TextField";
import Stack from "@mui/material/Stack";
import Switch from "@mui/material/Switch";
import FormControlLabel from "@mui/material/FormControlLabel";
import Typography from "@mui/material/Typography";
import Divider from "@mui/material/Divider";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import TableContainer from "@mui/material/TableContainer";
import LinearProgress from "@mui/material/LinearProgress";

import { SystemSettings, SyncEventLog } from "../hooks/useSystemSettings";

interface SystemSettingsDialogProps {
  open: boolean;
  settings: SystemSettings | null;
  logs: SyncEventLog[];
  loading: boolean;
  error?: string | null;
  onClose: () => void;
  onSave: (payload: SystemSettings) => Promise<void>;
  onRefresh: () => Promise<void>;
  onSyncAll: () => Promise<void>;
  onSyncSm: () => Promise<void>;
  onRebuildCompanies: () => Promise<void>;
}

const SystemSettingsDialog: React.FC<SystemSettingsDialogProps> = ({
  open,
  settings,
  logs,
  loading,
  error,
  onClose,
  onSave,
  onRefresh,
  onSyncAll,
  onSyncSm,
  onRebuildCompanies,
}) => {
  const [draft, setDraft] = useState<SystemSettings | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (open) {
      setDraft(settings);
    }
  }, [open, settings]);

  const updateField = (key: keyof SystemSettings["scheduler"], value: any) => {
    if (!draft) return;
    setDraft({
      ...draft,
      scheduler: { ...draft.scheduler, [key]: value },
    });
  };

  const handleSave = async () => {
    if (!draft) return;
    setSaving(true);
    try {
      await onSave(draft);
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onClose={onClose} maxWidth="lg" fullWidth>
      <DialogTitle>Настройки обновлений и логи</DialogTitle>
      <DialogContent dividers>
        <Stack spacing={2}>
          <Stack direction={{ xs: "column", md: "row" }} spacing={2} alignItems="center">
            <FormControlLabel
              control={
                <Switch
                  checked={draft?.scheduler.periodic_enabled ?? false}
                  onChange={(e) => updateField("periodic_enabled", e.target.checked)}
                />
              }
              label="Периодические обновления"
            />
            <FormControlLabel
              control={
                <Switch
                  checked={draft?.scheduler.run_on_start ?? false}
                  onChange={(e) => updateField("run_on_start", e.target.checked)}
                />
              }
              label="Запускать при старте"
            />
            <FormControlLabel
              control={
                <Switch
                  checked={draft?.scheduler.warm_cache_on_start ?? false}
                  onChange={(e) => updateField("warm_cache_on_start", e.target.checked)}
                />
              }
              label="Прогрев кэша при старте"
            />
          </Stack>

          <Stack direction={{ xs: "column", md: "row" }} spacing={2}>
            <TextField
              label="Ingestion, мин"
              type="number"
              size="small"
              value={draft?.scheduler.ingestion_interval_minutes ?? 60}
              onChange={(e) => updateField("ingestion_interval_minutes", Number(e.target.value))}
            />
            <TextField
              label="Google Sheets, мин"
              type="number"
              size="small"
              value={draft?.scheduler.google_sheets_interval_minutes ?? 60}
              onChange={(e) => updateField("google_sheets_interval_minutes", Number(e.target.value))}
            />
            <TextField
              label="PokerHub, часов"
              type="number"
              size="small"
              value={draft?.scheduler.pokerhub_interval_hours ?? 24}
              onChange={(e) => updateField("pokerhub_interval_hours", Number(e.target.value))}
            />
            <TextField
              label="Telegram, мин (0 = daily)"
              type="number"
              size="small"
              value={draft?.scheduler.telegram_interval_minutes ?? 0}
              onChange={(e) => updateField("telegram_interval_minutes", Number(e.target.value))}
            />
            <TextField
              label="Telegram daily hour"
              type="number"
              size="small"
              value={draft?.scheduler.telegram_daily_hour ?? 4}
              onChange={(e) => updateField("telegram_daily_hour", Number(e.target.value))}
            />
            <TextField
              label="Telegram batch size"
              type="number"
              size="small"
              value={draft?.scheduler.telegram_batch_size ?? 1000}
              onChange={(e) => updateField("telegram_batch_size", Number(e.target.value))}
            />
            <TextField
              label="Telegram timeout, сек"
              type="number"
              size="small"
              value={draft?.scheduler.telegram_job_timeout_seconds ?? 7200}
              onChange={(e) => updateField("telegram_job_timeout_seconds", Number(e.target.value))}
            />
          </Stack>

          <Stack direction="row" spacing={2}>
            <Button variant="outlined" onClick={onRefresh} disabled={loading}>
              Обновить
            </Button>
            <Button variant="outlined" onClick={onSyncAll} disabled={loading}>
              Синх сейчас
            </Button>
            <Button variant="outlined" onClick={onSyncSm} disabled={loading}>
              Синх SM
            </Button>
            <Button variant="outlined" color="warning" onClick={onRebuildCompanies} disabled={loading}>
              Пересчитать РК
            </Button>
          </Stack>

          <Divider />
          <Typography variant="subtitle1">Последние ошибки/предупреждения</Typography>
          {loading && <LinearProgress />}
          {error && <Typography color="error">{error}</Typography>}
          <TableContainer>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>Время</TableCell>
                  <TableCell>Источник</TableCell>
                  <TableCell>Уровень</TableCell>
                  <TableCell>Сообщение</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {logs.map((row) => (
                  <TableRow key={row.id}>
                    <TableCell>{new Date(row.created_at).toLocaleString("ru-RU")}</TableCell>
                    <TableCell>{row.source}</TableCell>
                    <TableCell>{row.level}</TableCell>
                    <TableCell>{row.message}</TableCell>
                  </TableRow>
                ))}
                {!logs.length && (
                  <TableRow>
                    <TableCell colSpan={4}>Нет данных</TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </TableContainer>
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} disabled={saving}>
          Закрыть
        </Button>
        <Button onClick={handleSave} variant="contained" disabled={saving || !draft}>
          Сохранить
        </Button>
      </DialogActions>
    </Dialog>
  );
};

export default SystemSettingsDialog;
