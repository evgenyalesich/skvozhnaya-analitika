import React, { useEffect, useMemo, useState } from "react";
import Dialog from "@mui/material/Dialog";
import DialogTitle from "@mui/material/DialogTitle";
import DialogContent from "@mui/material/DialogContent";
import DialogActions from "@mui/material/DialogActions";
import Button from "@mui/material/Button";
import TextField from "@mui/material/TextField";
import Switch from "@mui/material/Switch";
import FormControlLabel from "@mui/material/FormControlLabel";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import Divider from "@mui/material/Divider";
import { BotOption } from "../hooks/useBotRegistry";

interface BotRegistryDialogProps {
  open: boolean;
  bots: BotOption[];
  onClose: () => void;
  onSave: (bots: BotOption[]) => Promise<void>;
}

const BotRegistryDialog: React.FC<BotRegistryDialogProps> = ({ open, bots, onClose, onSave }) => {
  const [drafts, setDrafts] = useState<BotOption[]>([]);
  const [saving, setSaving] = useState(false);
  const [newKey, setNewKey] = useState("");
  const [newLabel, setNewLabel] = useState("");
  const [newCanonical, setNewCanonical] = useState("");
  const [newActive, setNewActive] = useState(true);
  const [newReplicate, setNewReplicate] = useState(true);

  useEffect(() => {
    if (open) {
      setDrafts(bots);
      setNewKey("");
      setNewLabel("");
      setNewCanonical("");
      setNewActive(true);
      setNewReplicate(true);
    }
  }, [open, bots]);

  const draftMap = useMemo(() => {
    const map = new Map<string, BotOption>();
    drafts.forEach((bot) => map.set(bot.bot_key, bot));
    return map;
  }, [drafts]);

  const handleDraftChange = (botKey: string, patch: Partial<BotOption>) => {
    setDrafts((prev) =>
      prev.map((bot) => (bot.bot_key === botKey ? { ...bot, ...patch } : bot))
    );
  };

  const handleAdd = () => {
    const key = newKey.trim();
    if (!key || draftMap.has(key)) return;
    setDrafts((prev) => [
      ...prev,
        {
          bot_key: key,
          display_name: newLabel.trim() || null,
          canonical_base: newCanonical.trim() || newLabel.trim() || key,
          is_active: newActive,
          replicate: newReplicate,
          exists: false,
        },
      ]);
    setNewKey("");
    setNewLabel("");
    setNewCanonical("");
    setNewActive(true);
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      await onSave(drafts);
      onClose();
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onClose={onClose} maxWidth="md" fullWidth PaperProps={{ sx: { borderRadius: "24px", border: "1px solid var(--app-shell-border)", background: "var(--app-panel-bg)", boxShadow: "var(--app-shell-shadow)" } }}>
      <DialogTitle>Управление базами</DialogTitle>
      <DialogContent dividers>
        <Stack spacing={2}>
          <Stack direction="row" spacing={2} alignItems="center">
            <TextField
              label="Ключ базы"
              value={newKey}
              onChange={(event) => setNewKey(event.target.value)}
              size="small"
              sx={{ minWidth: 180 }}
            />
            <TextField
              label="Отображаемое имя"
              value={newLabel}
              onChange={(event) => setNewLabel(event.target.value)}
              size="small"
              sx={{ flex: 1 }}
            />
            <TextField
              label="Каноническая база"
              value={newCanonical}
              onChange={(event) => setNewCanonical(event.target.value)}
              size="small"
              sx={{ flex: 1 }}
            />
            <FormControlLabel
              control={
                <Switch
                  checked={newActive}
                  onChange={(event) => setNewActive(event.target.checked)}
                />
              }
              label="Показывать"
            />
            <FormControlLabel
              control={
                <Switch
                  checked={newReplicate}
                  onChange={(event) => setNewReplicate(event.target.checked)}
                />
              }
              label="Реплицировать"
            />
            <Button variant="outlined" onClick={handleAdd} disabled={!newKey.trim()}>
              Добавить
            </Button>
          </Stack>
          <Divider />
          <Stack spacing={1}>
            {drafts.map((bot) => (
              <Stack
                key={bot.bot_key}
                direction={{ xs: "column", md: "row" }}
                spacing={2}
                alignItems="center"
              >
                <TextField
                  label="Ключ"
                  value={bot.bot_key}
                  size="small"
                  disabled
                  sx={{ minWidth: 180 }}
                />
                <TextField
                  label="Отображаемое имя"
                  value={bot.display_name || ""}
                  onChange={(event) =>
                    handleDraftChange(bot.bot_key, {
                      display_name: event.target.value || null,
                    })
                  }
                  size="small"
                  sx={{ flex: 1 }}
                />
                <TextField
                  label="Каноническая база"
                  value={bot.canonical_base || ""}
                  onChange={(event) =>
                    handleDraftChange(bot.bot_key, {
                      canonical_base: event.target.value || null,
                    })
                  }
                  size="small"
                  sx={{ flex: 1 }}
                />
                <FormControlLabel
                  control={
                    <Switch
                      checked={bot.is_active}
                      onChange={(event) =>
                        handleDraftChange(bot.bot_key, { is_active: event.target.checked })
                      }
                    />
                  }
                  label="Показывать"
                />
                <FormControlLabel
                  control={
                    <Switch
                      checked={bot.replicate}
                      onChange={(event) =>
                        handleDraftChange(bot.bot_key, { replicate: event.target.checked })
                      }
                    />
                  }
                  label="Реплицировать"
                />
                {!bot.exists && (
                  <Typography variant="caption" color="text.secondary">
                    нет в БД
                  </Typography>
                )}
              </Stack>
            ))}
          </Stack>
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} disabled={saving}>
          Отмена
        </Button>
        <Button onClick={handleSave} variant="contained" disabled={saving}>
          Сохранить
        </Button>
      </DialogActions>
    </Dialog>
  );
};

export default BotRegistryDialog;
