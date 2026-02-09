import React from "react";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableContainer from "@mui/material/TableContainer";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import Paper from "@mui/material/Paper";
import Typography from "@mui/material/Typography";
import Stack from "@mui/material/Stack";
import Chip from "@mui/material/Chip";
import TablePagination from "@mui/material/TablePagination";
import TableSortLabel from "@mui/material/TableSortLabel";
import TextField from "@mui/material/TextField";
import ToggleButton from "@mui/material/ToggleButton";
import ToggleButtonGroup from "@mui/material/ToggleButtonGroup";
import Autocomplete from "@mui/material/Autocomplete";
import Box from "@mui/material/Box";
import { RawColumnFilters } from "../hooks/useReports";
import { BotSelectOption } from "./FilterPanel";

export interface RawUsersTableProps {
  users: Array<Record<string, any>>;
  total: number;
  loading: boolean;
  page: number;
  pageSize: number;
  sortBy: string;
  sortDirection: "asc" | "desc";
  onSort: (field: string) => void;
  onPageChange: (event: unknown, page: number) => void;
  onRowsPerPageChange: (event: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => void;
  filters: RawColumnFilters;
  onFilterChange: (key: keyof RawColumnFilters, value: any) => void;
  botOptions: BotSelectOption[];
  companyOptions: string[];
  utmSourceOptions: string[];
  utmCampaignOptions: string[];
  utmMediumOptions: string[];
  utmContentOptions: string[];
  utmTermOptions: string[];
}

const sortableColumns = new Set([
  "created_at",
  "tg_user_id",
  "bot_key",
  "budget",
  "utm_source",
  "utm_campaign",
  "utm_medium",
  "utm_content",
  "utm_term",
  "advertising_company",
  "ingested_at",
]);

const formatBool = (value: boolean | null | undefined) =>
  value ? (
    <Chip
      label="✓"
      size="small"
      color="success"
      variant="filled"
      sx={{ minWidth: 28, fontWeight: 700 }}
    />
  ) : (
    <Chip
      label="✗"
      size="small"
      color="error"
      variant="filled"
      sx={{ minWidth: 28, fontWeight: 700 }}
    />
  );

const formatDate = (value: string | null | undefined) => {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  const pad = (v: number) => String(v).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(
    date.getHours()
  )}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`;
};

const renderTriState = (
  value: boolean | null,
  onChange: (next: boolean | null) => void
) => (
  <ToggleButtonGroup
    size="small"
    exclusive
    value={value === null ? "all" : value ? "yes" : "no"}
    onChange={(_e, next) => {
      if (next === "yes") onChange(true);
      else if (next === "no") onChange(false);
      else onChange(null);
    }}
  >
    <ToggleButton value="all">Все</ToggleButton>
    <ToggleButton value="yes">✓</ToggleButton>
    <ToggleButton value="no">✗</ToggleButton>
  </ToggleButtonGroup>
);

const RawUsersTable: React.FC<RawUsersTableProps> = ({
  users,
  total,
  loading,
  page,
  pageSize,
  sortBy,
  sortDirection,
  onSort,
  onPageChange,
  onRowsPerPageChange,
  filters,
  onFilterChange,
  botOptions,
  companyOptions,
  utmSourceOptions,
  utmCampaignOptions,
  utmMediumOptions,
  utmContentOptions,
  utmTermOptions,
}) => {
  const botLabelMap = React.useMemo(() => {
    const map = new Map<string, string>();
    botOptions.forEach((option) => map.set(option.value, option.label));
    return map;
  }, [botOptions]);
  const columns = [
    { key: "id", label: "ID" },
    { key: "bot_key", label: "База" },
    { key: "tg_user_id", label: "TG ID" },
    { key: "created_at", label: "Дата регистрации" },
    { key: "user_block", label: "User Block" },
    { key: "utm_source", label: "UTM Source" },
    { key: "utm_campaign", label: "UTM Campaign" },
    { key: "first_touch_bot", label: "First Touch Bot" },
    { key: "first_touch_campaign", label: "First Touch Campaign" },
    { key: "last_touch_bot", label: "Last Touch Bot" },
    { key: "last_touch_campaign", label: "Last Touch Campaign" },
    { key: "utm_medium", label: "UTM Medium" },
    { key: "utm_content", label: "UTM Content" },
    { key: "utm_term", label: "UTM Term" },
    { key: "advertising_company", label: "Компания" },
    { key: "budget", label: "Бюджет", align: "right" },
    { key: "ingested_at", label: "Загружено" },
    { key: "converted_to_lead", label: "Lead" },
    { key: "registered_platform", label: "Платформа" },
    { key: "started_learning", label: "Начал обучение" },
    { key: "completed_course", label: "Прошел курс" },
    { key: "interview_reached", label: "Дошел до собеседования" },
    { key: "interview_reached_status", label: "Статус собеседования" },
    { key: "interview_passed", label: "Прошел собеседование" },
    { key: "interview_passed_status", label: "Статус прохождения" },
    { key: "offer_received", label: "Оффер" },
    { key: "offer_received_status", label: "Статус оффера" },
    { key: "contract_signed", label: "Контракт" },
    { key: "contract_signed_status", label: "Статус контракта" },
    { key: "distance_grinding", label: "Наигрывают дистанцию" },
    { key: "channel_subscribed", label: "Канал" },
    { key: "community_member", label: "Салун" },
    { key: "community_member_status", label: "Статус салуна" },
    { key: "team_member", label: "Команда" },
    { key: "internal_status", label: "Внутренний статус" },
  ];

  return (
    <Paper sx={{ mt: 2 }}>
      <Stack direction="row" alignItems="center" justifyContent="space-between" px={2} pt={2}>
        <Typography variant="h6">RAW Users ({total.toLocaleString()})</Typography>
        {loading && (
          <Typography variant="body2" color="textSecondary">
            Загружаем...
          </Typography>
        )}
      </Stack>
      <TableContainer>
        <Table size="small">
          <TableHead>
            <TableRow
              sx={{
                position: "sticky",
                top: 0,
                backgroundColor: "#fff",
                zIndex: 2,
              }}
            >
              {columns.map((column) => (
                <TableCell
                  key={column.key}
                  align={column.align || "left"}
                  sortDirection={sortBy === column.key ? sortDirection : false}
                >
                  {sortableColumns.has(column.key) ? (
                    <TableSortLabel
                      active={sortBy === column.key}
                      direction={sortBy === column.key ? sortDirection : "asc"}
                      onClick={() => onSort(column.key)}
                    >
                      {column.label}
                    </TableSortLabel>
                  ) : (
                    column.label
                  )}
                </TableCell>
              ))}
            </TableRow>
            <TableRow>
              <TableCell />
              <TableCell>
                <Autocomplete
                  multiple
                  size="small"
                  options={botOptions}
                  value={botOptions.filter((option) => filters.botKeys.includes(option.value))}
                  onChange={(_e, value) =>
                    onFilterChange(
                      "botKeys",
                      value.map((option) => option.value)
                    )
                  }
                  getOptionLabel={(option) => option.label}
                  isOptionEqualToValue={(option, value) => option.value === value.value}
                  renderInput={(params) => <TextField {...params} placeholder="База" />}
                />
              </TableCell>
              <TableCell>
                <TextField
                  size="small"
                  placeholder="TG ID"
                  value={filters.tgUserId}
                  onChange={(event) => onFilterChange("tgUserId", event.target.value)}
                />
              </TableCell>
              <TableCell />
              <TableCell>{renderTriState(filters.userBlock, (v) => onFilterChange("userBlock", v))}</TableCell>
              <TableCell>
                <Autocomplete
                  multiple
                  size="small"
                  options={utmSourceOptions}
                  value={filters.utmSource}
                  onChange={(_e, value) => onFilterChange("utmSource", value)}
                  renderInput={(params) => <TextField {...params} placeholder="UTM Source" />}
                />
              </TableCell>
              <TableCell>
                <Autocomplete
                  multiple
                  size="small"
                  options={utmCampaignOptions}
                  value={filters.utmCampaign}
                  onChange={(_e, value) => onFilterChange("utmCampaign", value)}
                  renderInput={(params) => <TextField {...params} placeholder="UTM Campaign" />}
                />
              </TableCell>
              <TableCell>{renderTriState(filters.firstTouchPresent, (v) => onFilterChange("firstTouchPresent", v))}</TableCell>
              <TableCell />
              <TableCell>{renderTriState(filters.lastTouchPresent, (v) => onFilterChange("lastTouchPresent", v))}</TableCell>
              <TableCell />
              <TableCell>
                <Autocomplete
                  multiple
                  size="small"
                  options={utmMediumOptions}
                  value={filters.utmMedium}
                  onChange={(_e, value) => onFilterChange("utmMedium", value)}
                  renderInput={(params) => <TextField {...params} placeholder="UTM Medium" />}
                />
              </TableCell>
              <TableCell>
                <Autocomplete
                  multiple
                  size="small"
                  options={utmContentOptions}
                  value={filters.utmContent}
                  onChange={(_e, value) => onFilterChange("utmContent", value)}
                  renderInput={(params) => <TextField {...params} placeholder="UTM Content" />}
                />
              </TableCell>
              <TableCell>
                <Autocomplete
                  multiple
                  size="small"
                  options={utmTermOptions}
                  value={filters.utmTerm}
                  onChange={(_e, value) => onFilterChange("utmTerm", value)}
                  renderInput={(params) => <TextField {...params} placeholder="UTM Term" />}
                />
              </TableCell>
              <TableCell>
                <Autocomplete
                  multiple
                  size="small"
                  options={companyOptions}
                  value={filters.advertisingCompanies}
                  onChange={(_e, value) => onFilterChange("advertisingCompanies", value)}
                  renderInput={(params) => <TextField {...params} placeholder="Company" />}
                />
              </TableCell>
              <TableCell align="right" />
              <TableCell />
              <TableCell>{renderTriState(filters.convertedToLead, (v) => onFilterChange("convertedToLead", v))}</TableCell>
              <TableCell>{renderTriState(filters.registeredPlatform, (v) => onFilterChange("registeredPlatform", v))}</TableCell>
              <TableCell>{renderTriState(filters.startedLearning, (v) => onFilterChange("startedLearning", v))}</TableCell>
              <TableCell>{renderTriState(filters.completedCourse, (v) => onFilterChange("completedCourse", v))}</TableCell>
              <TableCell>{renderTriState(filters.interviewReached, (v) => onFilterChange("interviewReached", v))}</TableCell>
              <TableCell>
                <TextField
                  size="small"
                  placeholder="Статус собеседования"
                  value={filters.interviewReachedStatus}
                  onChange={(event) => onFilterChange("interviewReachedStatus", event.target.value)}
                />
              </TableCell>
              <TableCell>{renderTriState(filters.interviewPassed, (v) => onFilterChange("interviewPassed", v))}</TableCell>
              <TableCell>
                <TextField
                  size="small"
                  placeholder="Статус прохождения"
                  value={filters.interviewPassedStatus}
                  onChange={(event) => onFilterChange("interviewPassedStatus", event.target.value)}
                />
              </TableCell>
              <TableCell>{renderTriState(filters.offerReceived, (v) => onFilterChange("offerReceived", v))}</TableCell>
              <TableCell>
                <TextField
                  size="small"
                  placeholder="Статус оффера"
                  value={filters.offerReceivedStatus}
                  onChange={(event) => onFilterChange("offerReceivedStatus", event.target.value)}
                />
              </TableCell>
              <TableCell>{renderTriState(filters.contractSigned, (v) => onFilterChange("contractSigned", v))}</TableCell>
              <TableCell>
                <TextField
                  size="small"
                  placeholder="Статус контракта"
                  value={filters.contractSignedStatus}
                  onChange={(event) => onFilterChange("contractSignedStatus", event.target.value)}
                />
              </TableCell>
              <TableCell>{renderTriState(filters.distanceGrinding, (v) => onFilterChange("distanceGrinding", v))}</TableCell>
              <TableCell>{renderTriState(filters.channelSubscribed, (v) => onFilterChange("channelSubscribed", v))}</TableCell>
              <TableCell>{renderTriState(filters.communityMember, (v) => onFilterChange("communityMember", v))}</TableCell>
              <TableCell>
                <TextField
                  size="small"
                  placeholder="Статус салуна"
                  value={filters.communityMemberStatus}
                  onChange={(event) => onFilterChange("communityMemberStatus", event.target.value)}
                />
              </TableCell>
              <TableCell>{renderTriState(filters.teamMember, (v) => onFilterChange("teamMember", v))}</TableCell>
              <TableCell>
                <TextField
                  size="small"
                  placeholder="Внутренний статус"
                  value={filters.internalStatus}
                  onChange={(event) => onFilterChange("internalStatus", event.target.value)}
                />
              </TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {users.map((user) => (
              <TableRow key={user.id} hover>
                <TableCell>{user.id}</TableCell>
                <TableCell>{botLabelMap.get(user.bot_key) || user.bot_key}</TableCell>
                <TableCell>{user.tg_user_id}</TableCell>
                <TableCell>{formatDate(user.created_at)}</TableCell>
                <TableCell>{formatBool(user.user_block)}</TableCell>
                <TableCell>{user.utm_source || "(none)"}</TableCell>
                <TableCell>{user.utm_campaign || "(none)"}</TableCell>
                <TableCell>{user.first_touch_bot || "нет метки"}</TableCell>
                <TableCell>{user.first_touch_campaign || "нет метки"}</TableCell>
                <TableCell>{user.last_touch_bot || "нет метки"}</TableCell>
                <TableCell>{user.last_touch_campaign || "нет метки"}</TableCell>
                <TableCell>{user.utm_medium || "(none)"}</TableCell>
                <TableCell>{user.utm_content || "(none)"}</TableCell>
                <TableCell>{user.utm_term || "(none)"}</TableCell>
                <TableCell>{user.advertising_company || "—"}</TableCell>
                <TableCell align="right">
                  {user.budget ? Number(user.budget).toFixed(2) : "0.00"}
                </TableCell>
                <TableCell>{formatDate(user.ingested_at)}</TableCell>
                <TableCell>{formatBool(user.converted_to_lead)}</TableCell>
                <TableCell>{formatBool(user.registered_platform)}</TableCell>
                <TableCell>{formatBool(user.started_learning)}</TableCell>
                <TableCell>{formatBool(user.completed_course)}</TableCell>
                <TableCell>{formatBool(user.interview_reached)}</TableCell>
                <TableCell>{user.interview_reached_status || "—"}</TableCell>
                <TableCell>{formatBool(user.interview_passed)}</TableCell>
                <TableCell>{user.interview_passed_status || "—"}</TableCell>
                <TableCell>{formatBool(user.offer_received)}</TableCell>
                <TableCell>{user.offer_received_status || "—"}</TableCell>
                <TableCell>{formatBool(user.contract_signed)}</TableCell>
                <TableCell>{user.contract_signed_status || "—"}</TableCell>
                <TableCell>{formatBool(user.distance_grinding)}</TableCell>
                <TableCell>{formatBool(user.channel_subscribed)}</TableCell>
                <TableCell>{formatBool(user.community_member)}</TableCell>
                <TableCell>{user.community_member_status || "—"}</TableCell>
                <TableCell>{formatBool(user.team_member)}</TableCell>
                <TableCell>{user.internal_status || "—"}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableContainer>
      <TablePagination
        component="div"
        count={total}
        page={page}
        onPageChange={onPageChange}
        rowsPerPage={pageSize}
        onRowsPerPageChange={onRowsPerPageChange}
        rowsPerPageOptions={[50, 100, 200, 500, 1000]}
      />
    </Paper>
  );
};

export default RawUsersTable;
