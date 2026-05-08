// Диалог управления белым списком Telegram (добавить/удалить tg_user_id).
import React, { useState } from "react";
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
import { TelegramAccessEntry } from "../hooks/useTelegramAccess";

interface AccessManagerDialogProps {
  open: boolean;
  onClose: () => void;
  entries: TelegramAccessEntry[];
  loading?: boolean;
  error?: string | null;
  onAdd: (tgUserId: number) => Promise<void>;
  onRemove: (tgUserId: number) => Promise<void>;
}

const sanitizeId = (value: string) => value.replace(/\D/g, "");

const AccessManagerDialog: React.FC<AccessManagerDialogProps> = ({
  open,
  onClose,
  entries,
  loading,
  error,
  onAdd,
  onRemove,
}) => {
  const [input, setInput] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const handleAdd = async () => {
    const cleaned = sanitizeId(input);
    if (!cleaned) {
      return;
    }
    const parsed = Number(cleaned);
    if (!Number.isFinite(parsed) || parsed <= 0) {
      return;
    }
    setSubmitting(true);
    try {
      await onAdd(parsed);
      setInput("");
    } finally {
      setSubmitting(false);
    }
  };
  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth PaperProps={{ sx: { borderRadius: "24px", border: "1px solid var(--app-shell-border)", background: "var(--app-panel-bg)", boxShadow: "var(--app-shell-shadow)" } }}>
      <DialogTitle>Управление доступом</DialogTitle>
      <DialogContent dividers>
        <Stack spacing={2}>
          <TextField
            label="Telegram ID"
            value={input}
            onChange={(event) => setInput(sanitizeId(event.target.value))}
            helperText="Введите цифровой ID пользователя"
            fullWidth
            disabled={submitting}
          />
          <Button variant="contained" onClick={handleAdd} disabled={submitting || !input}>
            {submitting ? "Добавление..." : "Выдать доступ"}
          </Button>
          {error && (
            <Typography variant="body2" color="error">
              {error}
            </Typography>
          )}
          <Typography variant="subtitle2">Текущие доступы</Typography>
          <Stack spacing={1}>
            {entries.map((entry) => (
              <Stack
                key={entry.tg_user_id}
                direction="row"
                justifyContent="space-between"
                alignItems="center"
                sx={{ px: 1, py: 0.5, border: "1px solid var(--app-table-divider)", borderRadius: 1.5, background: "var(--app-panel-muted)" }}
              >
                <Typography>
                  {entry.tg_user_id} (создан {new Date(entry.created_at).toLocaleString()})
                </Typography>
                <IconButton
                  size="small"
                  color="error"
                  onClick={() => onRemove(entry.tg_user_id)}
                  disabled={loading}
                >
                  <DeleteIcon fontSize="small" />
                </IconButton>
              </Stack>
            ))}
            {!entries.length && (
              <Typography variant="body2" color="text.secondary">
                Список пуст.
              </Typography>
            )}
          </Stack>
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Закрыть</Button>
      </DialogActions>
    </Dialog>
  );
};

export default AccessManagerDialog;
