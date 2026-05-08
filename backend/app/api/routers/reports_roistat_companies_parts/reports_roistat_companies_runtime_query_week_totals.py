# SQL-построитель итоговых сумм по неделям (entered_all + все метрики без разбивки по компании).
# Используется только в weekly mode — в cohort mode week_totals не нужны.

from collections.abc import Callable
from typing import Any

def build_week_totals_query(
    *,
    sa_text: Callable[[str], Any],
    cohort_cte: str,
    cohort_join: str,
    utm_filter_sql: str,
    budget_filter_sql: str,
) -> Any:
    week_totals_query = sa_text(f"""
    WITH first_seen AS (
        SELECT tg_user_id, MIN(created_at) AS first_seen_at_system
        FROM raw_bot_users
        WHERE LOWER(TRIM(COALESCE(bot_key, ''))) <> ALL(:excluded_bot_keys)
        GROUP BY tg_user_id
    ),
    {cohort_cte}
    start_rows AS (
        SELECT DISTINCT ON (r.tg_user_id, COALESCE(NULLIF(BTRIM(r.bot_key), ''), 'Без бота'))
            r.tg_user_id,
            COALESCE(NULLIF(BTRIM(r.bot_key), ''), 'Без бота') AS bot_key,
            (r.created_at AT TIME ZONE 'Europe/Moscow')::date AS start_date,
            date_trunc('week', r.created_at AT TIME ZONE 'Europe/Moscow')::date AS week_start,
            fs.first_seen_at_system
        FROM raw_bot_users r
        JOIN first_seen fs ON fs.tg_user_id = r.tg_user_id
        {cohort_join}
        WHERE LOWER(TRIM(COALESCE(r.bot_key, ''))) <> ALL(:excluded_bot_keys)
          AND r.created_at IS NOT NULL
          AND (CAST(:start AS date) IS NULL OR (r.created_at AT TIME ZONE 'Europe/Moscow')::date >= CAST(:start AS date))
          AND (CAST(:end AS date) IS NULL OR (r.created_at AT TIME ZONE 'Europe/Moscow')::date <= CAST(:end AS date)){utm_filter_sql}
        ORDER BY r.tg_user_id, COALESCE(NULLIF(BTRIM(r.bot_key), ''), 'Без бота'), r.created_at
    ),
    entered_week_metrics AS (
        SELECT
            sr.week_start,
            COUNT(DISTINCT sr.tg_user_id) AS entered_all
        FROM start_rows sr
        GROUP BY sr.week_start
    ),
    start_week_segments AS (
        SELECT
            sr.week_start,
            COUNT(DISTINCT CASE WHEN (sr.first_seen_at_system AT TIME ZONE 'Europe/Moscow')::date = sr.start_date THEN sr.tg_user_id END) AS new_in_system,
            COUNT(DISTINCT CASE WHEN (sr.first_seen_at_system AT TIME ZONE 'Europe/Moscow')::date < sr.start_date THEN sr.tg_user_id END) AS old_in_system
        FROM start_rows sr
        GROUP BY sr.week_start
    ),
    lead_rows AS (
        SELECT DISTINCT ON (r.tg_user_id)
            r.tg_user_id,
            r.created_at AS lead_created_at,
            (r.created_at AT TIME ZONE 'Europe/Moscow')::date AS lead_date,
            date_trunc('week', r.created_at AT TIME ZONE 'Europe/Moscow')::date AS week_start,
            fs.first_seen_at_system
        FROM raw_bot_users r
        JOIN first_seen fs ON fs.tg_user_id = r.tg_user_id
        WHERE r.tg_user_id IN (SELECT tg_user_id FROM start_rows)
          AND lower(trim(COALESCE(r.bot_key, ''))) LIKE 'lead%'
          AND LOWER(TRIM(COALESCE(r.bot_key, ''))) <> ALL(:excluded_bot_keys)
          AND r.created_at IS NOT NULL
        ORDER BY r.tg_user_id, r.created_at
    ),
    ph_by_tg AS (
        SELECT
            ru.tg_user_id,
            MIN(ru.ph_user_id) FILTER (
                WHERE ru.ph_user_id IS NOT NULL
                  AND EXISTS (
                      SELECT 1
                      FROM ph_user_mirror_replica pm
                      WHERE pm.ph_id = ru.ph_user_id::text
                        AND NULLIF(BTRIM(COALESCE(pm.ph_registration_at, '')), '') IS NOT NULL
                  )
            ) AS ph_user_id
        FROM raw_bot_users ru
        GROUP BY ru.tg_user_id
    ),
    attributed_leads AS (
        SELECT
            lr.tg_user_id,
            lr.week_start,
            lr.lead_date,
            lr.first_seen_at_system,
            pbt.ph_user_id
        FROM lead_rows lr
        LEFT JOIN ph_by_tg pbt ON pbt.tg_user_id = lr.tg_user_id
    ),
    canonical_ph_owner AS (
        SELECT
            al.ph_user_id,
            MIN(al.tg_user_id) AS canonical_tg_user_id
        FROM attributed_leads al
        WHERE al.ph_user_id IS NOT NULL
        GROUP BY al.ph_user_id
    ),
    attributed_leads_canonical AS (
        SELECT al.*
        FROM attributed_leads al
        LEFT JOIN canonical_ph_owner cpo ON cpo.ph_user_id = al.ph_user_id
        WHERE al.ph_user_id IS NULL OR al.tg_user_id = cpo.canonical_tg_user_id
    ),
    user_flags AS (
        SELECT
            ru.tg_user_id,
            BOOL_OR(ru.converted_to_lead IS TRUE OR lower(trim(COALESCE(ru.bot_key, ''))) LIKE 'lead%') AS did_lead,
            BOOL_OR(
                EXISTS (
                    SELECT 1
                    FROM ph_user_mirror_replica pm
                    WHERE pm.ph_id = ru.ph_user_id::text
                      AND NULLIF(BTRIM(COALESCE(pm.ph_registration_at, '')), '') IS NOT NULL
                )
            ) AS did_platform,
            MIN(
                (
                    SELECT (pm.ph_registration_at::timestamptz AT TIME ZONE 'Europe/Moscow')::date
                    FROM ph_user_mirror_replica pm
                    WHERE pm.ph_id = ru.ph_user_id::text
                      AND NULLIF(BTRIM(COALESCE(pm.ph_registration_at, '')), '') IS NOT NULL
                    LIMIT 1
                )
            ) FILTER (WHERE ru.ph_user_id IS NOT NULL) AS first_platform_date,
            MIN(ru.ph_user_id) FILTER (
                WHERE ru.ph_user_id IS NOT NULL
                  AND EXISTS (
                      SELECT 1
                      FROM ph_user_mirror_replica pm
                      WHERE pm.ph_id = ru.ph_user_id::text
                        AND NULLIF(BTRIM(COALESCE(pm.ph_registration_at, '')), '') IS NOT NULL
                  )
            ) AS ph_user_id,
            BOOL_OR(
                EXISTS (
                    SELECT 1
                    FROM ph_user_mirror_replica pm
                    CROSS JOIN LATERAL jsonb_array_elements_text(COALESCE(pm.lessons::jsonb, '[]'::jsonb)) AS lesson(value)
                    WHERE pm.ph_id = ru.ph_user_id::text
                      AND (
                          lesson.value LIKE 'Базовый курс:%'
                          OR lesson.value LIKE 'MTT1:%'
                          OR lesson.value LIKE 'MTT2:%'
                          OR lesson.value LIKE 'SPIN1:%'
                          OR lesson.value LIKE 'CASH1:%'
                      )
                )
            ) AS did_course_registration,
            BOOL_OR(ru.started_learning IS TRUE OR ru.learn_start_date IS NOT NULL) AS did_learning,
            BOOL_OR(ru.completed_course IS TRUE OR ru.completed_course_at IS NOT NULL) AS did_complete,
            BOOL_OR(ru.interview_reached IS TRUE) AS did_interview,
            BOOL_OR(ru.offer_received IS TRUE) AS did_offer,
            BOOL_OR(ru.contract_signed IS TRUE) AS did_contract,
            BOOL_OR(
                lower(regexp_replace(trim(COALESCE(ru.interview_reached_status, '')), '\\s+', '_', 'g')) IN (
                    'мы_отказали', 'мы_отказали_арбитраж', 'отказали', 'отказался', 'отказ', 'не_назначали_арбитраж'
                )
                OR lower(regexp_replace(trim(COALESCE(ru.offer_received_status, '')), '\\s+', '_', 'g')) IN (
                    'мы_отказали', 'мы_отказали_арбитраж', 'отказали', 'отказался', 'отказ', 'не_назначали_арбитраж'
                )
            ) AS did_refused_interview,
            BOOL_OR(
                lower(regexp_replace(trim(COALESCE(ru.interview_reached_status, '')), '\\s+', '_', 'g')) IN (
                    'не_отвечает', 'не_ответил', 'пропал'
                )
                OR lower(regexp_replace(trim(COALESCE(ru.offer_received_status, '')), '\\s+', '_', 'g')) IN (
                    'не_отвечает', 'не_ответил', 'пропал'
                )
            ) AS did_no_response_interview,
            BOOL_OR(ru.distance_grinding IS TRUE) AS did_distance,
            BOOL_OR(
                EXISTS (
                    SELECT 1
                    FROM ph_user_mirror_replica pm
                    CROSS JOIN LATERAL jsonb_array_elements_text(COALESCE(pm.lessons::jsonb, '[]'::jsonb)) AS lesson(value)
                    WHERE pm.ph_id = ru.ph_user_id::text
                      AND (lesson.value LIKE 'MTT1:%' OR lesson.value LIKE 'MTT2:%')
                )
            ) AS is_mtt,
            BOOL_OR(
                EXISTS (
                    SELECT 1
                    FROM ph_user_mirror_replica pm
                    CROSS JOIN LATERAL jsonb_array_elements_text(COALESCE(pm.lessons::jsonb, '[]'::jsonb)) AS lesson(value)
                    WHERE pm.ph_id = ru.ph_user_id::text
                      AND lesson.value LIKE 'SPIN1:%'
                )
            ) AS is_spin,
            BOOL_OR(
                EXISTS (
                    SELECT 1
                    FROM ph_user_mirror_replica pm
                    CROSS JOIN LATERAL jsonb_array_elements_text(COALESCE(pm.lessons::jsonb, '[]'::jsonb)) AS lesson(value)
                    WHERE pm.ph_id = ru.ph_user_id::text
                      AND lesson.value LIKE 'CASH1:%'
                )
            ) AS is_cash,
            BOOL_OR(
                EXISTS (
                    SELECT 1
                    FROM ph_user_mirror_replica pm
                    CROSS JOIN LATERAL jsonb_array_elements_text(COALESCE(pm.lessons::jsonb, '[]'::jsonb)) AS lesson(value)
                    WHERE pm.ph_id = ru.ph_user_id::text
                      AND lesson.value LIKE 'Базовый курс:%'
                )
            ) AS is_base,
            BOOL_OR(
                lower(trim(COALESCE(ru.bot_key, ''))) LIKE 'lead%'
                AND ru.tg_user_id > 0
                AND ru.ph_user_id IS NOT NULL
                AND abs(ru.tg_user_id) = ru.ph_user_id
            ) AS is_direct_source,
            COALESCE(sf.did_channel, FALSE) AS did_channel,
            COALESCE(sf.did_saloon, FALSE) AS did_saloon
        FROM raw_bot_users ru
        LEFT JOIN (
            SELECT
                tg_user_id,
                BOOL_OR(status = 'subscribed' AND channel_id = :channel_id) AS did_channel,
                BOOL_OR(status = 'subscribed' AND channel_id = :community_id) AS did_saloon
            FROM telegram_subscription_events
            GROUP BY tg_user_id
        ) sf ON sf.tg_user_id = ru.tg_user_id
        WHERE ru.tg_user_id IN (SELECT tg_user_id FROM attributed_leads_canonical)
          AND LOWER(TRIM(COALESCE(ru.bot_key, ''))) <> ALL(:excluded_bot_keys)
        GROUP BY ru.tg_user_id, sf.did_channel, sf.did_saloon
    ),
    week_metrics AS (
        SELECT
            al.week_start,
            COUNT(DISTINCT CASE WHEN al.tg_user_id > 0 AND NOT uf.is_direct_source THEN al.tg_user_id END) AS almanah_starts,
            COUNT(DISTINCT CASE WHEN uf.is_direct_source AND uf.ph_user_id IS NOT NULL THEN uf.ph_user_id END) AS direct_source_cnt,
            COUNT(DISTINCT CASE WHEN (al.first_seen_at_system AT TIME ZONE 'Europe/Moscow')::date = al.lead_date THEN al.tg_user_id END) AS new_in_system,
            COUNT(DISTINCT CASE WHEN (al.first_seen_at_system AT TIME ZONE 'Europe/Moscow')::date < al.lead_date THEN al.tg_user_id END) AS old_in_system,
            COUNT(
                DISTINCT CASE
                    WHEN NOT uf.is_direct_source
                     AND uf.ph_user_id IS NOT NULL
                     AND uf.did_platform
                     AND uf.first_platform_date BETWEEN al.week_start AND (al.week_start + INTERVAL '6 day')::date
                    THEN uf.ph_user_id
                END
            ) AS platform_cnt,
            COUNT(DISTINCT CASE WHEN uf.ph_user_id IS NOT NULL AND uf.did_platform AND uf.did_course_registration THEN uf.ph_user_id END) AS learning,
            COUNT(DISTINCT CASE WHEN uf.did_learning THEN al.tg_user_id END) AS started_learning,
            COUNT(DISTINCT CASE WHEN uf.is_mtt THEN al.tg_user_id END) AS mtt,
            COUNT(DISTINCT CASE WHEN uf.is_spin THEN al.tg_user_id END) AS spin,
            COUNT(DISTINCT CASE WHEN uf.is_cash THEN al.tg_user_id END) AS cash,
            COUNT(DISTINCT CASE WHEN uf.is_base THEN al.tg_user_id END) AS base,
            COUNT(DISTINCT CASE WHEN uf.ph_user_id IS NOT NULL AND uf.did_platform AND NOT uf.did_learning THEN uf.ph_user_id END) AS not_started,
            COUNT(DISTINCT CASE WHEN uf.did_channel THEN al.tg_user_id END) AS channel_subscribed,
            COUNT(DISTINCT CASE WHEN uf.did_saloon THEN al.tg_user_id END) AS saloon,
            COUNT(DISTINCT CASE WHEN uf.did_complete THEN al.tg_user_id END) AS completed_course,
            COUNT(DISTINCT CASE WHEN uf.did_complete AND uf.is_mtt THEN al.tg_user_id END) AS completed_mtt,
            COUNT(DISTINCT CASE WHEN uf.did_complete AND uf.is_spin THEN al.tg_user_id END) AS completed_spin,
            COUNT(DISTINCT CASE WHEN uf.did_complete AND uf.is_cash THEN al.tg_user_id END) AS completed_cash,
            COUNT(DISTINCT CASE WHEN uf.did_complete AND uf.is_base THEN al.tg_user_id END) AS completed_base,
            COUNT(DISTINCT CASE WHEN uf.did_interview THEN al.tg_user_id END) AS interview_reached,
            COUNT(DISTINCT CASE WHEN uf.did_offer THEN al.tg_user_id END) AS offer_received,
            COUNT(DISTINCT CASE WHEN uf.did_contract THEN al.tg_user_id END) AS contract_signed,
            COUNT(DISTINCT CASE WHEN uf.did_refused_interview THEN al.tg_user_id END) AS refused_interview,
            COUNT(DISTINCT CASE WHEN uf.did_no_response_interview THEN al.tg_user_id END) AS no_response_interview,
            COUNT(DISTINCT CASE WHEN uf.did_contract AND uf.is_mtt THEN al.tg_user_id END) AS contract_mtt,
            COUNT(DISTINCT CASE WHEN uf.did_contract AND uf.is_spin THEN al.tg_user_id END) AS contract_spin,
            COUNT(DISTINCT CASE WHEN uf.did_contract AND uf.is_cash THEN al.tg_user_id END) AS contract_cash,
            COUNT(DISTINCT CASE WHEN uf.did_distance THEN al.tg_user_id END) AS distance_grinding
        FROM attributed_leads_canonical al
        JOIN user_flags uf ON uf.tg_user_id = al.tg_user_id
        GROUP BY al.week_start
    ),
    budgets AS (
        SELECT
            DATE_TRUNC('week', week_start)::date AS week_start,
            SUM(amount) AS budget
        FROM budget_weekly
        WHERE
            (CAST(:start AS date) IS NULL OR week_start::date >= CAST(:start AS date))
            AND (CAST(:end AS date) IS NULL OR week_start::date <= CAST(:end AS date))
            {budget_filter_sql}
        GROUP BY 1
    ),
    metric_weeks AS (
        SELECT week_start FROM week_metrics
        UNION
        SELECT week_start FROM budgets
    )
    SELECT
        mw.week_start,
        COALESCE(ewm.entered_all, 0) AS entered_all,
        COALESCE(b.budget, 0.0) AS budget,
        COALESCE(wm.almanah_starts, 0) AS almanah_starts,
        COALESCE(wm.direct_source_cnt, 0) AS direct_source_cnt,
        COALESCE(sws.new_in_system, 0) AS new_in_system,
        COALESCE(sws.old_in_system, 0) AS old_in_system,
        COALESCE(wm.platform_cnt, 0) AS platform_cnt,
        COALESCE(wm.learning, 0) AS learning,
        COALESCE(wm.started_learning, 0) AS started_learning,
        COALESCE(wm.mtt, 0) AS mtt,
        COALESCE(wm.spin, 0) AS spin,
        COALESCE(wm.cash, 0) AS cash,
        COALESCE(wm.base, 0) AS base,
        COALESCE(wm.not_started, 0) AS not_started,
        COALESCE(wm.channel_subscribed, 0) AS channel_subscribed,
        COALESCE(wm.saloon, 0) AS saloon,
        COALESCE(wm.completed_course, 0) AS completed_course,
        COALESCE(wm.completed_mtt, 0) AS completed_mtt,
        COALESCE(wm.completed_spin, 0) AS completed_spin,
        COALESCE(wm.completed_cash, 0) AS completed_cash,
        COALESCE(wm.completed_base, 0) AS completed_base,
        COALESCE(wm.interview_reached, 0) AS interview_reached,
        COALESCE(wm.offer_received, 0) AS offer_received,
        COALESCE(wm.contract_signed, 0) AS contract_signed,
        COALESCE(wm.refused_interview, 0) AS refused_interview,
        COALESCE(wm.no_response_interview, 0) AS no_response_interview,
        COALESCE(wm.contract_mtt, 0) AS contract_mtt,
        COALESCE(wm.contract_spin, 0) AS contract_spin,
        COALESCE(wm.contract_cash, 0) AS contract_cash,
        COALESCE(wm.distance_grinding, 0) AS distance_grinding
    FROM metric_weeks mw
    LEFT JOIN week_metrics wm ON wm.week_start = mw.week_start
    LEFT JOIN entered_week_metrics ewm ON ewm.week_start = mw.week_start
    LEFT JOIN start_week_segments sws ON sws.week_start = mw.week_start
    LEFT JOIN budgets b ON b.week_start = mw.week_start
    ORDER BY mw.week_start DESC
        """)
    return week_totals_query
