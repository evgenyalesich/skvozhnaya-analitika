# SQL-построитель weekly bot-уровневого запроса (добавляет bot_key к разбивке company × week).

from collections.abc import Callable
from typing import Any


def build_bot_weekly_query(
    *,
    sa_text: Callable[[str], Any],
    cohort_cte: str,
    cohort_join: str,
    event_date_filter: str,
    utm_filter_sql: str,
    normalized_company_sql: str,
    source_touch_filter_sql: str,
    budget_filter_sql: str,
    lc_company_sql: str,
) -> Any:
    bot_query = sa_text(f"""
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
            {lc_company_sql} AS company,
            COALESCE(NULLIF(BTRIM(r.bot_key), ''), 'Без бота') AS bot_key,
            (r.created_at AT TIME ZONE 'Europe/Moscow')::date AS start_date,
            date_trunc('week', r.created_at AT TIME ZONE 'Europe/Moscow')::date AS week_start,
            fs.first_seen_at_system
        FROM raw_bot_users r
        JOIN first_seen fs ON fs.tg_user_id = r.tg_user_id
        {cohort_join}
        WHERE LOWER(TRIM(COALESCE(r.bot_key, ''))) <> ALL(:excluded_bot_keys)
          AND r.created_at IS NOT NULL{event_date_filter}{utm_filter_sql}
        ORDER BY r.tg_user_id, COALESCE(NULLIF(BTRIM(r.bot_key), ''), 'Без бота'), r.created_at
    ),
    entered_bot_metrics AS (
        SELECT
            sr.week_start,
            sr.company,
            sr.bot_key,
            COUNT(DISTINCT sr.tg_user_id) AS entered_all
        FROM start_rows sr
        GROUP BY sr.week_start, sr.company, sr.bot_key
    ),
    lead_rows AS (
        SELECT DISTINCT ON (r.tg_user_id)
            r.tg_user_id,
            {lc_company_sql} AS lead_company,
            COALESCE(NULLIF(BTRIM(r.bot_key), ''), 'Без бота') AS lead_bot_key,
            COALESCE(NULLIF(BTRIM(r.first_touch_bot), ''), NULL) AS first_touch_bot,
            COALESCE(NULLIF(BTRIM(r.last_touch_bot), ''), NULL) AS last_touch_bot,
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
    attributed_leads AS (
        SELECT
            lr.tg_user_id,
            lr.week_start,
            lr.lead_date,
            lr.first_seen_at_system,
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
            BOOL_OR(ru.converted_to_lead IS TRUE OR lower(trim(COALESCE(ru.bot_key, ''))) LIKE 'lead%') AS did_lead,
            BOOL_OR(ru.ph_user_id IS NOT NULL AND ru.platform_registered_at IS NOT NULL) AS did_platform,
            MIN((ru.platform_registered_at AT TIME ZONE 'Europe/Moscow')::date) FILTER (
                WHERE ru.ph_user_id IS NOT NULL AND ru.platform_registered_at IS NOT NULL
            ) AS first_platform_date,
            MIN(ru.ph_user_id) FILTER (
                WHERE ru.ph_user_id IS NOT NULL AND ru.platform_registered_at IS NOT NULL
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
            BOOL_OR(ru.completed_course IS TRUE AND ru.completed_course_at IS NOT NULL) AS did_complete,
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
        WHERE ru.tg_user_id IN (SELECT tg_user_id FROM attributed_leads)
          AND LOWER(TRIM(COALESCE(ru.bot_key, ''))) <> ALL(:excluded_bot_keys)
        GROUP BY ru.tg_user_id, sf.did_channel, sf.did_saloon
    ),
    bot_metrics AS (
        SELECT
            al.week_start,
            al.company,
            al.bot_key,
            COUNT(DISTINCT CASE WHEN al.tg_user_id > 0 AND NOT uf.is_direct_source THEN al.tg_user_id END) AS almanah_starts,
            COUNT(DISTINCT CASE WHEN uf.is_direct_source AND uf.ph_user_id IS NOT NULL THEN uf.ph_user_id END) AS direct_source_cnt,
            COUNT(DISTINCT CASE WHEN (al.first_seen_at_system AT TIME ZONE 'Europe/Moscow')::date = al.lead_date THEN al.tg_user_id END) AS new_in_system,
            COUNT(DISTINCT CASE WHEN (al.first_seen_at_system AT TIME ZONE 'Europe/Moscow')::date < al.lead_date THEN al.tg_user_id END) AS old_in_system,
            COUNT(
                DISTINCT CASE
                    WHEN NOT uf.is_direct_source
                     AND uf.ph_user_id IS NOT NULL
                     AND uf.did_platform
                    THEN uf.ph_user_id
                END
            ) AS platform_cnt,
            COUNT(DISTINCT CASE WHEN uf.did_lead AND uf.ph_user_id IS NOT NULL AND uf.did_platform AND uf.did_course_registration THEN uf.ph_user_id END) AS learning,
            COUNT(DISTINCT CASE WHEN uf.did_lead AND uf.ph_user_id IS NOT NULL AND uf.did_platform AND uf.did_learning THEN uf.ph_user_id END) AS started_learning,
            COUNT(DISTINCT CASE WHEN uf.did_lead AND uf.ph_user_id IS NOT NULL AND uf.did_platform AND uf.is_mtt THEN uf.ph_user_id END) AS mtt,
            COUNT(DISTINCT CASE WHEN uf.did_lead AND uf.ph_user_id IS NOT NULL AND uf.did_platform AND uf.is_spin THEN uf.ph_user_id END) AS spin,
            COUNT(DISTINCT CASE WHEN uf.did_lead AND uf.ph_user_id IS NOT NULL AND uf.did_platform AND uf.is_cash THEN uf.ph_user_id END) AS cash,
            COUNT(DISTINCT CASE WHEN uf.did_lead AND uf.ph_user_id IS NOT NULL AND uf.did_platform AND uf.is_base THEN uf.ph_user_id END) AS base,
            COUNT(DISTINCT CASE WHEN uf.did_lead AND uf.ph_user_id IS NOT NULL AND uf.did_platform AND NOT uf.did_learning THEN uf.ph_user_id END) AS not_started,
            COUNT(DISTINCT CASE WHEN uf.did_channel THEN al.tg_user_id END) AS channel_subscribed,
            COUNT(DISTINCT CASE WHEN uf.did_saloon THEN al.tg_user_id END) AS saloon,
            COUNT(DISTINCT CASE WHEN uf.did_lead AND uf.ph_user_id IS NOT NULL AND uf.did_platform AND uf.did_learning AND uf.did_complete THEN uf.ph_user_id END) AS completed_course,
            COUNT(DISTINCT CASE WHEN uf.did_lead AND uf.ph_user_id IS NOT NULL AND uf.did_platform AND uf.did_learning AND uf.did_complete AND uf.is_mtt THEN uf.ph_user_id END) AS completed_mtt,
            COUNT(DISTINCT CASE WHEN uf.did_lead AND uf.ph_user_id IS NOT NULL AND uf.did_platform AND uf.did_learning AND uf.did_complete AND uf.is_spin THEN uf.ph_user_id END) AS completed_spin,
            COUNT(DISTINCT CASE WHEN uf.did_lead AND uf.ph_user_id IS NOT NULL AND uf.did_platform AND uf.did_learning AND uf.did_complete AND uf.is_cash THEN uf.ph_user_id END) AS completed_cash,
            COUNT(DISTINCT CASE WHEN uf.did_lead AND uf.ph_user_id IS NOT NULL AND uf.did_platform AND uf.did_learning AND uf.did_complete AND uf.is_base THEN uf.ph_user_id END) AS completed_base,
            COUNT(DISTINCT CASE WHEN uf.did_lead AND uf.ph_user_id IS NOT NULL AND uf.did_platform AND uf.did_learning AND uf.did_complete AND uf.did_interview THEN uf.ph_user_id END) AS interview_reached,
            COUNT(DISTINCT CASE WHEN uf.did_lead AND uf.ph_user_id IS NOT NULL AND uf.did_platform AND uf.did_learning AND uf.did_complete AND uf.did_interview AND uf.did_offer THEN uf.ph_user_id END) AS offer_received,
            COUNT(DISTINCT CASE WHEN uf.did_lead AND uf.ph_user_id IS NOT NULL AND uf.did_platform AND uf.did_learning AND uf.did_complete AND uf.did_interview AND uf.did_offer AND uf.did_contract THEN uf.ph_user_id END) AS contract_signed,
            COUNT(DISTINCT CASE WHEN uf.did_lead AND uf.ph_user_id IS NOT NULL AND uf.did_platform AND uf.did_learning AND uf.did_complete AND uf.did_refused_interview THEN uf.ph_user_id END) AS refused_interview,
            COUNT(DISTINCT CASE WHEN uf.did_lead AND uf.ph_user_id IS NOT NULL AND uf.did_platform AND uf.did_learning AND uf.did_complete AND uf.did_no_response_interview THEN uf.ph_user_id END) AS no_response_interview,
            COUNT(DISTINCT CASE WHEN uf.did_lead AND uf.ph_user_id IS NOT NULL AND uf.did_platform AND uf.did_learning AND uf.did_complete AND uf.did_interview AND uf.did_offer AND uf.did_contract AND uf.is_mtt THEN uf.ph_user_id END) AS contract_mtt,
            COUNT(DISTINCT CASE WHEN uf.did_lead AND uf.ph_user_id IS NOT NULL AND uf.did_platform AND uf.did_learning AND uf.did_complete AND uf.did_interview AND uf.did_offer AND uf.did_contract AND uf.is_spin THEN uf.ph_user_id END) AS contract_spin,
            COUNT(DISTINCT CASE WHEN uf.did_lead AND uf.ph_user_id IS NOT NULL AND uf.did_platform AND uf.did_learning AND uf.did_complete AND uf.did_interview AND uf.did_offer AND uf.did_contract AND uf.is_cash THEN uf.ph_user_id END) AS contract_cash,
            COUNT(DISTINCT CASE WHEN uf.did_lead AND uf.ph_user_id IS NOT NULL AND uf.did_platform AND uf.did_learning AND uf.did_complete AND uf.did_interview AND uf.did_offer AND uf.did_distance THEN uf.ph_user_id END) AS distance_grinding
        FROM attributed_leads al
        JOIN user_flags uf ON uf.tg_user_id = al.tg_user_id
        GROUP BY al.week_start, al.company, al.bot_key
    ),
    budgets_bot AS (
        SELECT DATE_TRUNC('week', week_start)::date AS week_start,
            CASE WHEN campaign IS NULL OR BTRIM(campaign) = '' OR LOWER(BTRIM(campaign)) IN ('-', '—', '(none)', 'none', 'null', 'нет метки') THEN 'Без категории' ELSE BTRIM(campaign) END AS company,
            COALESCE(NULLIF(BTRIM(bot_key), ''), 'Без бота') AS bot_key,
            SUM(amount) AS budget
        FROM budget_weekly
        WHERE (CAST(:start AS date) IS NULL OR week_start::date >= CAST(:start AS date))
          AND (CAST(:end AS date) IS NULL OR week_start::date <= CAST(:end AS date))
          {budget_filter_sql}
        GROUP BY 1, 2, 3
    ),
    bot_weeks AS (
        SELECT week_start, company, bot_key FROM bot_metrics
        UNION SELECT week_start, company, bot_key FROM budgets_bot
    )
    SELECT
        bw.week_start,
        bw.company,
        bw.bot_key,
        COALESCE(ebm.entered_all, 0) AS entered_all,
        COALESCE(b.budget, 0.0) AS budget,
        COALESCE(bm.almanah_starts, 0) AS almanah_starts,
        COALESCE(bm.direct_source_cnt, 0) AS direct_source_cnt,
        COALESCE(bm.new_in_system, 0) AS new_in_system,
        COALESCE(bm.old_in_system, 0) AS old_in_system,
        COALESCE(bm.platform_cnt, 0) AS platform_cnt,
        COALESCE(bm.learning, 0) AS learning,
        COALESCE(bm.started_learning, 0) AS started_learning,
        COALESCE(bm.mtt, 0) AS mtt,
        COALESCE(bm.spin, 0) AS spin,
        COALESCE(bm.cash, 0) AS cash,
        COALESCE(bm.base, 0) AS base,
        COALESCE(bm.not_started, 0) AS not_started,
        COALESCE(bm.channel_subscribed, 0) AS channel_subscribed,
        COALESCE(bm.saloon, 0) AS saloon,
        COALESCE(bm.completed_course, 0) AS completed_course,
        COALESCE(bm.completed_mtt, 0) AS completed_mtt,
        COALESCE(bm.completed_spin, 0) AS completed_spin,
        COALESCE(bm.completed_cash, 0) AS completed_cash,
        COALESCE(bm.completed_base, 0) AS completed_base,
        COALESCE(bm.interview_reached, 0) AS interview_reached,
        COALESCE(bm.offer_received, 0) AS offer_received,
        COALESCE(bm.contract_signed, 0) AS contract_signed,
        COALESCE(bm.refused_interview, 0) AS refused_interview,
        COALESCE(bm.no_response_interview, 0) AS no_response_interview,
        COALESCE(bm.contract_mtt, 0) AS contract_mtt,
        COALESCE(bm.contract_spin, 0) AS contract_spin,
        COALESCE(bm.contract_cash, 0) AS contract_cash,
        COALESCE(bm.distance_grinding, 0) AS distance_grinding
    FROM bot_weeks bw
    LEFT JOIN bot_metrics bm ON bm.week_start = bw.week_start AND bm.company = bw.company AND bm.bot_key = bw.bot_key
    LEFT JOIN entered_bot_metrics ebm ON ebm.week_start = bw.week_start AND ebm.company = bw.company AND ebm.bot_key = bw.bot_key
    LEFT JOIN budgets_bot b ON b.week_start = bw.week_start AND b.company = bw.company AND b.bot_key = bw.bot_key
    ORDER BY bw.week_start DESC, bw.company, COALESCE(bm.almanah_starts, 0) DESC, bw.bot_key
        """)
    return bot_query
