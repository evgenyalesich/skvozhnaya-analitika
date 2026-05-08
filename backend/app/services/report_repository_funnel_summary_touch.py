from typing import Any, List

from sqlalchemy import func, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.report_filters import ReportFilters
from app.services.report_bot_scope import normalized_excluded_bot_keys
from app.services.utm_normalization import normalize_utm_filter_values


class ReportRepositoryFunnelSummaryTouchMixin:
    def _build_touch_attr_filters_sql(
        self,
        alias: str,
        filters: ReportFilters,
        params: dict[str, Any],
    ) -> str:
        conditions: list[str] = []
        if filters.bots:
            normalized_bots = [b.strip() for b in filters.bots if isinstance(b, str) and b.strip()]
            if normalized_bots:
                params["filter_bots"] = normalized_bots
                params["filter_bots_norm"] = [b.lower() for b in normalized_bots]
                conditions.append(
                    f"""(
                        {alias}.bot_key = ANY(:filter_bots)
                        OR LOWER(TRIM(COALESCE({alias}.bot_key, ''))) IN (
                            SELECT LOWER(TRIM(br.bot_key))
                            FROM bot_registry br
                            WHERE LOWER(TRIM(COALESCE(br.bot_key, ''))) = ANY(:filter_bots_norm)
                               OR LOWER(TRIM(COALESCE(br.display_name, ''))) = ANY(:filter_bots_norm)
                               OR LOWER(TRIM(COALESCE(br.canonical_base, ''))) = ANY(:filter_bots_norm)
                        )
                    )"""
                )
        if filters.advertising_companies:
            normalized_companies = [c.strip() for c in filters.advertising_companies if isinstance(c, str) and c.strip()]
            if normalized_companies:
                params["filter_advertising_companies"] = normalized_companies
                conditions.append(f"{alias}.company = ANY(:filter_advertising_companies)")

        utm_fields = (
            ("utm_source", filters.utm_source),
            ("utm_campaign", filters.utm_campaign),
            ("utm_medium", filters.utm_medium),
            ("utm_content", filters.utm_content),
            ("utm_term", filters.utm_term),
        )
        for field_name, values in utm_fields:
            normalized_values = normalize_utm_filter_values(values or [])
            if normalized_values:
                params[f"filter_{field_name}"] = normalized_values
                conditions.append(f"LOWER(TRIM(COALESCE({alias}.{field_name}, ''))) = ANY(:filter_{field_name})")
        return "".join(f"\n              AND {condition}" for condition in conditions)

    async def _touch_summary_rows(
        self,
        session: AsyncSession,
        filters: ReportFilters,
        group_by: str,
        touch_mode: str,
    ) -> List[dict[str, int]]:
        if group_by not in {"bot_key", "advertising_company"}:
            return []

        params: dict[str, Any] = {
            "excluded_bot_keys": normalized_excluded_bot_keys(),
            "start": filters.start_date,
            "end": filters.end_date,
            "user_scope": filters.user_scope or "all",
        }
        attr_filter_sql = self._build_touch_attr_filters_sql("a", filters, params)
        group_expr = "a.bot_key" if group_by == "bot_key" else "a.company"

        if touch_mode == "first_touch":
            attributed_cte = f"""
            attributed AS (
                SELECT DISTINCT ON (be.tg_user_id)
                    be.tg_user_id,
                    be.company,
                    be.bot_key,
                    be.utm_source,
                    be.utm_campaign,
                    be.utm_medium,
                    be.utm_content,
                    be.utm_term,
                    be.first_bot_at AS touch_at,
                    be.first_bot_at,
                    be.first_bot_at AS filter_at
                FROM bot_entries be
                ORDER BY be.tg_user_id, be.first_bot_at ASC, be.bot_key ASC
            )
            """
        elif touch_mode == "last_touch":
            attributed_cte = f"""
            last_touch_candidates AS (
                SELECT
                    nr.tg_user_id,
                    nr.company,
                    nr.bot_key,
                    nr.utm_source,
                    nr.utm_campaign,
                    nr.utm_medium,
                    nr.utm_content,
                    nr.utm_term,
                    nr.created_at AS touch_at,
                    be.first_bot_at,
                    uf_touch.first_platform_at AS filter_at,
                    ROW_NUMBER() OVER (
                        PARTITION BY nr.tg_user_id
                        ORDER BY nr.created_at DESC, nr.bot_key ASC
                    ) AS rn
                FROM non_lead_rows nr
                JOIN bot_entries be
                  ON be.tg_user_id = nr.tg_user_id
                 AND be.company = nr.company
                 AND be.bot_key = nr.bot_key
                LEFT JOIN normalized_flags uf_touch
                  ON uf_touch.tg_user_id = nr.tg_user_id
                WHERE uf_touch.first_platform_at IS NULL
                   OR nr.created_at <= uf_touch.first_platform_at
            ),
            attributed AS (
                SELECT
                    ltc.tg_user_id,
                    ltc.company,
                    ltc.bot_key,
                    ltc.utm_source,
                    ltc.utm_campaign,
                    ltc.utm_medium,
                    ltc.utm_content,
                    ltc.utm_term,
                    ltc.touch_at,
                    ltc.first_bot_at,
                    ltc.filter_at
                FROM last_touch_candidates ltc
                WHERE ltc.rn = 1
            )
            """
        else:
            attributed_cte = f"""
            attributed AS (
                SELECT
                    be.tg_user_id,
                    be.company,
                    be.bot_key,
                    be.utm_source,
                    be.utm_campaign,
                    be.utm_medium,
                    be.utm_content,
                    be.utm_term,
                    be.first_bot_at AS touch_at,
                    be.first_bot_at,
                    be.first_bot_at AS filter_at
                FROM bot_entries be
            )
            """

        first_touch_new_only_filter = ""

        non_lead_exclusion_sql = (
            "\n                  AND LOWER(TRIM(COALESCE(r.bot_key, ''))) NOT LIKE 'lead%'"
            if touch_mode in {"first_touch", "last_touch"}
            else ""
        )

        query = text(
            f"""
            WITH first_seen AS (
                SELECT
                    tg_user_id,
                    MIN(created_at) AS first_seen_at_system
                FROM raw_bot_users
                WHERE tg_user_id > 0
                  AND created_at IS NOT NULL
                  AND LOWER(TRIM(COALESCE(bot_key, ''))) <> ALL(:excluded_bot_keys)
                GROUP BY tg_user_id
            ),
            user_flags AS (
                SELECT
                    ru.tg_user_id,
                    BOOL_OR(ru.converted_to_lead IS TRUE OR LOWER(TRIM(COALESCE(ru.bot_key, ''))) LIKE 'lead%') AS did_lead,
                    BOOL_OR(ru.channel_subscribed IS TRUE) AS did_channel,
                    BOOL_OR(ru.ph_user_id IS NOT NULL AND ru.platform_registered_at IS NOT NULL) AS raw_platform,
                    MIN(ru.ph_user_id) FILTER (
                        WHERE ru.ph_user_id IS NOT NULL AND ru.platform_registered_at IS NOT NULL
                    ) AS ph_user_id,
                    BOOL_OR(ru.started_learning IS TRUE OR ru.learn_start_date IS NOT NULL) AS raw_learning,
                    BOOL_OR(ru.completed_course IS TRUE AND ru.completed_course_at IS NOT NULL) AS raw_course,
                    BOOL_OR(ru.used_simulator IS TRUE) AS did_simulator,
                    BOOL_OR(ru.interview_reached IS TRUE) AS raw_interview,
                    BOOL_OR(ru.interview_passed IS TRUE) AS raw_passed,
                    BOOL_OR(ru.offer_received IS TRUE) AS raw_offer,
                    BOOL_OR(ru.contract_signed IS TRUE) AS raw_contract,
                    BOOL_OR(ru.distance_grinding IS TRUE) AS raw_distance,
                    MIN(ru.platform_registered_at) FILTER (
                        WHERE ru.ph_user_id IS NOT NULL AND ru.platform_registered_at IS NOT NULL
                    ) AS first_platform_at,
                    MIN(ru.learn_start_date) FILTER (
                        WHERE ru.ph_user_id IS NOT NULL
                          AND ru.platform_registered_at IS NOT NULL
                          AND ru.learn_start_date IS NOT NULL
                    ) AS first_lesson_at
                FROM raw_bot_users ru
                WHERE ru.tg_user_id > 0
                GROUP BY ru.tg_user_id
            ),
            normalized_flags AS (
                SELECT
                    uf.tg_user_id,
                    uf.did_lead,
                    uf.did_channel,
                    uf.ph_user_id,
                    uf.did_simulator,
                    uf.first_platform_at,
                    uf.first_lesson_at,
                    uf.raw_platform AS did_platform,
                    (uf.raw_platform AND uf.raw_learning) AS did_learning,
                    (uf.raw_platform AND uf.raw_learning AND uf.raw_course) AS did_course,
                    (uf.raw_platform AND uf.raw_learning AND uf.raw_course AND uf.raw_interview) AS did_interview,
                    (uf.raw_platform AND uf.raw_learning AND uf.raw_course AND uf.raw_interview AND uf.raw_passed) AS did_passed,
                    (uf.raw_platform AND uf.raw_learning AND uf.raw_course AND uf.raw_interview AND uf.raw_passed AND uf.raw_offer) AS did_offer,
                    (uf.raw_platform AND uf.raw_learning AND uf.raw_course AND uf.raw_interview AND uf.raw_passed AND uf.raw_offer AND uf.raw_contract) AS did_contract,
                    (uf.raw_platform AND uf.raw_learning AND uf.raw_course AND uf.raw_interview AND uf.raw_passed AND uf.raw_offer AND uf.raw_distance) AS did_distance
                FROM user_flags uf
            ),
            non_lead_rows AS (
                SELECT
                    r.tg_user_id,
                    {self._normalized_company_sql("r")} AS company,
                    {self._bot_label_sql("r")} AS bot_key,
                    COALESCE(
                        NULLIF(
                            CASE
                                WHEN LOWER(BTRIM(COALESCE(r.platform_utm_source, ''))) IN ('', '-', '—', 'none', 'null', '(none)', 'undefined', 'n/a', 'na', 'нет метки')
                                THEN ''
                                ELSE BTRIM(COALESCE(r.platform_utm_source, ''))
                            END,
                        ''),
                        NULLIF(
                            CASE
                                WHEN LOWER(BTRIM(COALESCE(r.utm_source, ''))) IN ('', '-', '—', 'none', 'null', '(none)', 'undefined', 'n/a', 'na', 'нет метки')
                                THEN ''
                                ELSE BTRIM(COALESCE(r.utm_source, ''))
                            END,
                        ''),
                    '') AS utm_source,
                    COALESCE(
                        NULLIF(
                            CASE
                                WHEN LOWER(BTRIM(COALESCE(r.platform_utm_campaign, ''))) IN ('', '-', '—', 'none', 'null', '(none)', 'undefined', 'n/a', 'na', 'нет метки')
                                THEN ''
                                ELSE BTRIM(COALESCE(r.platform_utm_campaign, ''))
                            END,
                        ''),
                        NULLIF(
                            CASE
                                WHEN LOWER(BTRIM(COALESCE(r.utm_campaign, ''))) IN ('', '-', '—', 'none', 'null', '(none)', 'undefined', 'n/a', 'na', 'нет метки')
                                THEN ''
                                ELSE BTRIM(COALESCE(r.utm_campaign, ''))
                            END,
                        ''),
                    '') AS utm_campaign,
                    COALESCE(
                        NULLIF(
                            CASE
                                WHEN LOWER(BTRIM(COALESCE(r.platform_utm_medium, ''))) IN ('', '-', '—', 'none', 'null', '(none)', 'undefined', 'n/a', 'na', 'нет метки')
                                THEN ''
                                ELSE BTRIM(COALESCE(r.platform_utm_medium, ''))
                            END,
                        ''),
                        NULLIF(
                            CASE
                                WHEN LOWER(BTRIM(COALESCE(r.utm_medium, ''))) IN ('', '-', '—', 'none', 'null', '(none)', 'undefined', 'n/a', 'na', 'нет метки')
                                THEN ''
                                ELSE BTRIM(COALESCE(r.utm_medium, ''))
                            END,
                        ''),
                    '') AS utm_medium,
                    COALESCE(
                        NULLIF(
                            CASE
                                WHEN LOWER(BTRIM(COALESCE(r.platform_utm_content, ''))) IN ('', '-', '—', 'none', 'null', '(none)', 'undefined', 'n/a', 'na', 'нет метки')
                                THEN ''
                                ELSE BTRIM(COALESCE(r.platform_utm_content, ''))
                            END,
                        ''),
                        NULLIF(
                            CASE
                                WHEN LOWER(BTRIM(COALESCE(r.utm_content, ''))) IN ('', '-', '—', 'none', 'null', '(none)', 'undefined', 'n/a', 'na', 'нет метки')
                                THEN ''
                                ELSE BTRIM(COALESCE(r.utm_content, ''))
                            END,
                        ''),
                    '') AS utm_content,
                    COALESCE(
                        NULLIF(
                            CASE
                                WHEN LOWER(BTRIM(COALESCE(r.platform_utm_term, ''))) IN ('', '-', '—', 'none', 'null', '(none)', 'undefined', 'n/a', 'na', 'нет метки')
                                THEN ''
                                ELSE BTRIM(COALESCE(r.platform_utm_term, ''))
                            END,
                        ''),
                        NULLIF(
                            CASE
                                WHEN LOWER(BTRIM(COALESCE(r.utm_term, ''))) IN ('', '-', '—', 'none', 'null', '(none)', 'undefined', 'n/a', 'na', 'нет метки')
                                THEN ''
                                ELSE BTRIM(COALESCE(r.utm_term, ''))
                            END,
                        ''),
                    '') AS utm_term,
                    r.created_at
                FROM raw_bot_users r
                WHERE r.tg_user_id > 0
                  AND r.created_at IS NOT NULL
                  AND LOWER(TRIM(COALESCE(r.bot_key, ''))) <> ALL(:excluded_bot_keys)
                  {non_lead_exclusion_sql}
            ),
            bot_entries AS (
                SELECT DISTINCT ON (nr.tg_user_id, nr.company, nr.bot_key)
                    nr.tg_user_id,
                    nr.company,
                    nr.bot_key,
                    nr.utm_source,
                    nr.utm_campaign,
                    nr.utm_medium,
                    nr.utm_content,
                    nr.utm_term,
                    nr.created_at AS first_bot_at
                FROM non_lead_rows nr
                ORDER BY nr.tg_user_id, nr.company, nr.bot_key, nr.created_at ASC
            ),
            {attributed_cte}
            SELECT
                {group_expr} AS group_value,
                COUNT(DISTINCT a.tg_user_id) AS entered,
                COUNT(
                    DISTINCT CASE
                        WHEN (fs.first_seen_at_system AT TIME ZONE 'Europe/Moscow')::date
                             = (a.first_bot_at AT TIME ZONE 'Europe/Moscow')::date
                        THEN a.tg_user_id
                    END
                ) AS new_in_system,
                COUNT(
                    DISTINCT CASE
                        WHEN (fs.first_seen_at_system AT TIME ZONE 'Europe/Moscow')::date
                             < (a.first_bot_at AT TIME ZONE 'Europe/Moscow')::date
                        THEN a.tg_user_id
                    END
                ) AS old_in_system,
                COUNT(DISTINCT CASE WHEN uf.did_lead THEN a.tg_user_id END) AS lead,
                COUNT(DISTINCT CASE WHEN uf.did_channel THEN a.tg_user_id END) AS subscribed,
                COUNT(DISTINCT CASE WHEN uf.did_platform THEN uf.ph_user_id END) AS platform,
                COUNT(DISTINCT CASE WHEN uf.did_learning THEN uf.ph_user_id END) AS learning,
                COUNT(DISTINCT CASE WHEN uf.did_course THEN uf.ph_user_id END) AS course,
                COUNT(DISTINCT CASE WHEN uf.did_simulator THEN uf.ph_user_id END) AS simulator,
                COUNT(DISTINCT CASE WHEN uf.did_interview THEN uf.ph_user_id END) AS interview,
                COUNT(DISTINCT CASE WHEN uf.did_passed THEN uf.ph_user_id END) AS passed,
                COUNT(DISTINCT CASE WHEN uf.did_offer THEN uf.ph_user_id END) AS offer,
                COUNT(DISTINCT CASE WHEN uf.did_contract THEN uf.ph_user_id END) AS contract,
                COUNT(DISTINCT CASE WHEN uf.did_distance THEN uf.ph_user_id END) AS distance_grinding
            FROM attributed a
            JOIN first_seen fs ON fs.tg_user_id = a.tg_user_id
            JOIN normalized_flags uf ON uf.tg_user_id = a.tg_user_id
            WHERE (CAST(:start AS date) IS NULL OR (a.filter_at AT TIME ZONE 'Europe/Moscow')::date >= CAST(:start AS date))
              AND (CAST(:end AS date) IS NULL OR (a.filter_at AT TIME ZONE 'Europe/Moscow')::date <= CAST(:end AS date))
              AND (
                    :user_scope = 'all'
                    OR (
                        :user_scope = 'new'
                        AND (fs.first_seen_at_system AT TIME ZONE 'Europe/Moscow')::date
                            = (a.first_bot_at AT TIME ZONE 'Europe/Moscow')::date
                    )
                    OR (
                        :user_scope = 'old'
                        AND (fs.first_seen_at_system AT TIME ZONE 'Europe/Moscow')::date
                            < (a.first_bot_at AT TIME ZONE 'Europe/Moscow')::date
                    )
                ){attr_filter_sql}{first_touch_new_only_filter}
            GROUP BY 1
            ORDER BY entered DESC, group_value
            """
        )
        result = await session.execute(query, params)
        return [
            {
                "group": row.group_value,
                "entered": int(row.entered or 0),
                "new_in_system": int(row.new_in_system or 0),
                "old_in_system": int(row.old_in_system or 0),
                "lead": int(row.lead or 0),
                "subscribed": int(row.subscribed or 0),
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
            for row in result.all()
            if row.group_value
        ]

    # ===== Core aggregate endpoints =====
