# Слой PH Lessons для Roistat companies:
# 1. SQL-запрос lesson_first извлекает дату первого урока по каждому курсу из ph_user_mirror_replica.
# 2. attributed связывает ph_user_id → company/bot_key (LATERAL JOIN по raw_bot_users, приоритет lead-боту).
# 3. course_events UNION ALL → grouped по week_start/company/bot_key → накапливает company/bot/week регистрации.
# 4. Второй проход через PokerHubLessonSummaryBuilder (courses.BASE/MTT/SPIN/CASH min date) — более точные даты.
# Итого: в payload base/mtt/spin/cash = число уникальных ph_user_id, зарегистрировавшихся на курс за неделю.
#
# ИСПРАВЛЕНИЕ: убран двойной apply_reg_maps + reset между ними.
# Порядок теперь:
#   1. zero-reset всех started_*/advanced_*/completed_* полей
#   2. apply_reg_maps из lesson_reg_query (PH mirror event-date) → started_*/advanced_*/base/mtt/spin/cash
#   3. mirror-loop через PokerHubLessonSummaryBuilder → completion_*_sets + company_reg_map (более точные даты)
#   4. reset_course_registration_metrics → обнуляет base/mtt/spin/cash ТОЛЬКО ПОСЛЕ того, как started_* уже записаны
#   5. apply_reg_maps из mirror company_reg_map → финальные base/mtt/spin/cash из mirror
#   6. completion_*_sets → completed_* метрики
#   7. platform_cnt из ph_reg_query (event-based)
#   8. not_started = platform_cnt - started_learning

from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Any

from app.services.pokerhub_lesson_summary import PokerHubLessonSummaryBuilder

from app.api.routers.reports_roistat_companies_postprocess_shared import (
    apply_reg_maps,
    reset_course_registration_metrics,
)


async def apply_lesson_registration_metrics(
    *,
    session,
    sa_text,
    params,
    cohort_cte: str,
    cohort_join: str,
    normalized_company_sql: str,
    source_touch_filter_sql: str,
    rows_payload: list[dict[str, Any]],
    bot_rows_payload: list[dict[str, Any]],
    week_totals_payload: list[dict[str, Any]],
    display_mode: str,
) -> None:
    lead_map_cte_sql = """
        lead_map AS (
            SELECT DISTINCT ON (ph_user_id)
                ph_user_id,
                tg_user_id,
                username,
                created_at
            FROM raw_bot_users
            WHERE bot_key = 'lead'
              AND ph_user_id IS NOT NULL
              AND tg_user_id > 0
            ORDER BY ph_user_id, created_at DESC
        )
    """

    start_date_param = params.get("start")
    end_date_param = params.get("end")

    if isinstance(start_date_param, datetime):
        start_date_param = start_date_param.date()
    if isinstance(end_date_param, datetime):
        end_date_param = end_date_param.date()

    def _normalize_date(value: Any) -> date | None:
        if value is None:
            return None
        if isinstance(value, date) and not isinstance(value, datetime):
            return value
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, str):
            normalized = value.strip()
            if not normalized:
                return None
            try:
                return datetime.fromisoformat(normalized.replace("Z", "+00:00")).date()
            except ValueError:
                try:
                    return date.fromisoformat(normalized)
                except ValueError:
                    return None
        return None

    def _in_selected_range(value: Any) -> bool:
        normalized = _normalize_date(value)
        if normalized is None:
            return False
        if isinstance(start_date_param, date) and normalized < start_date_param:
            return False
        if isinstance(end_date_param, date) and normalized > end_date_param:
            return False
        return True

    # ─────────────────────────────────────────────────────────────────────────
    # ШАГ 1: lesson_reg_query — event-date метрики из PH mirror SQL
    # Источник истины для started_*/advanced_*/base/mtt/spin/cash
    # ─────────────────────────────────────────────────────────────────────────
    lesson_reg_query = sa_text(f"""
        WITH lesson_first AS (
            SELECT
                pm.ph_id::bigint AS ph_user_id,
                MIN((((regexp_match(lesson.value, '\\(([^()]+)\\)$'))[1])::timestamptz AT TIME ZONE 'Europe/Moscow')::date)
                    FILTER (WHERE lesson.value LIKE 'Базовый курс:%') AS base_date,
                MIN((((regexp_match(lesson.value, '\\(([^()]+)\\)$'))[1])::timestamptz AT TIME ZONE 'Europe/Moscow')::date)
                    FILTER (WHERE lesson.value LIKE 'МТТ%' OR lesson.value LIKE 'MTT%') AS mtt_date,
                MIN((((regexp_match(lesson.value, '\\(([^()]+)\\)$'))[1])::timestamptz AT TIME ZONE 'Europe/Moscow')::date)
                    FILTER (WHERE lesson.value LIKE 'СПИН%' OR lesson.value LIKE 'SPIN%') AS spin_date,
                MIN((((regexp_match(lesson.value, '\\(([^()]+)\\)$'))[1])::timestamptz AT TIME ZONE 'Europe/Moscow')::date)
                    FILTER (WHERE lesson.value LIKE 'CASH1:%') AS cash_date
            FROM ph_user_mirror_replica pm
            LEFT JOIN LATERAL jsonb_array_elements_text(COALESCE(pm.lessons::jsonb, '[]'::jsonb)) AS lesson(value) ON TRUE
            GROUP BY pm.ph_id
        ),
        {lead_map_cte_sql},
        attributed AS (
            SELECT
                lf.ph_user_id,
                COALESCE(src.company, 'Без категории') AS company,
                COALESCE(src.bot_key, 'Без бота') AS bot_key,
                lf.base_date,
                lf.mtt_date,
                lf.spin_date,
                lf.cash_date
            FROM lesson_first lf
            LEFT JOIN lead_map lm ON lm.ph_user_id = lf.ph_user_id
            LEFT JOIN LATERAL (
                SELECT
                    {normalized_company_sql.replace("advertising_company", "src.advertising_company")} AS company,
                    COALESCE(NULLIF(BTRIM(src.bot_key), ''), 'Без бота') AS bot_key
                FROM raw_bot_users src
                WHERE (
                        (lm.tg_user_id IS NOT NULL AND src.tg_user_id = lm.tg_user_id)
                        OR src.ph_user_id = lf.ph_user_id
                      )
                  AND LOWER(TRIM(COALESCE(src.bot_key, ''))) <> ALL(:excluded_bot_keys)
                  AND src.created_at IS NOT NULL{source_touch_filter_sql}
                ORDER BY
                    CASE WHEN lower(trim(COALESCE(src.bot_key, ''))) LIKE 'lead%' THEN 1 ELSE 0 END,
                    CASE
                        WHEN COALESCE(lf.base_date, lf.mtt_date, lf.spin_date, lf.cash_date) IS NOT NULL
                             AND (src.created_at AT TIME ZONE 'Europe/Moscow')::date <= COALESCE(lf.base_date, lf.mtt_date, lf.spin_date, lf.cash_date)
                        THEN 0 ELSE 1
                    END,
                    ABS(((src.created_at AT TIME ZONE 'Europe/Moscow')::date - COALESCE(lf.base_date, lf.mtt_date, lf.spin_date, lf.cash_date))) ASC NULLS LAST,
                    src.created_at DESC
                LIMIT 1
            ) src ON TRUE
        ),
        course_events AS (
            SELECT DATE_TRUNC('week', base_date)::date AS week_start, company, bot_key, ph_user_id, 'base' AS course
            FROM attributed
            WHERE base_date IS NOT NULL
              AND (CAST(:start AS date) IS NULL OR base_date >= CAST(:start AS date))
              AND (CAST(:end AS date) IS NULL OR base_date <= CAST(:end AS date))
            UNION ALL
            SELECT DATE_TRUNC('week', mtt_date)::date AS week_start, company, bot_key, ph_user_id, 'mtt' AS course
            FROM attributed
            WHERE mtt_date IS NOT NULL
              AND (CAST(:start AS date) IS NULL OR mtt_date >= CAST(:start AS date))
              AND (CAST(:end AS date) IS NULL OR mtt_date <= CAST(:end AS date))
            UNION ALL
            SELECT DATE_TRUNC('week', spin_date)::date AS week_start, company, bot_key, ph_user_id, 'spin' AS course
            FROM attributed
            WHERE spin_date IS NOT NULL
              AND (CAST(:start AS date) IS NULL OR spin_date >= CAST(:start AS date))
              AND (CAST(:end AS date) IS NULL OR spin_date <= CAST(:end AS date))
            UNION ALL
            SELECT DATE_TRUNC('week', cash_date)::date AS week_start, company, bot_key, ph_user_id, 'cash' AS course
            FROM attributed
            WHERE cash_date IS NOT NULL
              AND (CAST(:start AS date) IS NULL OR cash_date >= CAST(:start AS date))
              AND (CAST(:end AS date) IS NULL OR cash_date <= CAST(:end AS date))
        )
        SELECT
            week_start,
            company,
            bot_key,
            COUNT(DISTINCT ph_user_id) FILTER (WHERE course = 'base') AS base,
            COUNT(DISTINCT ph_user_id) FILTER (WHERE course = 'mtt') AS mtt,
            COUNT(DISTINCT ph_user_id) FILTER (WHERE course = 'spin') AS spin,
            COUNT(DISTINCT ph_user_id) FILTER (WHERE course = 'cash') AS cash,
            COUNT(DISTINCT ph_user_id) AS learning_any,
            COUNT(DISTINCT ph_user_id) FILTER (WHERE course IN ('mtt', 'spin', 'cash')) AS advanced_any
        FROM course_events
        GROUP BY week_start, company, bot_key
    """)
    lesson_reg_result = await session.execute(lesson_reg_query, params)
    lesson_reg_rows = lesson_reg_result.fetchall()

    # ─────────────────────────────────────────────────────────────────────────
    # ШАГ 2: ph_reg_query — платформенные регистрации (event-based)
    # ─────────────────────────────────────────────────────────────────────────
    ph_reg_query = sa_text(f"""
        WITH ph_events AS (
            SELECT
                pm.ph_id::bigint AS ph_user_id,
                CASE
                    WHEN pm.ph_registration ~ '^\\d{4}-\\d{2}-\\d{2}$' THEN pm.ph_registration::date
                    WHEN NULLIF(BTRIM(COALESCE(pm.ph_registration_at, '')), '') IS NOT NULL
                        THEN (pm.ph_registration_at::timestamptz AT TIME ZONE 'Europe/Moscow')::date
                    ELSE NULL
                END AS ph_reg_date
            FROM ph_user_mirror_replica pm
            WHERE pm.ph_id ~ '^[0-9]+$'
              AND (
                    pm.ph_registration ~ '^\\d{4}-\\d{2}-\\d{2}$'
                    OR NULLIF(BTRIM(COALESCE(pm.ph_registration_at, '')), '') IS NOT NULL
                  )
        ),
        {lead_map_cte_sql},
        attributed AS (
            SELECT
                pe.ph_user_id,
                pe.ph_reg_date,
                COALESCE(src.company, 'Без категории') AS company,
                COALESCE(src.bot_key, 'Без бота') AS bot_key
            FROM ph_events pe
            LEFT JOIN lead_map lm ON lm.ph_user_id = pe.ph_user_id
            LEFT JOIN LATERAL (
                SELECT
                    {normalized_company_sql.replace("advertising_company", "src.advertising_company")} AS company,
                    COALESCE(NULLIF(BTRIM(src.bot_key), ''), 'Без бота') AS bot_key
                FROM raw_bot_users src
                WHERE (
                        (lm.tg_user_id IS NOT NULL AND src.tg_user_id = lm.tg_user_id)
                        OR src.ph_user_id = pe.ph_user_id
                      )
                  AND LOWER(TRIM(COALESCE(src.bot_key, ''))) <> ALL(:excluded_bot_keys)
                  AND src.created_at IS NOT NULL{source_touch_filter_sql}
                ORDER BY
                    CASE WHEN lower(trim(COALESCE(src.bot_key, ''))) LIKE 'lead%' THEN 1 ELSE 0 END,
                    CASE
                        WHEN pe.ph_reg_date IS NOT NULL
                             AND (src.created_at AT TIME ZONE 'Europe/Moscow')::date <= pe.ph_reg_date
                        THEN 0 ELSE 1
                    END,
                    ABS(((src.created_at AT TIME ZONE 'Europe/Moscow')::date - pe.ph_reg_date)) ASC NULLS LAST,
                    src.created_at DESC
                LIMIT 1
            ) src ON TRUE
        )
        SELECT
            DATE_TRUNC('week', ph_reg_date)::date AS week_start,
            company,
            bot_key,
            COUNT(DISTINCT ph_user_id) AS platform_cnt
        FROM attributed
        WHERE ph_reg_date IS NOT NULL
          AND (CAST(:start AS date) IS NULL OR ph_reg_date >= CAST(:start AS date))
          AND (CAST(:end AS date) IS NULL OR ph_reg_date <= CAST(:end AS date))
        GROUP BY 1, 2, 3
    """)
    ph_reg_result = await session.execute(ph_reg_query, params)
    ph_reg_rows = ph_reg_result.fetchall()

    # ─────────────────────────────────────────────────────────────────────────
    # ШАГ 3: Собираем lesson_reg_map из SQL-результатов
    # Эти данные — источник истины для started_*/advanced_*/base/mtt/spin/cash
    # ─────────────────────────────────────────────────────────────────────────
    _reg_zero: dict[str, int] = {
        "base": 0, "mtt": 0, "spin": 0, "cash": 0,
        "started_base": 0, "started_mtt": 0, "started_spin": 0, "started_cash": 0,
        "started_learning": 0, "advanced_started_uniq": 0, "advanced_started_total": 0,
    }
    lesson_company_reg_map: dict[tuple[str, str], dict[str, int]] = {}
    lesson_bot_reg_map: dict[tuple[str, str, str], dict[str, int]] = {}
    lesson_week_reg_map: dict[str, dict[str, int]] = {}

    for row in lesson_reg_rows:
        week_key = row.week_start.isoformat()
        company_key = (week_key, row.company)
        bot_key_tuple = (week_key, row.company, row.bot_key)
        base = int(row.base or 0)
        mtt = int(row.mtt or 0)
        spin = int(row.spin or 0)
        cash = int(row.cash or 0)
        learning_any = int(row.learning_any or 0)
        advanced_any = int(row.advanced_any or 0)
        metrics = {
            "base": base, "mtt": mtt, "spin": spin, "cash": cash,
            "started_base": base,
            "started_mtt": mtt,
            "started_spin": spin,
            "started_cash": cash,
            "started_learning": learning_any,
            "advanced_started_uniq": advanced_any,
            "advanced_started_total": mtt + spin + cash,
        }
        company_metrics = lesson_company_reg_map.setdefault(company_key, dict(_reg_zero))
        for k, v in metrics.items():
            company_metrics[k] += v
        lesson_bot_reg_map[bot_key_tuple] = metrics
        week_metrics = lesson_week_reg_map.setdefault(week_key, dict(_reg_zero))
        for k, v in metrics.items():
            week_metrics[k] += v

    # ─────────────────────────────────────────────────────────────────────────
    # ШАГ 4: Собираем platform_cnt из ph_reg_query
    # ─────────────────────────────────────────────────────────────────────────
    company_platform_map: dict[tuple[str, str], int] = {}
    bot_platform_map: dict[tuple[str, str, str], int] = {}
    week_platform_map: dict[str, int] = {}

    for row in ph_reg_rows:
        week_key = row.week_start.isoformat()
        company_key = (week_key, row.company)
        bot_key_tuple = (week_key, row.company, row.bot_key)
        value = int(row.platform_cnt or 0)
        company_platform_map[company_key] = company_platform_map.get(company_key, 0) + value
        bot_platform_map[bot_key_tuple] = bot_platform_map.get(bot_key_tuple, 0) + value
        week_platform_map[week_key] = week_platform_map.get(week_key, 0) + value

    # ─────────────────────────────────────────────────────────────────────────
    # ШАГ 5: Обнуляем все lesson/completion метрики в payload
    # Делаем это ДО apply_reg_maps, чтобы не было артефактов от SQL weekly слоя
    # ─────────────────────────────────────────────────────────────────────────
    completed_keys = {
        "completed_course",
        "completed_base",
        "completed_mtt",
        "completed_spin",
        "completed_cash",
    }
    started_direction_keys = (
        "started_base",
        "started_mtt",
        "started_spin",
        "started_cash",
    )
    advanced_started_keys = ("started_mtt", "started_spin", "started_cash")
    advanced_completed_keys = ("completed_mtt", "completed_spin", "completed_cash")
    extra_keys = {"advanced_started_uniq", "advanced_started_total", "advanced_completed_uniq", "advanced_completed_total"}
    started_keys = {"started_learning", *started_direction_keys}

    for payload_rows in (rows_payload, bot_rows_payload, week_totals_payload):
        for row in payload_rows:
            for key in completed_keys:
                row[key] = 0
            for key in started_keys:
                row[key] = 0
            for key in extra_keys:
                row[key] = 0

    # ─────────────────────────────────────────────────────────────────────────
    # ШАГ 6: Применяем lesson_reg_query метрики
    # Записывает: base/mtt/spin/cash + started_*/advanced_*
    # ─────────────────────────────────────────────────────────────────────────
    apply_reg_maps(
        rows_payload=rows_payload,
        bot_rows_payload=bot_rows_payload,
        week_totals_payload=week_totals_payload,
        company_reg_map=lesson_company_reg_map,
        bot_reg_map=lesson_bot_reg_map,
        week_reg_map=lesson_week_reg_map,
    )

    # ─────────────────────────────────────────────────────────────────────────
    # ШАГ 7: Применяем platform_cnt
    # ─────────────────────────────────────────────────────────────────────────
    for row in rows_payload:
        week_key = str(row.get("week_start"))
        company = str(row.get("company", ""))
        row["platform_cnt"] = int(company_platform_map.get((week_key, company), 0))

    for row in bot_rows_payload:
        week_key = str(row.get("week_start"))
        company = str(row.get("company", ""))
        bot_key = str(row.get("bot_key", ""))
        row["platform_cnt"] = int(bot_platform_map.get((week_key, company, bot_key), 0))

    for row in week_totals_payload:
        week_key = str(row.get("week_start"))
        row["platform_cnt"] = int(week_platform_map.get(week_key, 0))

    # ─────────────────────────────────────────────────────────────────────────
    # ШАГ 8: not_started = platform_cnt - started_learning
    # ─────────────────────────────────────────────────────────────────────────
    for payload_rows in (rows_payload, bot_rows_payload, week_totals_payload):
        for row in payload_rows:
            platform_cnt = int(row.get("platform_cnt") or 0)
            started_learning = int(row.get("started_learning") or 0)
            row["not_started"] = max(platform_cnt - started_learning, 0)

    # ─────────────────────────────────────────────────────────────────────────
    # ШАГ 9: _apply_business_overrides (entered_all, almanah, offer, contract, direct)
    # ─────────────────────────────────────────────────────────────────────────
    await _apply_business_overrides(
        session=session,
        sa_text=sa_text,
        params=params,
        display_mode=display_mode,
        normalized_company_sql=normalized_company_sql,
        source_touch_filter_sql=source_touch_filter_sql,
        rows_payload=rows_payload,
        bot_rows_payload=bot_rows_payload,
        week_totals_payload=week_totals_payload,
    )

    # ─────────────────────────────────────────────────────────────────────────
    # ШАГ 10: Mirror-loop через PokerHubLessonSummaryBuilder
    # Источник: более точные даты курсов + completion метрики
    # base/mtt/spin/cash из mirror перезаписывают SQL-версию (более точный источник)
    # started_*/advanced_* НЕ трогаем — они уже записаны из lesson_reg_query
    # ─────────────────────────────────────────────────────────────────────────
    def _terminal_date(entries: list[dict[str, Any]], terminal_module: int | None, terminal_lesson: int) -> date | None:
        dates: list[date] = []
        for entry in entries:
            lesson = entry.get("lesson")
            module = entry.get("module")
            raw_date = entry.get("date")
            if lesson is None or raw_date is None:
                continue
            try:
                lesson_num = int(lesson)
            except Exception:
                continue
            if terminal_module is None:
                if lesson_num < terminal_lesson:
                    continue
            else:
                try:
                    module_num = int(module) if module is not None else None
                except Exception:
                    continue
                if module_num is None:
                    continue
                if module_num < terminal_module:
                    continue
                if module_num == terminal_module and lesson_num < terminal_lesson:
                    continue
            try:
                parsed = date.fromisoformat(str(raw_date))
            except Exception:
                continue
            dates.append(parsed)
        return min(dates) if dates else None

    def _week_start_key(value: Any) -> str | None:
        normalized = _normalize_date(value)
        if normalized is None:
            return None
        week_start = normalized - timedelta(days=normalized.weekday())
        return week_start.isoformat()

    def _week_start_iso(value: Any) -> str | None:
        if value is None:
            return None
        if isinstance(value, str):
            normalized_str = value.strip()
            if not normalized_str:
                return None
            try:
                value = datetime.fromisoformat(normalized_str.replace("Z", "+00:00")).date()
            except ValueError:
                try:
                    value = date.fromisoformat(normalized_str)
                except ValueError:
                    return None
        elif isinstance(value, datetime):
            value = value.date()
        week_start = value - timedelta(days=value.weekday())
        return week_start.isoformat()

    completion_company_sets: dict[tuple[str, str], dict[str, set[str]]] = defaultdict(
        lambda: {
            "completed_course": set(),
            "completed_base": set(),
            "completed_mtt": set(),
            "completed_spin": set(),
            "completed_cash": set(),
        }
    )
    completion_bot_sets: dict[tuple[str, str, str], dict[str, set[str]]] = defaultdict(
        lambda: {
            "completed_course": set(),
            "completed_base": set(),
            "completed_mtt": set(),
            "completed_spin": set(),
            "completed_cash": set(),
        }
    )
    completion_week_sets: dict[str, dict[str, set[str]]] = defaultdict(
        lambda: {
            "completed_course": set(),
            "completed_base": set(),
            "completed_mtt": set(),
            "completed_spin": set(),
            "completed_cash": set(),
        }
    )

    # Attribution map: ph_user_id → (company, bot_key)
    # Используем ту же схему что для PH/learning:
    # lead.ph_user_id → lead.tg_user_id → обычные bot-строки
    attribution_query = sa_text(f"""
        WITH lead_map AS (
            SELECT DISTINCT ON (ph_user_id)
                ph_user_id,
                tg_user_id,
                created_at
            FROM raw_bot_users
            WHERE bot_key LIKE 'lead%'
              AND ph_user_id IS NOT NULL
              AND tg_user_id > 0
            ORDER BY ph_user_id, created_at DESC
        )
        SELECT
            lm.ph_user_id::text AS ph_user_id,
            COALESCE(src.company, 'Без категории') AS company,
            COALESCE(src.bot_key, 'Без бота') AS bot_key
        FROM lead_map lm
        LEFT JOIN LATERAL (
            SELECT
                {normalized_company_sql.replace("advertising_company", "src.advertising_company")} AS company,
                COALESCE(NULLIF(BTRIM(src.bot_key), ''), 'Без бота') AS bot_key
            FROM raw_bot_users src
            WHERE (
                    src.tg_user_id = lm.tg_user_id
                    OR src.ph_user_id = lm.ph_user_id
                  )
              AND LOWER(TRIM(COALESCE(src.bot_key, ''))) <> ALL(:excluded_bot_keys)
              AND src.created_at IS NOT NULL{source_touch_filter_sql}
            ORDER BY
                CASE WHEN lower(trim(COALESCE(src.bot_key, ''))) LIKE 'lead%' THEN 1 ELSE 0 END,
                src.created_at DESC NULLS LAST
            LIMIT 1
        ) src ON TRUE
    """)
    attribution_result = await session.execute(attribution_query, params)
    attribution_map = {
        str(row.ph_user_id): (row.company or "Без категории", row.bot_key or "Без бота")
        for row in attribution_result.fetchall()
    }

    mirror_result = await session.execute(
        sa_text("SELECT ph_id, lessons, courses, groups FROM ph_user_mirror_replica")
    )
    lesson_builder = PokerHubLessonSummaryBuilder()
    summary_by_ph_id: dict[str, dict[str, Any]] = {}

    # mirror_reg_map — более точные даты курсов из PokerHubLessonSummaryBuilder
    # Перезапишут base/mtt/spin/cash после reset
    mirror_company_reg_map: dict[tuple[str, str], dict[str, int]] = defaultdict(
        lambda: {"base": 0, "mtt": 0, "spin": 0, "cash": 0}
    )
    mirror_bot_reg_map: dict[tuple[str, str, str], dict[str, int]] = defaultdict(
        lambda: {"base": 0, "mtt": 0, "spin": 0, "cash": 0}
    )
    mirror_week_reg_map: dict[str, dict[str, int]] = defaultdict(
        lambda: {"base": 0, "mtt": 0, "spin": 0, "cash": 0}
    )

    course_keys = {
        "BASE": "base",
        "MTT": "mtt",
        "SPIN": "spin",
        "CASH": "cash",
    }

    for mirror_row in mirror_result.fetchall():
        ph_id = str(mirror_row.ph_id or "")
        if not ph_id:
            continue
        summary = lesson_builder.build(
            {
                "ph_id": ph_id,
                "lessons": mirror_row.lessons,
                "courses": mirror_row.courses,
                "groups": mirror_row.groups,
            }
        )
        summary_by_ph_id[ph_id] = summary
        company, bot_key = attribution_map.get(ph_id, ("Без категории", "Без бота"))

        for course_name, metric_key in course_keys.items():
            lesson_dates = [
                entry.get("date")
                for entry in summary["courses"].get(course_name, [])
                if entry.get("date") is not None
            ]
            if not lesson_dates:
                continue
            first_lesson_date = _normalize_date(min(lesson_dates))
            if not _in_selected_range(first_lesson_date):
                continue
            week_key = _week_start_iso(first_lesson_date)
            if not week_key:
                continue
            mirror_company_reg_map[(week_key, company)][metric_key] += 1
            mirror_bot_reg_map[(week_key, company, bot_key)][metric_key] += 1
            mirror_week_reg_map[week_key][metric_key] += 1

        # Completion даты
        completion_dates: dict[str, date] = {}
        base_done = _terminal_date(summary["courses"].get("BASE", []), None, 5)
        if base_done:
            completion_dates["completed_base"] = base_done

        mtt_old_done = _terminal_date(summary["courses"].get("MTT", []), 2, 21)
        mtt_new_done = _terminal_date(summary["courses"].get("MTT_NEW", []), None, 12)
        mtt_done = min([d for d in [mtt_old_done, mtt_new_done] if d is not None], default=None)
        if mtt_done:
            completion_dates["completed_mtt"] = mtt_done

        spin_old_done = _terminal_date(summary["courses"].get("SPIN", []), 1, 81)
        spin_new_done = _terminal_date(summary["courses"].get("SPIN_NEW", []), None, 80)
        spin_done = min([d for d in [spin_old_done, spin_new_done] if d is not None], default=None)
        if spin_done:
            completion_dates["completed_spin"] = spin_done

        cash_done = _terminal_date(summary["courses"].get("CASH", []), 1, 10)
        if cash_done:
            completion_dates["completed_cash"] = cash_done

        if completion_dates:
            overall_done = min(completion_dates.values())
            completion_dates["completed_course"] = overall_done

        for metric_key, completed_at in completion_dates.items():
            if not _in_selected_range(completed_at):
                continue
            week_key = _week_start_key(completed_at)
            if not week_key:
                continue
            completion_company_sets[(week_key, company)][metric_key].add(ph_id)
            completion_bot_sets[(week_key, company, bot_key)][metric_key].add(ph_id)
            completion_week_sets[week_key][metric_key].add(ph_id)

    # ─────────────────────────────────────────────────────────────────────────
    # ШАГ 11: Обнуляем base/mtt/spin/cash и перезаписываем из mirror
    # started_*/advanced_* НЕ трогаем — они уже записаны на шаге 6
    # ─────────────────────────────────────────────────────────────────────────
    reset_course_registration_metrics(
        rows_payload=rows_payload,
        bot_rows_payload=bot_rows_payload,
        week_totals_payload=week_totals_payload,
    )

    apply_reg_maps(
        rows_payload=rows_payload,
        bot_rows_payload=bot_rows_payload,
        week_totals_payload=week_totals_payload,
        company_reg_map=mirror_company_reg_map,
        bot_reg_map=mirror_bot_reg_map,
        week_reg_map=mirror_week_reg_map,
    )

    # ─────────────────────────────────────────────────────────────────────────
    # ШАГ 12: Применяем completed_* метрики из mirror-loop
    # ─────────────────────────────────────────────────────────────────────────
    for row in rows_payload:
        week_key = str(row.get("week_start") or "")
        company = str(row.get("company") or "")
        metric_sets = completion_company_sets.get((week_key, company))
        if not metric_sets:
            continue
        for metric_key in completed_keys:
            row[metric_key] = len(metric_sets[metric_key])
        row["advanced_completed_uniq"] = len(set().union(*(metric_sets[k] for k in advanced_completed_keys)))
        row["advanced_completed_total"] = sum(len(metric_sets[k]) for k in advanced_completed_keys)

    for row in bot_rows_payload:
        week_key = str(row.get("week_start") or "")
        company = str(row.get("company") or "")
        bot_key = str(row.get("bot_key") or "")
        metric_sets = completion_bot_sets.get((week_key, company, bot_key))
        if not metric_sets:
            continue
        for metric_key in completed_keys:
            row[metric_key] = len(metric_sets[metric_key])
        row["advanced_completed_uniq"] = len(set().union(*(metric_sets[k] for k in advanced_completed_keys)))
        row["advanced_completed_total"] = sum(len(metric_sets[k]) for k in advanced_completed_keys)

    for row in week_totals_payload:
        week_key = str(row.get("week_start") or "")
        metric_sets = completion_week_sets.get(week_key)
        if not metric_sets:
            continue
        for metric_key in completed_keys:
            row[metric_key] = len(metric_sets[metric_key])
        row["advanced_completed_uniq"] = len(set().union(*(metric_sets[k] for k in advanced_completed_keys)))
        row["advanced_completed_total"] = sum(len(metric_sets[k]) for k in advanced_completed_keys)

    # ─────────────────────────────────────────────────────────────────────────
    # ШАГ 13: Cohort-loop (оставлен для совместимости, cohort_only_keys пуст)
    # started_* берём из lesson_reg_query (шаг 6), не из cohort
    # ─────────────────────────────────────────────────────────────────────────
    started_company_sets: dict[tuple[str, str], dict[str, set[str]]] = defaultdict(
        lambda: {key: set() for key in started_direction_keys}
    )
    started_bot_sets: dict[tuple[str, str, str], dict[str, set[str]]] = defaultdict(
        lambda: {key: set() for key in started_direction_keys}
    )
    started_week_sets: dict[str, dict[str, set[str]]] = defaultdict(
        lambda: {key: set() for key in started_direction_keys}
    )

    lc_company_sql = normalized_company_sql.replace("advertising_company", "r.advertising_company")
    cohort_query = sa_text(f"""
        WITH first_seen AS (
            SELECT tg_user_id, MIN(created_at) AS first_seen_at_system
            FROM raw_bot_users
            WHERE LOWER(TRIM(COALESCE(bot_key, ''))) <> ALL(:excluded_bot_keys)
            GROUP BY tg_user_id
        ),
        {cohort_cte}
        start_rows AS (
            SELECT DISTINCT ON (r.tg_user_id, COALESCE(NULLIF(BTRIM(r.bot_key), ''), 'Без бота'))
                r.tg_user_id
            FROM raw_bot_users r
            JOIN first_seen fs ON fs.tg_user_id = r.tg_user_id
            {cohort_join}
            WHERE LOWER(TRIM(COALESCE(r.bot_key, ''))) <> ALL(:excluded_bot_keys)
              AND r.created_at IS NOT NULL
              AND (CAST(:start AS date) IS NULL OR (r.created_at AT TIME ZONE 'Europe/Moscow')::date >= CAST(:start AS date))
              AND (CAST(:end AS date) IS NULL OR (r.created_at AT TIME ZONE 'Europe/Moscow')::date <= CAST(:end AS date))
            ORDER BY r.tg_user_id, COALESCE(NULLIF(BTRIM(r.bot_key), ''), 'Без бота'), r.created_at
        ),
        lead_rows AS (
            SELECT DISTINCT ON (r.tg_user_id)
                r.tg_user_id,
                r.created_at AS lead_created_at,
                date_trunc('week', r.created_at AT TIME ZONE 'Europe/Moscow')::date AS week_start,
                {lc_company_sql} AS lead_company,
                COALESCE(NULLIF(BTRIM(r.bot_key), ''), 'Без бота') AS lead_bot_key,
                COALESCE(NULLIF(BTRIM(r.first_touch_bot), ''), NULL) AS first_touch_bot,
                COALESCE(NULLIF(BTRIM(r.last_touch_bot), ''), NULL) AS last_touch_bot
            FROM raw_bot_users r
            WHERE r.tg_user_id IN (SELECT tg_user_id FROM start_rows)
              AND lower(trim(COALESCE(r.bot_key, ''))) LIKE 'lead%'
              AND LOWER(TRIM(COALESCE(r.bot_key, ''))) <> ALL(:excluded_bot_keys)
              AND r.created_at IS NOT NULL
            ORDER BY r.tg_user_id, r.created_at
        ),
        attributed_leads AS (
            SELECT
                lr.tg_user_id,
                lr.week_start,
                COALESCE(src.company, lr.lead_company) AS company,
                COALESCE(src.bot_key, lr.lead_bot_key) AS bot_key
            FROM lead_rows lr
            LEFT JOIN LATERAL (
                SELECT
                    {normalized_company_sql.replace("advertising_company", "src.advertising_company")} AS company,
                    COALESCE(NULLIF(BTRIM(src.bot_key), ''), 'Без бота') AS bot_key
                FROM raw_bot_users src
                WHERE src.tg_user_id = lr.tg_user_id
                  AND LOWER(TRIM(COALESCE(src.bot_key, ''))) <> ALL(:excluded_bot_keys)
                  AND lower(trim(COALESCE(src.bot_key, ''))) NOT LIKE 'lead%'
                  AND src.created_at IS NOT NULL
                  AND (
                        (:mode = 'event' AND src.created_at <= lr.lead_created_at)
                     OR (:mode = 'first_touch' AND lr.first_touch_bot IS NOT NULL AND src.created_at <= lr.lead_created_at AND src.bot_key = lr.first_touch_bot)
                     OR (:mode = 'last_touch' AND lr.last_touch_bot IS NOT NULL AND src.created_at <= lr.lead_created_at AND src.bot_key = lr.last_touch_bot)
                     OR (:mode NOT IN ('event', 'first_touch', 'last_touch') AND src.created_at <= lr.lead_created_at)
                  ){source_touch_filter_sql}
                ORDER BY src.created_at DESC
                LIMIT 1
            ) src ON TRUE
        ),
        user_flags AS (
            SELECT
                ru.tg_user_id,
                (MIN(ru.ph_user_id) FILTER (WHERE ru.ph_user_id IS NOT NULL AND ru.platform_registered_at IS NOT NULL))::text AS ph_user_id,
                BOOL_OR(
                    lower(trim(COALESCE(ru.bot_key, ''))) LIKE 'lead%'
                    AND ru.tg_user_id > 0
                    AND ru.ph_user_id IS NOT NULL
                    AND abs(ru.tg_user_id) = ru.ph_user_id
                ) AS is_direct_source
            FROM raw_bot_users ru
            WHERE ru.tg_user_id IN (SELECT tg_user_id FROM attributed_leads)
              AND LOWER(TRIM(COALESCE(ru.bot_key, ''))) <> ALL(:excluded_bot_keys)
            GROUP BY ru.tg_user_id
        )
        SELECT DISTINCT
            al.week_start,
            al.company,
            al.bot_key,
            uf.ph_user_id
        FROM attributed_leads al
        JOIN user_flags uf ON uf.tg_user_id = al.tg_user_id
        WHERE uf.ph_user_id IS NOT NULL
          AND NOT uf.is_direct_source
    """)
    cohort_result = await session.execute(cohort_query, params)

    for cohort_row in cohort_result.fetchall():
        ph_id = str(cohort_row.ph_user_id or "").strip()
        cohort_week_start = _normalize_date(cohort_row.week_start)
        if not ph_id or cohort_week_start is None:
            continue
        summary = summary_by_ph_id.get(ph_id)
        if not isinstance(summary, dict):
            continue
        company = str(cohort_row.company or "Без категории")
        bot_key = str(cohort_row.bot_key or "Без бота")
        week_key = _week_start_key(cohort_week_start)
        if not week_key:
            continue

        courses = summary.get("courses") if isinstance(summary.get("courses"), dict) else {}
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
        base_entries = courses.get("BASE") or []

        def _is_base_terminal(entry: Any) -> bool:
            if not isinstance(entry, dict):
                return False
            if entry.get("date") is None:
                return False
            try:
                return int(entry.get("lesson")) == 5
            except Exception:
                return False

        base_completed = any(_is_base_terminal(entry) for entry in base_entries)

        def _course_present_any(*course_names: str) -> bool:
            for course_name in course_names:
                entries = courses.get(course_name) or []
                if isinstance(entries, list) and len(entries) > 0:
                    return True
                if course_name in memberships:
                    return True
            if base_completed and ("MTT_NEW" in course_names):
                if "MTT1" in raw_course_labels or "mtt after base couse" in summary_groups:
                    return True
            if base_completed and ("SPIN_NEW" in course_names):
                if "SPIN1" in raw_course_labels or "spin after base couse" in summary_groups:
                    return True
            return False

        direction_course_map = (
            ("started_base", ("BASE",)),
            ("started_mtt", ("MTT_NEW", "MTT")),
            ("started_spin", ("SPIN_NEW", "SPIN")),
            ("started_cash", ("CASH",)),
        )

        for metric_key, course_names in direction_course_map:
            if not _course_present_any(*course_names):
                continue
            started_company_sets[(week_key, company)][metric_key].add(ph_id)
            started_bot_sets[(week_key, company, bot_key)][metric_key].add(ph_id)
            started_week_sets[week_key][metric_key].add(ph_id)

    # cohort_only_keys пуст — started_* берём из lesson_reg_query (шаг 6)
    cohort_only_keys: tuple = ()
    for row in rows_payload:
        week_key = str(row.get("week_start") or "")
        company = str(row.get("company") or "")
        metric_sets = started_company_sets.get((week_key, company))
        if not metric_sets:
            continue
        for metric_key in cohort_only_keys:
            row[metric_key] = len(metric_sets[metric_key])

    for row in bot_rows_payload:
        week_key = str(row.get("week_start") or "")
        company = str(row.get("company") or "")
        bot_key = str(row.get("bot_key") or "")
        metric_sets = started_bot_sets.get((week_key, company, bot_key))
        if not metric_sets:
            continue
        for metric_key in cohort_only_keys:
            row[metric_key] = len(metric_sets[metric_key])

    for row in week_totals_payload:
        week_key = str(row.get("week_start") or "")
        metric_sets = started_week_sets.get(week_key)
        if not metric_sets:
            continue
        for metric_key in cohort_only_keys:
            row[metric_key] = len(metric_sets[metric_key])


async def _apply_business_overrides(
    *,
    session,
    sa_text,
    params,
    display_mode: str,
    normalized_company_sql: str,
    source_touch_filter_sql: str,
    rows_payload: list[dict[str, Any]],
    bot_rows_payload: list[dict[str, Any]],
    week_totals_payload: list[dict[str, Any]],
) -> None:
    source_touch_filter_sql_r = source_touch_filter_sql.replace("src.", "r.")

    starts_query = sa_text(f"""
        SELECT
            date_trunc('week', r.created_at AT TIME ZONE 'Europe/Moscow')::date AS week_start,
            {normalized_company_sql.replace("advertising_company", "r.advertising_company")} AS company,
            COALESCE(NULLIF(BTRIM(r.bot_key), ''), 'Без бота') AS bot_key,
            COUNT(DISTINCT r.tg_user_id) AS starts_cnt
        FROM raw_bot_users r
        WHERE LOWER(TRIM(COALESCE(r.bot_key, ''))) <> ALL(:excluded_bot_keys)
          AND lower(trim(COALESCE(r.bot_key, ''))) NOT LIKE 'lead%'
          AND r.created_at IS NOT NULL
          AND (CAST(:start AS date) IS NULL OR (r.created_at AT TIME ZONE 'Europe/Moscow')::date >= CAST(:start AS date))
          AND (CAST(:end AS date) IS NULL OR (r.created_at AT TIME ZONE 'Europe/Moscow')::date <= CAST(:end AS date))
          {source_touch_filter_sql_r}
        GROUP BY 1, 2, 3
    """)
    starts_rows = (await session.execute(starts_query, params)).fetchall()
    company_starts: dict[tuple[str, str], int] = {}
    bot_starts: dict[tuple[str, str, str], int] = {}
    week_starts: dict[str, int] = {}
    for row in starts_rows:
        wk = row.week_start.isoformat()
        v = int(row.starts_cnt or 0)
        company_starts[(wk, row.company)] = company_starts.get((wk, row.company), 0) + v
        bot_starts[(wk, row.company, row.bot_key)] = bot_starts.get((wk, row.company, row.bot_key), 0) + v
        week_starts[wk] = week_starts.get(wk, 0) + v

    almanah_query = sa_text(f"""
        WITH lead_rows AS (
            SELECT DISTINCT ON (r.tg_user_id)
                r.tg_user_id,
                r.created_at AS lead_created_at,
                date_trunc('week', r.created_at AT TIME ZONE 'Europe/Moscow')::date AS week_start
            FROM raw_bot_users r
            WHERE lower(trim(COALESCE(r.bot_key, ''))) LIKE 'lead%'
              AND r.tg_user_id > 0
              AND LOWER(TRIM(COALESCE(r.bot_key, ''))) <> ALL(:excluded_bot_keys)
              AND r.created_at IS NOT NULL
              AND (CAST(:start AS date) IS NULL OR (r.created_at AT TIME ZONE 'Europe/Moscow')::date >= CAST(:start AS date))
              AND (CAST(:end AS date) IS NULL OR (r.created_at AT TIME ZONE 'Europe/Moscow')::date <= CAST(:end AS date))
            ORDER BY r.tg_user_id, r.created_at
        ),
        attributed AS (
            SELECT
                lr.tg_user_id,
                lr.week_start,
                COALESCE(src.company, 'Без категории') AS company,
                COALESCE(src.bot_key, 'Без бота') AS bot_key
            FROM lead_rows lr
            LEFT JOIN LATERAL (
                SELECT
                    {normalized_company_sql.replace("advertising_company", "src.advertising_company")} AS company,
                    COALESCE(NULLIF(BTRIM(src.bot_key), ''), 'Без бота') AS bot_key
                FROM raw_bot_users src
                WHERE src.tg_user_id = lr.tg_user_id
                  AND LOWER(TRIM(COALESCE(src.bot_key, ''))) <> ALL(:excluded_bot_keys)
                  AND lower(trim(COALESCE(src.bot_key, ''))) NOT LIKE 'lead%'
                  AND src.created_at IS NOT NULL
                  AND src.created_at <= lr.lead_created_at
                  {source_touch_filter_sql}
                ORDER BY src.created_at DESC
                LIMIT 1
            ) src ON TRUE
        )
        SELECT week_start, company, bot_key, COUNT(DISTINCT tg_user_id) AS cnt
        FROM attributed
        GROUP BY 1, 2, 3
    """)
    almanah_rows = (await session.execute(almanah_query, params)).fetchall()
    company_almanah: dict[tuple[str, str], int] = {}
    bot_almanah: dict[tuple[str, str, str], int] = {}
    week_almanah: dict[str, int] = {}
    for row in almanah_rows:
        wk = row.week_start.isoformat()
        v = int(row.cnt or 0)
        company_almanah[(wk, row.company)] = company_almanah.get((wk, row.company), 0) + v
        bot_almanah[(wk, row.company, row.bot_key)] = bot_almanah.get((wk, row.company, row.bot_key), 0) + v
        week_almanah[wk] = week_almanah.get(wk, 0) + v

    sm_query = sa_text(f"""
        WITH sm_events AS (
            SELECT DISTINCT ON (r.tg_user_id)
                r.tg_user_id,
                r.offer_received,
                r.contract_signed,
                (r.offer_received_at AT TIME ZONE 'Europe/Moscow')::date AS offer_date,
                (r.contract_signed_at AT TIME ZONE 'Europe/Moscow')::date AS contract_date
            FROM raw_bot_users r
            WHERE lower(trim(COALESCE(r.bot_key, ''))) LIKE 'lead%'
              AND LOWER(TRIM(COALESCE(r.bot_key, ''))) <> ALL(:excluded_bot_keys)
            ORDER BY r.tg_user_id, r.created_at DESC NULLS LAST
        ),
        expanded AS (
            SELECT tg_user_id, 'offer'::text AS metric, offer_date AS event_date
            FROM sm_events
            WHERE offer_received IS TRUE AND offer_date IS NOT NULL
            UNION ALL
            SELECT tg_user_id, 'contract'::text AS metric, contract_date AS event_date
            FROM sm_events
            WHERE contract_signed IS TRUE AND contract_date IS NOT NULL
        ),
        ranged AS (
            SELECT * FROM expanded
            WHERE (CAST(:start AS date) IS NULL OR event_date >= CAST(:start AS date))
              AND (CAST(:end AS date) IS NULL OR event_date <= CAST(:end AS date))
        ),
        attributed AS (
            SELECT
                e.metric,
                e.event_date,
                e.tg_user_id,
                COALESCE(src.company, 'Без категории') AS company,
                COALESCE(src.bot_key, 'Без бота') AS bot_key
            FROM ranged e
            LEFT JOIN LATERAL (
                SELECT
                    {normalized_company_sql.replace("advertising_company", "src.advertising_company")} AS company,
                    COALESCE(NULLIF(BTRIM(src.bot_key), ''), 'Без бота') AS bot_key
                FROM raw_bot_users src
                WHERE src.tg_user_id = e.tg_user_id
                  AND LOWER(TRIM(COALESCE(src.bot_key, ''))) <> ALL(:excluded_bot_keys)
                  AND lower(trim(COALESCE(src.bot_key, ''))) NOT LIKE 'lead%'
                  AND src.created_at IS NOT NULL
                  {source_touch_filter_sql}
                ORDER BY src.created_at DESC
                LIMIT 1
            ) src ON TRUE
        )
        SELECT
            date_trunc('week', event_date)::date AS week_start,
            company,
            bot_key,
            COUNT(DISTINCT tg_user_id) FILTER (WHERE metric = 'offer') AS offer_cnt,
            COUNT(DISTINCT tg_user_id) FILTER (WHERE metric = 'contract') AS contract_cnt
        FROM attributed
        GROUP BY 1, 2, 3
    """)
    sm_rows = (await session.execute(sm_query, params)).fetchall()
    company_sm: dict[tuple[str, str], tuple[int, int]] = {}
    bot_sm: dict[tuple[str, str, str], tuple[int, int]] = {}
    week_sm: dict[str, tuple[int, int]] = {}
    for row in sm_rows:
        wk = row.week_start.isoformat()
        off = int(row.offer_cnt or 0)
        con = int(row.contract_cnt or 0)
        po, pc = company_sm.get((wk, row.company), (0, 0))
        bo, bc = bot_sm.get((wk, row.company, row.bot_key), (0, 0))
        wo, wc = week_sm.get(wk, (0, 0))
        company_sm[(wk, row.company)] = (po + off, pc + con)
        bot_sm[(wk, row.company, row.bot_key)] = (bo + off, bc + con)
        week_sm[wk] = (wo + off, wc + con)

    direct_query = sa_text(f"""
        WITH direct_candidates AS (
            SELECT DISTINCT ON (r.ph_user_id)
                r.ph_user_id,
                r.tg_user_id,
                r.created_at AS lead_created_at,
                date_trunc('week', r.created_at AT TIME ZONE 'Europe/Moscow')::date AS week_start
            FROM raw_bot_users r
            WHERE lower(trim(COALESCE(r.bot_key, ''))) LIKE 'lead%'
              AND r.ph_user_id IS NOT NULL
              AND (
                    r.tg_user_id IS NULL
                    OR r.tg_user_id <= 0
                    OR abs(r.tg_user_id) = r.ph_user_id
                  )
              AND LOWER(TRIM(COALESCE(r.bot_key, ''))) <> ALL(:excluded_bot_keys)
              AND r.created_at IS NOT NULL
              AND (CAST(:start AS date) IS NULL OR (r.created_at AT TIME ZONE 'Europe/Moscow')::date >= CAST(:start AS date))
              AND (CAST(:end AS date) IS NULL OR (r.created_at AT TIME ZONE 'Europe/Moscow')::date <= CAST(:end AS date))
            ORDER BY r.ph_user_id, r.created_at
        ),
        direct_only AS (
            SELECT dc.*
            FROM direct_candidates dc
            WHERE NOT EXISTS (
                SELECT 1
                FROM raw_bot_users src
                WHERE src.ph_user_id = dc.ph_user_id
                  AND LOWER(TRIM(COALESCE(src.bot_key, ''))) <> ALL(:excluded_bot_keys)
                  AND lower(trim(COALESCE(src.bot_key, ''))) NOT LIKE 'lead%'
            )
        ),
        attributed AS (
            SELECT
                d.ph_user_id,
                d.week_start,
                COALESCE(src.company, 'Без категории') AS company,
                COALESCE(src.bot_key, 'Без бота') AS bot_key
            FROM direct_only d
            LEFT JOIN LATERAL (
                SELECT
                    {normalized_company_sql.replace("advertising_company", "src.advertising_company")} AS company,
                    COALESCE(NULLIF(BTRIM(src.bot_key), ''), 'Без бота') AS bot_key
                FROM raw_bot_users src
                WHERE src.ph_user_id = d.ph_user_id
                  AND LOWER(TRIM(COALESCE(src.bot_key, ''))) <> ALL(:excluded_bot_keys)
                  AND src.created_at IS NOT NULL
                  {source_touch_filter_sql}
                ORDER BY src.created_at DESC
                LIMIT 1
            ) src ON TRUE
        )
        SELECT week_start, company, bot_key, COUNT(DISTINCT ph_user_id) AS direct_cnt
        FROM attributed
        GROUP BY 1, 2, 3
    """)
    direct_rows = (await session.execute(direct_query, params)).fetchall()
    company_direct: dict[tuple[str, str], int] = {}
    bot_direct: dict[tuple[str, str, str], int] = {}
    week_direct: dict[str, int] = {}
    for row in direct_rows:
        wk = row.week_start.isoformat()
        v = int(row.direct_cnt or 0)
        company_direct[(wk, row.company)] = company_direct.get((wk, row.company), 0) + v
        bot_direct[(wk, row.company, row.bot_key)] = bot_direct.get((wk, row.company, row.bot_key), 0) + v
        week_direct[wk] = week_direct.get(wk, 0) + v

    for row in rows_payload:
        wk = str(row.get("week_start"))
        company = str(row.get("company", ""))
        row["entered_all"] = int(company_starts.get((wk, company), 0))
        row["almanah_starts"] = int(company_almanah.get((wk, company), 0))
        off, con = company_sm.get((wk, company), (0, 0))
        row["offer_received"] = int(off)
        row["contract_signed"] = int(con)
        row["direct_source_cnt"] = int(company_direct.get((wk, company), 0))
    for row in bot_rows_payload:
        wk = str(row.get("week_start"))
        company = str(row.get("company", ""))
        bot_key = str(row.get("bot_key", ""))
        row["entered_all"] = int(bot_starts.get((wk, company, bot_key), 0))
        row["almanah_starts"] = int(bot_almanah.get((wk, company, bot_key), 0))
        off, con = bot_sm.get((wk, company, bot_key), (0, 0))
        row["offer_received"] = int(off)
        row["contract_signed"] = int(con)
        row["direct_source_cnt"] = int(bot_direct.get((wk, company, bot_key), 0))
    for row in week_totals_payload:
        wk = str(row.get("week_start"))
        row["entered_all"] = int(week_starts.get(wk, 0))
        row["almanah_starts"] = int(week_almanah.get(wk, 0))
        off, con = week_sm.get(wk, (0, 0))
        row["offer_received"] = int(off)
        row["contract_signed"] = int(con)
        row["direct_source_cnt"] = int(week_direct.get(wk, 0))


async def _apply_cohort_business_overrides(
    *,
    session,
    sa_text,
    params,
    normalized_company_sql: str,
    source_touch_filter_sql: str,
    rows_payload: list[dict[str, Any]],
    bot_rows_payload: list[dict[str, Any]],
) -> None:
    cohort_query = sa_text(f"""
        WITH cohort_starts AS (
            SELECT DISTINCT ON (r.tg_user_id, COALESCE(NULLIF(BTRIM(r.bot_key), ''), 'Без бота'))
                r.tg_user_id,
                {normalized_company_sql.replace("advertising_company", "r.advertising_company")} AS company,
                COALESCE(NULLIF(BTRIM(r.bot_key), ''), 'Без бота') AS bot_key,
                date_trunc('week', r.created_at AT TIME ZONE 'Europe/Moscow')::date AS week_start,
                r.created_at AS start_created_at
            FROM raw_bot_users r
            WHERE LOWER(TRIM(COALESCE(r.bot_key, ''))) <> ALL(:excluded_bot_keys)
              AND lower(trim(COALESCE(r.bot_key, ''))) NOT LIKE 'lead%'
              AND r.created_at IS NOT NULL
              AND (CAST(:start AS date) IS NULL OR (r.created_at AT TIME ZONE 'Europe/Moscow')::date >= CAST(:start AS date))
              AND (CAST(:end AS date) IS NULL OR (r.created_at AT TIME ZONE 'Europe/Moscow')::date <= CAST(:end AS date))
              {source_touch_filter_sql.replace('src.', 'r.')}
            ORDER BY r.tg_user_id, COALESCE(NULLIF(BTRIM(r.bot_key), ''), 'Без бота'), r.created_at
        ),
        cohort_users AS (
            SELECT
                cs.tg_user_id,
                cs.company,
                cs.bot_key,
                cs.week_start,
                MIN(ru.ph_user_id) FILTER (WHERE ru.ph_user_id IS NOT NULL) AS ph_user_id,
                BOOL_OR(
                    ru.converted_to_lead IS TRUE
                    OR lower(trim(COALESCE(ru.bot_key, ''))) LIKE 'lead%'
                ) AS did_lead,
                BOOL_OR(
                    ru.ph_user_id IS NOT NULL
                    AND ru.registered_platform IS TRUE
                    AND ru.platform_registered_at IS NOT NULL
                ) AS did_platform,
                BOOL_OR(ru.started_learning IS TRUE) AS did_learning
            FROM cohort_starts cs
            LEFT JOIN raw_bot_users ru ON ru.tg_user_id = cs.tg_user_id
            GROUP BY cs.tg_user_id, cs.company, cs.bot_key, cs.week_start
        ),
        lesson_first AS (
            SELECT
                pm.ph_id::bigint AS ph_user_id,
                (pm.ph_registration_at::timestamptz AT TIME ZONE 'Europe/Moscow')::date AS ph_reg_date,
                MIN((((regexp_match(lesson.value, '\\(([^()]+)\\)$'))[1])::timestamptz AT TIME ZONE 'Europe/Moscow')::date)
                    FILTER (WHERE lesson.value LIKE 'Базовый курс:%' OR lesson.value LIKE 'MTT1:%' OR lesson.value LIKE 'MTT2:%' OR lesson.value LIKE 'SPIN1:%' OR lesson.value LIKE 'CASH1:%') AS learning_date,
                MIN((((regexp_match(lesson.value, '\\(([^()]+)\\)$'))[1])::timestamptz AT TIME ZONE 'Europe/Moscow')::date)
                    FILTER (WHERE lesson.value LIKE 'Базовый курс:%') AS base_date,
                MIN((((regexp_match(lesson.value, '\\(([^()]+)\\)$'))[1])::timestamptz AT TIME ZONE 'Europe/Moscow')::date)
                    FILTER (WHERE lesson.value LIKE 'МТТ%' OR lesson.value LIKE 'MTT%') AS mtt_date,
                MIN((((regexp_match(lesson.value, '\\(([^()]+)\\)$'))[1])::timestamptz AT TIME ZONE 'Europe/Moscow')::date)
                    FILTER (WHERE lesson.value LIKE 'СПИН%' OR lesson.value LIKE 'SPIN%') AS spin_date,
                MIN((((regexp_match(lesson.value, '\\(([^()]+)\\)$'))[1])::timestamptz AT TIME ZONE 'Europe/Moscow')::date)
                    FILTER (WHERE lesson.value LIKE 'CASH1:%') AS cash_date
            FROM ph_user_mirror_replica pm
            LEFT JOIN LATERAL jsonb_array_elements_text(COALESCE(pm.lessons::jsonb, '[]'::jsonb)) AS lesson(value) ON TRUE
            WHERE pm.ph_id ~ '^[0-9]+$'
            GROUP BY pm.ph_id, pm.ph_registration_at
        ),
        stage_metrics AS (
            SELECT
                cu.week_start,
                cu.company,
                cu.bot_key,
                COUNT(DISTINCT cu.tg_user_id) AS entered_all,
                COUNT(DISTINCT cu.tg_user_id) FILTER (WHERE cu.did_lead) AS almanah_starts,
                COUNT(DISTINCT cu.ph_user_id) FILTER (WHERE cu.did_platform) AS platform_cnt,
                COUNT(DISTINCT cu.ph_user_id) FILTER (WHERE cu.did_platform AND cu.did_learning) AS started_learning,
                COUNT(DISTINCT cu.ph_user_id) FILTER (WHERE cu.did_platform AND cu.did_learning AND lf.base_date IS NOT NULL) AS started_base,
                COUNT(DISTINCT cu.ph_user_id) FILTER (WHERE cu.did_platform AND cu.did_learning AND lf.mtt_date IS NOT NULL) AS started_mtt,
                COUNT(DISTINCT cu.ph_user_id) FILTER (WHERE cu.did_platform AND cu.did_learning AND lf.spin_date IS NOT NULL) AS started_spin,
                COUNT(DISTINCT cu.ph_user_id) FILTER (WHERE cu.did_platform AND cu.did_learning AND lf.cash_date IS NOT NULL) AS started_cash,
                COUNT(DISTINCT cu.tg_user_id) FILTER (
                    WHERE EXISTS (
                        SELECT 1 FROM raw_bot_users l
                        WHERE l.tg_user_id = cu.tg_user_id
                          AND l.offer_received IS TRUE
                          AND l.offer_received_at IS NOT NULL
                          AND (l.offer_received_at AT TIME ZONE 'Europe/Moscow')::date >= cu.week_start
                          AND (l.offer_received_at AT TIME ZONE 'Europe/Moscow')::date < cu.week_start + INTERVAL '7 day'
                    )
                ) AS offer_received,
                COUNT(DISTINCT cu.tg_user_id) FILTER (
                    WHERE EXISTS (
                        SELECT 1 FROM raw_bot_users l
                        WHERE l.tg_user_id = cu.tg_user_id
                          AND l.contract_signed IS TRUE
                          AND l.contract_signed_at IS NOT NULL
                          AND (l.contract_signed_at AT TIME ZONE 'Europe/Moscow')::date >= cu.week_start
                          AND (l.contract_signed_at AT TIME ZONE 'Europe/Moscow')::date < cu.week_start + INTERVAL '7 day'
                    )
                ) AS contract_signed
            FROM cohort_users cu
            LEFT JOIN lesson_first lf ON lf.ph_user_id = cu.ph_user_id
            GROUP BY cu.week_start, cu.company, cu.bot_key
        )
        SELECT
            sm.week_start,
            sm.company,
            sm.bot_key,
            sm.entered_all,
            sm.almanah_starts,
            sm.platform_cnt,
            sm.started_learning,
            sm.started_base,
            sm.started_mtt,
            sm.started_spin,
            sm.started_cash,
            sm.offer_received,
            sm.contract_signed
        FROM stage_metrics sm
    """)
    rows = (await session.execute(cohort_query, params)).fetchall()
    row_map = {
        (row.week_start.isoformat(), str(row.company), str(row.bot_key)): row
        for row in rows
    }
    company_totals: dict[tuple[str, str], dict[str, int]] = {}
    for row in rows:
        key = (row.week_start.isoformat(), str(row.company))
        bucket = company_totals.setdefault(
            key,
            {
                "entered_all": 0,
                "almanah_starts": 0,
                "platform_cnt": 0,
                "started_learning": 0,
                "started_base": 0,
                "started_mtt": 0,
                "started_spin": 0,
                "started_cash": 0,
                "offer_received": 0,
                "contract_signed": 0,
            },
        )
        for field in bucket:
            bucket[field] += int(getattr(row, field) or 0)

    for payload_row in bot_rows_payload:
        key = (str(payload_row.get("week_start")), str(payload_row.get("company", "")), str(payload_row.get("bot_key", "")))
        item = row_map.get(key)
        if item is None:
            continue
        payload_row["entered_all"] = int(item.entered_all or 0)
        payload_row["almanah_starts"] = int(item.almanah_starts or 0)
        payload_row["platform_cnt"] = int(item.platform_cnt or 0)
        payload_row["started_learning"] = int(item.started_learning or 0)
        payload_row["base"] = int(item.started_base or 0)
        payload_row["mtt"] = int(item.started_mtt or 0)
        payload_row["spin"] = int(item.started_spin or 0)
        payload_row["cash"] = int(item.started_cash or 0)
        payload_row["offer_received"] = int(item.offer_received or 0)
        payload_row["contract_signed"] = int(item.contract_signed or 0)
        payload_row["not_started"] = max(payload_row["platform_cnt"] - payload_row["started_learning"], 0)

    for payload_row in rows_payload:
        key = (str(payload_row.get("week_start")), str(payload_row.get("company", "")))
        item = company_totals.get(key)
        if item is None:
            continue
        for field, value in item.items():
            payload_row[field] = int(value)
        payload_row["base"] = int(item["started_base"])
        payload_row["mtt"] = int(item["started_mtt"])
        payload_row["spin"] = int(item["started_spin"])
        payload_row["cash"] = int(item["started_cash"])
        payload_row["not_started"] = max(int(item["platform_cnt"]) - int(item["started_learning"]), 0)
        payload_row["direct_source_cnt"] = 0
