// Визуализация воронки: горизонтальные бары entered→almanah→platform→learning→course→interview→offer→contract.
// Показывает % конверсии между соседними этапами.
import React, { useMemo } from "react";
import Paper from "@mui/material/Paper";
import Typography from "@mui/material/Typography";
import Box from "@mui/material/Box";
import Stack from "@mui/material/Stack";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import FormControl from "@mui/material/FormControl";
import InputLabel from "@mui/material/InputLabel";
import Select from "@mui/material/Select";
import MenuItem from "@mui/material/MenuItem";
import Chip from "@mui/material/Chip";
import { ResponsiveContainer, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Cell } from "recharts";

interface FunnelViewProps {
  stages: Record<string, number>;
  userScope: "all" | "new" | "old";
  onUserScopeChange: (value: "all" | "new" | "old") => void;
  touchMode?: "event" | "first_touch" | "last_touch";
}

// Этапы воронки — ключи соответствуют полям из stages (или вычисленным в data useMemo)
const STAGE_ORDER: Array<{ key: string; label: string }> = [
  { key: "_total_entered", label: "Весь входной трафик (боты + прямые)" },
  { key: "_almanah_total", label: "Регистрация в Альманах" },
  { key: "platform", label: "Регистрация на платформе PokerHUB" },
  { key: "learning", label: "Начали обучение" },
  { key: "course", label: "Окончили курс полностью" },
  { key: "interview", label: "Достигли собеседования" },
  { key: "passed", label: "Прошли собеседование" },
  { key: "offer", label: "Получили оффер" },
  { key: "distance_grinding", label: "Наигрывают дистанцию" },
  { key: "contract", label: "Подписали контракт" },
];

const STAGE_COLORS = [
  "#1976d2",
  "#2e7d32",
  "#ef6c00",
  "#c62828",
  "#6a1b9a",
  "#6d4c41",
  "#546e7a",
  "#8e24aa",
  "#0277bd",
  "#00897b",
];

const APPROX_CHAR_WIDTH = 7.2;

const formatCount = (value: number) => value.toLocaleString("ru-RU");
const formatPercent = (value: number) => `${value.toFixed(1)}%`;

const FunnelView: React.FC<FunnelViewProps> = ({ stages, userScope, onUserScopeChange, touchMode = "event" }) => {
  const data = useMemo(() => {
    const direct = stages.direct_source_cnt ?? 0;
    const enriched: Record<string, number> = {
      ...stages,
      _total_entered: (stages.entered ?? 0) + direct,
      _almanah_total: (stages.lead ?? 0) + direct,
    };

    const total = enriched._total_entered || 0;
    let prev = 0;
    return STAGE_ORDER.map((stage, index) => {
      const count = enriched[stage.key] ?? 0;
      const percentFromPrev = index === 0 ? 100 : prev ? (count / prev) * 100 : 0;
      const percentFromEntered = total ? (count / total) * 100 : 0;
      const dropoff = index === 0 ? null : 100 - percentFromPrev;
      prev = count;
      return {
        key: stage.key,
        label: stage.label,
        users: count,
        percentFromPrev,
        percentFromEntered,
        percentDisplay: index === 0 ? percentFromEntered : percentFromPrev,
        dropoff,
      };
    });
  }, [stages]);

  const maxUsers = useMemo(() => Math.max(...data.map((d) => d.users), 1), [data]);

  const renderLabel = (props: any): React.ReactElement => {
    const { x, y, width, height, value, index } = props;
    if (value === undefined || value === null || !data[index]) {
      return <g />;
    }
    const row = data[index];
    const label = `${formatCount(Number(value) || 0)} · ${formatPercent(row.percentDisplay)}`;
    const labelPx = label.length * APPROX_CHAR_WIDTH;
    // Внутри бара — когда влезает с запасом; текст белый, прижат к правому краю
    if ((width ?? 0) > labelPx + 24) {
      return (
        <text
          x={(x ?? 0) + (width ?? 0) - 10}
          y={(y ?? 0) + (height ?? 0) / 2}
          dy={4}
          textAnchor="end"
          fontSize={11}
          fontWeight={600}
          fill="#ffffff"
        >
          {label}
        </text>
      );
    }
    // Снаружи бара
    return (
      <text
        x={(x ?? 0) + (width ?? 0) + 6}
        y={(y ?? 0) + (height ?? 0) / 2}
        dy={4}
        fontSize={11}
        fill="var(--c-ink2)"
      >
        {label}
      </text>
    );
  };

  // Правый отступ: достаточно под самый длинный лейбл снаружи (у мелких баров)
  const rightMargin = useMemo(() => {
    const longest = data.reduce((max, row) => {
      const label = `${formatCount(row.users)} · ${formatPercent(row.percentDisplay)}`;
      const barRatio = maxUsers ? row.users / maxUsers : 0;
      // Только строки где бар слишком мал для внутреннего текста
      if (barRatio > 0.6) return max;
      return Math.max(max, label.length * APPROX_CHAR_WIDTH + 12);
    }, 80);
    return Math.min(longest, 200);
  }, [data, maxUsers]);

  return (
    <Box>
      <Paper sx={{ mt: 2, p: 2 }}>
        <Stack
          direction={{ xs: "column", md: "row" }}
          alignItems={{ xs: "stretch", md: "center" }}
          justifyContent="space-between"
          spacing={2}
          mb={2}
        >
          <Box>
            <Typography variant="h6" mb={1}>
              Сквозная аналитика: Воронка конверсий
            </Typography>
            <Typography variant="body2" color="textSecondary">
              Воронка конверсий по этапам.
            </Typography>
            <Chip
              size="small"
              sx={{ mt: 1 }}
              label={
                touchMode === "first_touch"
                  ? "Режим: First Touch"
                  : touchMode === "last_touch"
                    ? "Режим: Last Touch"
                    : "Режим: Без атрибуции"
              }
            />
          </Box>
          <FormControl size="small" sx={{ minWidth: 220 }}>
            <InputLabel id="funnel-user-scope-label">Пользователи</InputLabel>
            <Select
              labelId="funnel-user-scope-label"
              value={userScope}
              label="Пользователи"
              onChange={(event) =>
                onUserScopeChange(String(event.target.value) as "all" | "new" | "old")
              }
            >
              <MenuItem value="all">Все</MenuItem>
              <MenuItem value="new">Новые в системе</MenuItem>
              <MenuItem value="old">Старые в системе</MenuItem>
            </Select>
          </FormControl>
        </Stack>
        <Box sx={{ width: "100%", height: STAGE_ORDER.length * 46 + 60 }}>
          <ResponsiveContainer>
            <BarChart
              layout="vertical"
              data={data}
              barCategoryGap={10}
              margin={{ left: 16, right: rightMargin, top: 4, bottom: 4 }}
            >
              <CartesianGrid strokeDasharray="3 3" horizontal={false} />
              <XAxis
                type="number"
                tickFormatter={(value) => formatCount(Number(value) || 0)}
                tick={{ fontSize: 11 }}
              />
              <YAxis type="category" dataKey="label" width={270} tick={{ fontSize: 11 }} />
              <Tooltip
                formatter={(value: any, _name, props: any) => {
                  if (props?.dataKey === "users") {
                    const row = data[props.index ?? 0];
                    const modeLabel = (props.index ?? 0) === 0 ? "от входа" : "от пред. шага";
                    return [
                      `${formatCount(Number(value) || 0)} (${formatPercent(row?.percentDisplay ?? 0)} ${modeLabel})`,
                      "Пользователей",
                    ];
                  }
                  return value;
                }}
                labelFormatter={(label: any) => label}
                contentStyle={{ fontSize: 12 }}
              />
              <Bar dataKey="users" radius={4} label={renderLabel} maxBarSize={32}>
                {data.map((entry, index) => (
                  <Cell key={entry.key} fill={STAGE_COLORS[index % STAGE_COLORS.length]} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </Box>
      </Paper>

      <Paper sx={{ mt: 2, p: 2 }}>
        <Typography variant="h6" mb={1}>
          Детали воронки конверсий
        </Typography>
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>Шаг воронки</TableCell>
              <TableCell align="right">Пользователей</TableCell>
              <TableCell align="right">% от входа</TableCell>
              <TableCell align="right">CR от пред. шага</TableCell>
              <TableCell align="right">Отток от пред. шага</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {data.map((row, index) => (
              <TableRow key={row.key} sx={{ "&:hover": { backgroundColor: "var(--app-table-row-hover)" } }}>
                <TableCell>{row.label}</TableCell>
                <TableCell align="right" sx={{ fontWeight: 600 }}>
                  {formatCount(row.users)}
                </TableCell>
                <TableCell align="right">{formatPercent(row.percentFromEntered)}</TableCell>
                <TableCell align="right">
                  {index === 0 ? "—" : formatPercent(row.percentFromPrev)}
                </TableCell>
                <TableCell align="right">
                  {index === 0 ? "—" : formatPercent(row.dropoff ?? 0)}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
        {(stages.direct_source_cnt ?? 0) > 0 && (
          <Typography variant="caption" color="textSecondary" sx={{ mt: 1, display: "block" }}>
            Прямые в Альманах (без бота): {formatCount(stages.direct_source_cnt ?? 0)} чел.
            — включены в "Весь входной трафик" и "Регистрация в Альманах".
          </Typography>
        )}
      </Paper>
    </Box>
  );
};

export default FunnelView;
