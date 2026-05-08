// Поиск пользователя по tg_user_id или username: показывает все записи raw_bot_users + воронку.
import React, { useMemo, useState, useCallback } from "react";
import axios from "axios";
import Paper from "@mui/material/Paper";
import Box from "@mui/material/Box";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import TextField from "@mui/material/TextField";
import Button from "@mui/material/Button";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableContainer from "@mui/material/TableContainer";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import LinearProgress from "@mui/material/LinearProgress";
import Chip from "@mui/material/Chip";
import Tooltip from "@mui/material/Tooltip";
import Divider from "@mui/material/Divider";
import SearchIcon from "@mui/icons-material/Search";
import ExportButtons from "./ExportButtons";

const API_BASE = import.meta.env.VITE_API_BASE || "";

const fmt = (v: string | null | undefined) => {
  if (!v) return "—";
  const d = new Date(v);
  if (isNaN(d.getTime())) return v;
  const p = (n: number) => String(n).padStart(2, "0");
  return `${p(d.getDate())}.${p(d.getMonth() + 1)}.${d.getFullYear()}`;
};

const bool = (v: boolean | null | undefined) => {
  if (v === true) return "✓";
  if (v === false) return "✗";
  return "—";
};

const boolChip = (v: boolean | null | undefined, label: string) => {
  if (v === true) return <Chip label={label} color="success" size="small" sx={{ fontSize: "0.7rem" }} />;
  return null;
};

const hasStage = (rows: Record<string, any>[], key: string) => rows.some((row) => Boolean(row[key]));

const uniqueNonEmpty = (values: Array<string | null | undefined>) =>
  [...new Set(values.map((value) => (value || "").trim()).filter(Boolean))];

const fmtDateTime = (v: string | null | undefined) => {
  if (!v) return "—";
  const d = new Date(v);
  if (isNaN(d.getTime())) return v;
  const p = (n: number) => String(n).padStart(2, "0");
  return `${p(d.getDate())}.${p(d.getMonth() + 1)}.${d.getFullYear()} ${p(d.getHours())}:${p(d.getMinutes())}`;
};

interface UserSearchPanelProps {
  registryBotKeys?: string[];
}

const UserSearchPanel: React.FC<UserSearchPanelProps> = ({ registryBotKeys }) => {
  const [tgUserId, setTgUserId] = useState("");
  const [rows, setRows] = useState<Record<string, any>[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [searched, setSearched] = useState(false);

  const search = useCallback(async (id: string) => {
    const trimmed = id.trim();
    if (!trimmed) return;
    setLoading(true);
    setError(null);
    setSearched(true);
    try {
      const params = new URLSearchParams();
      params.append("raw_tg_user_id", trimmed);
      params.append("limit", "500");
      params.append("sort_by", "created_at");
      params.append("sort_direction", "asc");
      // Filter to only registered bots
      if (registryBotKeys && registryBotKeys.length > 0) {
        registryBotKeys.forEach((key) => params.append("bots", key));
      }
      const res = await axios.get(`${API_BASE}/api/reports/funnel-start/raw`, { params });
      setRows(res.data.users || []);
    } catch (err: any) {
      setError(err?.response?.data?.detail || err?.message || "Ошибка запроса");
      setRows([]);
    } finally {
      setLoading(false);
    }
  }, [registryBotKeys]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") search(tgUserId);
  };

  const getExportData = () => {
    const headers = [
      "TG User ID", "Bot Key", "Дата старта", "Компания", "UTM Source", "UTM Campaign",
      "New in system", "Альманах", "Платформа", "Обучение", "Курс", "Симулятор",
      "Собеседование", "Прошёл собес", "Оффер", "Контракт", "Наигрыш дистанции",
    ];
    const lines = rows.map((r) => [
      r.tg_user_id, r.bot_key, fmt(r.created_at), r.advertising_company || "",
      r.utm_source || "", r.utm_campaign || "",
      bool(r.new_in_system), bool(r.converted_to_lead), bool(r.registered_platform),
      bool(r.started_learning), bool(r.completed_course), bool(r.used_simulator),
      bool(r.interview_reached), bool(r.interview_passed), bool(r.offer_received),
      bool(r.contract_signed), bool(r.distance_grinding),
    ]);
    return [headers, ...lines];
  };

  const groupedUsers = useMemo(() => {
    return [...new Set(rows.map((r) => r.tg_user_id))]
      .map((userId) => {
        const userRows = rows
          .filter((r) => r.tg_user_id === userId)
          .sort((a, b) => String(a.created_at || "").localeCompare(String(b.created_at || "")));
        const firstRow = userRows[0];
        const lastRow = userRows[userRows.length - 1];
        return {
          userId,
          rows: userRows,
          username: firstRow?.username || lastRow?.username || null,
          firstStartAt: userRows[0]?.created_at || null,
          lastStartAt: userRows[userRows.length - 1]?.created_at || null,
          firstSeenAtSystem: firstRow?.first_seen_at_system || null,
          firstSeenAtBot: firstRow?.first_seen_at_bot || null,
          bots: uniqueNonEmpty(userRows.map((row) => row.bot_key)),
          companies: uniqueNonEmpty(userRows.map((row) => row.advertising_company)),
          firstTouchBots: uniqueNonEmpty(userRows.map((row) => row.first_touch_bot)),
          lastTouchBots: uniqueNonEmpty(userRows.map((row) => row.last_touch_bot)),
          stages: {
            converted_to_lead: hasStage(userRows, "converted_to_lead"),
            registered_platform: hasStage(userRows, "registered_platform"),
            started_learning: hasStage(userRows, "started_learning"),
            completed_course: hasStage(userRows, "completed_course"),
            used_simulator: hasStage(userRows, "used_simulator"),
            interview_reached: hasStage(userRows, "interview_reached"),
            interview_passed: hasStage(userRows, "interview_passed"),
            offer_received: hasStage(userRows, "offer_received"),
            contract_signed: hasStage(userRows, "contract_signed"),
            distance_grinding: hasStage(userRows, "distance_grinding"),
          },
        };
      })
      .sort((a, b) => String(a.firstStartAt || "").localeCompare(String(b.firstStartAt || "")));
  }, [rows]);

  return (
    <Box>
      <Paper sx={{ p: 2, mb: 2, borderRadius: "24px", border: "1px solid var(--app-shell-border)", background: "var(--app-panel-bg)", boxShadow: "var(--app-shell-shadow)" }}>
        <Stack direction="row" spacing={2} alignItems="center" flexWrap="wrap">
          <Typography variant="h6" sx={{ fontWeight: 700, mr: 1 }}>
            Поиск пользователя
          </Typography>
          <TextField
            size="small"
            label="TG User ID / Username"
            placeholder="ID или username, несколько значений через запятую"
            value={tgUserId}
            onChange={(e) => setTgUserId(e.target.value)}
            onKeyDown={handleKeyDown}
            sx={{ minWidth: 360 }}
          />
          <Button
            variant="contained"
            startIcon={<SearchIcon />}
            onClick={() => search(tgUserId)}
            disabled={loading || !tgUserId.trim()}
          >
            Найти
          </Button>
          {rows.length > 0 && (
            <ExportButtons
              getData={getExportData}
              baseName={`user_${tgUserId.trim()}`}
              sheetName="Users"
            />
          )}
        </Stack>
        {loading && <LinearProgress sx={{ mt: 1 }} />}
        {error && (
          <Typography color="error" variant="body2" mt={1}>
            {error}
          </Typography>
        )}
        {searched && !loading && !error && rows.length === 0 && (
          <Typography color="text.secondary" variant="body2" mt={1}>
            Пользователь не найден
          </Typography>
        )}
        <Typography variant="body2" color="text.secondary" mt={1}>
          В этой вкладке верхние фильтры не используются. Поиск идёт напрямую по сырым данным пользователя.
        </Typography>
        {groupedUsers.length > 0 && (
          <Typography variant="caption" color="text.secondary" mt={0.5} display="block">
            {groupedUsers.length === 1
              ? `TG ID: ${groupedUsers[0].userId} — ${rows.length} записей по пользователю`
              : `Найдено ${groupedUsers.length} пользователей, ${rows.length} записей`}
          </Typography>
        )}
      </Paper>

      {groupedUsers.length > 0 && (
        <Paper sx={{ borderRadius: "24px", border: "1px solid var(--app-shell-border)", background: "var(--app-panel-bg)", boxShadow: "var(--app-shell-shadow)", overflow: "hidden" }}>
          {groupedUsers.map((group, groupIndex) => {
            const userRows = group.rows;
            const stages = [
              { key: "converted_to_lead", label: "Альманах" },
              { key: "registered_platform", label: "Платформа" },
              { key: "started_learning", label: "Обучение" },
              { key: "completed_course", label: "Курс" },
              { key: "used_simulator", label: "Симулятор" },
              { key: "interview_reached", label: "Собес" },
              { key: "interview_passed", label: "Прошёл" },
              { key: "offer_received", label: "Оффер" },
              { key: "contract_signed", label: "Контракт" },
              { key: "distance_grinding", label: "Дистанция" },
            ];

            return (
              <Box key={group.userId} sx={{ p: 2 }}>
                <Stack direction="row" spacing={1} alignItems="center" mb={1} flexWrap="wrap">
                  <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
                    TG {group.userId}
                  </Typography>
                  {group.username && (
                    <Chip label={`@${group.username}`} size="small" variant="outlined" />
                  )}
                  {stages.map(({ key, label }) =>
                    group.stages[key as keyof typeof group.stages] ? boolChip(true, label) : null
                  )}
                </Stack>

                <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap sx={{ mb: 1.5 }}>
                  <Chip label={`Первый старт: ${fmtDateTime(group.firstStartAt)}`} size="small" variant="outlined" />
                  <Chip label={`Последний старт: ${fmtDateTime(group.lastStartAt)}`} size="small" variant="outlined" />
                  <Chip label={`Записей: ${group.rows.length}`} size="small" variant="outlined" />
                  <Chip label={`Ботов: ${group.bots.length}`} size="small" variant="outlined" />
                  {group.companies.length > 0 && (
                    <Chip label={`РК: ${group.companies.join(", ")}`} size="small" variant="outlined" />
                  )}
                </Stack>

                <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap sx={{ mb: 1.5 }}>
                  {group.bots.map((bot) => (
                    <Chip key={bot} label={bot} size="small" />
                  ))}
                </Stack>

                <TableContainer sx={{ maxHeight: 300 }}>
                  <Table size="small" stickyHeader>
                    <TableHead>
                      <TableRow>
                        <TableCell sx={{ fontWeight: 700, minWidth: 150, backgroundColor: "var(--app-table-head-bg)", color: "var(--c-ink2)" }}>База</TableCell>
                        <TableCell sx={{ fontWeight: 700, backgroundColor: "var(--app-table-head-bg)", color: "var(--c-ink2)" }}>Компания</TableCell>
                        <TableCell sx={{ fontWeight: 700, backgroundColor: "var(--app-table-head-bg)", color: "var(--c-ink2)" }}>UTM Source</TableCell>
                        <TableCell sx={{ fontWeight: 700, backgroundColor: "var(--app-table-head-bg)", color: "var(--c-ink2)" }}>UTM Campaign</TableCell>
                        <TableCell sx={{ fontWeight: 700, backgroundColor: "var(--app-table-head-bg)", color: "var(--c-ink2)" }}>First Touch</TableCell>
                        <TableCell sx={{ fontWeight: 700, backgroundColor: "var(--app-table-head-bg)", color: "var(--c-ink2)" }}>Last Touch</TableCell>
                        <TableCell sx={{ fontWeight: 700, minWidth: 100, backgroundColor: "var(--app-table-head-bg)", color: "var(--c-ink2)" }}>Старт</TableCell>
                        <TableCell sx={{ fontWeight: 700, backgroundColor: "var(--app-table-head-bg)", color: "var(--c-ink2)" }}>Новый</TableCell>
                        <TableCell sx={{ fontWeight: 700, minWidth: 100, backgroundColor: "var(--app-table-head-bg)", color: "var(--c-ink2)" }}>Нач. обуч.</TableCell>
                        <TableCell sx={{ fontWeight: 700, backgroundColor: "var(--app-table-head-bg)", color: "var(--c-ink2)" }}>Курс</TableCell>
                        <TableCell sx={{ fontWeight: 700, minWidth: 100, backgroundColor: "var(--app-table-head-bg)", color: "var(--c-ink2)" }}>Оконч. курса</TableCell>
                        {stages.map(({ key, label }) => (
                          <TableCell key={key} sx={{ fontWeight: 700, minWidth: 70, backgroundColor: "var(--app-table-head-bg)", color: "var(--c-ink2)" }} align="center">
                            {label}
                          </TableCell>
                        ))}
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {userRows.map((row, i) => (
                        <TableRow
                          key={i}
                          sx={{ "&:nth-of-type(odd)": { backgroundColor: "var(--app-table-row-alt)" } }}
                        >
                          <TableCell>
                            <Tooltip title={row.bot_key} arrow>
                              <span>{row.bot_key}</span>
                            </Tooltip>
                          </TableCell>
                          <TableCell>{row.advertising_company || "—"}</TableCell>
                          <TableCell>{row.utm_source || "—"}</TableCell>
                          <TableCell sx={{ maxWidth: 160, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                            <Tooltip title={row.utm_campaign || ""} arrow>
                              <span>{row.utm_campaign || "—"}</span>
                            </Tooltip>
                          </TableCell>
                          <TableCell>{row.first_touch_bot || "—"}</TableCell>
                          <TableCell>{row.last_touch_bot || "—"}</TableCell>
                          <TableCell>{fmt(row.created_at)}</TableCell>
                          <TableCell align="center">
                            {row.new_in_system ? (
                              <Chip label="Новый" color="primary" size="small" sx={{ fontSize: "0.65rem" }} />
                            ) : (
                              <Chip label="Старый" color="default" size="small" sx={{ fontSize: "0.65rem" }} />
                            )}
                          </TableCell>
                          <TableCell>{fmt(row.learn_start_date)}</TableCell>
                          <TableCell>{row.start_course || "—"}</TableCell>
                          <TableCell>{fmt(row.completed_course_at)}</TableCell>
                          {stages.map(({ key }) => (
                            <TableCell key={key} align="center" sx={{ color: row[key] ? "var(--app-chip-success)" : "var(--c-ink3)", fontWeight: row[key] ? 700 : 400 }}>
                              {row[key] ? "✓" : "—"}
                            </TableCell>
                          ))}
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </TableContainer>
                {groupIndex < groupedUsers.length - 1 && <Divider sx={{ mt: 2 }} />}
              </Box>
            );
          })}
        </Paper>
      )}
    </Box>
  );
};

export default UserSearchPanel;
