// Древовидная таблица воронки (Platform → Company → Bot) с раскрытием/скрытием уровней.
import React, { useState } from "react";
import Paper from "@mui/material/Paper";
import Typography from "@mui/material/Typography";
import LinearProgress from "@mui/material/LinearProgress";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableContainer from "@mui/material/TableContainer";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import IconButton from "@mui/material/IconButton";
import Stack from "@mui/material/Stack";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import KeyboardArrowDownIcon from "@mui/icons-material/KeyboardArrowDown";
import KeyboardArrowRightIcon from "@mui/icons-material/KeyboardArrowRight";
import { FunnelTreeSource } from "../hooks/useFunnelTree";
import SyncedTableScroll from "./SyncedTableScroll";
import ExportButtons from "./ExportButtons";
import MiniSparkline from "./ui/MiniSparkline";
import EmptyState from "./ui/EmptyState";
import TableSkeleton from "./ui/TableSkeleton";

interface FunnelTreeTableProps {
  tree: FunnelTreeSource[];
  loading: boolean;
  error?: string | null;
  botNameResolver?: (botKey: string) => string;
}

const numberCellSx = { whiteSpace: "nowrap" };

const metricColumns = [
  { key: "entered", label: "Вход" },
  { key: "lead", label: "Альманах" },
  { key: "platform", label: "Платформа" },
  { key: "learning", label: "Обучение" },
  { key: "course", label: "Курс" },
  { key: "interview", label: "Собес" },
  { key: "passed", label: "Прошел" },
  { key: "offer", label: "Оффер" },
  { key: "contract", label: "Контракт" },
  { key: "distance", label: "Дистанция" },
] as const;

const trendValues = (node: any) => [
  node.entered ?? 0,
  node.lead ?? 0,
  node.platform ?? 0,
  node.learning ?? 0,
  node.course ?? 0,
  node.contract ?? 0,
];

const FunnelTreeTable: React.FC<FunnelTreeTableProps> = ({ tree, loading, error, botNameResolver }) => {
  const [expandedSources, setExpandedSources] = React.useState<Set<string>>(new Set());
  const [expandedCompanies, setExpandedCompanies] = React.useState<Set<string>>(new Set());

  React.useEffect(() => {
    setExpandedSources(new Set(tree.map((source) => source.source)));
  }, [tree]);

  const getExportData = (): (string | number)[][] => {
    const headers = ["Источник / РК / Бот", ...metricColumns.map((c) => c.label)];
    const rows: (string | number)[][] = [headers];
    tree.forEach((src) => {
      rows.push([src.source, ...metricColumns.map((c) => (src as any)[c.key] ?? 0)]);
      src.companies.forEach((comp) => {
        rows.push([`  ${comp.company}`, ...metricColumns.map((c) => (comp as any)[c.key] ?? 0)]);
        comp.bots.forEach((bot) => {
          const botLabel = botNameResolver ? botNameResolver(bot.bot) : bot.bot;
          rows.push([`    ${botLabel}`, ...metricColumns.map((c) => (bot as any)[c.key] ?? 0)]);
        });
      });
    });
    return rows;
  };

  const toggleSource = (source: string) => {
    setExpandedSources((prev) => {
      const next = new Set(prev);
      if (next.has(source)) next.delete(source);
      else next.add(source);
      return next;
    });
  };

  const toggleCompany = (source: string, company: string) => {
    const key = `${source}::${company}`;
    setExpandedCompanies((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  return (
    <Paper sx={{ mt: 2, p: 2, borderRadius: "24px", border: "1px solid var(--app-shell-border)", background: "var(--app-panel-bg)", boxShadow: "var(--app-shell-shadow)" }}>
      <Stack direction="row" justifyContent="space-between" alignItems="center" mb={1}>
        <Box>
          <Typography variant="h6">Детализация источников</Typography>
          <Typography variant="body2" color="text.secondary">
            Источник → рекламная кампания → бот
          </Typography>
        </Box>
        <Stack direction="row" spacing={1} alignItems="center">
          <Chip label={`Источников: ${tree.length}`} size="small" variant="outlined" />
          <ExportButtons getData={getExportData} baseName="funnel_sources" sheetName="Sources" disabled={!tree.length} />
        </Stack>
      </Stack>
      {loading && <LinearProgress sx={{ mb: 1 }} />}
      {loading && !tree.length && <TableSkeleton columns={8} rows={6} />}
      {error && (
        <Typography color="error" variant="body2" mb={1}>
          {error}
        </Typography>
      )}
      <SyncedTableScroll maxHeight="calc(100vh - 320px)" topOffset={0}>
      <TableContainer>
        <Table size="small" stickyHeader sx={{
          "& .MuiTableCell-root": { borderBottom: "1px solid var(--app-table-divider)", py: 1.05, fontSize: "0.78rem" },
          "& .MuiTableHead-root .MuiTableCell-root": { backgroundColor: "var(--app-table-head-bg)", color: "var(--c-ink2)", fontWeight: 700 },
          "& .MuiTableBody-root .MuiTableRow-root:nth-of-type(even)": { backgroundColor: "var(--app-table-row-alt)" },
          "& .MuiTableBody-root .MuiTableRow-root:hover": { backgroundColor: "var(--app-table-row-hover)" },
        }}>
          <TableHead>
            <TableRow>
              <TableCell>Источник / РК / Бот</TableCell>
              {metricColumns.map((column) => (
                <TableCell key={column.key} align="right" sx={numberCellSx}>
                  {column.label}
                </TableCell>
              ))}
            </TableRow>
          </TableHead>
          <TableBody>
            {tree.map((source) => {
              const sourceOpen = expandedSources.has(source.source);
              return (
                <React.Fragment key={source.source}>
                  <TableRow hover sx={{ backgroundColor: "var(--app-table-month-bg)" }}>
                    <TableCell sx={{ fontWeight: 700 }}>
                      <Stack direction="row" spacing={1} alignItems="center">
                        <IconButton size="small" onClick={() => toggleSource(source.source)}>
                          {sourceOpen ? <KeyboardArrowDownIcon fontSize="small" /> : <KeyboardArrowRightIcon fontSize="small" />}
                        </IconButton>
                        <span>{source.source || "нет метки"}</span>
                        <MiniSparkline values={trendValues(source)} color="var(--c-blue)" fill="color-mix(in srgb, var(--c-blue) 12%, transparent)" />
                      </Stack>
                    </TableCell>
                    {metricColumns.map((column) => (
                      <TableCell key={column.key} align="right" sx={{ ...numberCellSx, fontWeight: 700 }}>
                        {source[column.key].toLocaleString()}
                      </TableCell>
                    ))}
                  </TableRow>
                  {sourceOpen &&
                    source.companies.map((company) => {
                      const companyKey = `${source.source}::${company.company}`;
                      const companyOpen = expandedCompanies.has(companyKey);
                      return (
                        <React.Fragment key={companyKey}>
                          <TableRow hover sx={{ backgroundColor: "var(--app-table-week-bg)" }}>
                            <TableCell sx={{ pl: 4, fontWeight: 600 }}>
                              <Stack direction="row" spacing={1} alignItems="center">
                                <IconButton size="small" onClick={() => toggleCompany(source.source, company.company)}>
                                  {companyOpen ? <KeyboardArrowDownIcon fontSize="small" /> : <KeyboardArrowRightIcon fontSize="small" />}
                                </IconButton>
                                <span>{company.company || "нет метки"}</span>
                                <MiniSparkline values={trendValues(company)} color="var(--c-green)" fill="color-mix(in srgb, var(--c-green) 12%, transparent)" />
                              </Stack>
                            </TableCell>
                            {metricColumns.map((column) => (
                              <TableCell key={column.key} align="right" sx={{ ...numberCellSx, fontWeight: 600 }}>
                                {company[column.key].toLocaleString()}
                              </TableCell>
                            ))}
                          </TableRow>
                          {companyOpen &&
                            company.bots.map((bot) => (
                              <TableRow key={companyKey + bot.bot} hover>
                                <TableCell sx={{ pl: 8 }}>
                                  <Stack direction="row" spacing={1} alignItems="center">
                                    <span>{(botNameResolver ? botNameResolver(bot.bot) : bot.bot) || "нет метки"}</span>
                                    <MiniSparkline values={trendValues(bot)} color="var(--c-amber)" fill="color-mix(in srgb, var(--c-amber) 12%, transparent)" />
                                  </Stack>
                                </TableCell>
                                {metricColumns.map((column) => (
                                  <TableCell key={column.key} align="right" sx={numberCellSx}>
                                    {bot[column.key].toLocaleString()}
                                  </TableCell>
                                ))}
                              </TableRow>
                            ))}
                        </React.Fragment>
                      );
                    })}
                </React.Fragment>
              );
            })}
            {!tree.length && !loading && (
              <TableRow>
                <TableCell colSpan={metricColumns.length + 1} sx={{ py: 0 }}>
                  <EmptyState compact title="Дерево источников пусто" description="Нет строк под текущий период. Когда данные появятся, здесь раскроется структура источник → РК → бот." />
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </TableContainer>
      </SyncedTableScroll>
    </Paper>
  );
};

export default FunnelTreeTable;
