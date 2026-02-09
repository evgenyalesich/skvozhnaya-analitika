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
import Autocomplete from "@mui/material/Autocomplete";
import { AdvertisingCompanyOption } from "../hooks/useAdvertisingCompanies";
import { BotOption } from "../hooks/useBotRegistry";

interface AdvertisingCompaniesDialogProps {
  open: boolean;
  companies: AdvertisingCompanyOption[];
  bots: BotOption[];
  onClose: () => void;
  onSave: (companies: AdvertisingCompanyOption[]) => Promise<void>;
}

const AdvertisingCompaniesDialog: React.FC<AdvertisingCompaniesDialogProps> = ({
  open,
  companies,
  bots,
  onClose,
  onSave,
}) => {
  const [drafts, setDrafts] = useState<AdvertisingCompanyOption[]>([]);
  const [saving, setSaving] = useState(false);
  const [newName, setNewName] = useState("");
  const [newActive, setNewActive] = useState(true);
  const [newBots, setNewBots] = useState<string[]>([]);

  useEffect(() => {
    if (open) {
      setDrafts(companies);
      setNewName("");
      setNewActive(true);
      setNewBots([]);
    }
  }, [open, companies]);

  const botOptions = useMemo(
    () => bots.map((bot) => ({ value: bot.bot_key, label: bot.display_name || bot.bot_key })),
    [bots]
  );

  const handleDraftChange = (companyId: string | undefined, patch: Partial<AdvertisingCompanyOption>) => {
    setDrafts((prev) =>
      prev.map((company) =>
        company.company_id === companyId ? { ...company, ...patch } : company
      )
    );
  };

  const handleAdd = () => {
    const name = newName.trim();
    if (!name) return;
    setDrafts((prev) => [
      ...prev,
      {
        company_id: null,
        company_name: name,
        is_active: newActive,
        bot_keys: newBots,
      },
    ]);
    setNewName("");
    setNewActive(true);
    setNewBots([]);
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
    <Dialog open={open} onClose={onClose} maxWidth="md" fullWidth>
      <DialogTitle>Управление рекламными компаниями</DialogTitle>
      <DialogContent dividers>
        <Stack spacing={2}>
          <Stack direction={{ xs: "column", md: "row" }} spacing={2} alignItems="center">
            <TextField
              label="Название РК"
              value={newName}
              onChange={(event) => setNewName(event.target.value)}
              size="small"
              sx={{ minWidth: 220 }}
            />
            <Autocomplete
              multiple
              options={botOptions}
              value={botOptions.filter((bot) => newBots.includes(bot.value))}
              onChange={(_event, value) => setNewBots(value.map((item) => item.value))}
              getOptionLabel={(option) => option.label}
              renderInput={(params) => <TextField {...params} label="Боты" size="small" />}
              sx={{ flex: 1, minWidth: 280 }}
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
            <Button variant="outlined" onClick={handleAdd} disabled={!newName.trim()}>
              Добавить
            </Button>
          </Stack>
          <Divider />
          <Stack spacing={2}>
            {drafts.map((company) => (
              <Stack
                key={company.company_id || company.company_name}
                direction={{ xs: "column", md: "row" }}
                spacing={2}
                alignItems="center"
              >
                <TextField
                  label="Название"
                  value={company.company_name}
                  onChange={(event) =>
                    handleDraftChange(company.company_id, { company_name: event.target.value })
                  }
                  size="small"
                  sx={{ minWidth: 220 }}
                />
                <Autocomplete
                  multiple
                  options={botOptions}
                  value={botOptions.filter((bot) => company.bot_keys.includes(bot.value))}
                  onChange={(_event, value) =>
                    handleDraftChange(company.company_id, {
                      bot_keys: value.map((item) => item.value),
                    })
                  }
                  getOptionLabel={(option) => option.label}
                  renderInput={(params) => <TextField {...params} label="Боты" size="small" />}
                  sx={{ flex: 1, minWidth: 280 }}
                />
                <FormControlLabel
                  control={
                    <Switch
                      checked={company.is_active}
                      onChange={(event) =>
                        handleDraftChange(company.company_id, { is_active: event.target.checked })
                      }
                    />
                  }
                  label="Показывать"
                />
                {!company.company_id && (
                  <Typography variant="caption" color="text.secondary">
                    новая
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

export default AdvertisingCompaniesDialog;
