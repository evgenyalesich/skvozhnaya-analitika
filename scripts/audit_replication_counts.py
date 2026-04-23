import asyncio
import sys
from pathlib import Path

import asyncpg
from sqlalchemy.engine import make_url

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.core.config import settings


DATABASES = [
    "Goddes_of_luck_bot",
    "Molodoy_bot",
    "PokerHUB_partners_bot",
    "PokerRates_bot",
    "direktiteration2",
    "dota2usd_bot",
    "lead",
    "leveliq_bot",
    "tgads_HH_Review_bot",
    "tgads_MindStack_bot",
    "tgads_allin_mind_bd",
    "tgads_bot1",
    "tgads_bot2",
    "tgads_bot3",
    "tgads_bot4",
    "tgads_bot5",
    "tgads_bot6",
    "tgads_bot_charttrainer_bot",
    "tgads_charttrainer_bot",
    "tgads_cortexflex_bd",
    "tgads_hand_matrix_bot",
    "tgads_logicdrill_bd",
    "tgads_mindgamesup_bot",
    "tgads_nashnode_bd",
    "tgads_rangelab_bd",
    "tgads_rangemind_bd",
    "tgads_rangmind_bd",
    "tgads_stratmind_bot",
    "tgads_strong_hand_bot",
    "tgads_zeroemotion_bd",
    "tgads_zrange_bot",
]


async def _source_counts(db_name: str, kwargs: dict) -> tuple[int, int]:
    conn = await asyncpg.connect(database=db_name, **kwargs)
    try:
        columns = {
            row["column_name"]
            for row in await conn.fetch(
                "SELECT column_name "
                "FROM information_schema.columns "
                "WHERE table_schema='public' AND table_name='users'"
            )
        }
        if "telegram_id" in columns:
            row = await conn.fetchrow(
                "SELECT count(*) AS rows, "
                "count(DISTINCT COALESCE(telegram_id, id)) AS tg_users "
                "FROM users"
            )
        else:
            row = await conn.fetchrow(
                "SELECT count(*) AS rows, count(DISTINCT id) AS tg_users FROM users"
            )
        return int(row["rows"] or 0), int(row["tg_users"] or 0)
    finally:
        await conn.close()


async def _source_ids(db_name: str, kwargs: dict) -> set[int]:
    conn = await asyncpg.connect(database=db_name, **kwargs)
    try:
        columns = {
            row["column_name"]
            for row in await conn.fetch(
                "SELECT column_name "
                "FROM information_schema.columns "
                "WHERE table_schema='public' AND table_name='users'"
            )
        }
        if "telegram_id" in columns:
            rows = await conn.fetch("SELECT DISTINCT COALESCE(telegram_id, id) AS id FROM users")
        else:
            rows = await conn.fetch("SELECT DISTINCT id FROM users")
        return {int(row["id"]) for row in rows if row["id"] is not None}
    finally:
        await conn.close()


async def main() -> None:
    admin_url = make_url(str(settings.postgres_admin_dsn))
    source_kwargs = {
        "user": admin_url.username,
        "password": admin_url.password,
        "host": admin_url.host or "localhost",
        "port": admin_url.port or 5432,
    }

    analytics_url = make_url(str(settings.analytics_db_dsn))
    analytics = await asyncpg.connect(
        user=analytics_url.username,
        password=analytics_url.password,
        host=analytics_url.host or "localhost",
        port=analytics_url.port or 5432,
        database=analytics_url.database,
    )

    print(
        "db\tsource_rows\tsource_tg_users\tanalytics_rows\tanalytics_tg_users\t"
        "analytics_real_rows\tanalytics_real_tg_users\tsynthetic_ph\t"
        "diff_real_vs_source_tg\tstatus"
    )

    totals = [0, 0, 0, 0, 0, 0, 0]
    mismatches: list[tuple[str, int]] = []
    try:
        for db_name in DATABASES:
            try:
                source_rows, source_tg_users = await _source_counts(db_name, source_kwargs)
            except Exception as exc:
                error = str(exc).replace("\t", " ")[:100]
                print(f"{db_name}\t-\t-\t-\t-\t-\t-\t-\t-\tSOURCE_ERROR:{error}")
                continue

            analytics_row = await analytics.fetchrow(
                """
                SELECT
                    count(*) AS rows,
                    count(DISTINCT tg_user_id) AS tg_users,
                    count(*) FILTER (WHERE tg_user_id > 0) AS real_rows,
                    count(DISTINCT tg_user_id) FILTER (WHERE tg_user_id > 0) AS real_tg_users,
                    count(*) FILTER (WHERE tg_user_id < 0) AS synthetic_ph
                FROM raw_bot_users
                WHERE bot_key = $1
                """,
                db_name,
            )
            analytics_rows = int(analytics_row["rows"] or 0)
            analytics_tg_users = int(analytics_row["tg_users"] or 0)
            analytics_real_rows = int(analytics_row["real_rows"] or 0)
            analytics_real_tg_users = int(analytics_row["real_tg_users"] or 0)
            synthetic_ph = int(analytics_row["synthetic_ph"] or 0)

            diff = analytics_real_tg_users - source_tg_users
            status = (
                "OK"
                if diff == 0
                else "MISSING_IN_ANALYTICS"
                if diff < 0
                else "EXTRA_IN_ANALYTICS"
            )

            print(
                f"{db_name}\t{source_rows}\t{source_tg_users}\t"
                f"{analytics_rows}\t{analytics_tg_users}\t"
                f"{analytics_real_rows}\t{analytics_real_tg_users}\t"
                f"{synthetic_ph}\t{diff}\t{status}"
            )
            if diff != 0:
                mismatches.append((db_name, diff))

            totals[0] += source_rows
            totals[1] += source_tg_users
            totals[2] += analytics_rows
            totals[3] += analytics_tg_users
            totals[4] += analytics_real_rows
            totals[5] += analytics_real_tg_users
            totals[6] += synthetic_ph

        print(
            f"TOTAL\t{totals[0]}\t{totals[1]}\t{totals[2]}\t{totals[3]}\t"
            f"{totals[4]}\t{totals[5]}\t{totals[6]}\t"
            f"{totals[5] - totals[1]}\tTOTAL"
        )

        if mismatches:
            print()
            print("details")
            for db_name, _diff in mismatches:
                source_ids = await _source_ids(db_name, source_kwargs)
                analytics_ids_rows = await analytics.fetch(
                    """
                    SELECT DISTINCT tg_user_id
                    FROM raw_bot_users
                    WHERE bot_key = $1 AND tg_user_id > 0
                    """,
                    db_name,
                )
                analytics_ids = {int(row["tg_user_id"]) for row in analytics_ids_rows}
                missing = sorted(source_ids - analytics_ids)
                extra = sorted(analytics_ids - source_ids)
                print(
                    f"{db_name}: missing={missing[:20]} "
                    f"missing_count={len(missing)} extra={extra[:20]} extra_count={len(extra)}"
                )
    finally:
        await analytics.close()


if __name__ == "__main__":
    asyncio.run(main())
