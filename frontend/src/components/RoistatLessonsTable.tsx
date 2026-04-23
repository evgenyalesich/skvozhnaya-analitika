import React, { useMemo, useState } from "react";
import Paper from "@mui/material/Paper";
import Tabs from "@mui/material/Tabs";
import Tab from "@mui/material/Tab";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableContainer from "@mui/material/TableContainer";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import Typography from "@mui/material/Typography";
import LinearProgress from "@mui/material/LinearProgress";
import Box from "@mui/material/Box";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import TablePagination from "@mui/material/TablePagination";
import Chip from "@mui/material/Chip";
import Divider from "@mui/material/Divider";
import Tooltip from "@mui/material/Tooltip";
import Avatar from "@mui/material/Avatar";
import TableSortLabel from "@mui/material/TableSortLabel";
import Button from "@mui/material/Button";
import ExportButtons from "./ExportButtons";
import Slider from "@mui/material/Slider";
import FormControl from "@mui/material/FormControl";
import InputLabel from "@mui/material/InputLabel";
import Select from "@mui/material/Select";
import MenuItem from "@mui/material/MenuItem";
import { RoistatLessonCourse } from "../hooks/useRoistatLessons";
import EmptyState from "./ui/EmptyState";
import TableSkeleton from "./ui/TableSkeleton";

interface RoistatLessonsTableProps {
  courses: RoistatLessonCourse[];
  loading: boolean;
  error?: string | null;
  pokerhubUserId: string;
  onPokerhubUserIdChange: (value: string) => void;
  learnStartDateFrom: string;
  learnStartDateTo: string;
  onLearnStartDateFromChange: (value: string) => void;
  onLearnStartDateToChange: (value: string) => void;
}

const formatLessonDate = (value: string | null | undefined) => {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  const pad = (part: number) => String(part).padStart(2, "0");
  return `${pad(date.getDate())}.${pad(date.getMonth() + 1)}.${date.getFullYear()}`;
};

const lessonCellSx = (value: string | null | undefined) => {
  if (!value) {
    return {
      color: "text.disabled",
      backgroundColor: "transparent",
      fontWeight: 400,
    };
  }
  const now = new Date();
  const parsed = new Date(value);
  const diffDays = Number.isNaN(parsed.getTime())
    ? null
    : Math.floor((now.getTime() - parsed.getTime()) / (1000 * 60 * 60 * 24));

  if (diffDays !== null && diffDays <= 7) {
    return {
      color: "#166534",
      backgroundColor: "rgba(34, 197, 94, 0.12)",
      fontWeight: 700,
    };
  }
  if (diffDays !== null && diffDays <= 30) {
    return {
      color: "#1d4ed8",
      backgroundColor: "rgba(59, 130, 246, 0.10)",
      fontWeight: 600,
    };
  }
  return {
    color: "text.primary",
    backgroundColor: "rgba(148, 163, 184, 0.10)",
    fontWeight: 500,
  };
};

const labelForCourse = (course: string) => {
  if (course === "BASE") return "Базовый курс";
  if (course === "MTT_NEW") return "МТТ (NEW)";
  if (course === "SPIN_NEW") return "SPIN (NEW)";
  if (course === "MTT") return "MTT";
  if (course === "SPIN") return "SPIN";
  if (course === "CASH") return "CASH";
  return course;
};

const stickyCellSx = (left: number, zIndex: number, backgroundColor: string) => ({
  position: "sticky",
  left,
  zIndex,
  backgroundColor,
});

const compactLessonLabel = (label: string) => {
  const moduleMatch = label.match(/Модуль\s+(\d+)/i);
  const lessonMatch = label.match(/Урок\s+(\d+)/i);
  if (moduleMatch || lessonMatch) {
    const modulePart = moduleMatch ? `M${moduleMatch[1]}` : "";
    const lessonPart = lessonMatch ? `L${lessonMatch[1]}` : "";
    return [modulePart, lessonPart].filter(Boolean).join(" / ");
  }
  return label;
};

const progressStats = (completed: number, total: number) => {
  const percent = total > 0 ? Math.round((completed / total) * 100) : 0;
  return { completed, percent };
};

const initials = (value: string | null | undefined) => {
  if (!value) return "?";
  return value.trim().slice(0, 1).toUpperCase();
};

type SortDirection = "asc" | "desc";

const parseLessonTimestamp = (value: string | null | undefined) => {
  if (!value) return null;
  const direct = Date.parse(value);
  if (!Number.isNaN(direct)) {
    return direct;
  }
  const local = value.match(/^(\d{2})\.(\d{2})\.(\d{4})$/);
  if (!local) {
    return null;
  }
  const [, dd, mm, yyyy] = local;
  const fallback = Date.parse(`${yyyy}-${mm}-${dd}T00:00:00`);
  return Number.isNaN(fallback) ? null : fallback;
};

const parseDayStart = (value: string) => {
  if (!value) return null;
  const dt = new Date(`${value}T00:00:00`);
  if (Number.isNaN(dt.getTime())) return null;
  return dt.getTime();
};

const parseDayEndExclusive = (value: string) => {
  const start = parseDayStart(value);
  if (start === null) return null;
  return start + 24 * 60 * 60 * 1000;
};

const applyLessonDateRange = (
  lessons: Record<string, string | null>,
  fromTs: number | null,
  toExclusiveTs: number | null,
) => {
  const scopedLessons: Record<string, string | null> = {};
  Object.entries(lessons).forEach(([key, value]) => {
    if (!value) {
      scopedLessons[key] = null;
      return;
    }
    const lessonTs = parseLessonTimestamp(value);
    if (lessonTs === null) {
      scopedLessons[key] = null;
      return;
    }
    if (fromTs !== null && lessonTs < fromTs) {
      scopedLessons[key] = null;
      return;
    }
    if (toExclusiveTs !== null && lessonTs >= toExclusiveTs) {
      scopedLessons[key] = null;
      return;
    }
    scopedLessons[key] = value;
  });
  return {
    lessons: scopedLessons,
    completed: Object.values(scopedLessons).filter(Boolean).length,
  };
};

const RoistatLessonsTable: React.FC<RoistatLessonsTableProps> = ({
  courses,
  loading,
  error,
  pokerhubUserId,
  onPokerhubUserIdChange,
  learnStartDateFrom,
  learnStartDateTo,
  onLearnStartDateFromChange,
  onLearnStartDateToChange,
}) => {
  const orderedCourses = useMemo(() => {
    const preferred = ["BASE", "MTT_NEW", "SPIN_NEW", "MTT", "SPIN", "CASH"];
    return [...courses].sort((a, b) => {
      const left = preferred.indexOf(a.course);
      const right = preferred.indexOf(b.course);
      return (left === -1 ? 999 : left) - (right === -1 ? 999 : right);
    });
  }, [courses]);
  const [selectedCourse, setSelectedCourse] = useState("BASE");
  const [page, setPage] = useState(0);
  const [rowsPerPage, setRowsPerPage] = useState(100);
  const [sortColumn, setSortColumn] = useState<string | null>(null);
  const [sortDirection, setSortDirection] = useState<SortDirection>("asc");
  const [completionRange, setCompletionRange] = useState<[number, number]>([0, 100]);
  const [lessonFilterKey, setLessonFilterKey] = useState<string>("all");
  const [lessonFilterState, setLessonFilterState] = useState<"all" | "done" | "not_done">("all");

  const activeCourse =
    orderedCourses.find((course) => course.course === selectedCourse) || orderedCourses[0] || null;

  const normalizedDateRange = useMemo(() => {
    const fromTs = parseDayStart(learnStartDateFrom);
    const toExclusiveTs = parseDayEndExclusive(learnStartDateTo);
    if (fromTs === null && toExclusiveTs === null) {
      return { fromTs: null as number | null, toExclusiveTs: null as number | null };
    }
    if (fromTs !== null && toExclusiveTs !== null && fromTs > toExclusiveTs) {
      return { fromTs: toExclusiveTs - 24 * 60 * 60 * 1000, toExclusiveTs: fromTs + 24 * 60 * 60 * 1000 };
    }
    return { fromTs, toExclusiveTs };
  }, [learnStartDateFrom, learnStartDateTo]);

  const rowsByLessonDateByCourse = useMemo(() => {
    const hasDateFilter = normalizedDateRange.fromTs !== null || normalizedDateRange.toExclusiveTs !== null;
    const result: Record<string, typeof courses[number]["rows"]> = {};
    orderedCourses.forEach((course) => {
      result[course.course] = course.rows
        .map((row) => {
          const scoped = applyLessonDateRange(
            row.lessons,
            normalizedDateRange.fromTs,
            normalizedDateRange.toExclusiveTs,
          );
          return {
            ...row,
            lessons: scoped.lessons,
            completed_lessons: scoped.completed,
          };
        })
        .filter((row) => !hasDateFilter || row.completed_lessons > 0);
    });
    return result;
  }, [courses, normalizedDateRange.fromTs, normalizedDateRange.toExclusiveTs, orderedCourses]);

  const rowsByLessonDate = useMemo(() => {
    if (!activeCourse) return [];
    return rowsByLessonDateByCourse[activeCourse.course] || [];
  }, [activeCourse, rowsByLessonDateByCourse]);

  const filteredRows = useMemo(() => {
    if (!activeCourse) return [];
    const total = activeCourse.total_lessons || 1;
    return rowsByLessonDate.filter((row) => {
      const pct = Math.round((row.completed_lessons / total) * 100);
      if (pct < completionRange[0] || pct > completionRange[1]) {
        return false;
      }
      if (lessonFilterKey === "all" || lessonFilterState === "all") {
        return true;
      }
      const hasLesson = Boolean(row.lessons[lessonFilterKey]);
      if (lessonFilterState === "done") {
        return hasLesson;
      }
      return !hasLesson;
    });
  }, [activeCourse, completionRange, lessonFilterKey, lessonFilterState, rowsByLessonDate]);

  const sortedRows = useMemo(() => {
    if (!activeCourse) return [];
    if (!sortColumn) return filteredRows;

    return [...filteredRows].sort((left, right) => {
      const leftValue = parseLessonTimestamp(left.lessons[sortColumn]);
      const rightValue = parseLessonTimestamp(right.lessons[sortColumn]);

      if (leftValue === null && rightValue === null) {
        return left.tg_user_id - right.tg_user_id;
      }
      if (leftValue === null) {
        return 1;
      }
      if (rightValue === null) {
        return -1;
      }
      if (leftValue === rightValue) {
        return left.tg_user_id - right.tg_user_id;
      }
      return sortDirection === "asc" ? leftValue - rightValue : rightValue - leftValue;
    });
  }, [activeCourse, filteredRows, sortColumn, sortDirection]);
  const visibleRows = useMemo(() => {
    if (!activeCourse) return [];
    const start = page * rowsPerPage;
    return sortedRows.slice(start, start + rowsPerPage);
  }, [activeCourse, page, rowsPerPage, sortedRows]);
  const totalLessons = activeCourse?.total_lessons ?? 0;
  const rowsWithProgress = filteredRows.filter((row) => row.completed_lessons > 0).length;

  const getLessonsExportData = () => {
    if (!activeCourse) return [];
    const headers = ["TG ID", "Username", "PokerHub ID", "Completed", ...activeCourse.columns.map((c) => c.label)];
    const lines = sortedRows.map((row) => [
      row.tg_user_id,
      row.username || "",
      row.pokerhub_user_id || "",
      row.completed_lessons,
      ...activeCourse.columns.map((c) => row.lessons[c.key] || ""),
    ]);
    return [headers, ...lines];
  };

  const toggleSort = (columnKey: string) => {
    setPage(0);
    if (sortColumn !== columnKey) {
      setSortColumn(columnKey);
      setSortDirection("asc");
      return;
    }
    if (sortDirection === "asc") {
      setSortDirection("desc");
      return;
    }
    setSortColumn(null);
    setSortDirection("asc");
  };

  return (
    <Paper
      sx={{
        mt: 2,
        p: 2,
        borderRadius: 3,
        background:
          "linear-gradient(180deg, rgba(248,250,252,0.98) 0%, rgba(255,255,255,1) 22%)",
        boxShadow: "0 18px 40px rgba(15, 23, 42, 0.08)",
      }}
    >
      <Stack
        direction={{ xs: "column", md: "row" }}
        spacing={2}
        justifyContent="space-between"
        alignItems={{ xs: "stretch", md: "center" }}
        mb={2}
      >
        <Stack direction="row" spacing={1} alignItems="flex-start">
          <Box>
            <Typography variant="h5" sx={{ fontWeight: 700 }}>
              PokerHub Lessons
            </Typography>
            <Typography variant="body2" color="text.secondary">
              Движение пользователей по урокам PokerHub
            </Typography>
            <Typography variant="caption" color="text.secondary">
              M = Module, L = Lesson
            </Typography>
          </Box>
          <ExportButtons
            getData={getLessonsExportData}
            baseName={activeCourse ? `lessons_${activeCourse.course}` : "lessons"}
            sheetName="Lessons"
            disabled={!activeCourse}
          />
        </Stack>
        <Stack
          direction="row"
          spacing={1.5}
          alignItems="center"
          useFlexGap
          flexWrap="wrap"
          sx={{ width: "100%", justifyContent: { xs: "flex-start", md: "flex-end" } }}
        >
          <Chip
            label={`${rowsWithProgress} пользователей`}
            color="primary"
            variant="outlined"
            sx={{ flexShrink: 0 }}
          />
          <Chip label={`${totalLessons} уроков`} color="default" variant="outlined" sx={{ flexShrink: 0 }} />
          <Box
            sx={{
              px: 1,
              minWidth: { xs: "100%", sm: 220, md: 200 },
              flex: { xs: "1 1 100%", lg: "0 1 260px" },
            }}
          >
            <Typography variant="caption" color="text.secondary">
              Прогресс: {completionRange[0]}%–{completionRange[1]}%
            </Typography>
            <Slider
              size="small"
              value={completionRange}
              onChange={(_e, val) => { setPage(0); setCompletionRange(val as [number, number]); }}
              valueLabelDisplay="auto"
              min={0}
              max={100}
            />
          </Box>
          <FormControl
            size="small"
            sx={{
              minWidth: { xs: "100%", sm: 220 },
              flex: { xs: "1 1 100%", md: "1 1 220px", xl: "0 1 240px" },
            }}
          >
            <InputLabel id="lesson-column-filter-label">Урок</InputLabel>
            <Select
              labelId="lesson-column-filter-label"
              label="Урок"
              value={lessonFilterKey}
              onChange={(event) => {
                setPage(0);
                setLessonFilterKey(String(event.target.value));
              }}
            >
              <MenuItem value="all">Все уроки</MenuItem>
              {(activeCourse?.columns || []).map((column) => (
                <MenuItem key={column.key} value={column.key}>
                  {column.label}
                </MenuItem>
              ))}
            </Select>
          </FormControl>
          <FormControl
            size="small"
            sx={{
              minWidth: { xs: "100%", sm: 200 },
              flex: { xs: "1 1 100%", md: "1 1 200px", xl: "0 1 220px" },
            }}
          >
            <InputLabel id="lesson-status-filter-label">Статус урока</InputLabel>
            <Select
              labelId="lesson-status-filter-label"
              label="Статус урока"
              value={lessonFilterState}
              onChange={(event) => {
                setPage(0);
                setLessonFilterState(event.target.value as "all" | "done" | "not_done");
              }}
            >
              <MenuItem value="all">Все</MenuItem>
              <MenuItem value="done">Прошли урок</MenuItem>
              <MenuItem value="not_done">Не прошли урок</MenuItem>
            </Select>
          </FormControl>
          <TextField
            size="small"
            label="Поиск (PH ID / TG ID / Username)"
            value={pokerhubUserId}
            onChange={(event) => {
              setPage(0);
              onPokerhubUserIdChange(event.target.value);
            }}
            sx={{
              minWidth: { xs: "100%", sm: 260, md: 300 },
              flex: { xs: "1 1 100%", md: "1 1 320px", lg: "1 1 360px" },
            }}
          />
          <TextField
            size="small"
            type="date"
            label="Начало обучения с"
            value={learnStartDateFrom}
            onChange={(event) => {
              setPage(0);
              onLearnStartDateFromChange(event.target.value);
            }}
            InputLabelProps={{ shrink: true }}
            sx={{
              minWidth: { xs: "100%", sm: 220 },
              flex: { xs: "1 1 100%", md: "0 1 220px" },
            }}
          />
          <TextField
            size="small"
            type="date"
            label="Начало обучения по"
            value={learnStartDateTo}
            onChange={(event) => {
              setPage(0);
              onLearnStartDateToChange(event.target.value);
            }}
            InputLabelProps={{ shrink: true }}
            sx={{
              minWidth: { xs: "100%", sm: 220 },
              flex: { xs: "1 1 100%", md: "0 1 220px" },
            }}
          />
        </Stack>
      </Stack>
      <Tabs
        value={activeCourse?.course || false}
        onChange={(_event, value) => {
          setSelectedCourse(String(value));
          setPage(0);
          setSortColumn(null);
          setSortDirection("asc");
          setCompletionRange([0, 100]);
          setLessonFilterKey("all");
          setLessonFilterState("all");
        }}
        sx={{ mb: 2 }}
      >
        {orderedCourses.map((course) => (
          <Tab
            key={course.course}
            value={course.course}
            label={`${labelForCourse(course.course)} (${(rowsByLessonDateByCourse[course.course] || []).length})`}
            sx={{ fontWeight: 700 }}
          />
        ))}
      </Tabs>
      <Divider sx={{ mb: 2 }} />
      {loading && <LinearProgress sx={{ mb: 1 }} />}
      {loading && !activeCourse && <TableSkeleton columns={7} rows={7} />}
      {error && (
        <Typography variant="body2" color="error" mb={1}>
          {error}
        </Typography>
      )}
      {!activeCourse && !loading && (
        <EmptyState compact title="По урокам пока нет данных" description="Здесь появится матрица прохождения уроков, когда PokerHub отдаст данные по выбранным пользователям." />
      )}
      {activeCourse && (
        <TableContainer
          sx={{
            maxHeight: "70vh",
            border: "1px solid var(--app-table-divider)",
            borderRadius: 2,
            backgroundColor: "var(--app-panel-bg)",
          }}
        >
          <Table size="small" stickyHeader>
            <TableHead>
              <TableRow>
                <TableCell
                  sx={{
                    minWidth: 110,
                    fontWeight: 700,
                    ...stickyCellSx(0, 5, "var(--app-table-head-bg)"),
                  }}
                >
                  TG ID
                </TableCell>
                <TableCell
                  sx={{
                    minWidth: 220,
                    fontWeight: 700,
                    ...stickyCellSx(110, 5, "var(--app-table-head-bg)"),
                  }}
                >
                  User name
                </TableCell>
                <TableCell
                  sx={{
                    minWidth: 120,
                    fontWeight: 700,
                    ...stickyCellSx(330, 5, "var(--app-table-head-bg)"),
                  }}
                >
                  PokerHub ID
                </TableCell>
                <TableCell
                  sx={{
                    minWidth: 120,
                    fontWeight: 700,
                    ...stickyCellSx(450, 5, "var(--app-table-head-bg)"),
                  }}
                >
                  Прогресс
                </TableCell>
                {activeCourse.columns.map((column) => (
                  <TableCell
                    key={column.key}
                    align="center"
                    sx={{
                      minWidth: 92,
                      fontWeight: 700,
                      backgroundColor: "var(--app-table-head-bg)",
                      whiteSpace: "nowrap",
                    }}
                  >
                    <Tooltip title={column.label} arrow>
                      <TableSortLabel
                        active={sortColumn === column.key}
                        direction={sortColumn === column.key ? sortDirection : "asc"}
                        hideSortIcon={sortColumn !== column.key}
                        onClick={() => toggleSort(column.key)}
                        >
                          <Box component="span">{compactLessonLabel(column.label)}</Box>
                        </TableSortLabel>
                      </Tooltip>
                    </TableCell>
                  ))}
              </TableRow>
            </TableHead>
            <TableBody>
              {visibleRows.map((row, index) => (
                (() => {
                  const progress = progressStats(row.completed_lessons, activeCourse.total_lessons);
                  const remainingLessons = Math.max((activeCourse.total_lessons || 0) - progress.completed, 0);
                  const stickyBg = index % 2 === 0 ? "var(--app-table-row-alt)" : "var(--app-panel-bg)";
                  const rowIdentity = row.pokerhub_user_id || row.tg_user_id || `${row.username || "unknown"}-${index}`;
                  return (
                <TableRow
                  key={`${activeCourse.course}-${rowIdentity}`}
                  sx={{
                    "&:nth-of-type(odd)": { backgroundColor: "var(--app-table-row-alt)" },
                    "&:hover": { backgroundColor: "var(--app-table-row-hover)" },
                    "& .MuiTableCell-root": { py: 1.05, fontSize: "0.78rem" },
                  }}
                >
                  <TableCell
                    sx={{
                      fontVariantNumeric: "tabular-nums",
                      ...stickyCellSx(0, 2, stickyBg),
                    }}
                  >
                    {row.tg_user_id}
                  </TableCell>
                  <TableCell
                    sx={{
                      fontWeight: 500,
                      ...stickyCellSx(110, 2, stickyBg),
                    }}
                  >
                    <Stack direction="row" spacing={1.25} alignItems="center">
                      <Avatar sx={{ width: 28, height: 28, fontSize: 13, bgcolor: "var(--c-blue-bg)", color: "var(--c-blue)" }}>
                        {initials(row.username)}
                      </Avatar>
                      <Box>
                        <Typography variant="body2" sx={{ fontWeight: 600, lineHeight: 1.2 }}>
                          {row.username || "—"}
                        </Typography>
                        <Typography variant="caption" color="text.secondary">
                          TG {row.tg_user_id}
                        </Typography>
                      </Box>
                    </Stack>
                  </TableCell>
                  <TableCell
                    sx={{
                      fontVariantNumeric: "tabular-nums",
                      ...stickyCellSx(330, 2, stickyBg),
                    }}
                  >
                    {row.pokerhub_user_id || "—"}
                  </TableCell>
                  <TableCell
                    sx={{
                      ...stickyCellSx(450, 2, stickyBg),
                    }}
                  >
                    <Stack spacing={0.5}>
                      <Typography variant="body2" sx={{ fontWeight: 600 }}>
                        {progress.completed}/{activeCourse.total_lessons}
                      </Typography>
                      <Typography variant="caption" color="text.secondary">
                        Осталось {remainingLessons}
                      </Typography>
                      <Box
                        sx={{
                          height: 6,
                          borderRadius: 999,
                          backgroundColor: "rgba(148,163,184,0.2)",
                          overflow: "hidden",
                        }}
                      >
                        <Box
                          sx={{
                            width: `${progress.percent}%`,
                            height: "100%",
                            backgroundColor: progress.percent >= 80 ? "#16a34a" : progress.percent >= 40 ? "#2563eb" : "#94a3b8",
                          }}
                        />
                      </Box>
                    </Stack>
                  </TableCell>
                  {activeCourse.columns.map((column) => (
                    (() => {
                      const lessonValue = row.lessons[column.key];
                      const style = lessonCellSx(lessonValue);
                      return (
                        <TableCell
                          key={`${rowIdentity}-${column.key}`}
                          align="center"
                          sx={{
                            fontVariantNumeric: "tabular-nums",
                            ...style,
                          }}
                        >
                          {formatLessonDate(lessonValue)}
                        </TableCell>
                      );
                    })()
                  ))}
                </TableRow>
                  );
                })()
              ))}
              {!visibleRows.length && !loading && (
                <TableRow>
                  <TableCell colSpan={4 + activeCourse.columns.length} sx={{ py: 0 }}>
                    <EmptyState
                      compact
                      title="По выбранному курсу ничего не найдено"
                      description="Попробуй другой фильтр урока, диапазон прогресса или поисковый запрос."
                    />
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </TableContainer>
      )}
      {activeCourse && (
        <TablePagination
          component="div"
          count={sortedRows.length}
          page={page}
          onPageChange={(_event, nextPage) => setPage(nextPage)}
          rowsPerPage={rowsPerPage}
          onRowsPerPageChange={(event) => {
            setRowsPerPage(Number(event.target.value));
            setPage(0);
          }}
          rowsPerPageOptions={[50, 100, 200]}
          labelRowsPerPage="Строк на странице:"
          sx={{ borderTop: "1px solid var(--app-table-divider)" }}
        />
      )}
    </Paper>
  );
};

export default RoistatLessonsTable;
