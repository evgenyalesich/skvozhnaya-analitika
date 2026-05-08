// Диалог настройки рекламных компаний: редактирование company_name/bot_keys/UTM-правил/platform.
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
import IconButton from "@mui/material/IconButton";
import DialogContentText from "@mui/material/DialogContentText";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Tooltip from "@mui/material/Tooltip";
import Alert from "@mui/material/Alert";
import AddIcon from "@mui/icons-material/Add";
import DeleteIcon from "@mui/icons-material/Delete";
import { AdvertisingCompanyOption, UtmRule } from "../hooks/useAdvertisingCompanies";
import { BotOption } from "../hooks/useBotRegistry";

const UTM_FIELDS: Array<{ key: keyof UtmRule; label: string; placeholder: string }> = [
  { key: "utm_source", label: "Источник", placeholder: "tgads, vk…" },
  { key: "utm_campaign", label: "Кампания", placeholder: "ukraine_2024…" },
  { key: "utm_medium", label: "Медиум", placeholder: "cpc…" },
  { key: "utm_content", label: "Контент", placeholder: "необязательно" },
  { key: "utm_term", label: "Термин", placeholder: "необязательно" },
];

interface UtmRulesEditorProps {
  rules: UtmRule[];
  botOptions: Array<{ value: string; label: string }>;
  onChange: (rules: UtmRule[]) => void;
  onSaveAll?: () => void;
  saveDisabled?: boolean;
}

const createEmptyRule = (): UtmRule => ({
  bot_keys: [],
  priority: 0,
  match_mode: "all",
});

const UtmRulesEditor: React.FC<UtmRulesEditorProps> = ({
  rules,
  botOptions,
  onChange,
  onSaveAll,
  saveDisabled = false,
}) => {
  const addRule = () => onChange([...rules, createEmptyRule()]);
  const removeRule = (i: number) => onChange(rules.filter((_, idx) => idx !== i));
  const updateRule = (i: number, patch: Partial<UtmRule>) => {
    onChange(rules.map((r, idx) => idx === i ? { ...r, ...patch } : r));
  };

  const ruleLabel = (rule: UtmRule) => {
    const parts = [rule.utm_source, rule.utm_campaign, rule.utm_medium]
      .filter(Boolean).join(" / ");
    const botPart = rule.bot_keys?.length ? ` | ${rule.bot_keys.length} бот` : "";
    return `${parts || "пустое правило"}${botPart}`;
  };

  return (
    <Box sx={{ mt: 1, borderTop: "1px dashed var(--app-table-divider)", pt: 1 }}>
      <Stack direction="row" alignItems="center" spacing={1} mb={rules.length ? 1 : 0}>
        <Typography variant="caption" sx={{ fontWeight: 700, color: "var(--c-ink2)", textTransform: "uppercase", letterSpacing: 0.5 }}>
          UTM атрибуция
        </Typography>
        <Tooltip title="Правило можно ограничить ботами и диапазоном дат. Пустые поля = любое значение. Более приоритетные и более точные правила переопределяют общие." placement="top">
          <Typography variant="caption" sx={{ color: "var(--c-ink3)", cursor: "help", borderBottom: "1px dashed var(--c-ink3)" }}>
            ?
          </Typography>
        </Tooltip>
        {rules.length > 0 && (
          <Chip label={`${rules.length} правил${rules.length === 1 ? "о" : "а"}`} size="small" color="primary" variant="outlined" sx={{ fontSize: "0.7rem", height: 18 }} />
        )}
      </Stack>

      {rules.map((rule, i) => (
        <Box
          key={i}
          sx={{
            mb: 1,
            p: 1,
            border: "1px solid var(--app-table-divider)",
            borderRadius: 2,
            backgroundColor: "var(--app-panel-muted)",
          }}
        >
          <Stack direction="row" alignItems="center" justifyContent="space-between" mb={0.5}>
            <Typography variant="caption" sx={{ color: "var(--c-ink2)", fontWeight: 700 }}>
              Правило {i + 1}: <span style={{ color: "var(--c-blue)" }}>{ruleLabel(rule)}</span>
            </Typography>
            <IconButton size="small" onClick={() => removeRule(i)} color="error" sx={{ p: 0.2 }}>
              <DeleteIcon sx={{ fontSize: 15 }} />
            </IconButton>
          </Stack>
          <Stack direction="row" spacing={0.75} flexWrap="wrap" useFlexGap>
            <Autocomplete
              multiple
              options={botOptions}
              value={botOptions.filter((bot) => (rule.bot_keys || []).includes(bot.value))}
              onChange={(_event, value) => updateRule(i, { bot_keys: value.map((item) => item.value) })}
              getOptionLabel={(option) => option.label}
              renderInput={(params) => <TextField {...params} label="Боты правила" size="small" />}
              sx={{ minWidth: 260, flex: 1 }}
            />
            {UTM_FIELDS.map(({ key, label, placeholder }) => (
              <TextField
                key={key}
                label={label}
                value={rule[key] || ""}
                onChange={(e) => updateRule(i, { [key]: e.target.value.trim() || null })}
                size="small"
                placeholder={placeholder}
                sx={{ width: 140, "& .MuiInputBase-root": { fontSize: "0.8rem" } }}
                InputLabelProps={{ style: { fontSize: "0.78rem" } }}
              />
            ))}
            <TextField
              label="Дата с"
              type="date"
              value={rule.date_from || ""}
              onChange={(e) => updateRule(i, { date_from: e.target.value || null })}
              size="small"
              sx={{ width: 150 }}
              InputLabelProps={{ shrink: true, style: { fontSize: "0.78rem" } }}
            />
            <TextField
              label="Дата по"
              type="date"
              value={rule.date_to || ""}
              onChange={(e) => updateRule(i, { date_to: e.target.value || null })}
              size="small"
              sx={{ width: 150 }}
              InputLabelProps={{ shrink: true, style: { fontSize: "0.78rem" } }}
            />
            <TextField
              label="Приоритет"
              type="number"
              value={rule.priority ?? 0}
              onChange={(e) => updateRule(i, { priority: Number(e.target.value || 0) })}
              size="small"
              sx={{ width: 120 }}
              inputProps={{ step: 1 }}
              InputLabelProps={{ style: { fontSize: "0.78rem" } }}
              helperText="Выше = сильнее"
            />
          </Stack>
        </Box>
      ))}

      <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
        <Button
          size="small"
          variant="outlined"
          startIcon={<AddIcon />}
          onClick={addRule}
          sx={{ fontSize: "0.75rem", py: 0.3, borderStyle: "dashed" }}
        >
          Добавить UTM правило
        </Button>
        {onSaveAll && (
          <Button
            size="small"
            variant="contained"
            onClick={onSaveAll}
            disabled={saveDisabled}
            sx={{ fontSize: "0.75rem", py: 0.3 }}
          >
            Сохранить изменения
          </Button>
        )}
      </Stack>
    </Box>
  );
};

interface AdvertisingCompaniesDialogProps {
  open: boolean;
  companies: AdvertisingCompanyOption[];
  bots: BotOption[];
  onClose: () => void;
  onSave: (companies: AdvertisingCompanyOption[]) => Promise<void>;
  onDelete: (companyId: string) => Promise<void>;
}

const AdvertisingCompaniesDialog: React.FC<AdvertisingCompaniesDialogProps> = ({
  open,
  companies,
  bots,
  onClose,
  onSave,
  onDelete,
}) => {
  const [drafts, setDrafts] = useState<AdvertisingCompanyOption[]>([]);
  const [saving, setSaving] = useState(false);
  const [newName, setNewName] = useState("");
  const [newPlatform, setNewPlatform] = useState("");
  const [newActive, setNewActive] = useState(true);
  const [newBots, setNewBots] = useState<string[]>([]);
  const [newUtmRules, setNewUtmRules] = useState<UtmRule[]>([]);
  const [deleteTarget, setDeleteTarget] = useState<AdvertisingCompanyOption | null>(null);
  const [error, setError] = useState<string | null>(null);

  const prevOpenRef = React.useRef(false);
  useEffect(() => {
    const wasOpen = prevOpenRef.current;
    prevOpenRef.current = open;
    if (open && !wasOpen) {
      setDrafts(companies);
      setNewName("");
      setNewPlatform("");
      setNewActive(true);
      setNewBots([]);
      setNewUtmRules([]);
      setError(null);
    }
  }, [open, companies]);

  const botOptions = useMemo(
    () => bots.map((bot) => ({ value: bot.bot_key, label: bot.display_name || bot.bot_key })),
    [bots]
  );

  const handleDraftChange = (index: number, patch: Partial<AdvertisingCompanyOption>) => {
    setDrafts((prev) =>
      prev.map((company, companyIndex) =>
        companyIndex === index ? { ...company, ...patch } : company
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
        platform: newPlatform.trim() || null,
        is_active: newActive,
        bot_keys: newBots,
        utm_rules: newUtmRules,
      },
    ]);
    setNewName("");
    setNewPlatform("");
    setNewActive(true);
    setNewBots([]);
    setNewUtmRules([]);
  };

  const confirmDelete = async () => {
    if (!deleteTarget) return;
    if (!deleteTarget.company_id) {
      setDrafts((prev) => prev.filter((c) => c !== deleteTarget));
      setDeleteTarget(null);
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await onDelete(deleteTarget.company_id);
    } catch (err: any) {
      setError(err?.response?.data?.detail || err?.message || "Не удалось удалить РК");
    } finally {
      setSaving(false);
      setDeleteTarget(null);
    }
  };

  const handleSave = async (closeAfter = true) => {
    setSaving(true);
    setError(null);
    try {
      await onSave(drafts);
      if (closeAfter) onClose();
    } catch (err: any) {
      setError(err?.response?.data?.detail || err?.message || "Не удалось сохранить РК");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog
      open={open}
      onClose={onClose}
      maxWidth="md"
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
      <DialogTitle>Управление рекламными компаниями</DialogTitle>
      <DialogContent dividers>
        <Stack spacing={2}>
          {error && <Alert severity="error">{error}</Alert>}
          <Stack direction={{ xs: "column", md: "row" }} spacing={2} alignItems="center" flexWrap="wrap">
            <TextField
              label="Название РК"
              value={newName}
              onChange={(event) => setNewName(event.target.value)}
              size="small"
              sx={{ minWidth: 180 }}
            />
            <TextField
              label="Источник (TGads, VK…)"
              value={newPlatform}
              onChange={(event) => setNewPlatform(event.target.value)}
              size="small"
              sx={{ minWidth: 160 }}
              placeholder="например: TGads"
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
          <UtmRulesEditor rules={newUtmRules} botOptions={botOptions} onChange={setNewUtmRules} />
          <Divider />
          <Stack spacing={2}>
            {drafts.map((company, index) => (
              <React.Fragment key={company.company_id || `${company.company_name}-${index}`}>
                <Stack
                  direction={{ xs: "column", md: "row" }}
                  spacing={2}
                  alignItems="center"
                >
                  <TextField
                    label="Название"
                    value={company.company_name}
                    onChange={(event) =>
                      handleDraftChange(index, { company_name: event.target.value })
                    }
                    size="small"
                    sx={{ minWidth: 180 }}
                  />
                  <TextField
                    label="Источник"
                    value={company.platform || ""}
                    onChange={(event) =>
                      handleDraftChange(index, { platform: event.target.value || null })
                    }
                    size="small"
                    sx={{ minWidth: 140 }}
                    placeholder="TGads, VK…"
                  />
                  <Autocomplete
                    multiple
                    options={botOptions}
                    value={botOptions.filter((bot) => company.bot_keys.includes(bot.value))}
                    onChange={(_event, value) =>
                      handleDraftChange(index, {
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
                          handleDraftChange(index, { is_active: event.target.checked })
                        }
                      />
                    }
                    label="Показывать"
                  />
                  <IconButton
                    onClick={() => setDeleteTarget(company)}
                    size="small"
                    aria-label="Удалить"
                  >
                    <DeleteIcon fontSize="small" />
                  </IconButton>
                  {!company.company_id && (
                    <Typography variant="caption" color="text.secondary">
                      новая
                    </Typography>
                  )}
                </Stack>
                <UtmRulesEditor
                  rules={company.utm_rules || []}
                  botOptions={botOptions}
                  onChange={(rules) => handleDraftChange(index, { utm_rules: rules })}
                  onSaveAll={() => handleSave(false)}
                  saveDisabled={saving}
                />
              </React.Fragment>
            ))}
          </Stack>
        </Stack>
      </DialogContent>
      <DialogActions
        sx={{
          position: "sticky",
          bottom: 0,
          zIndex: 2,
          borderTop: "1px solid var(--app-table-divider)",
          background: "var(--app-panel-bg)",
        }}
      >
        <Button onClick={onClose} disabled={saving}>
          Отмена
        </Button>
        <Button onClick={handleSave} variant="contained" disabled={saving}>
          Сохранить
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
        <DialogTitle>Удалить РК?</DialogTitle>
        <DialogContent dividers>
          <DialogContentText>
            РК будет удалена. Это действие необратимо.
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

export default AdvertisingCompaniesDialog;
