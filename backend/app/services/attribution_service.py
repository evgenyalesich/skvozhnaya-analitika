from sqlalchemy import text

from app.core.config import settings
from app.db.session import async_session


class AttributionService:
    async def rebuild(self) -> None:
        async with async_session() as session:
            await self.rebuild_in_session(session)
            await session.commit()

    async def rebuild_in_session(self, session) -> None:
        await session.execute(
            text(
                """
                UPDATE raw_bot_users
                SET
                    first_touch_bot = 'нет метки',
                    first_touch_campaign = 'нет метки',
                    last_touch_bot = 'нет метки',
                    last_touch_campaign = 'нет метки'
                """
            )
        )

        await session.execute(
            text(
                """
                WITH ranked AS (
                    SELECT
                        tg_user_id,
                        bot_key,
                        COALESCE(utm_campaign, 'нет метки') AS utm_campaign,
                        ROW_NUMBER() OVER (
                            PARTITION BY tg_user_id
                            ORDER BY created_at ASC, bot_key ASC
                        ) AS rn
                    FROM raw_bot_users
                    WHERE created_at IS NOT NULL
                      AND bot_key IS NOT NULL
                      AND trim(bot_key) <> ''
                      AND lower(trim(bot_key)) != ALL(:excluded_bots)
                      AND lower(trim(bot_key)) NOT LIKE 'lead%'
                )
                UPDATE raw_bot_users AS target
                SET
                    first_touch_bot = ranked.bot_key,
                    first_touch_campaign = ranked.utm_campaign
                FROM ranked
                WHERE target.tg_user_id = ranked.tg_user_id
                  AND ranked.rn = 1
                """
            ),
            {"excluded_bots": settings.first_touch_exclude_bot_keys},
        )

        await session.execute(
            text(
                """
                WITH learning_users AS (
                    SELECT
                        tg_user_id,
                        MIN(learn_start_date) AS learn_start_date
                    FROM raw_bot_users
                    WHERE learn_start_date IS NOT NULL
                    GROUP BY tg_user_id
                ),
                ranked AS (
                    SELECT
                        raw.tg_user_id,
                        raw.bot_key,
                        COALESCE(raw.utm_campaign, 'нет метки') AS utm_campaign,
                        ROW_NUMBER() OVER (
                            PARTITION BY raw.tg_user_id
                            ORDER BY raw.created_at DESC, raw.bot_key ASC
                        ) AS rn
                    FROM raw_bot_users AS raw
                    JOIN learning_users ON learning_users.tg_user_id = raw.tg_user_id
                    WHERE raw.created_at IS NOT NULL
                      AND raw.created_at <= learning_users.learn_start_date
                      AND raw.bot_key IS NOT NULL
                      AND trim(raw.bot_key) <> ''
                      AND lower(trim(raw.bot_key)) != ALL(:excluded_bots)
                      AND lower(trim(raw.bot_key)) NOT LIKE 'lead%'
                )
                UPDATE raw_bot_users AS target
                SET
                    last_touch_bot = ranked.bot_key,
                    last_touch_campaign = ranked.utm_campaign
                FROM ranked
                WHERE target.tg_user_id = ranked.tg_user_id
                  AND ranked.rn = 1
                """
            ),
            {"excluded_bots": settings.last_touch_exclude_bot_keys},
        )
