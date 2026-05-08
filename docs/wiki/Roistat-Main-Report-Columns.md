# Main Report: колонки и источники

Эта страница описывает, как считается каждая колонка основного отчета (`/api/reports/roistat-weekly/companies-weekly`).

## Где считается

- SQL (основной weekly): `backend/app/api/routers/reports_roistat_companies_parts/reports_roistat_companies_runtime_query_main_weekly.py`
- SQL (итоги по неделям): `backend/app/api/routers/reports_roistat_companies_parts/reports_roistat_companies_runtime_query_week_totals.py`
- Постобработка payload: `backend/app/api/routers/reports_roistat_companies_parts/reports_roistat_companies_postprocess_shared.py`
- Формулы UI: `frontend/src/components/MainReportTable.tsx`

## Важно: Прямой источник

`Прямой источник` **оставлен** и считается.

Смысл сейчас в коде:
- пользователь попал в `lead%` напрямую (не через обычный бот),
- есть `ph_user_id`,
- и выполняется условие `abs(tg_user_id) = ph_user_id`.

В SQL это флаг `is_direct_source`, а в выдаче метрика `direct_source_cnt`.

## Маппинг колонок

| Колонка | Как считается | Источник |
|---|---|---|
| Месяц | `month(week_start)` | `week_start` из API |
| Расход $ | `budget` | `budget_weekly.amount` |
| План Расход $ | не реализовано | источника нет |
| Подписки в салун | `saloon` | `telegram_subscription_events` |
| Подписки на канал | `channel_subscribed` | `telegram_subscription_events` |
| Старт в бота | `entered_all` | `raw_bot_users` distinct starts |
| Стоимость старта $ | `budget / entered_all` | UI формула |
| Регистрации в Альманах | `almanah_starts` | `raw_bot_users` (lead attribution) |
| Прямой источник | `direct_source_cnt` | `raw_bot_users` (`is_direct_source`) |
| Стоимость Альманах | `budget / almanah_starts` | UI формула |
| Регистрация на ПХ | `platform_cnt` | `raw_bot_users.ph_user_id + platform_registered_at` |
| % Регистрация на ПХ | `platform_cnt / almanah_starts` | UI формула |
| Стоимость регистрации на ПХ | `budget / platform_cnt` | UI формула |
| Квал лид (старт обучения) | `started_learning` | `raw_bot_users.started_learning OR learn_start_date` |
| % старта обучения | `started_learning / platform_cnt` | UI формула |
| Стоимость старта обучения | `budget / started_learning` | UI формула |
| Активные | не реализовано | источника нет |
| % активных | не реализовано | источника нет |
| Неактивные | `not_started` | SQL: есть platform, нет learning |
| % неактивных | не реализовано | источника нет |
| ПХ лид (прошли курс) | `completed_course` | `raw_bot_users.completed_course` |
| Потрачено на курс дней, сред. | не реализовано | источника нет |
| Стоимость ПХ лид | `budget / completed_course` | UI формула |
| % прохождения | `completed_course / started_learning` | UI формула |
| Скорость прохождения (уроков в день) | не реализовано | источника нет |
| Предофер лид | `interview_reached` | `raw_bot_users.interview_reached` |
| Стоимость предофер лид | `budget / interview_reached` | UI формула (`cpa_preoffer`) |
| Отказали/отказались | `refused_interview` | `interview_reached_status/offer_received_status` |
| Не выходят на связь | `no_response_interview` | `interview_reached_status/offer_received_status` |
| % передано | `interview_reached / almanah_starts` | UI формула |
| Офер лид (с рег в этом мес) | отдельного поля нет | используется `offer_received` |
| Офер лид (итого) | `offer_received` | `raw_bot_users.offer_received` |
| Ожидаемых офер лидов | `interview_reached*0.5 + completed_course*0.026` | UI формула |
| Потенциальная стоимость офер | `budget / offer_expected` | UI формула |
| Стоимость офер лида | `budget / offer_received` | UI формула |
| Контракт лид (с рег в этом мес) | отдельного поля нет | используется `contract_signed` |
| Контракт лид (итого) | `contract_signed` | `raw_bot_users.contract_signed` |
| Стоимость контракта | `budget / contract_signed` | UI формула |
| Ожидаемых контрактов | `completed_course*0.024 + interview_reached*0.46` | UI формула |
| Потенциальная стоимость контракта | `budget / contract_expected` | UI формула |
| % выполнения плана | `contract_signed / contract_expected` | UI формула |
| Кол-во регистраций по афке | не реализовано | источника нет |
| МТТ | `mtt` | `ph_user_mirror_replica.lessons` |
| % МТТ | `mtt / learning` | UI формула |
| Спины | `spin` | `ph_user_mirror_replica.lessons` |
| % СПИН | `spin / learning` | UI формула |
| Кеш | `cash` | `ph_user_mirror_replica.lessons` |
| % Кеш | `cash / learning` | UI формула |
| Только Базовый | `base` | `ph_user_mirror_replica.lessons` |
| % Только Базовый | `base / learning` | UI формула |
| Прошли курс МТТ | `completed_mtt` | completed + MTT |
| Прошли курс Спины | `completed_spin` | completed + SPIN |
| Прошли курс Кеш | `completed_cash` | completed + CASH |
| Контракт МТТ | `contract_mtt` | contract + MTT |
| Стоимость контракт МТТ | `budget / contract_mtt` | UI формула |
| Контракт Спины | `contract_spin` | contract + SPIN |
| Стоимость контракт Спины | `budget / contract_spin` | UI формула |

## Что еще не покрыто 1-в-1

- Нет отдельного источника `План Расход $`.
- Нет отдельного поля split для "с рег в этом мес" по `offer/contract`.
- Нет отдельной метрики "регистрации по афке".
