import React, { useMemo, useState, useEffect } from "react";
import axios from "axios";
import Box from "@mui/material/Box";
import Paper from "@mui/material/Paper";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableContainer from "@mui/material/TableContainer";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import Typography from "@mui/material/Typography";
import LinearProgress from "@mui/material/LinearProgress";
import IconButton from "@mui/material/IconButton";
import Collapse from "@mui/material/Collapse";
import Stack from "@mui/material/Stack";
import Select from "@mui/material/Select";
import MenuItem from "@mui/material/MenuItem";
import FormControl from "@mui/material/FormControl";
import InputLabel from "@mui/material/InputLabel";
import KeyboardArrowDownIcon from "@mui/icons-material/KeyboardArrowDown";
import KeyboardArrowUpIcon from "@mui/icons-material/KeyboardArrowUp";
import DownloadIcon from "@mui/icons-material/Download";
import { format, parseISO } from "date-fns";

import { TouchFunnelRow } from "../hooks/useTouchFunnelSummary";

interface TouchFunnelTableProps {
  title: string;
  rows: TouchFunnelRow[];
  loading: boolean;
  botLabel: string;
  mode: "first" | "last";
  onModeChange: (mode: "first" | "last") => void;
}

interface ColumnDef {
  key: string;
  label: string;
  type: "count" | "cr" | "percent" | "money";
  stageIndex: number;
}

const STAGES = [
  { key: "entered", label: "Вход" },
  { key: "interview", label: "Собеседование" },
  { key: "passed", label: "Прошел собес" },
  { key: "offer", label: "Оффер" },
  { key: "distance_grinding", label: "Наигрывают дистанцию" },
  { key: "contract", label: "Контракт" },
];

const STAGE_KEYS = STAGES.map((stage) => stage.key);
const CONVERSION_SUFFIX = "_cr";

const percentColor = (percent: number) => {
  if (percent >= 50) return "#2e7d32";
  if (percent >= 10) return "#ed6c02";
  return "#d32f2f";
};

const formatPercentValue = (percent: number | null) => {
  if (percent === null || !Number.isFinite(percent)) {
    return "—";
  }
  return `${percent.toFixed(2)}%`;
};

const calculateMedian = (values: number[]) => {
  if (!values.length) {
    return 0;
  }
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  if (sorted.length % 2 === 1) {
    return sorted[mid];
  }
  return (sorted[mid - 1] + sorted[mid]) / 2;
};

const formatAggregateValue = (value: number) => {
  if (!Number.isFinite(value)) {
    return "—";
  }
  return Number.isInteger(value) ? value : value.toFixed(1);
};

const formatMoneyValue = (value: number | null) => {
  if (value === null || !Number.isFinite(value)) {
    return "—";
  }
  return `$${value.toFixed(2)}`;
};

interface WeeklyCacheRow {
  week_start: string;
  week_end: string;
  values: Record<string, number>;
}

const API_BASE = import.meta.env.VITE_API_BASE || "";

const formatMonthLabel = (value: string) => {
  const [year, month] = value.split("-");
  if (!year || !month) return value;
  const monthIndex = Number(month) - 1;
  const monthNames = [
    "январь",
    "февраль",
    "март",
    "апрель",
    "май",
    "июнь",
    "июль",
    "август",
    "сентябрь",
    "октябрь",
    "ноябрь",
    "декабрь",
  ];
  return `${monthNames[monthIndex] || month} ${year}`;
};

const METRIC_COLUMNS: ColumnDef[] = [
  { key: "impressions", label: "Показы", type: "count", stageIndex: -1 },
  { key: "clicks", label: "Клики", type: "count", stageIndex: -1 },
  { key: "ctr", label: "CTR", type: "percent", stageIndex: -1 },
  { key: "subscribed", label: "Подписчик", type: "count", stageIndex: -1 },
  { key: "cr_subscribed", label: "CR Подписчик", type: "percent", stageIndex: -1 },
  { key: "cpm", label: "CPM", type: "money", stageIndex: -1 },
  { key: "cpc", label: "CPC", type: "money", stageIndex: -1 },
  { key: "cpf", label: "CPF", type: "money", stageIndex: -1 },
  { key: "cpl", label: "CPL", type: "money", stageIndex: -1 },
  { key: "cpa", label: "CPA", type: "money", stageIndex: -1 },
  { key: "contract_cost", label: "Цена контракта", type: "money", stageIndex: -1 },
  { key: "spend", label: "Spend", type: "money", stageIndex: -1 },
  { key: "budget", label: "Budget", type: "money", stageIndex: -1 },
  { key: "done_percent", label: "% Done", type: "percent", stageIndex: -1 },
];

const getSpendBase = (source: Record<string, number>) => {
  const spend = source.spend ?? 0;
  const budget = source.budget ?? 0;
  return spend > 0 ? spend : budget;
};

const getMetricValue = (source: Record<string, number>, key: string): number | null => {
  const impressions = source.impressions ?? 0;
  const clicks = source.clicks ?? 0;
  const subscribed = source.subscribed ?? 0;
  const spendBase = getSpendBase(source);
  switch (key) {
    case "ctr":
      return impressions ? (clicks / impressions) * 100 : null;
    case "cr_subscribed":
      return clicks ? (subscribed / clicks) * 100 : null;
    case "cpm":
      return impressions ? (spendBase / impressions) * 1000 : null;
    case "cpc":
      return clicks ? spendBase / clicks : null;
    case "cpf":
      return subscribed ? spendBase / subscribed : null;
    case "cpl":
      return source.lead ? spendBase / source.lead : null;
    case "cpa":
      return source.platform ? spendBase / source.platform : null;
    case "contract_cost":
      return source.contract ? spendBase / source.contract : null;
    case "done_percent":
      return source.budget ? (source.spend ?? 0) / source.budget * 100 : null;
    default:
      return null;
  }
};

const WeeklyStats: React.FC<{ groupKey: string; mode: "first" | "last" }> = ({ groupKey, mode }) => {
  const [monthlyRows, setMonthlyRows] = useState<Record<string, WeeklyCacheRow[]>>({});
  const [monthOptions, setMonthOptions] = useState<string[]>([]);
  const [selectedMonth, setSelectedMonth] = useState<string | null>(null);
  const [loadingWeekly, setLoadingWeekly] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!groupKey) {
      setMonthlyRows({});
      setMonthOptions([]);
      setSelectedMonth(null);
      return;
    }
    let cancelled = false;
    const fetchWeekly = async () => {
      setLoadingWeekly(true);
      setError(null);
      try {
        const params = new URLSearchParams();
        params.append("group_key", groupKey);
        params.append("mode", mode);
        const response = await axios.get(`${API_BASE}/api/reports/touch/weekly`, { params });
        if (cancelled) {
          return;
        }
        const months = response.data?.months || [];
        const data = response.data?.data || {};
        setMonthlyRows(data);
        setMonthOptions(months);
      } catch (err) {
        if (!cancelled) {
          setMonthlyRows({});
          setMonthOptions([]);
          setError("Не удалось загрузить недельные данные");
        }
      } finally {
        if (!cancelled) {
          setLoadingWeekly(false);
        }
      }
    };
    fetchWeekly();
    return () => {
      cancelled = true;
    };
  }, [groupKey, mode]);

  useEffect(() => {
    if (!monthOptions.length) {
      setSelectedMonth(null);
      return;
    }
    if (!selectedMonth || !monthOptions.includes(selectedMonth)) {
      setSelectedMonth(monthOptions[monthOptions.length - 1]);
    }
  }, [monthOptions, selectedMonth]);

  const weeklyRows = useMemo(() => {
    if (!selectedMonth) {
      return [];
    }
    const rows = monthlyRows[selectedMonth];
    if (!rows?.length) {
      return [];
    }
    return rows
      .map((row) => ({
        weekStart: parseISO(row.week_start),
        weekEnd: parseISO(row.week_end),
        values: row.values || {},
      }))
      .sort((a, b) => a.weekStart.getTime() - b.weekStart.getTime());
  }, [monthlyRows, selectedMonth]);

  const handleMonthChange = (event: any) => {
    setSelectedMonth(event.target.value as string);
  };

  return (
    <Box sx={{ p: 2 }}>
      <Typography variant="subtitle2" gutterBottom>
        Понедельная статистика
      </Typography>
      <Stack direction="row" spacing={2} alignItems="center" sx={{ mb: 2 }}>
        <FormControl size="small" sx={{ minWidth: 200 }}>
          <InputLabel id={`touch-weekly-month-${groupKey}`}>Месяц</InputLabel>
          <Select
            labelId={`touch-weekly-month-${groupKey}`}
            value={selectedMonth || ""}
            label="Месяц"
            onChange={handleMonthChange}
            disabled={!monthOptions.length}
          >
            {monthOptions.map((month) => (
              <MenuItem key={month} value={month}>
                {formatMonthLabel(month)}
              </MenuItem>
            ))}
          </Select>
        </FormControl>
      </Stack>
      {loadingWeekly && <LinearProgress sx={{ mb: 2 }} />}
      {error && (
        <Typography variant="caption" color="error" sx={{ display: "block", mb: 2 }}>
          {error}
        </Typography>
      )}
      <Table size="small">
        <TableHead>
          <TableRow>
            <TableCell>Дата</TableCell>
            <TableCell>Вход</TableCell>
            <TableCell>Собеседование</TableCell>
            <TableCell>Прошел собес</TableCell>
            <TableCell>Оффер</TableCell>
            <TableCell>Наигрывают дистанцию</TableCell>
            <TableCell>Контракт</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {weeklyRows.map((row) => (
            <TableRow key={row.weekStart.toISOString()}>
              <TableCell>
                {format(row.weekStart, "dd.MM")} - {format(row.weekEnd, "dd.MM")}
              </TableCell>
              <TableCell>{row.values.entered ?? 0}</TableCell>
              <TableCell>{row.values.interview ?? 0}</TableCell>
              <TableCell>{row.values.passed ?? 0}</TableCell>
              <TableCell>{row.values.offer ?? 0}</TableCell>
              <TableCell>{row.values.distance_grinding ?? 0}</TableCell>
              <TableCell>{row.values.contract ?? 0}</TableCell>
            </TableRow>
          ))}
          {!weeklyRows.length && !loadingWeekly && (
            <TableRow>
              <TableCell colSpan={7}>Нет данных</TableCell>
            </TableRow>
          )}
        </TableBody>
      </Table>
    </Box>
  );
};

const TouchFunnelTable: React.FC<TouchFunnelTableProps> = ({
  title,
  rows,
  loading,
  botLabel,
  mode,
  onModeChange,
}) => {
  const [sortKey, setSortKey] = useState<string>("entered");
  const [sortDirection, setSortDirection] = useState<"asc" | "desc">("desc");
  const [expandedRows, setExpandedRows] = useState<string[]>([]);

  const columns = useMemo<ColumnDef[]>(() => {
    const result: ColumnDef[] = [];
    STAGES.forEach((stage, index) => {
      result.push({
        key: stage.key,
        label: stage.label,
        type: "count",
        stageIndex: index,
      });
      if (index > 0) {
        result.push({
          key: `${stage.key}${CONVERSION_SUFFIX}`,
          label: `CR ${stage.label}`,
          type: "cr",
          stageIndex: index,
        });
      }
    });
    return [...result, ...METRIC_COLUMNS];
  }, []);

  const columnByKey = useMemo(
    () =>
      columns.reduce((acc, column) => {
        acc[column.key] = column;
        return acc;
      }, {} as Record<string, ColumnDef>),
    [columns]
  );

  const getCountValue = (source: Record<string, number>, stageKey: string) =>
    source[stageKey] ?? 0;

  const getConversionValue = (source: Record<string, number>, stageIndex: number) => {
    if (stageIndex <= 0) {
      return null;
    }
    const currentKey = STAGES[stageIndex].key;
    const prevKey = STAGES[stageIndex - 1].key;
    const current = getCountValue(source, currentKey);
    const previous = getCountValue(source, prevKey);
    if (!previous) {
      return null;
    }
    return (current / previous) * 100;
  };

  const sortedRows = useMemo(() => {
    if (sortKey === "bot") {
      return [...rows].sort((a, b) => {
        const nameA = (a.bot || "").toLowerCase();
        const nameB = (b.bot || "").toLowerCase();
        return sortDirection === "asc" ? nameA.localeCompare(nameB) : nameB.localeCompare(nameA);
      });
    }
    const column = columnByKey[sortKey];
    return [...rows].sort((a, b) => {
      const valuesA = a as Record<string, number>;
      const valuesB = b as Record<string, number>;
      const fallbackA = valuesA[sortKey] ?? 0;
      const fallbackB = valuesB[sortKey] ?? 0;
      const valueA =
        column?.type === "cr"
          ? getConversionValue(valuesA, column.stageIndex) ?? -1
          : column?.type === "percent" || column?.type === "money"
            ? getMetricValue(valuesA, sortKey) ?? fallbackA
            : fallbackA;
      const valueB =
        column?.type === "cr"
          ? getConversionValue(valuesB, column.stageIndex) ?? -1
          : column?.type === "percent" || column?.type === "money"
            ? getMetricValue(valuesB, sortKey) ?? fallbackB
            : fallbackB;
      return sortDirection === "asc" ? valueA - valueB : valueB - valueA;
    });
  }, [rows, sortKey, sortDirection, columnByKey]);

  const aggregateRows = useMemo(() => {
    const baseKeys = [...STAGE_KEYS, "impressions", "clicks", "subscribed", "spend", "budget"];
    const valuesByKey: Record<string, number[]> = baseKeys.reduce((acc, key) => {
      acc[key] = rows.map((row) => (row as any)[key] ?? 0);
      return acc;
    }, {} as Record<string, number[]>);

    const buildRow = (label: string, calculator: (values: number[]) => number) => {
      const aggregated: Record<string, number> = {};
      baseKeys.forEach((key) => {
        aggregated[key] = calculator(valuesByKey[key]);
      });
      return { label, values: aggregated };
    };

    const totalRow = buildRow("Всего", (values) => values.reduce((sum, value) => sum + value, 0));
    const averageRow = buildRow("Средняя", (values) =>
      values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : 0
    );
    const medianRow = buildRow("Медиана", (values) => calculateMedian(values));
    return [totalRow, averageRow, medianRow];
  }, [rows]);

  const handleSort = (key: string) => {
    if (sortKey === key) {
      setSortDirection((prev) => (prev === "asc" ? "desc" : "asc"));
      return;
    }
    setSortKey(key);
    setSortDirection("desc");
  };

  const handleExportSummary = () => {
    const escapeValue = (value: string) => {
      if (value.includes('"') || value.includes(",") || value.includes("\n")) {
        return `"${value.replace(/"/g, '""')}"`;
      }
      return value;
    };
    const header = [botLabel, ...columns.map((column) => column.label)];
    const rowsCsv: string[][] = [
      header,
      ...sortedRows.map((row) => [
        row.bot || "нет метки",
        ...columns.map((column) => {
          if (column.type === "cr") {
            const percent = getConversionValue(row as Record<string, number>, column.stageIndex);
            return formatPercentValue(percent);
          }
          const value = (row as any)[column.key] ?? getMetricValue(row as any, column.key);
          if (column.type === "percent") {
            return formatPercentValue(value);
          }
          if (column.type === "money") {
            return formatMoneyValue(value);
          }
          return String(value ?? 0);
        }),
      ]),
    ];
    const csv = rowsCsv.map((row) => row.map((cell) => escapeValue(cell)).join(",")).join("\n");
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `${title.replace(/\s+/g, "_")}.csv`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  };

  const toggleExpand = (key: string) => {
    setExpandedRows((prev) =>
      prev.includes(key) ? prev.filter((item) => item !== key) : [...prev, key]
    );
  };

  return (
    <TableContainer component={Paper} sx={{ mt: 2 }}>
      <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ p: 2, pb: 1 }}>
        <Stack direction="row" spacing={2} alignItems="center">
          <Typography variant="subtitle1">{title}</Typography>
          <Stack direction="row" spacing={1}>
            <Box
              component="button"
              onClick={() => onModeChange("first")}
              style={{
                border: "1px solid #1976d2",
                background: mode === "first" ? "#1976d2" : "transparent",
                color: mode === "first" ? "#fff" : "#1976d2",
                padding: "4px 10px",
                borderRadius: "4px 0 0 4px",
                cursor: "pointer",
              }}
            >
              FIRST TOUCH
            </Box>
            <Box
              component="button"
              onClick={() => onModeChange("last")}
              style={{
                border: "1px solid #1976d2",
                background: mode === "last" ? "#1976d2" : "transparent",
                color: mode === "last" ? "#fff" : "#1976d2",
                padding: "4px 10px",
                borderRadius: "0 4px 4px 0",
                cursor: "pointer",
                borderLeft: "none",
              }}
            >
              LAST TOUCH
            </Box>
          </Stack>
        </Stack>
        <IconButton size="small" onClick={handleExportSummary} disabled={!rows.length} title="Скачать CSV">
          <DownloadIcon fontSize="small" />
        </IconButton>
      </Stack>
      {loading && <LinearProgress />}
      <Table size="small">
        <TableHead>
          <TableRow>
            <TableCell />
            <TableCell sx={{ cursor: "pointer" }} onClick={() => handleSort("bot")}>
              {botLabel}
            </TableCell>
            {columns.map((column) => (
              <TableCell key={column.key} sx={{ cursor: "pointer" }} onClick={() => handleSort(column.key)}>
                {column.label}
              </TableCell>
            ))}
          </TableRow>
        </TableHead>
        <TableBody>
          {aggregateRows.map((summary) => (
            <TableRow
              key={`summary-${summary.label}`}
              sx={{ fontWeight: 600, backgroundColor: "rgba(0,0,0,0.03)" }}
            >
              <TableCell />
              <TableCell>{summary.label}</TableCell>
              {columns.map((column) => {
                if (column.type === "cr") {
                  const percent = getConversionValue(summary.values, column.stageIndex);
                  return (
                    <TableCell key={column.key}>
                      <Box
                        component="span"
                        sx={{
                          color: percent === null ? "text.secondary" : percentColor(percent),
                          fontWeight: 600,
                        }}
                      >
                        {formatPercentValue(percent)}
                      </Box>
                    </TableCell>
                  );
                }
                if (column.type === "percent") {
                  const percent = getMetricValue(summary.values, column.key);
                  return (
                    <TableCell key={column.key}>
                      <Box
                        component="span"
                        sx={{
                          color: percent === null ? "text.secondary" : percentColor(percent),
                          fontWeight: 600,
                        }}
                      >
                        {formatPercentValue(percent)}
                      </Box>
                    </TableCell>
                  );
                }
                if (column.type === "money") {
                  const money = summary.values[column.key] ?? getMetricValue(summary.values, column.key);
                  return <TableCell key={column.key}>{formatMoneyValue(money)}</TableCell>;
                }
                return (
                  <TableCell key={column.key}>
                    {formatAggregateValue(summary.values[column.key] ?? 0)}
                  </TableCell>
                );
              })}
            </TableRow>
          ))}
          {sortedRows.map((row) => {
            const rowKey = `${row.bot || "нет метки"}`;
            const expanded = expandedRows.includes(rowKey);
            return (
              <React.Fragment key={rowKey}>
                <TableRow>
                  <TableCell>
                    <IconButton size="small" onClick={() => toggleExpand(rowKey)}>
                      {expanded ? <KeyboardArrowUpIcon /> : <KeyboardArrowDownIcon />}
                    </IconButton>
                  </TableCell>
                  <TableCell>{row.bot || "нет метки"}</TableCell>
                  {columns.map((column) => {
                    if (column.type === "cr") {
                      const percent = getConversionValue(row as Record<string, number>, column.stageIndex);
                      return (
                        <TableCell key={column.key}>
                          <Box
                            component="span"
                            sx={{
                              color: percent === null ? "text.secondary" : percentColor(percent),
                              fontWeight: 600,
                            }}
                          >
                            {formatPercentValue(percent)}
                          </Box>
                        </TableCell>
                      );
                    }
                    if (column.type === "percent") {
                      const percent = getMetricValue(row as Record<string, number>, column.key);
                      return (
                        <TableCell key={column.key}>
                          <Box
                            component="span"
                            sx={{
                              color: percent === null ? "text.secondary" : percentColor(percent),
                              fontWeight: 600,
                            }}
                          >
                            {formatPercentValue(percent)}
                          </Box>
                        </TableCell>
                      );
                    }
                    if (column.type === "money") {
                      const money = (row as any)[column.key] ?? getMetricValue(row as any, column.key);
                      return <TableCell key={column.key}>{formatMoneyValue(money)}</TableCell>;
                    }
                    return <TableCell key={column.key}>{(row as any)[column.key] ?? 0}</TableCell>;
                  })}
                </TableRow>
                <TableRow>
                  <TableCell colSpan={columns.length + 2} sx={{ p: 0 }}>
                    <Collapse in={expanded} timeout="auto" unmountOnExit>
                      <WeeklyStats groupKey={rowKey} mode={mode} />
                    </Collapse>
                  </TableCell>
                </TableRow>
              </React.Fragment>
            );
          })}
          {!rows.length && !loading && (
            <TableRow>
              <TableCell colSpan={columns.length + 2}>Нет данных</TableCell>
            </TableRow>
          )}
        </TableBody>
      </Table>
    </TableContainer>
  );
};

export default TouchFunnelTable;
