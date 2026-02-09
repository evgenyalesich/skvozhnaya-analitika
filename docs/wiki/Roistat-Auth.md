# Аутентификация Roistat (Telegram)

Дашборд использует логин через Telegram и хранит access token в браузере.

## Фронтенд

Основные файлы:

- `frontend/src/hooks/useTelegramAuth.ts`
- `frontend/src/hooks/useTelegramAccess.ts`

Хранилище:

- localStorage key: `auth_token`

Флоу:

1. Фронт вызывает `POST /api/auth/telegram/start`.
2. Бек создает `start_token` и `login_url` для Telegram.
3. Пользователь открывает Telegram и нажимает "Авторизоваться" в боте.
4. Бек создает сессию; фронт поллит статус и сохраняет `access_token` в localStorage.

## Бекенд

Основные файлы:

- `backend/app/api/routers/auth.py`
- `backend/app/services/telegram_auth.py`

Redis:

- Сессии: `auth:session:{token}` с TTL `settings.auth_session_ttl_seconds`.

Сообщение бота:

- В тексте упоминается домен `roistat.pokerhub.pro` (захардкожено в `telegram_auth.py`).

Доступы:

- Есть таблица `telegram_access`.
- Есть whitelist `settings.initial_allowed_telegram_ids`.

## Операционные нюансы

- Если `settings.telegram_bot_token` не задан, сообщения в Telegram не будут отправляться.
- Если `settings.auth_jwt_secret` не задан, выдача токенов сломается.
