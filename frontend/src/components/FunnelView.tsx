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
import { ResponsiveContainer, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Cell } from "recharts";

interface FunnelViewProps {
  stages: Record<string, number>;
  userScope: "all" | "new" | "old";
  onUserScopeChange: (value: "all" | "new" | "old") => void;
}

const STAGE_ORDER: Array<{ key: string; label: string }> = [
  { key: "entered", label: "Входные боты (регистрации)" },
  { key: "lead", label: "Конверсии в lead/pokerhub_bot" },
  { key: "platform", label: "Регистрация на платформе PokerHUB (ph_user_id)" },
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

const formatCount = (value: number) => value.toLocaleString("ru-RU");
const formatPercent = (value: number) => `${value.toFixed(1)}%`;

const FunnelView: React.FC<FunnelViewProps> = ({ stages, userScope, onUserScopeChange }) => {
  const data = useMemo(() => {
    let prev = 0;
    const entered = stages.entered || 0;
    return STAGE_ORDER.map((stage, index) => {
      const count = stages[stage.key] || 0;
      const percentFromPrev = index === 0 ? 100 : prev ? (count / prev) * 100 : 0;
      const percentFromEntered = entered ? (count / entered) * 100 : 0;
      const dropoff = index === 0 ? null : 100 - percentFromPrev;
      prev = count;
      return {
        key: stage.key,
        label: stage.label,
        users: count,
        percentFromPrev,
        percentFromEntered,
        dropoff,
      };
    });
  }, [stages]);

  const renderLabel = (props: any) => {
    const { x, y, width, height, value, index } = props;
    if (value === undefined || value === null) {
      return null;
    }
    const row = data[index];
    const label = row
      ? `${formatCount(Number(value) || 0)} · ${formatPercent(row.percentFromEntered)}`
      : String(value);
    return (
      <text
        x={(x || 0) + (width || 0) + 6}
        y={(y || 0) + (height || 0) / 2}
        dy={4}
        fontSize={11}
        fill="var(--c-ink2)"
      >
        {label}
      </text>
    );
  };

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
        <Box sx={{ width: "100%", height: 360 }}>
          <ResponsiveContainer>
            <BarChart layout="vertical" data={data} barCategoryGap={14} margin={{ left: 16, right: 88 }}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis type="number" tickFormatter={(value) => formatCount(Number(value) || 0)} />
              <YAxis type="category" dataKey="label" width={260} />
              <Tooltip
                formatter={(value: any, _name, props: any) => {
                  if (props?.dataKey === "users") {
                    return [formatCount(Number(value) || 0), "Пользователей"];
                  }
                  return value;
                }}
                labelFormatter={(label: any) => label}
                contentStyle={{ fontSize: 12 }}
              />
              <Bar dataKey="users" radius={[4, 4, 4, 4]} label={renderLabel}>
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
              <TableCell align="right">Процент от входа</TableCell>
              <TableCell align="right">CR от предыдущего</TableCell>
              <TableCell align="right">Отток от предыдущего</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {data.map((row, index) => (
              <TableRow key={row.key}>
                <TableCell>{row.label}</TableCell>
                <TableCell align="right">{formatCount(row.users)}</TableCell>
                <TableCell align="right">
                  {formatPercent(row.percentFromEntered)}
                </TableCell>
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
      </Paper>
    </Box>
  );
};

export default FunnelView;
