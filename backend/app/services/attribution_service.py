import asyncio
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.core.config import settings
from app.db.session import async_session


class AttributionService:
    """Обновляет атрибуцию first_touch / last_touch для всех пользователей.

    first_touch — самый ранний бот пользователя (исключая lead/ almanah),
    last_touch  — последний бот до даты регистрации на платформе (platform_registered_at).
                  Для пользователей без platform_registered_at last_touch остаётся 'нет метки'.
    Обновляет поля first_touch_bot, first_touch_campaign, last_touch_bot,
    last_touch_campaign прямо в raw_bot_users одним UPDATE+CTE.

    Запускается из worker после ингестии или принудительно через admin API.
    """

    def _is_retryable_lock_error(self, exc: Exception) -> bool:
        """Deadlock или lock timeout — оба ретраятся."""
        if not isinstance(exc, DBAPIError):
            return False
        orig = exc.orig
        if orig is None:
            return False
        try:
            import asyncpg  # type: ignore

            if isinstance(orig, (
                asyncpg.exceptions.DeadlockDetectedError,
                asyncpg.exceptions.LockNotAvailableError,
            )):
                return True
        except Exception:
            pass
        orig_str = str(orig)
        return "DeadlockDetectedError" in orig_str or "LockNotAvailableError" in orig_str

    async def _execute_with_retry(self, session, stmt, params=None, retries: int = 5):
        """Выполняет запрос с экспоненциальным retry при deadlock/lock timeout (до 5 попыток, 1/2/4/8/16с)."""
        for attempt in range(retries):
            try:
                if params is None:
                    return await session.execute(stmt)
                return await session.execute(stmt, params)
            except DBAPIError as exc:
                if self._is_retryable_lock_error(exc) and attempt < retries - 1:
                    await session.rollback()
                    await asyncio.sleep(1.0 * (2 ** attempt))
                    continue
                raise

    async def rebuild(self) -> None:
        """Создаёт сессию и запускает rebuild_in_session — публичная точка входа."""
        async with async_session() as session:
            await self.rebuild_in_session(session)
            await session.commit()

    async def rebuild_in_session(self, session) -> None:
        """Выполняет атрибуцию в переданной сессии.

        Устанавливает lock_timeout=15s, чтобы не висеть на блокировке.
        Один UPDATE через CTE: сначала вычисляет first_touch и last_touch,
        потом применяет их за один проход — вместо трёх отдельных UPDATE.
        excluded_bots читается из settings.last_touch_exclude_bot_keys.
        """
        await session.execute(text("SET LOCAL lock_timeout = '15s'"))
        # Один UPDATE вместо трёх — один проход по таблице, меньше локов.
        await self._execute_with_retry(
            session,
            text(
                """
                WITH platform_users AS (
                    SELECT
                        tg_user_id,
                        MIN(platform_registered_at) AS platform_registered_at
                    FROM raw_bot_users
                    WHERE ph_user_id IS NOT NULL
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
                    JOIN platform_users ON platform_users.tg_user_id = raw.tg_user_id
                    WHERE raw.created_at IS NOT NULL
                      AND raw.created_at <= platform_users.platform_registered_at
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
                  AND (
                    target.first_touch_bot      IS DISTINCT FROM COALESCE(ft.bot_key,      'нет метки')
                    OR target.first_touch_campaign IS DISTINCT FROM COALESCE(ft.utm_campaign, 'нет метки')
                    OR target.last_touch_bot       IS DISTINCT FROM COALESCE(lt.bot_key,      'нет метки')
                    OR target.last_touch_campaign  IS DISTINCT FROM COALESCE(lt.utm_campaign, 'нет метки')
                  )
                """
            ),
            {"excluded_bots": settings.last_touch_exclude_bot_keys},
        )
