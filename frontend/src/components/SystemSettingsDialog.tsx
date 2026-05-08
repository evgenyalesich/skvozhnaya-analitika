// Диалог системных настроек: планировщик, синхронизация, Marketing Daily (preview/send), логи.
// Marketing Daily виджеты показываются только marketingDailyEnabledForUser=true (hardcoded user IDs).
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
import Accordion from "@mui/material/Accordion";
import AccordionSummary from "@mui/material/AccordionSummary";
import AccordionDetails from "@mui/material/AccordionDetails";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import Chip from "@mui/material/Chip";

import {
  MarketingDailyHistoryItem,
  MarketingDailyPreview,
  MarketingDailySettings,
  SystemSettings,
  SyncEventLog,
} from "../hooks/useSystemSettings";

interface SystemSettingsDialogProps {
  open: boolean;
  settings: SystemSettings | null;
  logs: SyncEventLog[];
  marketingDailySettings?: MarketingDailySettings | null;
  marketingDailyPreview?: MarketingDailyPreview | null;
  marketingDailyHistory?: MarketingDailyHistoryItem[];
  marketingDailyEnabledForUser?: boolean;
  loading: boolean;
  error?: string | null;
  onClose: () => void;
  onSave: (payload: SystemSettings) => Promise<void>;
  onSaveMarketingDaily?: (payload: MarketingDailySettings) => Promise<void>;
  onRefreshMarketingDailyPreview?: () => Promise<void>;
  onSendMarketingDailyTest?: () => Promise<void>;
  onResendMarketingDaily?: () => Promise<void>;
  onRefresh: () => Promise<void>;
  onSyncAll: () => Promise<void>;
  onSyncSm: () => Promise<void>;
  onRebuildCompanies: () => Promise<void>;
}

const SystemSettingsDialog: React.FC<SystemSettingsDialogProps> = ({
  open,
  settings,
  logs,
  marketingDailySettings,
  marketingDailyPreview,
  marketingDailyHistory = [],
  marketingDailyEnabledForUser,
  loading,
  error,
  onClose,
  onSave,
  onSaveMarketingDaily,
  onRefreshMarketingDailyPreview,
  onSendMarketingDailyTest,
  onResendMarketingDaily,
  onRefresh,
  onSyncAll,
  onSyncSm,
  onRebuildCompanies,
}) => {
  const [draft, setDraft] = useState<SystemSettings | null>(null);
  const [marketingDraft, setMarketingDraft] = useState<MarketingDailySettings | null>(null);
  const [allowedIdInput, setAllowedIdInput] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (open) {
      setDraft(settings);
      setMarketingDraft(marketingDailySettings || null);
      setAllowedIdInput("");
    }
  }, [open, settings, marketingDailySettings]);

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

  const handleSaveMarketingDaily = async () => {
    if (!marketingDraft || !onSaveMarketingDaily) return;
    setSaving(true);
    try {
      await onSaveMarketingDaily(marketingDraft);
    } finally {
      setSaving(false);
    }
  };

  const parseIds = (raw: string) =>
    raw
      .split(/[\n, ]+/)
      .map((item) => Number(item.trim()))
      .filter((item) => Number.isFinite(item) && item > 0);

  const removeAllowedId = (tgUserId: number) => {
    if (!marketingDraft) return;
    setMarketingDraft({
      ...marketingDraft,
      allowed_subscriber_ids: marketingDraft.allowed_subscriber_ids.filter((item) => item !== tgUserId),
    });
  };

  const addAllowedId = () => {
    if (!marketingDraft) return;
    const nextIds = parseIds(allowedIdInput);
    if (!nextIds.length) {
      return;
    }
    const merged = [...marketingDraft.allowed_subscriber_ids];
    nextIds.forEach((item) => {
      if (!merged.includes(item)) {
        merged.push(item);
      }
    });
    setMarketingDraft({
      ...marketingDraft,
      allowed_subscriber_ids: merged,
    });
    setAllowedIdInput("");
  };

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
          {marketingDailyEnabledForUser && marketingDraft && (
            <Accordion defaultExpanded>
              <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                <Typography variant="subtitle1">Marketing Daily</Typography>
              </AccordionSummary>
              <AccordionDetails>
                <Stack spacing={2}>
                  <Stack direction={{ xs: "column", md: "row" }} spacing={2} alignItems="center">
                    <FormControlLabel
                      control={
                        <Switch
                          checked={marketingDraft.enabled}
                          onChange={(e) =>
                            setMarketingDraft({ ...marketingDraft, enabled: e.target.checked })
                          }
                        />
                      }
                      label="Включить daily-дайджест"
                    />
                    <TextField
                      label="Час отправки (MSK)"
                      type="number"
                      size="small"
                      value={marketingDraft.send_hour_msk}
                      onChange={(e) =>
                        setMarketingDraft({
                          ...marketingDraft,
                          send_hour_msk: Number(e.target.value),
                        })
                      }
                    />
                    <TextField
                      label="Топ роста"
                      type="number"
                      size="small"
                      value={marketingDraft.show_top_growth}
                      onChange={(e) =>
                        setMarketingDraft({
                          ...marketingDraft,
                          show_top_growth: Number(e.target.value),
                        })
                      }
                    />
                    <TextField
                      label="Топ просадок"
                      type="number"
                      size="small"
                      value={marketingDraft.show_top_decline}
                      onChange={(e) =>
                        setMarketingDraft({
                          ...marketingDraft,
                          show_top_decline: Number(e.target.value),
                        })
                      }
                    />
                  </Stack>
                  <Stack direction={{ xs: "column", md: "row" }} spacing={2}>
                    <TextField
                      label="Порог аномалии, %"
                      type="number"
                      size="small"
                      value={marketingDraft.anomaly_drop_threshold_pct}
                      onChange={(e) =>
                        setMarketingDraft({
                          ...marketingDraft,
                          anomaly_drop_threshold_pct: Number(e.target.value),
                        })
                      }
                    />
                    <TextField
                      label="Дней падения подряд"
                      type="number"
                      size="small"
                      value={marketingDraft.downward_streak_days}
                      onChange={(e) =>
                        setMarketingDraft({
                          ...marketingDraft,
                          downward_streak_days: Number(e.target.value),
                        })
                      }
                    />
                  </Stack>
                  <Stack direction={{ xs: "column", md: "row" }} spacing={2}>
                    <TextField
                      label="Кому можно подписываться"
                      value={allowedIdInput}
                      helperText="Введите один или несколько Telegram ID через пробел, запятую или перенос строки."
                      onChange={(e) => setAllowedIdInput(e.target.value)}
                      fullWidth
                    />
                    <Button variant="outlined" onClick={addAllowedId} disabled={!allowedIdInput.trim()}>
                      Добавить ID
                    </Button>
                  </Stack>
                  <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                    {marketingDraft.allowed_subscriber_ids.map((tgUserId) => (
                      <Chip
                        key={tgUserId}
                        label={String(tgUserId)}
                        onDelete={() => removeAllowedId(tgUserId)}
                        color="primary"
                        variant="outlined"
                      />
                    ))}
                    {!marketingDraft.allowed_subscriber_ids.length && (
                      <Typography variant="body2" color="text.secondary">
                        Пока никого не добавили.
                      </Typography>
                    )}
                  </Stack>
                  <Stack direction="row" spacing={2}>
                    <Button
                      variant="contained"
                      onClick={handleSaveMarketingDaily}
                      disabled={saving}
                    >
                      Сохранить Marketing Daily
                    </Button>
                    <Button
                      variant="outlined"
                      onClick={onRefreshMarketingDailyPreview}
                      disabled={saving || !onRefreshMarketingDailyPreview}
                    >
                      Обновить предпросмотр
                    </Button>
                    <Button
                      variant="outlined"
                      color="secondary"
                      onClick={onSendMarketingDailyTest}
                      disabled={saving || !onSendMarketingDailyTest}
                    >
                      Отправить тест в Telegram
                    </Button>
                    <Button
                      variant="outlined"
                      color="warning"
                      onClick={onResendMarketingDaily}
                      disabled={saving || !onResendMarketingDaily}
                    >
                      Переслать дайджест принудительно
                    </Button>
                  </Stack>
                  <TextField
                    label="Предпросмотр сообщения"
                    multiline
                    minRows={18}
                    value={marketingDailyPreview?.text || "Нет данных"}
                    fullWidth
                    InputProps={{ readOnly: true }}
                  />
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
                          <TableCell>Дата</TableCell>
                          <TableCell>Статус</TableCell>
                          <TableCell>Получатели</TableCell>
                          <TableCell>Успешно</TableCell>
                          <TableCell>Ошибки</TableCell>
                          <TableCell>Создано</TableCell>
                        </TableRow>
                      </TableHead>
                      <TableBody>
                        {marketingDailyHistory.map((row) => (
                          <TableRow key={row.id}>
                            <TableCell>{row.report_date}</TableCell>
                            <TableCell>{row.status}</TableCell>
                            <TableCell>{row.total_recipients}</TableCell>
                            <TableCell>{row.success_count}</TableCell>
                            <TableCell>{row.failure_count}</TableCell>
                            <TableCell>{new Date(row.created_at).toLocaleString("ru-RU")}</TableCell>
                          </TableRow>
                        ))}
                        {!marketingDailyHistory.length && (
                          <TableRow>
                            <TableCell colSpan={6}>История пока пустая</TableCell>
                          </TableRow>
                        )}
                      </TableBody>
                    </Table>
                  </TableContainer>
                </Stack>
              </AccordionDetails>
            </Accordion>
          )}

          <Divider />
          <Typography variant="subtitle1">Последние ошибки/предупреждения</Typography>
          {loading && <LinearProgress />}
          {error && <Typography color="error">{error}</Typography>}
          <TableContainer sx={{ borderRadius: "18px", border: "1px solid var(--app-table-divider)", overflow: "hidden" }}>
            <Table
              size="small"
              sx={{
                "& .MuiTableCell-root": {
                  borderBottom: "1px solid var(--app-table-divider)",
                  verticalAlign: "top",
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
