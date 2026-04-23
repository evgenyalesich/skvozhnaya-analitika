from datetime import date
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, select, cast, String, case
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.report_filters import ReportFilters
from app.models.analytics import PhUserMirrorReplica, RawBotUser
from app.services.employee_registry_service import apply_employee_exclusion
from app.services.pokerhub_lesson_summary import PokerHubLessonSummaryBuilder
from app.services.report_repository import ReportRepository


@dataclass
class LessonColumn:
    key: str
    label: str
    module: int | None
    lesson: int | None


@dataclass
class LessonUserRow:
    tg_user_id: int | None
    username: str | None
    pokerhub_user_id: str | None
    completed_lessons: int
    lessons: dict[str, str | None]


@dataclass
class LessonCourseReport:
    course: str
    total_lessons: int
    columns: list[LessonColumn]
    rows: list[LessonUserRow]


class RoistatLessonsReport:
    COURSE_ORDER = ("BASE", "MTT_NEW", "SPIN_NEW", "MTT", "SPIN", "CASH")
    COURSE_TOTALS = {
        "BASE": 5,
        "MTT_NEW": 12,
        "SPIN_NEW": 80,
        "MTT": 36,
        "SPIN": 81,
        "CASH": 10,
    }

    def __init__(self) -> None:
        self.report_repository = ReportRepository()
        self.summary_builder = PokerHubLessonSummaryBuilder()

    async def build(
        self,
        session: AsyncSession,
        filters: ReportFilters,
        pokerhub_user_id: str | None = None,
        learn_start_date_from: date | None = None,
        learn_start_date_to: date | None = None,
    ) -> list[LessonCourseReport]:
        cohort_ph_ids = await self._load_cohort_ph_ids(session, filters)
        if cohort_ph_ids is not None and not cohort_ph_ids:
            return self._empty_reports()

        users = await self._load_users(session, cohort_ph_ids=cohort_ph_ids)
        if not users:
            return self._empty_reports()

        search = (pokerhub_user_id or "").strip().lower()

        course_columns: dict[str, dict[str, LessonColumn]] = {course: {} for course in self.COURSE_ORDER}
        course_rows: dict[str, list[LessonUserRow]] = {course: [] for course in self.COURSE_ORDER}

        for user in users:
            summary = user.get("summary") if isinstance(user, dict) else None
            if not isinstance(summary, dict):
                continue
            summary_learn_start = self._summary_learn_start_date(summary)
            if learn_start_date_from and (summary_learn_start is None or summary_learn_start < learn_start_date_from):
                continue
            if learn_start_date_to and (summary_learn_start is None or summary_learn_start > learn_start_date_to):
                continue
            tg_user_id = self._coerce_int(user.get("tg_user_id"))
            summary_pokerhub_id = self._normalize_text(summary.get("pokerhub_user_id"))
            if search:
                tg_id_str = str(tg_user_id) if tg_user_id is not None else ""
                username_str = self._normalize_text(user.get("username"))
                if (
                    search not in summary_pokerhub_id
                    and search not in tg_id_str
                    and search not in username_str
                ):
                    continue
            courses = summary.get("courses") if isinstance(summary, dict) else None
            if not isinstance(courses, dict):
                continue
            memberships = {
                str(course).strip()
                for course in (summary.get("course_memberships") or [])
                if str(course).strip()
            }
            raw_course_labels = {
                str(course).strip().upper()
                for course in (summary.get("raw_course_labels") or [])
                if str(course).strip()
            }
            summary_groups = {
                str(group).strip().lower()
                for group in (summary.get("groups") or [])
                if str(group).strip()
            }
            if not any(courses.get(course) for course in self.COURSE_ORDER):
                if not memberships:
                    continue
            username = self._pick_username(user.get("username"), summary.get("username"))
            base_entries = courses.get("BASE") or []
            base_completed = any(
                isinstance(entry, dict)
                and self._coerce_int(entry.get("lesson")) == 5
                and self._normalize_nullable_text(entry.get("date"))
                for entry in base_entries
            )
            for course in self.COURSE_ORDER:
                base_entries = courses.get(course) or []
                entries = list(base_entries)
                if course == "MTT_NEW" and isinstance(base_entries, list) and len(base_entries) > 0:
                    # Include module 2 from MTT into MTT_NEW so the base funnel
                    # is visible in a single tab for the user.
                    mtt_entries = courses.get("MTT") or []
                    module2_entries = [
                        entry
                        for entry in mtt_entries
                        if isinstance(entry, dict) and self._coerce_int(entry.get("module")) == 2
                    ]
                    entries.extend(module2_entries)
                if not isinstance(entries, list):
                    entries = []
                lesson_map: dict[str, str | None] = {}
                for entry in entries:
                    if not isinstance(entry, dict):
                        continue
                    key = str(entry.get("key") or "").strip()
                    if not key:
                        continue
                    column = LessonColumn(
                        key=key,
                        label=str(entry.get("label") or key),
                        module=self._coerce_int(entry.get("module")),
                        lesson=self._coerce_int(entry.get("lesson")),
                    )
                    course_columns[course][key] = column
                    lesson_map[key] = self._normalize_nullable_text(entry.get("date"))
                is_post_base_registry_match = False
                if base_completed:
                    if course == "MTT_NEW":
                        is_post_base_registry_match = "MTT1" in raw_course_labels or "mtt after base couse" in summary_groups
                    elif course == "SPIN_NEW":
                        is_post_base_registry_match = "SPIN1" in raw_course_labels or "spin after base couse" in summary_groups
                if not lesson_map and course not in memberships and not is_post_base_registry_match:
                    continue
                course_rows[course].append(
                    LessonUserRow(
                        tg_user_id=tg_user_id,
                        username=username,
                        pokerhub_user_id=summary_pokerhub_id or None,
                        completed_lessons=sum(1 for value in lesson_map.values() if value),
                        lessons=lesson_map,
                    )
                )

        reports: list[LessonCourseReport] = []
        for course in self.COURSE_ORDER:
            columns = sorted(course_columns[course].values(), key=self._column_sort_key)
            rows = [
                LessonUserRow(
                    tg_user_id=row.tg_user_id,
                    username=row.username,
                    pokerhub_user_id=row.pokerhub_user_id,
                    completed_lessons=row.completed_lessons,
                    lessons={column.key: row.lessons.get(column.key) for column in columns},
                )
                for row in course_rows[course]
            ]
            reports.append(
                LessonCourseReport(
                    course=course,
                    total_lessons=max(int(self.COURSE_TOTALS.get(course) or 0), len(columns)),
                    columns=columns,
                    rows=rows,
                )
            )
        return reports

    def _cohort_filters(self, filters: ReportFilters) -> ReportFilters:
        return ReportFilters(
            start_date=filters.start_date,
            end_date=filters.end_date,
            bots=filters.bots,
            advertising_companies=filters.advertising_companies,
            utm_source=filters.utm_source,
            utm_campaign=filters.utm_campaign,
            utm_medium=filters.utm_medium,
            utm_content=filters.utm_content,
            utm_term=filters.utm_term,
            user_scope=filters.user_scope,
        )

    def _empty_reports(self) -> list[LessonCourseReport]:
        return [
            LessonCourseReport(
                course=course,
                total_lessons=int(self.COURSE_TOTALS.get(course) or 0),
                columns=[],
                rows=[],
            )
            for course in self.COURSE_ORDER
        ]

    async def _load_cohort_ph_ids(self, session: AsyncSession, filters: ReportFilters) -> set[str] | None:
        cohort_filters = self._cohort_filters(filters)
        if not cohort_filters.has_filters():
            return None
        stmt = select(RawBotUser.ph_user_id).where(RawBotUser.ph_user_id.is_not(None)).distinct()
        stmt = self.report_repository._apply_filters(stmt, cohort_filters)
        result = await session.execute(stmt)
        return {str(int(row.ph_user_id)) for row in result.fetchall() if row.ph_user_id is not None}

    async def _load_users(
        self,
        session: AsyncSession,
        cohort_ph_ids: set[str] | None = None,
    ) -> list[dict[str, Any]]:
        # DISTINCT ON (ph_id): for duplicate rows keep the one with most lessons.
        # PostgreSQL requires ORDER BY to start with the DISTINCT ON column.
        from sqlalchemy import func
        stmt = (
            select(
                PhUserMirrorReplica.id.label("lead_user_id"),
                PhUserMirrorReplica.ph_id.label("ph_user_id"),
                PhUserMirrorReplica.username.label("mirror_username"),
                PhUserMirrorReplica.ph_group.label("ph_group"),
                PhUserMirrorReplica.groups.label("groups"),
                PhUserMirrorReplica.courses.label("courses"),
                PhUserMirrorReplica.lessons.label("lessons"),
            )
            .where(PhUserMirrorReplica.ph_id.is_not(None))
            .distinct(PhUserMirrorReplica.ph_id)
            .order_by(
                PhUserMirrorReplica.ph_id,
                func.jsonb_array_length(PhUserMirrorReplica.lessons).desc(),
                PhUserMirrorReplica.id.desc(),
            )
        )
        if cohort_ph_ids is not None:
            stmt = stmt.where(PhUserMirrorReplica.ph_id.in_(sorted(cohort_ph_ids)))
        result = await session.execute(stmt)
        rows = result.fetchall()

        ph_ids = [str(row.ph_user_id) for row in rows if row.ph_user_id is not None and str(row.ph_user_id).strip()]
        identity_map = await self._load_identity_map(session, ph_ids)

        users: list[dict[str, Any]] = []
        for row in rows:
            ph_id = str(row.ph_user_id).strip()
            summary = self.summary_builder.build(
                {
                    "ph_id": ph_id,
                    "username": row.mirror_username,
                    "group": row.ph_group,
                    "groups": row.groups,
                    "courses": row.courses,
                    "lessons": row.lessons,
                },
                course_catalog={},
            )
            identity = identity_map.get(ph_id, {})
            username = self._pick_username(identity.get("username"), row.mirror_username, summary.get("username"))
            users.append(
                {
                    "tg_user_id": identity.get("tg_user_id"),
                    "username": username,
                    "ph_user_id": ph_id,
                    "summary": summary,
                }
            )
        return users

    async def _load_identity_map(self, session: AsyncSession, ph_ids: list[str]) -> dict[str, dict[str, Any]]:
        if not ph_ids:
            return {}
        stmt = (
            select(
                cast(RawBotUser.ph_user_id, String).label("ph_id"),
                func.max(case((RawBotUser.tg_user_id > 0, RawBotUser.tg_user_id), else_=None)).label("tg_user_id"),
                func.max(RawBotUser.username).label("username"),
            )
            .where(RawBotUser.ph_user_id.is_not(None), cast(RawBotUser.ph_user_id, String).in_(ph_ids))
            .group_by(cast(RawBotUser.ph_user_id, String))
        )
        stmt = apply_employee_exclusion(stmt, RawBotUser.tg_user_id)
        result = await session.execute(stmt)
        identity_map: dict[str, dict[str, Any]] = {}
        for row in result.fetchall():
            ph_id = str(row.ph_id).strip()
            if not ph_id:
                continue
            identity_map[ph_id] = {
                "tg_user_id": int(row.tg_user_id) if row.tg_user_id is not None else None,
                "username": row.username,
            }
        return identity_map

    def _summary_learn_start_date(self, summary: dict[str, Any]) -> date | None:
        courses = summary.get("courses")
        if not isinstance(courses, dict):
            return None
        earliest: date | None = None
        for entries in courses.values():
            if not isinstance(entries, list):
                continue
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                raw_date = self._normalize_nullable_text(entry.get("date"))
                if not raw_date:
                    continue
                try:
                    parsed = date.fromisoformat(raw_date)
                except ValueError:
                    continue
                if earliest is None or parsed < earliest:
                    earliest = parsed
        return earliest

    def _column_sort_key(self, column: LessonColumn) -> tuple[int, int, str]:
        module = column.module if column.module is not None else 999
        lesson = column.lesson if column.lesson is not None else 999
        return module, lesson, column.label

    def _normalize_text(self, value: Any) -> str:
        if value is None:
            return ""
        return str(value).strip().lower()

    def _normalize_nullable_text(self, value: Any) -> str | None:
        normalized = self._normalize_text(value)
        return normalized or None

    def _pick_username(self, *values: Any) -> str | None:
        for value in values:
            if value is not None and str(value).strip():
                return str(value).strip()
        return None

    def _coerce_int(self, value: Any) -> int | None:
        try:
            return int(str(value))
        except (TypeError, ValueError):
            return None
