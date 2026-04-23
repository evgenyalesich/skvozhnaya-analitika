import React, { useState } from "react";
import Box from "@mui/material/Box";
import Paper from "@mui/material/Paper";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import Typography from "@mui/material/Typography";
import LinearProgress from "@mui/material/LinearProgress";
import IconButton from "@mui/material/IconButton";
import Stack from "@mui/material/Stack";
import Tooltip from "@mui/material/Tooltip";
import KeyboardArrowDownIcon from "@mui/icons-material/KeyboardArrowDown";
import KeyboardArrowRightIcon from "@mui/icons-material/KeyboardArrowRight";
import SyncedTableScroll from "./SyncedTableScroll";
import ExportButtons from "./ExportButtons";
import { RoistatTreeSource, RoistatTreeMetrics } from "../hooks/useRoistatWeeklyTree";
import MiniSparkline from "./ui/MiniSparkline";
import EmptyState from "./ui/EmptyState";
import TableSkeleton from "./ui/TableSkeleton";

interface Props {
  tree: RoistatTreeSource[];
  loading: boolean;
  error?: string | null;
}

const pct = (num: number, den: number) =>
  den > 0 ? `${((num / den) * 100).toFixed(1)}%` : "—";

const COLS: { key: keyof RoistatTreeMetrics; label: string; tooltip?: string }[] = [
  { key: "almanah_starts", label: "Рег. Альманах", tooltip: "Лидов стартовало в боте" },
  { key: "new_in_system", label: "Новые", tooltip: "Новые в системе" },
  { key: "platform_cnt", label: "Платформа (ph)", tooltip: "Уникальные регистрации на платформе по ph_user_id" },
  { key: "started_learning", label: "Обучение", tooltip: "Начали обучение" },
  { key: "completed_course", label: "Курс", tooltip: "Прошли курс" },
  { key: "completed_mtt", label: "МТТ", tooltip: "Прошли MTT курс" },
  { key: "completed_spin", label: "SPIN", tooltip: "Прошли SPIN курс" },
  { key: "completed_cash", label: "КЕШ", tooltip: "Прошли CASH курс" },
  { key: "interview_reached", label: "Предофер", tooltip: "Предофер лид" },
  { key: "offer_received", label: "Оффер", tooltip: "Оффер лид" },
  { key: "contract_signed", label: "Контракт", tooltip: "Подписали контракт" },
  { key: "contract_mtt", label: "Конт. МТТ" },
  { key: "contract_spin", label: "Конт. SPIN" },
  { key: "contract_cash", label: "Конт. КЕШ" },
  { key: "distance_grinding", label: "Дистанция", tooltip: "Наигрыш дистанции" },
];

const cellSx = { fontSize: "0.75rem", px: 1, py: 0.5, whiteSpace: "nowrap" as const };

const trendValues = (m: RoistatTreeMetrics) => [
  m.almanah_starts,
  m.platform_cnt,
  m.started_learning,
  m.completed_course,
  m.offer_received,
  m.contract_signed,
];

const MetricCells: React.FC<{ m: RoistatTreeMetrics }> = ({ m }) => (
  <>
    {COLS.map(({ key }) => (
      <TableCell key={key} align="right" sx={cellSx}>
        {m[key]}
      </TableCell>
    ))}
  </>
);

const RoistatWeeklyTreeTable: React.FC<Props> = ({ tree, loading, error }) => {
  const [openSources, setOpenSources] = useState<Set<string>>(new Set());
  const [openCompanies, setOpenCompanies] = useState<Set<string>>(new Set());

  const toggleSource = (src: string) =>
    setOpenSources((prev) => {
      const next = new Set(prev);
      next.has(src) ? next.delete(src) : next.add(src);
      return next;
    });

  const toggleCompany = (key: string) =>
    setOpenCompanies((prev) => {
      const next = new Set(prev);
      next.has(key) ? next.delete(key) : next.add(key);
      return next;
    });

  const getExportData = (): (string | number)[][] => {
    const headers = ["Источник / Кабинет / Бот", ...COLS.map((c) => c.label)];
    const rows: (string | number)[][] = [headers];
    tree.forEach((src) => {
      rows.push([src.source, ...COLS.map((c) => src[c.key])]);
      src.companies.forEach((comp) => {
        rows.push([`  ${comp.company}`, ...COLS.map((c) => comp[c.key])]);
        comp.bots.forEach((bot) => {
          rows.push([`    ${bot.bot}`, ...COLS.map((c) => bot[c.key])]);
        });
      });
    });
    return rows;
  };

  return (
    <Paper sx={{ mt: 2, p: 2, borderRadius: "24px", border: "1px solid var(--app-shell-border)", background: "var(--app-panel-bg)", boxShadow: "var(--app-shell-shadow)" }}>
      <Stack direction="row" spacing={1} alignItems="center" mb={1}>
        <Typography variant="h6">Детализация по источникам (Roistat)</Typography>
        <Typography variant="body2" color="text.secondary">
          Источник → рекламный кабинет → бот
        </Typography>
        <ExportButtons getData={getExportData} baseName="roistat_weekly_tree" sheetName="Roistat Tree" disabled={!tree.length} />
      </Stack>
      {loading && <LinearProgress sx={{ mb: 1 }} />}
      {loading && !tree.length && <TableSkeleton columns={8} rows={6} />}
      {error && (
        <Typography color="error" variant="body2">
          {error}
        </Typography>
      )}
      {!loading && !error && tree.length === 0 && (
        <EmptyState compact title="Roistat-детализация пуста" description="Нет источников под текущий период. Как только данные появятся, здесь раскроется дерево источник → кабинет → бот." />
      )}
      {tree.length > 0 && (
        <SyncedTableScroll>
          <Table size="small" stickyHeader sx={{
            "& .MuiTableCell-root": { borderBottom: "1px solid var(--app-table-divider)", py: 1.05, fontSize: "0.78rem" },
            "& .MuiTableHead-root .MuiTableCell-root": { backgroundColor: "var(--app-table-head-bg)", color: "var(--c-ink2)", fontWeight: 700 },
            "& .MuiTableBody-root .MuiTableRow-root:nth-of-type(even)": { backgroundColor: "var(--app-table-row-alt)" },
            "& .MuiTableBody-root .MuiTableRow-root:hover": { backgroundColor: "var(--app-table-row-hover)" },
          }}>
            <TableHead>
              <TableRow>
                <TableCell sx={{ ...cellSx, minWidth: 240, fontWeight: 700 }}>
                  Источник / Кабинет / Бот
                </TableCell>
                {COLS.map(({ key, label, tooltip }) => (
                  <TableCell key={key} align="right" sx={{ ...cellSx, fontWeight: 700, minWidth: 70 }}>
                    {tooltip ? <Tooltip title={tooltip} arrow><span>{label}</span></Tooltip> : label}
                  </TableCell>
                ))}
              </TableRow>
            </TableHead>
            <TableBody>
              {tree.map((src) => {
                const srcOpen = openSources.has(src.source);
                return (
                  <React.Fragment key={src.source}>
                    {/* Source row */}
                    <TableRow sx={{ backgroundColor: "var(--app-table-month-bg)", "& td": { fontWeight: 700 } }}>
                      <TableCell sx={{ ...cellSx, minWidth: 240 }}>
                        <Stack direction="row" alignItems="center" spacing={0.5}>
                          <IconButton size="small" onClick={() => toggleSource(src.source)} sx={{ p: 0 }}>
                            {srcOpen ? <KeyboardArrowDownIcon fontSize="small" /> : <KeyboardArrowRightIcon fontSize="small" />}
                          </IconButton>
                          <span>{src.source}</span>
                          <MiniSparkline values={trendValues(src)} color="var(--c-blue)" fill="color-mix(in srgb, var(--c-blue) 12%, transparent)" />
                        </Stack>
                      </TableCell>
                      <MetricCells m={src} />
                    </TableRow>
                    {srcOpen &&
                      src.companies.map((comp) => {
                        const compKey = `${src.source}::${comp.company}`;
                        const compOpen = openCompanies.has(compKey);
                        return (
                          <React.Fragment key={compKey}>
                            {/* Company row */}
                            <TableRow sx={{ backgroundColor: "var(--app-table-week-bg)", "& td": { fontWeight: 600 } }}>
                              <TableCell sx={{ ...cellSx, pl: 4 }}>
                                <Stack direction="row" alignItems="center" spacing={0.5}>
                                  <IconButton size="small" onClick={() => toggleCompany(compKey)} sx={{ p: 0 }}>
                                    {compOpen ? <KeyboardArrowDownIcon fontSize="small" /> : <KeyboardArrowRightIcon fontSize="small" />}
                                  </IconButton>
                                  <span>{comp.company}</span>
                                  <MiniSparkline values={trendValues(comp)} color="var(--c-green)" fill="color-mix(in srgb, var(--c-green) 12%, transparent)" />
                                </Stack>
                              </TableCell>
                              <MetricCells m={comp} />
                            </TableRow>
                            {compOpen &&
                              comp.bots.map((bot) => (
                                <TableRow key={bot.bot} sx={{ "&:nth-of-type(odd)": { backgroundColor: "var(--app-table-row-alt)" } }}>
                                  <TableCell sx={{ ...cellSx, pl: 7 }}>
                                    <Stack direction="row" spacing={1} alignItems="center">
                                      <span>{bot.bot}</span>
                                      <MiniSparkline values={trendValues(bot)} color="var(--c-amber)" fill="color-mix(in srgb, var(--c-amber) 12%, transparent)" />
                                    </Stack>
                                  </TableCell>
                                  <MetricCells m={bot} />
                                </TableRow>
                              ))}
                          </React.Fragment>
                        );
                      })}
                  </React.Fragment>
                );
              })}
            </TableBody>
          </Table>
        </SyncedTableScroll>
      )}
    </Paper>
  );
};

export default RoistatWeeklyTreeTable;
