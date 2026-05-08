# Иерархический (tree) Roistat-отчёт: Platform → Company → Bot.
# Один большой CTE-запрос: first_seen / lead_rows / user_flags → GROUP BY platform/company/bot.
# Результат собирается в 3-уровневый дерево: source[companies[bots[metrics]]].
# Метрики на каждом уровне суммируются (sum_metrics). Не кешируется отдельно — лёгкий запрос.

from datetime import date
from typing import Any, Optional

from fastapi import Depends, Query

from app.api.dependencies import get_db_session
from app.services.report_bot_scope import normalized_excluded_bot_keys


# ===== Roistat tree logic =====
async def roistat_weekly_tree(
    event_start: Optional[date] = Query(None),
    event_end: Optional[date] = Query(None),
    session=Depends(get_db_session),
) -> dict[str, Any]:
    from sqlalchemy import text as sa_text

    params: dict[str, Any] = {
        "start": event_start,
        "end": event_end,
        "excluded_bot_keys": normalized_excluded_bot_keys(),
    }
    query = sa_text("""
        WITH first_seen AS (
            SELECT tg_user_id, MIN(created_at) AS first_seen_at_system
            FROM raw_bot_users
            WHERE LOWER(TRIM(COALESCE(bot_key, ''))) <> ALL(:excluded_bot_keys)
            GROUP BY tg_user_id
        ),
        lead_rows AS (
            SELECT DISTINCT ON (r.tg_user_id)
                r.tg_user_id,
                r.bot_key,
                COALESCE(r.advertising_company, 'Без категории') AS company,
                (r.created_at AT TIME ZONE 'Europe/Moscow')::date AS lead_date,
                fs.first_seen_at_system
            FROM raw_bot_users r
            JOIN first_seen fs ON fs.tg_user_id = r.tg_user_id
            WHERE lower(trim(r.bot_key)) LIKE 'lead%'
              AND r.tg_user_id > 0
              AND LOWER(TRIM(COALESCE(r.bot_key, ''))) <> ALL(:excluded_bot_keys)
              AND r.created_at IS NOT NULL
              AND (CAST(:start AS date) IS NULL OR (r.created_at AT TIME ZONE 'Europe/Moscow')::date >= CAST(:start AS date))
              AND (CAST(:end AS date) IS NULL OR (r.created_at AT TIME ZONE 'Europe/Moscow')::date <= CAST(:end AS date))
            ORDER BY r.tg_user_id, r.created_at
        ),
        user_flags AS (
            SELECT
                tg_user_id,
                BOOL_OR(ph_user_id IS NOT NULL AND platform_registered_at IS NOT NULL) AS did_platform,
                MIN(ph_user_id) FILTER (
                    WHERE ph_user_id IS NOT NULL AND platform_registered_at IS NOT NULL
                ) AS ph_user_id,
                BOOL_OR(learn_start_date IS NOT NULL) AS did_learning,
                BOOL_OR(completed_course IS TRUE AND completed_course_at IS NOT NULL) AS did_complete,
                BOOL_OR(interview_reached IS TRUE) AS did_interview,
                BOOL_OR(offer_received IS TRUE) AS did_offer,
                BOOL_OR(contract_signed IS TRUE) AS did_contract,
                BOOL_OR(distance_grinding IS TRUE) AS did_distance,
                BOOL_OR(LOWER(TRIM(COALESCE(start_course, ''))) LIKE 'mtt%') AS is_mtt,
                BOOL_OR(LOWER(TRIM(COALESCE(start_course, ''))) LIKE 'spin%') AS is_spin,
                BOOL_OR(LOWER(TRIM(COALESCE(start_course, ''))) LIKE 'cash%') AS is_cash,
                BOOL_OR(LOWER(TRIM(COALESCE(start_course, ''))) LIKE 'base%') AS is_base,
                BOOL_OR(
                    lower(trim(COALESCE(bot_key, ''))) LIKE 'lead%'
                    AND tg_user_id > 0
                    AND ph_user_id IS NOT NULL
                    AND abs(tg_user_id) = ph_user_id
                ) AS is_direct_source
            FROM raw_bot_users
            WHERE tg_user_id IN (SELECT tg_user_id FROM lead_rows)
              AND LOWER(TRIM(COALESCE(bot_key, ''))) <> ALL(:excluded_bot_keys)
            GROUP BY tg_user_id
        )
        SELECT
            COALESCE(ac.platform, 'Без источника') AS platform,
            lr.company,
            lr.bot_key AS bot,
            COUNT(DISTINCT CASE WHEN lr.tg_user_id > 0 AND NOT uf.is_direct_source THEN lr.tg_user_id END) AS almanah_starts,
            COUNT(DISTINCT CASE WHEN uf.is_direct_source AND uf.ph_user_id IS NOT NULL THEN uf.ph_user_id END) AS direct_source_cnt,
            COUNT(DISTINCT CASE WHEN (lr.first_seen_at_system AT TIME ZONE 'Europe/Moscow')::date = lr.lead_date THEN lr.tg_user_id END) AS new_in_system,
            COUNT(DISTINCT CASE WHEN uf.ph_user_id IS NOT NULL AND NOT uf.is_direct_source THEN uf.ph_user_id END) AS platform_cnt,
            COUNT(DISTINCT CASE WHEN uf.did_learning THEN lr.tg_user_id END) AS started_learning,
            COUNT(DISTINCT CASE WHEN uf.did_complete THEN lr.tg_user_id END) AS completed_course,
            COUNT(DISTINCT CASE WHEN uf.did_complete AND uf.is_mtt THEN lr.tg_user_id END) AS completed_mtt,
            COUNT(DISTINCT CASE WHEN uf.did_complete AND uf.is_spin THEN lr.tg_user_id END) AS completed_spin,
            COUNT(DISTINCT CASE WHEN uf.did_complete AND uf.is_cash THEN lr.tg_user_id END) AS completed_cash,
            COUNT(DISTINCT CASE WHEN uf.did_complete AND uf.is_base THEN lr.tg_user_id END) AS completed_base,
            COUNT(DISTINCT CASE WHEN uf.did_interview THEN lr.tg_user_id END) AS interview_reached,
            COUNT(DISTINCT CASE WHEN uf.did_offer THEN lr.tg_user_id END) AS offer_received,
            COUNT(DISTINCT CASE WHEN uf.did_contract THEN lr.tg_user_id END) AS contract_signed,
            COUNT(DISTINCT CASE WHEN uf.did_contract AND uf.is_mtt THEN lr.tg_user_id END) AS contract_mtt,
            COUNT(DISTINCT CASE WHEN uf.did_contract AND uf.is_spin THEN lr.tg_user_id END) AS contract_spin,
            COUNT(DISTINCT CASE WHEN uf.did_contract AND uf.is_cash THEN lr.tg_user_id END) AS contract_cash,
            COUNT(DISTINCT CASE WHEN uf.did_distance THEN lr.tg_user_id END) AS distance_grinding
        FROM lead_rows lr
        JOIN user_flags uf ON uf.tg_user_id = lr.tg_user_id
        LEFT JOIN advertising_company_bots acb ON acb.bot_key = lr.bot_key
        LEFT JOIN advertising_companies ac ON ac.company_id = acb.company_id
        GROUP BY COALESCE(ac.platform, 'Без источника'), lr.company, lr.bot_key
        ORDER BY COALESCE(ac.platform, 'Без источника'), lr.company, lr.bot_key
    """)
    result = await session.execute(query, params)
    rows = result.fetchall()

    METRIC_KEYS = [
        "almanah_starts", "direct_source_cnt", "new_in_system", "platform_cnt", "started_learning",
        "completed_course", "completed_mtt", "completed_spin", "completed_cash", "completed_base",
        "interview_reached", "offer_received", "contract_signed",
        "contract_mtt", "contract_spin", "contract_cash", "distance_grinding",
    ]

    def sum_metrics(items: list[dict]) -> dict:
        return {k: sum(m[k] for m in items) for k in METRIC_KEYS}

    tree_map: dict = {}
    for row in rows:
        p, c, b = row.platform, row.company, row.bot
        metrics = {k: int(getattr(row, k) or 0) for k in METRIC_KEYS}
        tree_map.setdefault(p, {}).setdefault(c, {})[b] = metrics

    tree = []
    for plat, companies in sorted(tree_map.items()):
        company_nodes = []
        for comp, bots in sorted(companies.items()):
            bot_nodes = [{"bot": b, **m} for b, m in sorted(bots.items())]
            company_nodes.append({"company": comp, **sum_metrics(bot_nodes), "bots": bot_nodes})
        tree.append({"source": plat, **sum_metrics(company_nodes), "companies": company_nodes})
    return {"tree": tree}


