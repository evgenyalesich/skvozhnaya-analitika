from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from sqlalchemy import text as sa_text
from sqlalchemy.ext.asyncio import AsyncSession



class MainReportWeeklyAuditService:
    async def run(self, session: AsyncSession, weeks: int = 8) -> list[str]:
        # Lazy import avoids heavy API router import graph at worker startup.
        from app.api.routers.reports_roistat_companies_runtime import roistat_weekly_by_company

        end = date.today()
        start = end - timedelta(days=max(7, weeks * 7))
        payload = await roistat_weekly_by_company(
            event_start=start,
            event_end=end,
            mode="event",
            first_touch_start=None,
            first_touch_end=None,
            display_mode="weekly",
            bots=None,
            advertising_companies=None,
            utm_source=None,
            utm_campaign=None,
            utm_medium=None,
            utm_content=None,
            utm_term=None,
            session=session,
        )
        week_totals = payload.get("week_totals", []) if isinstance(payload, dict) else []
        report_by_week: dict[str, dict[str, int]] = {}
        for row in week_totals:
            wk = str(row.get("week_start"))
            report_by_week[wk] = {
                "entered_all": int(row.get("entered_all") or 0),
                "almanah_starts": int(row.get("almanah_starts") or 0),
                "platform_cnt": int(row.get("platform_cnt") or 0),
                "started_learning": int(row.get("started_learning") or 0),
                "offer_received": int(row.get("offer_received") or 0),
                "contract_signed": int(row.get("contract_signed") or 0),
            }

        source_rows = (
            await session.execute(
                sa_text(
                    """
                    WITH bot_starts AS (
                        SELECT date_trunc('week', created_at AT TIME ZONE 'Europe/Moscow')::date AS week_start,
                               COUNT(DISTINCT tg_user_id) AS entered_all
                        FROM raw_bot_users
                        WHERE created_at IS NOT NULL
                          AND lower(trim(COALESCE(bot_key, ''))) NOT LIKE 'lead%'
                          AND lower(trim(COALESCE(bot_key, ''))) <> ALL(:excluded_bot_keys)
                          AND (created_at AT TIME ZONE 'Europe/Moscow')::date BETWEEN :start AND :end
                        GROUP BY 1
                    ),
                    almanah AS (
                        SELECT date_trunc('week', created_at AT TIME ZONE 'Europe/Moscow')::date AS week_start,
                               COUNT(DISTINCT tg_user_id) AS almanah_starts
                        FROM raw_bot_users
                        WHERE created_at IS NOT NULL
                          AND lower(trim(COALESCE(bot_key, ''))) LIKE 'lead%'
                          AND lower(trim(COALESCE(bot_key, ''))) <> ALL(:excluded_bot_keys)
                          AND (created_at AT TIME ZONE 'Europe/Moscow')::date BETWEEN :start AND :end
                        GROUP BY 1
                    ),
                    ph_reg AS (
                        SELECT date_trunc('week', (ph_registration_at::timestamptz AT TIME ZONE 'Europe/Moscow'))::date AS week_start,
                               COUNT(DISTINCT ph_id) AS platform_cnt
                        FROM ph_user_mirror_replica
                        WHERE ph_id ~ '^[0-9]+$'
                          AND NULLIF(BTRIM(COALESCE(ph_registration_at, '')), '') IS NOT NULL
                          AND (ph_registration_at::timestamptz AT TIME ZONE 'Europe/Moscow')::date BETWEEN :start AND :end
                        GROUP BY 1
                    ),
                    sm AS (
                        SELECT week_start,
                               COUNT(DISTINCT tg_user_id) FILTER (WHERE metric='offer') AS offer_received,
                               COUNT(DISTINCT tg_user_id) FILTER (WHERE metric='contract') AS contract_signed
                        FROM (
                            SELECT date_trunc('week', (offer_received_at AT TIME ZONE 'Europe/Moscow'))::date AS week_start, tg_user_id, 'offer'::text AS metric
                            FROM raw_bot_users
                            WHERE lower(trim(COALESCE(bot_key, ''))) LIKE 'lead%'
                              AND offer_received IS TRUE
                              AND offer_received_at IS NOT NULL
                              AND (offer_received_at AT TIME ZONE 'Europe/Moscow')::date BETWEEN :start AND :end
                            UNION ALL
                            SELECT date_trunc('week', (contract_signed_at AT TIME ZONE 'Europe/Moscow'))::date AS week_start, tg_user_id, 'contract'::text AS metric
                            FROM raw_bot_users
                            WHERE lower(trim(COALESCE(bot_key, ''))) LIKE 'lead%'
                              AND contract_signed IS TRUE
                              AND contract_signed_at IS NOT NULL
                              AND (contract_signed_at AT TIME ZONE 'Europe/Moscow')::date BETWEEN :start AND :end
                        ) x
                        GROUP BY week_start
                    )
                    SELECT
                        w.week_start::date AS week_start,
                        COALESCE(bs.entered_all, 0) AS entered_all,
                        COALESCE(a.almanah_starts, 0) AS almanah_starts,
                        COALESCE(p.platform_cnt, 0) AS platform_cnt,
                        COALESCE(sm.offer_received, 0) AS offer_received,
                        COALESCE(sm.contract_signed, 0) AS contract_signed
                    FROM (
                        SELECT generate_series(:start::date, :end::date, interval '1 week')::date AS week_start
                    ) w
                    LEFT JOIN bot_starts bs ON bs.week_start = w.week_start
                    LEFT JOIN almanah a ON a.week_start = w.week_start
                    LEFT JOIN ph_reg p ON p.week_start = w.week_start
                    LEFT JOIN sm ON sm.week_start = w.week_start
                    ORDER BY 1
                    """
                ),
                {
                    "start": start,
                    "end": end,
                    "excluded_bot_keys": ["", "-", "—", "none", "(none)", "null", "нет метки"],
                },
            )
        ).fetchall()

        issues: list[str] = []
        for src in source_rows:
            wk = src.week_start.isoformat()
            rep = report_by_week.get(wk, {})
            for key in ("entered_all", "almanah_starts", "platform_cnt", "offer_received", "contract_signed"):
                expected = int(getattr(src, key) or 0)
                actual = int(rep.get(key) or 0)
                if expected != actual:
                    issues.append(f"{wk} {key}: report={actual} source={expected}")
        return issues
