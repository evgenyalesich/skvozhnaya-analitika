// Таблица бюджет+подписки по неделям: budget/spend/impressions/clicks/subscribed по кампании.
import React, { useMemo } from "react";
import Paper from "@mui/material/Paper";
import Typography from "@mui/material/Typography";
import LinearProgress from "@mui/material/LinearProgress";
import Table from "@mui/material/Table";
import TableHead from "@mui/material/TableHead";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableRow from "@mui/material/TableRow";
import TableContainer from "@mui/material/TableContainer";
import IconButton from "@mui/material/IconButton";
import Box from "@mui/material/Box";
import KeyboardArrowDownIcon from "@mui/icons-material/KeyboardArrowDown";
import KeyboardArrowRightIcon from "@mui/icons-material/KeyboardArrowRight";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import FormControl from "@mui/material/FormControl";
import InputLabel from "@mui/material/InputLabel";
import Select from "@mui/material/Select";
import MenuItem from "@mui/material/MenuItem";

import { BudgetWeeklyReportRow } from "../hooks/useBudgetWeeklyReport";

interface BudgetWeeklyTableProps {
  data: BudgetWeeklyReportRow[];
  loading: boolean;
}

type Aggregate = {
  budget: number;
  spend: number;
  impressions: number;
  clicks: number;
  subscribed: number;
  starts: number;
  lead: number;
  platform: number;
  learning: number;
  completed_course: number;
  interview: number;
  offer: number;
  contract: number;
};

const formatMoney = (value: number | null | undefined) => {
  if (value === null || value === undefined) return "—";
  return `$${value.toFixed(2)}`;
};

const formatPct = (value: number | null | undefined) => {
  if (value === null || value === undefined) return "—";
  return `${value.toFixed(2)}%`;
};

const calcRatio = (num: number, denom: number) => (denom > 0 ? (num / denom) * 100 : null);
const calcCost = (budget: number, denom: number) => (denom > 0 ? budget / denom : null);
const calcSpendBase = (spend: number, budget: number) => (spend > 0 ? spend : budget);
const formatMonthLabel = (month: string) => {
  if (!month || month.length !== 7) return month;
  const [year, mon] = month.split("-");
  const names = [
    "Январь",
    "Февраль",
    "Март",
    "Апрель",
    "Май",
    "Июнь",
    "Июль",
    "Август",
    "Сентябрь",
    "Октябрь",
    "Ноябрь",
    "Декабрь",
  ];
  const idx = Number(mon) - 1;
  if (idx < 0 || idx > 11) return month;
  return `${names[idx]} ${year}`;
};

const aggregateRows = (rows: BudgetWeeklyReportRow[]): Aggregate =>
  rows.reduce(
    (acc, row) => {
      acc.budget += row.budget || 0;
      acc.spend += row.spend || 0;
      acc.impressions += row.impressions || 0;
      acc.clicks += row.clicks || 0;
      acc.subscribed += row.subscribed || 0;
      acc.starts += row.starts || 0;
      acc.lead += row.lead || 0;
      acc.platform += row.platform || 0;
      acc.learning += row.learning || 0;
      acc.completed_course += row.completed_course || 0;
      acc.interview += row.interview || 0;
      acc.offer += row.offer || 0;
      acc.contract += row.contract || 0;
      return acc;
    },
    {
      budget: 0,
      spend: 0,
      impressions: 0,
      clicks: 0,
      subscribed: 0,
      starts: 0,
      lead: 0,
      platform: 0,
      learning: 0,
      completed_course: 0,
      interview: 0,
      offer: 0,
      contract: 0,
    },
  );

const BudgetWeeklyTable: React.FC<BudgetWeeklyTableProps> = ({ data, loading }) => {
  const [expandedCampaigns, setExpandedCampaigns] = React.useState<Set<string>>(new Set());
  const [expandedBots, setExpandedBots] = React.useState<Set<string>>(new Set());
  const [periodFrom, setPeriodFrom] = React.useState("");
  const [periodTo, setPeriodTo] = React.useState("");
  const [monthFilter, setMonthFilter] = React.useState("");

  const monthOptions = useMemo(() => {
    const unique = new Set(
      data
        .map((row) => (row.week_start || "").slice(0, 7))
        .filter((month) => month.length === 7),
    );
    return Array.from(unique).sort((a, b) => b.localeCompare(a));
  }, [data]);

  const filteredData = useMemo(() => {
    return data.filter((row) => {
      const week = row.week_start || "";
      if (periodFrom && week < periodFrom) return false;
      if (periodTo && week > periodTo) return false;
      if (monthFilter && !week.startsWith(monthFilter)) return false;
      return true;
    });
  }, [data, monthFilter, periodFrom, periodTo]);

  const overall = useMemo(() => aggregateRows(filteredData), [filteredData]);

  const grouped = useMemo(() => {
    type BotNode = {
      botKey: string;
      rows: BudgetWeeklyReportRow[];
      agg: Aggregate;
    };
    const campaignMap = new Map<string, Map<string, BudgetWeeklyReportRow[]>>();
    filteredData.forEach((row) => {
      const campaign = row.campaign || "нет метки";
      const botKey = row.bot_key || "Все боты РК";
      if (!campaignMap.has(campaign)) {
        campaignMap.set(campaign, new Map());
      }
      const botMap = campaignMap.get(campaign)!;
      const rows = botMap.get(botKey) || [];
      rows.push(row);
      botMap.set(botKey, rows);
    });

    return Array.from(campaignMap.entries())
      .map(([campaign, botMap]) => {
        const bots: BotNode[] = Array.from(botMap.entries()).map(([botKey, rows]) => {
          const sortedRows = [...rows].sort((a, b) => (b.week_start || "").localeCompare(a.week_start || ""));
          return {
            botKey,
            rows: sortedRows,
            agg: aggregateRows(rows),
          };
        });
        const totalAgg = aggregateRows(bots.flatMap((bot) => bot.rows));
        bots.sort((a, b) => b.agg.budget - a.agg.budget);
        return {
          campaign,
          bots,
          agg: totalAgg,
        };
      })
      .sort((a, b) => b.agg.budget - a.agg.budget);
  }, [filteredData]);

  const toggleCampaign = (campaign: string) => {
    setExpandedCampaigns((prev) => {
      const next = new Set(prev);
      if (next.has(campaign)) {
        next.delete(campaign);
      } else {
        next.add(campaign);
      }
      return next;
    });
  };

  const toggleBot = (key: string) => {
    setExpandedBots((prev) => {
      const next = new Set(prev);
      if (next.has(key)) {
        next.delete(key);
      } else {
        next.add(key);
      }
      return next;
    });
  };

  const renderMetrics = (agg: Aggregate) => {
    const spendBase = calcSpendBase(agg.spend, agg.budget);
    const ctr = calcRatio(agg.clicks, agg.impressions);
    const crSub = calcRatio(agg.subscribed, agg.clicks);
    const cpm = agg.impressions ? (spendBase / agg.impressions) * 1000 : null;
    const cpc = calcCost(spendBase, agg.clicks);
    const cpf = calcCost(spendBase, agg.subscribed);
    const crStarts = calcRatio(agg.starts, agg.subscribed);
    const cpl = calcCost(spendBase, agg.lead);
    const crLead = calcRatio(agg.lead, agg.starts);
    const crPlatform = calcRatio(agg.platform, agg.lead);
    const cpa = calcCost(spendBase, agg.platform);
    const priceLearning = calcCost(spendBase, agg.learning);
    const crLearningFromSubs = calcRatio(agg.learning, agg.subscribed);
    const crLearningFromPlatform = calcRatio(agg.learning, agg.platform);
    const crCourse = calcRatio(agg.completed_course, agg.learning);
    const cor = calcRatio(agg.interview, agg.completed_course);
    const interviewConvAfterCourse = cor;
    const priceInterview = calcCost(spendBase, agg.interview);
    const offerConv = calcRatio(agg.offer, agg.interview);
    const priceOffer = calcCost(spendBase, agg.offer);
    const contractConv = calcRatio(agg.contract, agg.offer);
    const priceContract = calcCost(spendBase, agg.contract);
    const donePct = agg.budget > 0 ? (agg.spend / agg.budget) * 100 : null;

    return {
      spendBase,
      ctr,
      crSub,
      cpm,
      cpc,
      cpf,
      crStarts,
      cpl,
      crLead,
      crPlatform,
      cpa,
      priceLearning,
      crLearningFromSubs,
      crLearningFromPlatform,
      crCourse,
      cor,
      interviewConvAfterCourse,
      priceInterview,
      offerConv,
      priceOffer,
      contractConv,
      priceContract,
      donePct,
    };
  };

  const renderRow = (agg: Aggregate) => {
    const metrics = renderMetrics(agg);
    return (
      <>
        <TableCell>{agg.impressions}</TableCell>
        <TableCell>{agg.clicks}</TableCell>
        <TableCell>{formatPct(metrics.ctr)}</TableCell>
        <TableCell>{agg.subscribed}</TableCell>
        <TableCell>{formatPct(metrics.crSub)}</TableCell>
        <TableCell>{formatMoney(metrics.cpm)}</TableCell>
        <TableCell>{formatMoney(metrics.cpc)}</TableCell>
        <TableCell>{formatMoney(metrics.cpf)}</TableCell>
        <TableCell>{formatMoney(agg.spend)}</TableCell>
        <TableCell>{formatMoney(agg.budget)}</TableCell>
        <TableCell>{formatPct(metrics.donePct)}</TableCell>
        <TableCell>{agg.starts}</TableCell>
        <TableCell>{formatPct(metrics.crStarts)}</TableCell>
        <TableCell>{formatMoney(metrics.cpl)}</TableCell>
        <TableCell>{agg.lead}</TableCell>
        <TableCell>{formatPct(metrics.crLead)}</TableCell>
        <TableCell>{agg.platform}</TableCell>
        <TableCell>{formatPct(metrics.crPlatform)}</TableCell>
        <TableCell>{formatMoney(metrics.cpa)}</TableCell>
        <TableCell>{agg.learning}</TableCell>
        <TableCell>{formatMoney(metrics.priceLearning)}</TableCell>
        <TableCell>{formatPct(metrics.crLearningFromSubs)}</TableCell>
        <TableCell>{formatPct(metrics.crLearningFromPlatform)}</TableCell>
        <TableCell>{agg.completed_course}</TableCell>
        <TableCell>{formatPct(metrics.crCourse)}</TableCell>
        <TableCell>{formatPct(metrics.cor)}</TableCell>
        <TableCell>{agg.interview}</TableCell>
        <TableCell>{formatPct(metrics.interviewConvAfterCourse)}</TableCell>
        <TableCell>{formatMoney(metrics.priceInterview)}</TableCell>
        <TableCell>{agg.offer}</TableCell>
        <TableCell>{formatPct(metrics.offerConv)}</TableCell>
        <TableCell>{formatMoney(metrics.priceOffer)}</TableCell>
        <TableCell>{agg.contract}</TableCell>
        <TableCell>{formatPct(metrics.contractConv)}</TableCell>
        <TableCell>{formatMoney(metrics.priceContract)}</TableCell>
      </>
    );
  };

  const renderRowFromRow = (row: BudgetWeeklyReportRow) => {
    const agg: Aggregate = {
      budget: row.budget || 0,
      spend: row.spend || 0,
      impressions: row.impressions || 0,
      clicks: row.clicks || 0,
      subscribed: row.subscribed || 0,
      starts: row.starts || 0,
      lead: row.lead || 0,
      platform: row.platform || 0,
      learning: row.learning || 0,
      completed_course: row.completed_course || 0,
      interview: row.interview || 0,
      offer: row.offer || 0,
      contract: row.contract || 0,
    };
    return renderRow(agg);
  };

  return (
    <Paper sx={{ mt: 2, p: 2 }}>
      <Typography variant="h6" mb={1}>
        Бюджеты по РК (дерево: РК → боты → недели)
      </Typography>
      {loading && <LinearProgress sx={{ mb: 2 }} />}
      {!grouped.length && !loading && (
        <Typography variant="body2" color="text.secondary">
          Нет бюджетов. Добавьте записи в «Бюджеты».
        </Typography>
      )}
      <Stack direction={{ xs: "column", md: "row" }} spacing={2} sx={{ mb: 2 }}>
        <TextField
          label="Период с"
          type="date"
          size="small"
          value={periodFrom}
          onChange={(event) => setPeriodFrom(event.target.value)}
          InputLabelProps={{ shrink: true }}
        />
        <TextField
          label="Период по"
          type="date"
          size="small"
          value={periodTo}
          onChange={(event) => setPeriodTo(event.target.value)}
          InputLabelProps={{ shrink: true }}
        />
        <FormControl size="small" sx={{ minWidth: 220 }}>
          <InputLabel id="budget-month-filter-label">Месяц</InputLabel>
          <Select
            labelId="budget-month-filter-label"
            label="Месяц"
            value={monthFilter}
            onChange={(event) => setMonthFilter(event.target.value)}
          >
            <MenuItem value="">
              <em>Все месяцы</em>
            </MenuItem>
            {monthOptions.map((month) => (
              <MenuItem key={month} value={month}>
                {formatMonthLabel(month)}
              </MenuItem>
            ))}
          </Select>
        </FormControl>
      </Stack>
      <TableContainer>
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>Источник</TableCell>
              <TableCell>Период</TableCell>
              <TableCell>Показы</TableCell>
              <TableCell>Клики</TableCell>
              <TableCell>CTR</TableCell>
              <TableCell>Подписчики КД</TableCell>
              <TableCell>CR</TableCell>
              <TableCell>CPM</TableCell>
              <TableCell>CPC</TableCell>
              <TableCell>CPF</TableCell>
              <TableCell>Spend</TableCell>
              <TableCell>Budget</TableCell>
              <TableCell>% Done</TableCell>
              <TableCell>Старты в бота</TableCell>
              <TableCell>CR</TableCell>
              <TableCell>CPL</TableCell>
              <TableCell>Зависли</TableCell>
              <TableCell>CR</TableCell>
              <TableCell>Регистрации на платформе</TableCell>
              <TableCell>CR</TableCell>
              <TableCell>CPA</TableCell>
              <TableCell>Количество начавших обучение</TableCell>
              <TableCell>Цена начавшего обучение</TableCell>
              <TableCell>Конверсия в начало обучения из подписчиков</TableCell>
              <TableCell>Конверсия в начало обучения из зарегистрированных</TableCell>
              <TableCell>Количество завершивших обучение</TableCell>
              <TableCell>CR</TableCell>
              <TableCell>COR</TableCell>
              <TableCell>Количество дошедших до собеседования</TableCell>
              <TableCell>Конверсия в собеседование после курса</TableCell>
              <TableCell>Цена за дошедшего до собеседования</TableCell>
              <TableCell>Количество оффер.лидов (кому дали оффер)</TableCell>
              <TableCell>Конверсия</TableCell>
              <TableCell>Цена оффер.лида</TableCell>
              <TableCell>Количество подписанных контрактов</TableCell>
              <TableCell>Конверсия</TableCell>
              <TableCell>Цена контракта</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {!!grouped.length && (
              <TableRow sx={{ backgroundColor: "rgba(0, 0, 0, 0.06)" }}>
                <TableCell>
                  <Typography fontWeight={700}>Total</Typography>
                </TableCell>
                <TableCell>Все недели</TableCell>
                {renderRow(overall)}
              </TableRow>
            )}
            {grouped.map((group) => {
              const campaignOpen = expandedCampaigns.has(group.campaign);
              return (
                <React.Fragment key={group.campaign}>
                  <TableRow sx={{ backgroundColor: "rgba(25, 118, 210, 0.06)" }}>
                    <TableCell>
                      <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
                        <IconButton size="small" onClick={() => toggleCampaign(group.campaign)}>
                          {campaignOpen ? <KeyboardArrowDownIcon /> : <KeyboardArrowRightIcon />}
                        </IconButton>
                        <Typography fontWeight={700}>{group.campaign}</Typography>
                      </Box>
                    </TableCell>
                    <TableCell>Все недели</TableCell>
                    {renderRow(group.agg)}
                  </TableRow>
                  {campaignOpen &&
                    group.bots.map((bot) => {
                      const botNodeKey = `${group.campaign}::${bot.botKey}`;
                      const botOpen = expandedBots.has(botNodeKey);
                      return (
                        <React.Fragment key={botNodeKey}>
                          <TableRow sx={{ backgroundColor: "rgba(0, 0, 0, 0.02)" }}>
                            <TableCell>
                              <Box sx={{ display: "flex", alignItems: "center", gap: 1, pl: 4 }}>
                                <IconButton size="small" onClick={() => toggleBot(botNodeKey)}>
                                  {botOpen ? <KeyboardArrowDownIcon /> : <KeyboardArrowRightIcon />}
                                </IconButton>
                                <Typography>{bot.botKey}</Typography>
                              </Box>
                            </TableCell>
                            <TableCell>Все недели</TableCell>
                            {renderRow(bot.agg)}
                          </TableRow>
                          {botOpen &&
                            bot.rows.map((row, idx) => (
                              <TableRow key={`${botNodeKey}:${row.week_start}:${idx}`}>
                                <TableCell>
                                  <Box sx={{ pl: 10, color: "text.secondary" }}>Неделя</Box>
                                </TableCell>
                                <TableCell>{row.week_start}</TableCell>
                                {renderRowFromRow(row)}
                              </TableRow>
                            ))}
                        </React.Fragment>
                      );
                    })}
                </React.Fragment>
              );
            })}
            {!grouped.length && !loading && (
              <TableRow>
                <TableCell colSpan={37}>Нет данных</TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </TableContainer>
    </Paper>
  );
};

export default BudgetWeeklyTable;
