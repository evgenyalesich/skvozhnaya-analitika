import asyncio
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.core.config import settings
from app.db.session import async_session


class AttributionService:
    def _is_deadlock(self, exc: Exception) -> bool:
        if not isinstance(exc, DBAPIError):
            return False
        orig = exc.orig
        if orig is None:
            return False
        try:
            import asyncpg  # type: ignore

            if isinstance(orig, asyncpg.exceptions.DeadlockDetectedError):
                return True
        except Exception:
            pass
        return "DeadlockDetectedError" in str(orig)

    async def _execute_with_retry(self, session, stmt, params=None, retries: int = 5):
        for attempt in range(retries):
            try:
                if params is None:
                    return await session.execute(stmt)
                return await session.execute(stmt, params)
            except DBAPIError as exc:
                if self._is_deadlock(exc) and attempt < retries - 1:
                    await session.rollback()
                    await asyncio.sleep(1.0 * (2 ** attempt))
                    continue
                raise

    async def rebuild(self) -> None:
        async with async_session() as session:
            await self.rebuild_in_session(session)
            await session.commit()

    async def rebuild_in_session(self, session) -> None:
        await session.execute(text("SET LOCAL lock_timeout = '15s'"))
        # Single UPDATE combining first_touch + last_touch — one lock pass instead of three.
        await self._execute_with_retry(
            session,
            text(
                """
                WITH learning_users AS (
                    SELECT
                        tg_user_id,
                        MIN(learn_start_date) AS learn_start_date
                    FROM raw_bot_users
                    WHERE learn_start_date IS NOT NULL
                      AND ph_user_id IS NOT NULL
                      AND platform_registered_at IS NOT NULL
                    GROUP BY tg_user_id
                ),
                first_touch AS (
                    SELECT DISTINCT ON (tg_user_id)
                        tg_user_id,
                        bot_key,
                        COALESCE(platform_utm_campaign, utm_campaign, 'нет метки') AS utm_campaign
                    FROM raw_bot_users
                    WHERE created_at IS NOT NULL
                      AND bot_key IS NOT NULL
                      AND trim(bot_key) <> ''
                      AND lower(trim(bot_key)) != ALL(:excluded_bots)
                      AND lower(trim(bot_key)) NOT LIKE 'lead%'
                    ORDER BY tg_user_id, created_at ASC, bot_key ASC
                ),
                last_touch AS (
                    SELECT DISTINCT ON (raw.tg_user_id)
                        raw.tg_user_id,
                        raw.bot_key,
                        COALESCE(raw.platform_utm_campaign, raw.utm_campaign, 'нет метки') AS utm_campaign
                    FROM raw_bot_users AS raw
                    JOIN learning_users ON learning_users.tg_user_id = raw.tg_user_id
                    WHERE raw.created_at IS NOT NULL
                      AND raw.created_at <= learning_users.learn_start_date
                      AND raw.bot_key IS NOT NULL
                      AND trim(raw.bot_key) <> ''
                      AND lower(trim(raw.bot_key)) != ALL(:excluded_bots)
                      AND lower(trim(raw.bot_key)) NOT LIKE 'lead%'
                    ORDER BY raw.tg_user_id, raw.created_at DESC, raw.bot_key ASC
                )
                UPDATE raw_bot_users AS target
                SET
                    first_touch_bot      = COALESCE(ft.bot_key,      'нет метки'),
                    first_touch_campaign = COALESCE(ft.utm_campaign,  'нет метки'),
                    last_touch_bot       = COALESCE(lt.bot_key,       'нет метки'),
                    last_touch_campaign  = COALESCE(lt.utm_campaign,  'нет метки')
                FROM (SELECT tg_user_id, bot_key, utm_campaign FROM first_touch) ft
                FULL JOIN (SELECT tg_user_id, bot_key, utm_campaign FROM last_touch) lt
                    USING (tg_user_id)
                WHERE target.tg_user_id = COALESCE(ft.tg_user_id, lt.tg_user_id)
                """
            ),
            {"excluded_bots": settings.last_touch_exclude_bot_keys},
        )
