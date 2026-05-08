from dataclasses import dataclass
from typing import Any, List, Optional, Tuple

from datetime import date as dt_date

from sqlalchemy import Date, Integer, desc, exists, func, literal_column, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.api.report_filters import ReportFilters
from app.models.analytics import (
    BotRegistry,
    RawBotUser,
    WeeklyFunnelBotAgg,
)
from app.services.employee_registry_service import apply_employee_exclusion
from app.services.report_bot_scope import apply_excluded_bot_filter
from app.services.report_repository_budget import ReportRepositoryBudgetMixin
from app.services.report_repository_funnel_summary import ReportRepositoryFunnelSummaryMixin
from app.services.report_repository_subscriptions import ReportRepositorySubscriptionsMixin
from app.services.report_repository_touch import ReportRepositoryTouchMixin
from app.services.utm_normalization import normalize_utm_filter_values


@dataclass
class BreakdownResult:
    group: Optional[str]
    users: int
    budget: float


class ReportRepository(
    ReportRepositoryTouchMixin,
    ReportRepositoryFunnelSummaryMixin,
    ReportRepositorySubscriptionsMixin,
    ReportRepositoryBudgetMixin,
):
    """Репозиторий всех аналитических отчётов — основной источник данных для дашборда.

    Логика воронки строго последовательная (strict):
    entered → lead → platform → learning → course → interview → passed → offer → contract.
    Все даты конвертируются в МСК (func.timezone("Europe/Moscow")).
    Фильтры применяются через _apply_filters / _apply_filters_with_date.
    """

    # ===== Core helpers =====
    @staticmethod
    def _can_use_weekly_bot_agg(filters: ReportFilters, touch_mode: str = "event") -> bool:
        # Агрегат использует старую семантику (UTC-даты, converted_to_lead).
        # Отключён до миграции агрегат-билдера на новые правила.
        return False

    @staticmethod
    def _pct(num: int, den: int) -> float:
        """Безопасный процент num/den, возвращает 0.0 при нулевом знаменателе."""
        if not den:
            return 0.0
        return round((num / den) * 100, 2)

    @staticmethod
    def _apply_utm_filter(stmt, primary_col, platform_col, values: list[str]):
        """Добавляет фильтр по UTM с OR между bot-UTM и platform-UTM.

        Пользователь найдётся, если значение совпадает в любом из двух наборов UTM.
        Нормализует к lower + trim перед сравнением.
        """
        normalized = normalize_utm_filter_values(values)
        if normalized:
            stmt = stmt.where(
                or_(
                    func.lower(func.trim(func.coalesce(primary_col, ""))).in_(normalized),
                    func.lower(func.trim(func.coalesce(platform_col, ""))).in_(normalized),
                )
            )
        return stmt

    @staticmethod
    def _completed_course_condition():
        """Условие завершения курса: флаг + дата + дата >= дата регистрации.

        Проверяет completed_course_at >= created_at, чтобы отсечь некорректные
        данные где дата завершения раньше даты регистрации.
        """
        return (
            RawBotUser.completed_course.is_(True)
            & RawBotUser.completed_course_at.is_not(None)
            & (RawBotUser.completed_course_at >= RawBotUser.created_at)
        )

    @staticmethod
    def _coerce_date(value: Optional[str | dt_date]) -> Optional[dt_date]:
        if value is None:
            return None
        if isinstance(value, dt_date):
            return value
        return dt_date.fromisoformat(value)

    @staticmethod
    def _msk_date(column):
        """Конвертирует timestamp-колонку в дату по МСК-часовому поясу."""
        return func.timezone("Europe/Moscow", column).cast(Date)

    @staticmethod
    def _real_lead_condition():
        """Условие «настоящий лид-бот»: tg_user_id > 0 и bot_key начинается с 'lead'."""
        return (
            (RawBotUser.tg_user_id > 0)
            & func.lower(func.trim(func.coalesce(RawBotUser.bot_key, ""))).like("lead%")
        )

    def _lead_transition_condition(self, filters: ReportFilters | None = None, reference_col=None):
        """Подзапрос EXISTS: у пользователя есть запись в lead-боте после reference_col даты.

        Используется для определения «перешёл в лид» в рамках фильтрованного периода.
        reference_col по умолчанию — created_at текущей записи.
        """
        lead_user = aliased(RawBotUser)
        reference_col = reference_col if reference_col is not None else RawBotUser.created_at
        conditions = [
            lead_user.tg_user_id == RawBotUser.tg_user_id,
            lead_user.tg_user_id > 0,
            lead_user.created_at.is_not(None),
            func.lower(func.trim(func.coalesce(lead_user.bot_key, ""))).like("lead%"),
            self._msk_date(lead_user.created_at) >= self._msk_date(reference_col),
        ]
        if filters and filters.start_date:
            conditions.append(self._msk_date(lead_user.created_at) >= filters.start_date)
        if filters and filters.end_date:
            conditions.append(self._msk_date(lead_user.created_at) <= filters.end_date)
        return exists(select(1).where(*conditions))

    @staticmethod
    def _converted_to_lead_condition():
        lead_user = aliased(RawBotUser)
        has_lead_row = exists(
            select(1).where(
                lead_user.tg_user_id == RawBotUser.tg_user_id,
                func.lower(func.trim(func.coalesce(lead_user.bot_key, ""))).like("lead%"),
            )
        )
        return or_(RawBotUser.converted_to_lead.is_(True), has_lead_row)

    def _strict_stage_conditions(self, filters: ReportFilters | None = None):
        """Строит словарь условий для каждого этапа воронки (строгая последовательность).

        Каждый этап включает все предыдущие: course = learning & completed_course.
        simulator — побочная метрика, не блокирует interview/offer.
        distance и contract — постоферные ветки, независимы друг от друга.
        """
        # Строгая воронка:
        # entered -> lead -> platform -> learning -> course -> interview -> passed -> offer
        # simulator is a side metric from course (must not block interview/offer/contract),
        # distance/contract are post-offer branches and should not block each other.
        lead = self._lead_transition_condition(filters)
        platform = (
            RawBotUser.ph_user_id.is_not(None)
            & RawBotUser.registered_platform.is_(True)
            & RawBotUser.platform_registered_at.is_not(None)
        )
        learning = platform & RawBotUser.started_learning.is_(True)
        course = learning & self._completed_course_condition()
        simulator = course & RawBotUser.used_simulator.is_(True)
        interview = course & RawBotUser.interview_reached.is_(True)
        passed = interview & RawBotUser.interview_passed.is_(True)
        offer = passed & RawBotUser.offer_received.is_(True)
        distance = offer & RawBotUser.distance_grinding.is_(True)
        contract = offer & RawBotUser.contract_signed.is_(True)
        return {
            "lead": lead,
            "platform": platform,
            "learning": learning,
            "course": course,
            "simulator": simulator,
            "interview": interview,
            "passed": passed,
            "offer": offer,
            "distance_grinding": distance,
            "contract": contract,
        }

    def _apply_filters_with_date(self, stmt, filters: ReportFilters, date_col):
        """Применяет все фильтры ReportFilters с привязкой к произвольной date_col.

        Кроме стандартных (дата, боты, компании, UTM) обрабатывает user_scope:
        - "new" — пользователь впервые в системе именно в этот день
        - "old" — уже был в системе до этой записи
        """
        stmt = apply_excluded_bot_filter(stmt, RawBotUser.bot_key)
        msk_date_col = self._msk_date(date_col)
        if filters.start_date:
            stmt = stmt.where(msk_date_col >= filters.start_date)
        if filters.end_date:
            stmt = stmt.where(msk_date_col <= filters.end_date)
        if filters.bots:
            normalized_bots = [b.strip().lower() for b in filters.bots if isinstance(b, str) and b.strip()]
            if normalized_bots:
                registry_matched_bot_keys_sq = (
                    select(func.lower(func.trim(BotRegistry.bot_key)))
                    .where(
                        or_(
                            func.lower(func.trim(func.coalesce(BotRegistry.bot_key, ""))).in_(normalized_bots),
                            func.lower(func.trim(func.coalesce(BotRegistry.display_name, ""))).in_(normalized_bots),
                            func.lower(func.trim(func.coalesce(BotRegistry.canonical_base, ""))).in_(normalized_bots),
                        )
                    )
                )
                stmt = stmt.where(
                    or_(
                        func.lower(func.trim(func.coalesce(RawBotUser.bot_key, ""))).in_(normalized_bots),
                        func.lower(func.trim(func.coalesce(RawBotUser.bot_key, ""))).in_(registry_matched_bot_keys_sq),
                    )
                )
        if filters.advertising_companies:
            stmt = stmt.where(RawBotUser.advertising_company.in_(filters.advertising_companies))
        stmt = self._apply_utm_filter(stmt, RawBotUser.utm_source, RawBotUser.platform_utm_source, filters.utm_source)
        stmt = self._apply_utm_filter(stmt, RawBotUser.utm_campaign, RawBotUser.platform_utm_campaign, filters.utm_campaign)
        stmt = self._apply_utm_filter(stmt, RawBotUser.utm_medium, RawBotUser.platform_utm_medium, filters.utm_medium)
        stmt = self._apply_utm_filter(stmt, RawBotUser.utm_content, RawBotUser.platform_utm_content, filters.utm_content)
        stmt = self._apply_utm_filter(stmt, RawBotUser.utm_term, RawBotUser.platform_utm_term, filters.utm_term)
        if filters.user_scope in {"new", "old"}:
            system_user = aliased(RawBotUser)
            first_seen_system_sq = (
                select(func.min(system_user.created_at))
                .where(system_user.tg_user_id == RawBotUser.tg_user_id)
                .scalar_subquery()
            )
            if filters.user_scope == "new":
                stmt = stmt.where(self._msk_date(first_seen_system_sq) == self._msk_date(RawBotUser.created_at))
            elif filters.user_scope == "old":
                stmt = stmt.where(self._msk_date(first_seen_system_sq) < self._msk_date(RawBotUser.created_at))
        return stmt

    def _apply_filters(self, stmt, filters: ReportFilters):
        stmt = self._apply_filters_with_date(stmt, filters, RawBotUser.created_at)
        return apply_employee_exclusion(stmt, RawBotUser.tg_user_id)

    @staticmethod
    def _normalized_company_sql(alias: str) -> str:
        return f"""
            CASE
                WHEN {alias}.advertising_company IS NULL
                  OR BTRIM({alias}.advertising_company) = ''
                  OR LOWER(BTRIM({alias}.advertising_company)) IN ('-', '—', '(none)', 'none', 'null', 'нет метки')
                THEN 'Без категории'
                ELSE BTRIM({alias}.advertising_company)
            END
        """

    @staticmethod
    def _bot_label_sql(alias: str) -> str:
        return f"COALESCE(NULLIF(BTRIM({alias}.bot_key), ''), 'Без бота')"

    async def total(self, session: AsyncSession, filters: ReportFilters) -> dict[str, Optional[float]]:
        stmt = select(
            func.count(func.distinct(RawBotUser.tg_user_id)).label("users"),
            func.coalesce(func.sum(RawBotUser.budget), 0).label("budget"),
        )
        stmt = self._apply_filters(stmt, filters)
        result = await session.execute(stmt)
        row = result.one()
        total_users = row.users or 0
        total_budget = row.budget or 0.0
        return {
            "total_users": total_users,
            "total_budget": total_budget,
            "cac": (total_budget / total_users) if total_users else None,
        }

    async def daily(self, session: AsyncSession, filters: ReportFilters, limit: Optional[int] = None) -> List[dict[str, Optional[float]]]:
        """Новые пользователи по дням: дата, count(distinct tg_user_id), сумма бюджетов."""
        date_expr = func.date_trunc("day", RawBotUser.created_at)
        stmt = (
            select(
                date_expr.label("date"),
                func.count(func.distinct(RawBotUser.tg_user_id)).label("users"),
                func.coalesce(func.sum(RawBotUser.budget), 0).label("budget"),
            )
            .group_by(date_expr)
            .order_by(date_expr)
        )
        stmt = self._apply_filters(stmt, filters)
        if limit:
            stmt = stmt.limit(limit)
        result = await session.execute(stmt)
        return [
            {"date": row.date.strftime("%Y-%m-%d"), "users": row.users, "budget": row.budget}
            for row in result.all()
        ]

    async def breakdown(
        self, session: AsyncSession, filters: ReportFilters, group_by: str, limit: int = 20
    ) -> List[BreakdownResult]:
        """Разбивка пользователей по произвольному полю (utm_source, advertising_company и др.).

        group_by="source_campaign" → конкатенирует utm_source + " / " + utm_campaign.
        Для UTM всегда берёт platform-UTM если есть, иначе bot-UTM.
        """
        effective_source = func.coalesce(RawBotUser.platform_utm_source, RawBotUser.utm_source, "—")
        effective_campaign = func.coalesce(RawBotUser.platform_utm_campaign, RawBotUser.utm_campaign, "—")
        if group_by == "source_campaign":
            label = func.concat(
                effective_source,
                " / ",
                effective_campaign,
            ).label("group_value")
        elif group_by == "utm_source":
            label = effective_source.label("group_value")
        elif group_by == "utm_campaign":
            label = effective_campaign.label("group_value")
        else:
            column = getattr(RawBotUser, group_by)
            label = func.coalesce(column, "—").label("group_value")

        stmt = (
            select(
                label,
                func.count(func.distinct(RawBotUser.tg_user_id)).label("users"),
                func.coalesce(func.sum(RawBotUser.budget), 0).label("budget"),
            )
            .group_by(label)
            .order_by(desc("users"))
            .limit(limit)
        )
        stmt = self._apply_filters(stmt, filters)
        result = await session.execute(stmt)
        return [
            BreakdownResult(group=row.group_value, users=row.users, budget=row.budget) for row in result.all()
        ]

    async def conversions(self, session: AsyncSession, filters: ReportFilters) -> List[dict[str, Optional[float]]]:
        """Конверсия entered→lead по каждому боту + общий итог.

        entered = все пользователи бота в периоде,
        converted = те, у кого появилась запись в lead-боте (EXISTS-подзапрос).
        """
        if self._can_use_weekly_bot_agg(filters):
            result = await session.execute(
                select(
                    WeeklyFunnelBotAgg.bot_key.label("bot_key"),
                    func.sum(WeeklyFunnelBotAgg.entered).label("entered"),
                    func.sum(WeeklyFunnelBotAgg.lead).label("converted"),
                )
                .group_by(WeeklyFunnelBotAgg.bot_key)
                .order_by(desc("entered"))
            )
            rows = result.all()
            total_entered = sum(row.entered or 0 for row in rows)
            total_converted = sum(row.converted or 0 for row in rows)
            overall_rate = (total_converted / total_entered) * 100 if total_entered else 0
            return [
                {
                    "bot_key": row.bot_key,
                    "entered": row.entered or 0,
                    "converted": row.converted or 0,
                    "conversion_rate": (row.converted or 0) / (row.entered or 1) * 100 if row.entered else 0,
                    "overall_entered": total_entered,
                    "overall_converted": total_converted,
                    "overall_rate": overall_rate,
                }
                for row in rows
            ]
        entered_count = func.count(func.distinct(RawBotUser.tg_user_id))
        converted_to_lead_condition = self._lead_transition_condition(filters)
        converted_count = func.count(func.distinct(RawBotUser.tg_user_id)).filter(
            converted_to_lead_condition
        )
        stmt = (
            select(
                RawBotUser.bot_key.label("bot_key"),
                entered_count.label("entered"),
                converted_count.label("converted"),
            )
            .group_by(RawBotUser.bot_key)
            .order_by(desc("entered"))
        )
        stmt = self._apply_filters(stmt, filters)
        result = await session.execute(stmt)
        rows = result.all()
        total_entered = sum(row.entered or 0 for row in rows)
        total_converted = sum(row.converted or 0 for row in rows)
        overall_rate = (total_converted / total_entered) * 100 if total_entered else 0
        return [
            {
                "bot_key": row.bot_key,
                "entered": row.entered or 0,
                "converted": row.converted or 0,
                "conversion_rate": (row.converted or 0) / (row.entered or 1) * 100 if row.entered else 0,
                "overall_entered": total_entered,
                "overall_converted": total_converted,
                "overall_rate": overall_rate,
            }
            for row in rows
        ]

    async def stages(self, session: AsyncSession, filters: ReportFilters) -> dict[str, int]:
        """Считает количество пользователей на каждом этапе воронки (один SELECT).

        entered считается по tg_user_id, все остальные этапы — по ph_user_id
        (уникальные пользователи платформы). Использует _strict_stage_conditions.
        """
        entered_count = func.count(func.distinct(RawBotUser.tg_user_id))
        stage_conditions = self._strict_stage_conditions(filters)
        platform_count = func.count(func.distinct(RawBotUser.ph_user_id)).filter(
            RawBotUser.ph_user_id.is_not(None),
            RawBotUser.platform_registered_at.is_not(None),
        )
        stmt = select(
            entered_count.label("entered"),
            func.count(func.distinct(RawBotUser.tg_user_id)).filter(
                stage_conditions["lead"]
            ).label("lead"),
            platform_count.label("platform"),
            func.count(func.distinct(RawBotUser.ph_user_id)).filter(
                stage_conditions["learning"]
            ).label("learning"),
            func.count(func.distinct(RawBotUser.ph_user_id)).filter(
                stage_conditions["course"]
            ).label("course"),
            func.count(func.distinct(RawBotUser.ph_user_id)).filter(
                stage_conditions["simulator"]
            ).label("simulator"),
            func.count(func.distinct(RawBotUser.ph_user_id)).filter(
                stage_conditions["interview"]
            ).label("interview"),
            func.count(func.distinct(RawBotUser.ph_user_id)).filter(
                stage_conditions["passed"]
            ).label("passed"),
            func.count(func.distinct(RawBotUser.ph_user_id)).filter(
                stage_conditions["offer"]
            ).label("offer"),
            func.count(func.distinct(RawBotUser.ph_user_id)).filter(
                stage_conditions["contract"]
            ).label("contract"),
            func.count(func.distinct(RawBotUser.ph_user_id)).filter(
                stage_conditions["distance_grinding"]
            ).label("distance_grinding"),
        )
        stmt = self._apply_filters(stmt, filters)
        result = await session.execute(stmt)
        row = result.one()
        return {
            "entered": int(row.entered or 0),
            "lead": int(row.lead or 0),
            "platform": int(row.platform or 0),
            "learning": int(row.learning or 0),
            "course": int(row.course or 0),
            "simulator": int(row.simulator or 0),
            "interview": int(row.interview or 0),
            "passed": int(row.passed or 0),
            "offer": int(row.offer or 0),
            "contract": int(row.contract or 0),
            "distance_grinding": int(row.distance_grinding or 0),
        }
