# Cohort mode override для Roistat companies:
# В cohort режиме platform/learning/course/completed метрики считаются по дате события (не по дате лида).
# Запрос stage_events строит UNION ALL из 13 метрик с event_date по каждому пользователю.
# Результат перезаписывает EVENT_METRIC_KEYS в rows_payload/bot_rows/week_totals.
# Если DB вернул 0 строк (нет данных) — override не применяется, оставляем исходные значения.

from typing import Any

from app.api.routers.reports_roistat_companies_postprocess_shared import (
    EVENT_METRIC_KEYS,
    METRIC_KEYS,
)


async def apply_cohort_stage_override(
    *,
    session,
    sa_text,
    params,
    cohort_cte: str,
    cohort_join: str,
    utm_filter_sql: str,
    normalized_company_sql: str,
    source_touch_filter_sql: str,
    rows_payload: list[dict[str, Any]],
    bot_rows_payload: list[dict[str, Any]],
    week_totals_payload: list[dict[str, Any]],
) -> None:
    event_stage_query = sa_text(f"""
    WITH first_seen AS (
        SELECT tg_user_id, MIN(created_at) AS first_seen_at_system
        FROM raw_bot_users
        WHERE LOWER(TRIM(COALESCE(bot_key, ''))) <> ALL(:excluded_bot_keys)
        GROUP BY tg_user_id
    ),
    {cohort_cte}
    lead_rows AS (
        SELECT DISTINCT ON (r.tg_user_id)
            r.tg_user_id,
            {normalized_company_sql.replace("advertising_company", "r.advertising_company")} AS lead_company,
            COALESCE(NULLIF(BTRIM(r.bot_key), ''), 'Без бота') AS lead_bot_key,
            COALESCE(NULLIF(BTRIM(r.first_touch_bot), ''), NULL) AS first_touch_bot,
            COALESCE(NULLIF(BTRIM(r.last_touch_bot), ''), NULL) AS last_touch_bot,
            r.created_at AS lead_created_at
        FROM raw_bot_users r
        JOIN first_seen fs ON fs.tg_user_id = r.tg_user_id
        {cohort_join}
        WHERE lower(trim(r.bot_key)) LIKE 'lead%'
          AND r.tg_user_id > 0
          AND LOWER(TRIM(COALESCE(r.bot_key, ''))) <> ALL(:excluded_bot_keys)
          AND r.created_at IS NOT NULL{utm_filter_sql}
        ORDER BY r.tg_user_id, r.created_at
    ),
    attributed_leads AS (
        SELECT
            lr.tg_user_id,
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
    user_events AS (
        SELECT
            ru.tg_user_id,
            MIN(ru.ph_user_id) FILTER (
                WHERE ru.ph_user_id IS NOT NULL
            ) AS ph_user_id,
            MIN((ru.platform_registered_at AT TIME ZONE 'Europe/Moscow')::date) FILTER (
                WHERE ru.ph_user_id IS NOT NULL AND ru.platform_registered_at IS NOT NULL
            ) AS platform_date,
            MIN((ru.learn_start_date AT TIME ZONE 'Europe/Moscow')::date) FILTER (
                WHERE ru.learn_start_date IS NOT NULL
            ) AS learn_date,
            MIN((COALESCE(ru.learn_start_date, ru.platform_registered_at) AT TIME ZONE 'Europe/Moscow')::date) FILTER (
                WHERE TRIM(COALESCE(ru.start_course, '')) <> ''
            ) AS course_event_date,
            MIN((ru.completed_course_at AT TIME ZONE 'Europe/Moscow')::date) FILTER (
                WHERE ru.completed_course IS TRUE AND ru.completed_course_at IS NOT NULL
            ) AS completed_date,
            MIN((ru.interview_reached_at AT TIME ZONE 'Europe/Moscow')::date) FILTER (
                WHERE ru.interview_reached IS TRUE AND ru.interview_reached_at IS NOT NULL
            ) AS interview_reached_date,
            MIN((ru.offer_received_at AT TIME ZONE 'Europe/Moscow')::date) FILTER (
                WHERE ru.offer_received IS TRUE AND ru.offer_received_at IS NOT NULL
            ) AS offer_received_date,
            MIN((ru.contract_signed_at AT TIME ZONE 'Europe/Moscow')::date) FILTER (
                WHERE ru.contract_signed IS TRUE AND ru.contract_signed_at IS NOT NULL
            ) AS contract_signed_date,
            BOOL_OR(TRIM(COALESCE(ru.start_course, '')) <> '') AS did_course_registration,
            BOOL_OR(ru.interview_reached IS TRUE) AS did_interview_reached,
            BOOL_OR(ru.offer_received IS TRUE) AS did_offer_received,
            BOOL_OR(ru.contract_signed IS TRUE) AS did_contract_signed,
            BOOL_OR(LOWER(TRIM(COALESCE(ru.start_course, ''))) LIKE 'mtt%') AS is_mtt,
            BOOL_OR(LOWER(TRIM(COALESCE(ru.start_course, ''))) LIKE 'spin%') AS is_spin,
            BOOL_OR(LOWER(TRIM(COALESCE(ru.start_course, ''))) LIKE 'cash%') AS is_cash,
            BOOL_OR(LOWER(TRIM(COALESCE(ru.start_course, ''))) LIKE 'base%') AS is_base
        FROM raw_bot_users ru
        WHERE LOWER(TRIM(COALESCE(ru.bot_key, ''))) <> ALL(:excluded_bot_keys)
        GROUP BY ru.tg_user_id
    ),
    stage_events AS (
        SELECT al.company, al.bot_key, ue.platform_date AS event_date, 'platform_cnt' AS metric,
               COALESCE(ue.ph_user_id::text, ue.tg_user_id::text) AS entity_key
        FROM attributed_leads al JOIN user_events ue ON ue.tg_user_id = al.tg_user_id
        WHERE ue.platform_date IS NOT NULL AND ue.ph_user_id IS NOT NULL
        UNION ALL
        SELECT al.company, al.bot_key, ue.course_event_date, 'learning',
               COALESCE(ue.ph_user_id::text, ue.tg_user_id::text)
        FROM attributed_leads al JOIN user_events ue ON ue.tg_user_id = al.tg_user_id
        WHERE ue.course_event_date IS NOT NULL AND ue.did_course_registration AND ue.ph_user_id IS NOT NULL
        UNION ALL
        SELECT al.company, al.bot_key, ue.learn_date, 'started_learning',
               COALESCE(ue.ph_user_id::text, ue.tg_user_id::text)
        FROM attributed_leads al JOIN user_events ue ON ue.tg_user_id = al.tg_user_id
        WHERE ue.learn_date IS NOT NULL AND ue.ph_user_id IS NOT NULL
        UNION ALL
        SELECT al.company, al.bot_key, ue.course_event_date, 'mtt',
               COALESCE(ue.ph_user_id::text, ue.tg_user_id::text)
        FROM attributed_leads al JOIN user_events ue ON ue.tg_user_id = al.tg_user_id
        WHERE ue.course_event_date IS NOT NULL AND ue.is_mtt AND ue.ph_user_id IS NOT NULL
        UNION ALL
        SELECT al.company, al.bot_key, ue.course_event_date, 'spin',
               COALESCE(ue.ph_user_id::text, ue.tg_user_id::text)
        FROM attributed_leads al JOIN user_events ue ON ue.tg_user_id = al.tg_user_id
        WHERE ue.course_event_date IS NOT NULL AND ue.is_spin AND ue.ph_user_id IS NOT NULL
        UNION ALL
        SELECT al.company, al.bot_key, ue.course_event_date, 'cash',
               COALESCE(ue.ph_user_id::text, ue.tg_user_id::text)
        FROM attributed_leads al JOIN user_events ue ON ue.tg_user_id = al.tg_user_id
        WHERE ue.course_event_date IS NOT NULL AND ue.is_cash AND ue.ph_user_id IS NOT NULL
        UNION ALL
        SELECT al.company, al.bot_key, ue.course_event_date, 'base',
               COALESCE(ue.ph_user_id::text, ue.tg_user_id::text)
        FROM attributed_leads al JOIN user_events ue ON ue.tg_user_id = al.tg_user_id
        WHERE ue.course_event_date IS NOT NULL AND ue.is_base AND ue.ph_user_id IS NOT NULL
        UNION ALL
        SELECT al.company, al.bot_key, ue.platform_date, 'not_started',
               COALESCE(ue.ph_user_id::text, ue.tg_user_id::text)
        FROM attributed_leads al JOIN user_events ue ON ue.tg_user_id = al.tg_user_id
        WHERE ue.platform_date IS NOT NULL AND ue.learn_date IS NULL AND ue.ph_user_id IS NOT NULL
        UNION ALL
        SELECT al.company, al.bot_key, ue.completed_date, 'completed_course',
               COALESCE(ue.ph_user_id::text, ue.tg_user_id::text)
        FROM attributed_leads al JOIN user_events ue ON ue.tg_user_id = al.tg_user_id
        WHERE ue.completed_date IS NOT NULL AND ue.ph_user_id IS NOT NULL
        UNION ALL
        SELECT al.company, al.bot_key, ue.completed_date, 'completed_mtt',
               COALESCE(ue.ph_user_id::text, ue.tg_user_id::text)
        FROM attributed_leads al JOIN user_events ue ON ue.tg_user_id = al.tg_user_id
        WHERE ue.completed_date IS NOT NULL AND ue.is_mtt AND ue.ph_user_id IS NOT NULL
        UNION ALL
        SELECT al.company, al.bot_key, ue.completed_date, 'completed_spin',
               COALESCE(ue.ph_user_id::text, ue.tg_user_id::text)
        FROM attributed_leads al JOIN user_events ue ON ue.tg_user_id = al.tg_user_id
        WHERE ue.completed_date IS NOT NULL AND ue.is_spin AND ue.ph_user_id IS NOT NULL
        UNION ALL
        SELECT al.company, al.bot_key, ue.completed_date, 'completed_cash',
               COALESCE(ue.ph_user_id::text, ue.tg_user_id::text)
        FROM attributed_leads al JOIN user_events ue ON ue.tg_user_id = al.tg_user_id
        WHERE ue.completed_date IS NOT NULL AND ue.is_cash AND ue.ph_user_id IS NOT NULL
        UNION ALL
        SELECT al.company, al.bot_key, ue.completed_date, 'completed_base',
               COALESCE(ue.ph_user_id::text, ue.tg_user_id::text)
        FROM attributed_leads al JOIN user_events ue ON ue.tg_user_id = al.tg_user_id
        WHERE ue.completed_date IS NOT NULL AND ue.is_base AND ue.ph_user_id IS NOT NULL
        UNION ALL
        SELECT al.company, al.bot_key, COALESCE(ue.interview_reached_date, ue.completed_date), 'interview_reached',
               COALESCE(ue.ph_user_id::text, ue.tg_user_id::text)
        FROM attributed_leads al JOIN user_events ue ON ue.tg_user_id = al.tg_user_id
        WHERE ue.did_interview_reached
          AND COALESCE(ue.interview_reached_date, ue.completed_date) IS NOT NULL
          AND ue.ph_user_id IS NOT NULL
        UNION ALL
        SELECT al.company, al.bot_key, COALESCE(ue.offer_received_date, ue.interview_reached_date, ue.completed_date), 'offer_received',
               COALESCE(ue.ph_user_id::text, ue.tg_user_id::text)
        FROM attributed_leads al JOIN user_events ue ON ue.tg_user_id = al.tg_user_id
        WHERE ue.did_offer_received
          AND COALESCE(ue.offer_received_date, ue.interview_reached_date, ue.completed_date) IS NOT NULL
          AND ue.ph_user_id IS NOT NULL
        UNION ALL
        SELECT al.company, al.bot_key, COALESCE(ue.contract_signed_date, ue.offer_received_date, ue.interview_reached_date, ue.completed_date), 'contract_signed',
               COALESCE(ue.ph_user_id::text, ue.tg_user_id::text)
        FROM attributed_leads al JOIN user_events ue ON ue.tg_user_id = al.tg_user_id
        WHERE ue.did_contract_signed
          AND COALESCE(ue.contract_signed_date, ue.offer_received_date, ue.interview_reached_date, ue.completed_date) IS NOT NULL
          AND ue.ph_user_id IS NOT NULL
    )
    SELECT
        DATE_TRUNC('week', event_date)::date AS week_start,
        company,
        bot_key,
        COUNT(DISTINCT entity_key) FILTER (WHERE metric = 'platform_cnt') AS platform_cnt,
        COUNT(DISTINCT entity_key) FILTER (WHERE metric = 'learning') AS learning,
        COUNT(DISTINCT entity_key) FILTER (WHERE metric = 'started_learning') AS started_learning,
        COUNT(DISTINCT entity_key) FILTER (WHERE metric = 'mtt') AS mtt,
        COUNT(DISTINCT entity_key) FILTER (WHERE metric = 'spin') AS spin,
        COUNT(DISTINCT entity_key) FILTER (WHERE metric = 'cash') AS cash,
        COUNT(DISTINCT entity_key) FILTER (WHERE metric = 'base') AS base,
        COUNT(DISTINCT entity_key) FILTER (WHERE metric = 'not_started') AS not_started,
        COUNT(DISTINCT entity_key) FILTER (WHERE metric = 'completed_course') AS completed_course,
        COUNT(DISTINCT entity_key) FILTER (WHERE metric = 'completed_mtt') AS completed_mtt,
        COUNT(DISTINCT entity_key) FILTER (WHERE metric = 'completed_spin') AS completed_spin,
        COUNT(DISTINCT entity_key) FILTER (WHERE metric = 'completed_cash') AS completed_cash,
        COUNT(DISTINCT entity_key) FILTER (WHERE metric = 'completed_base') AS completed_base,
        COUNT(DISTINCT entity_key) FILTER (WHERE metric = 'interview_reached') AS interview_reached,
        COUNT(DISTINCT entity_key) FILTER (WHERE metric = 'offer_received') AS offer_received,
        COUNT(DISTINCT entity_key) FILTER (WHERE metric = 'contract_signed') AS contract_signed
    FROM stage_events
    WHERE (CAST(:start AS date) IS NULL OR event_date >= CAST(:start AS date))
      AND (CAST(:end AS date) IS NULL OR event_date <= CAST(:end AS date))
    GROUP BY 1, 2, 3
    """)
    event_stage_rows = (await session.execute(event_stage_query, params)).fetchall()

    has_stage_data = any(
        any(int(getattr(event_row, key) or 0) > 0 for key in EVENT_METRIC_KEYS)
        for event_row in event_stage_rows
    )

    if not has_stage_data:
        return

    _cohort_started_keys = ("started_base", "started_mtt", "started_spin", "started_cash",
                            "advanced_started_uniq", "advanced_started_total")
    for row in rows_payload + bot_rows_payload:
        for key in EVENT_METRIC_KEYS:
            row[key] = 0
        for key in _cohort_started_keys:
            row[key] = 0

    company_map = {(row["week_start"], row["company"]): row for row in rows_payload}
    bot_map = {(row["week_start"], row["company"], row["bot_key"]): row for row in bot_rows_payload}

    for event_row in event_stage_rows:
        week_key = event_row.week_start.isoformat()
        company_key = (week_key, event_row.company)
        company_row = company_map.get(company_key)
        if company_row is None:
            company_row = {
                "week_start": week_key,
                "company": event_row.company,
                "entered_all": 0,
                "budget": 0.0,
                **{k: 0 for k in METRIC_KEYS},
            }
            rows_payload.append(company_row)
            company_map[company_key] = company_row

        bot_key = (week_key, event_row.company, event_row.bot_key)
        bot_row = bot_map.get(bot_key)
        if bot_row is None:
            bot_row = {
                "week_start": week_key,
                "company": event_row.company,
                "bot_key": event_row.bot_key,
                "entered_all": 0,
                "budget": 0.0,
                **{k: 0 for k in METRIC_KEYS},
            }
            bot_rows_payload.append(bot_row)
            bot_map[bot_key] = bot_row

        for key in EVENT_METRIC_KEYS:
            value = int(getattr(event_row, key) or 0)
            company_row[key] += value
            bot_row[key] = value

    # Sync started_* from cohort base/mtt/spin/cash so that % BASE <= 100%.
    # In cohort mode EVENT_METRIC_KEYS overwrites base/mtt/spin/cash but leaves
    # started_base/started_mtt/started_spin/started_cash from lesson_reg_query,
    # which uses lesson-event dates — a different grouping that can exceed started_learning.
    for row in rows_payload + bot_rows_payload:
        row["started_base"] = row.get("base", 0)
        row["started_mtt"] = row.get("mtt", 0)
        row["started_spin"] = row.get("spin", 0)
        row["started_cash"] = row.get("cash", 0)
        _adv_total = row["started_mtt"] + row["started_spin"] + row["started_cash"]
        row["advanced_started_total"] = _adv_total
        # advanced_started_uniq: exact dedup needs set logic; upper bound is _adv_total
        row["advanced_started_uniq"] = _adv_total

    # В cohort/event режиме week_totals нужно собирать полностью из company rows,
    # иначе в parent-строках UI появляются нули по entered_all/budget и части метрик.
    week_totals_map: dict[str, dict[str, Any]] = {}
    for row in rows_payload:
        week_key = str(row.get("week_start") or "")
        week_total = week_totals_map.get(week_key)
        if week_total is None:
            week_total = {
                "week_start": week_key,
                "entered_all": 0,
                "budget": 0.0,
                **{k: 0 for k in METRIC_KEYS},
            }
            week_totals_map[week_key] = week_total

        week_total["entered_all"] += int(row.get("entered_all") or 0)
        week_total["budget"] += float(row.get("budget") or 0.0)
        for key in METRIC_KEYS:
            week_total[key] += int(row.get(key) or 0)

    week_totals_payload.clear()
    week_totals_payload.extend(
        sorted(week_totals_map.values(), key=lambda item: str(item.get("week_start") or ""), reverse=True)
    )
