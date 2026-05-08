# Main Report Formula Matrix

## Scope

This matrix maps the target `Weekly` sheet columns to the current implementation in:

- `backend/app/api/routers/reports_roistat_companies_parts/*`
- `frontend/src/components/MainReportTable.tsx`

Status legend:

- `OK` — metric/formula is already implemented with the same business meaning.
- `DIFF` — implemented, but denominator/semantics differ from sheet formula.
- `MISS` — not implemented in current main report pipeline.

## Column Mapping

| Target column (RU) | Current source/field | Current formula | Status | Notes |
|---|---|---|---|---|
| Месяц | UI grouping by `week_start[:7]` | N/A | OK | Grouping exists. |
| Расход $ | `budget` | from `budget_weekly` | OK | |
| План Расход $ | — | — | MISS | No plan budget field in main report payload. |
| Подписки в салун | `saloon` | count | OK | |
| Подписки на канал | `channel_subscribed` | count | OK | |
| Старт в бота | `entered_all` | count | OK | |
| Стоимость старта $ | `cpa_start` | `budget / entered_all` | OK | |
| Регистрации в Альманах | `almanah_starts` | count | OK | |
| Регистрация на ПХ | `platform_cnt` | count | OK | |
| % Регистрация на ПХ | `platform_cr` | `platform_cnt / almanah_starts` | OK | |
| Стоимость регистрации на ПХ | `cpa_platform` | `budget / platform_cnt` | OK | |
| Квал лид (старт обучения) | `started_learning` | count | OK | |
| % старта обучения | `started_course_cr` | `started_learning / platform_cnt` | OK | |
| Стоимость старта обучения | `cpa_learning` | `budget / started_learning` | OK | |
| Активные | — | — | MISS | No explicit active bucket metric in payload. |
| % активных | — | — | MISS | Depends on missing "Активные". |
| Неактивные | `not_started` (closest) | count | DIFF | Sheet has separate active/inactive from another base; current uses `platform - started_learning`. |
| % неактивных | — | — | MISS | No dedicated percentage column. |
| ПХ лид (Прошли курс до конца) | `completed_course` | count | OK | |
| Потрачено на курс дней, сред. | — | — | MISS | No avg days metric in main report. |
| Стоимость ПХ лид | `cpa_course` | `budget / completed_course` | OK | |
| % прохождения | `course_cr` | `completed_course / started_learning` | OK | |
| Скорость прохождения (уроков в день) | — | — | MISS | Not in payload/UI. |
| Предофер Лид (Передано направлениям) | `interview_reached` | count | OK | |
| Стоимость Предофер лид | `cpa_preoffer` | `budget / interview_reached` | OK | |
| Отказали/отказались от собеседования | `refused_interview` | count by status map | OK | `raw_bot_users.interview_reached_status/offer_received_status` |
| Не выходят на связь | `no_response_interview` | count by status map | OK | `raw_bot_users.interview_reached_status/offer_received_status` |
| % передано | `interview_cr` | `interview_reached / started_learning` | DIFF | In sheet examples denominator is often `almanah_starts` (`AO/I`). |
| Офер лид (с рег в этом мес) | `offer_received` (closest) | count | DIFF | Current does not separate "this month" vs "total". |
| Офер лид (Итого) | `offer_received` (closest) | count | DIFF | Only one offer metric is present now. |
| Ожидаемых офер лидов | `offer_expected` | `interview_reached*0.5 + completed_course*0.026` | OK | Assumption: active ~ completed_course |
| Потенциальная стоимость офер лида | `cpa_offer_expected` | `budget / offer_expected` | OK | |
| Стоимость оффер лида | `cpa_offer` | `budget / offer_received` | OK | |
| Контракт лид (с рег в этом мес) | `contract_signed` (closest) | count | DIFF | No split by "this month". |
| Контракт лид (итого) | `contract_signed` (closest) | count | DIFF | Only one contract metric is present now. |
| Стоимость контракта | `cpa_contract` | `budget / contract_signed` | OK | |
| Ожидаемых контрактов | `contract_expected` | `completed_course*0.024 + interview_reached*0.46` | OK | Assumption: active ~ completed_course |
| Потенциальная стоимость контракта | `cpa_contract_expected` | `budget / contract_expected` | OK | |
| % выполнения плана | `plan_completion` | `contract_signed / contract_expected` | OK | Interpreted as forecast plan completion |
| Количество регистраций по афке | — | — | MISS | No dedicated "affiliate registrations" metric in current payload. |
| МТТ | `mtt` | count | OK | |
| % МТТ | `mtt_share` | `mtt / learning` | OK | |
| Спины | `spin` | count | OK | |
| % СПИН | `spin_share` | `spin / learning` | OK | |
| Кеш | `cash` | count | OK | |
| % Кеш | `cash_share` | `cash / learning` | OK | |
| Только Базовый | `base` | count | OK | |
| % Только Базовый | `base_share` | `base / learning` | OK | |
| Прошли курс МТТ | `completed_mtt` | count | OK | |
| Прошли курс Спины | `completed_spin` | count | OK | |
| Прошли курс Кеш | `completed_cash` | count | OK | |
| Контракт МТТ | `contract_mtt` | count | OK | |
| Стоимость контракт МТТ | `cpa_contract_mtt` | `budget / contract_mtt` | OK | |
| Контракт Спины | `contract_spin` | count | OK | |
| Стоимость контракт Спины | `cpa_contract_spin` | `budget / contract_spin` | OK | |

## Technical Notes

1. Current divide-by-zero behavior in UI:
- money KPI: `0 -> "—"`
- percent KPI: `0 -> "0.00%"`

2. Sheet behavior frequently uses `#DIV/0!`.
We need an explicit policy for parity:
- either preserve sheet-style errors in export only,
- or keep UI-safe zero/empty rendering.

3. `Weekly` sheet includes manual and forecast formulas (`AE/AK/...`) that are not present in backend payload.
Those should be defined as either:
- deterministic API metrics, or
- UI-only calculated helper columns with explicit formula specs.

## Next Implementation Step

Create a canonical formula registry:

- column key
- display label
- numerator expression
- denominator expression
- zero-division policy
- scope (`week/company/bot/total`)

Then wire both:

- backend export
- frontend table rendering

to the same registry to avoid drift.
