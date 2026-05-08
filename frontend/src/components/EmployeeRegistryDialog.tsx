// Диалог реестра сотрудников: список tg_user_id → excludes из воронки как "внутренние".
import React, { useEffect, useMemo, useState } from "react";
import Dialog from "@mui/material/Dialog";
import DialogTitle from "@mui/material/DialogTitle";
import DialogContent from "@mui/material/DialogContent";
import DialogActions from "@mui/material/DialogActions";
import Button from "@mui/material/Button";
import TextField from "@mui/material/TextField";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import IconButton from "@mui/material/IconButton";
import DeleteIcon from "@mui/icons-material/Delete";
import Alert from "@mui/material/Alert";
import { EmployeeRegistryEntry } from "../hooks/useEmployeeRegistry";

interface EmployeeRegistryDialogProps {
  open: boolean;
  onClose: () => void;
  entries: EmployeeRegistryEntry[];
  loading?: boolean;
  error?: string | null;
  onSave: (tgUserIds: number[]) => Promise<void>;
}

const extractIds = (value: string) => {
  const matches = value.match(/\d+/g) || [];
  return Array.from(new Set(matches.map((match) => Number(match)).filter((value) => Number.isFinite(value) && value > 0)));
};

const EmployeeRegistryDialog: React.FC<EmployeeRegistryDialogProps> = ({
  open,
  onClose,
  entries,
  loading,
  error,
  onSave,
}) => {
  const [input, setInput] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [pendingDelete, setPendingDelete] = useState<EmployeeRegistryEntry | null>(null);
  const [draftEntries, setDraftEntries] = useState<EmployeeRegistryEntry[]>([]);

  useEffect(() => {
    if (open) {
      setDraftEntries(entries);
      setInput("");
      setPendingDelete(null);
    }
  }, [open, entries]);

  const handleAdd = async () => {
    const ids = extractIds(input);
    if (!ids.length) {
      return;
    }
    const draftMap = new Map(draftEntries.map((entry) => [entry.tg_user_id, entry]));
    ids.forEach((tg_user_id) => {
      if (!draftMap.has(tg_user_id)) {
        draftMap.set(tg_user_id, {
          tg_user_id,
          username: null,
          created_at: new Date().toISOString(),
          created_by: null,
        });
      }
    });
    setDraftEntries(Array.from(draftMap.values()).sort((a, b) => a.tg_user_id - b.tg_user_id));
    setInput("");
  };
  const parsedIds = extractIds(input);
  const hasChanges = useMemo(() => {
    const actual = entries.map((entry) => entry.tg_user_id).sort((a, b) => a - b).join(",");
    const draft = draftEntries.map((entry) => entry.tg_user_id).sort((a, b) => a - b).join(",");
    return actual !== draft;
  }, [entries, draftEntries]);

  return (
    <Dialog open={open} onClose={onClose} maxWidth="md" fullWidth PaperProps={{ sx: { borderRadius: "24px", border: "1px solid var(--app-shell-border)", background: "var(--app-panel-bg)", boxShadow: "var(--app-shell-shadow)" } }}>
      <DialogTitle>Реестр сотрудников</DialogTitle>
      <DialogContent dividers>
        <Stack spacing={2}>
          <Typography variant="body2" color="text.secondary">
            Пользователи из этого списка будут исключены из статистики и отчетов.
          </Typography>
          <Alert severity="info">
            Можно вставить сразу несколько Telegram ID через пробел, запятую или с новой строки. Изменения применяются только после нажатия «Сохранить», и тогда будет один пересчет агрегатов.
          </Alert>
          <TextField
            label="Telegram ID"
            value={input}
            onChange={(event) => setInput(event.target.value)}
            helperText={parsedIds.length > 1 ? `Найдено ID: ${parsedIds.length}` : "Введите один или несколько Telegram ID"}
            fullWidth
            disabled={submitting}
            multiline
            minRows={3}
          />
          <Button variant="contained" onClick={handleAdd} disabled={submitting || !input}>
            {submitting ? "Добавление..." : parsedIds.length > 1 ? "Добавить сотрудников" : "Добавить сотрудника"}
          </Button>
          {error && (
            <Typography variant="body2" color="error">
              {error}
            </Typography>
          )}
          <Typography variant="subtitle2">Список исключений</Typography>
          <Stack spacing={1}>
            {draftEntries.map((entry) => (
              <Stack
                key={entry.tg_user_id}
                direction="row"
                justifyContent="space-between"
                alignItems="center"
                sx={{ px: 1, py: 0.5, border: "1px solid var(--app-table-divider)", borderRadius: 1.5, background: "var(--app-panel-muted)" }}
              >
                <Stack spacing={0.25}>
                  <Typography fontWeight={600}>{entry.username || "Без username"}</Typography>
                  <Typography variant="body2" color="text.secondary">
                    TG ID {entry.tg_user_id} • добавлен {new Date(entry.created_at).toLocaleString()}
                  </Typography>
                </Stack>
                <IconButton
                  size="small"
                  color="error"
                  onClick={() => setPendingDelete(entry)}
                  disabled={loading}
                >
                  <DeleteIcon fontSize="small" />
                </IconButton>
              </Stack>
            ))}
            {!draftEntries.length && (
              <Typography variant="body2" color="text.secondary">
                Список пуст.
              </Typography>
            )}
          </Stack>
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Отмена</Button>
        <Button
          variant="contained"
          disabled={submitting || !hasChanges}
          onClick={async () => {
            setSubmitting(true);
            try {
              await onSave(draftEntries.map((entry) => entry.tg_user_id));
              onClose();
            } finally {
              setSubmitting(false);
            }
          }}
        >
          {submitting ? "Сохранение..." : "Сохранить"}
        </Button>
      </DialogActions>
      <Dialog open={Boolean(pendingDelete)} onClose={() => setPendingDelete(null)} maxWidth="xs" fullWidth PaperProps={{ sx: { borderRadius: "20px", border: "1px solid var(--app-shell-border)", background: "var(--app-panel-bg)" } }}>
        <DialogTitle>Удалить сотрудника?</DialogTitle>
        <DialogContent dividers>
          <Typography>
            {pendingDelete
              ? `Пользователь ${pendingDelete.username || pendingDelete.tg_user_id} будет снова учитываться в статистике.`
              : ""}
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setPendingDelete(null)}>Отмена</Button>
          <Button
            color="error"
            variant="contained"
            onClick={() => {
              if (!pendingDelete) {
                return;
              }
              const tgUserId = pendingDelete.tg_user_id;
              setPendingDelete(null);
              setDraftEntries((current) => current.filter((entry) => entry.tg_user_id !== tgUserId));
            }}
          >
            Удалить
          </Button>
        </DialogActions>
      </Dialog>
    </Dialog>
  );
};

export default EmployeeRegistryDialog;
