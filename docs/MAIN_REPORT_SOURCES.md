# Main Report Data Sources

## API flow

1. Frontend reads main report from:
- `GET /api/reports/roistat-weekly/companies-weekly`

2. Backend handler:
- [reports_roistat_companies_runtime_core.py](/home/fervuld/prod/analytic-system/backend/app/api/routers/reports_roistat_companies_parts/reports_roistat_companies_runtime_core.py)

3. SQL builders:
- company/week rows: [reports_roistat_companies_runtime_query_main_weekly.py](/home/fervuld/prod/analytic-system/backend/app/api/routers/reports_roistat_companies_parts/reports_roistat_companies_runtime_query_main_weekly.py)
- week totals: [reports_roistat_companies_runtime_query_week_totals.py](/home/fervuld/prod/analytic-system/backend/app/api/routers/reports_roistat_companies_parts/reports_roistat_companies_runtime_query_week_totals.py)

4. Post-processing (course registrations via PH lessons):
- [reports_roistat_companies_postprocess_lessons.py](/home/fervuld/prod/analytic-system/backend/app/api/routers/reports_roistat_companies_parts/reports_roistat_companies_postprocess_lessons.py)

## Physical tables used

- `raw_bot_users` — primary event/user funnel source.
- `budget_weekly` — spend source (`budget`).
- `telegram_subscription_events` — channel/saloon subscriptions.
- `ph_user_mirror_replica` — course and lesson derived metrics (`mtt/spin/cash/base`, completed and contract splits).

## Metric source map

- `budget`:
  - from `budget_weekly.amount` grouped by week/company.

- `entered_all`:
  - `raw_bot_users` distinct users in `start_rows` CTE (week/company attribution).

- `almanah_starts`, `direct_source_cnt`:
  - from `lead_rows` + `user_flags` logic over `raw_bot_users`.

- `new_in_system`, `old_in_system`:
  - `first_seen` (min created_at per tg_user_id) compared with lead date.

- `platform_cnt`:
  - weekly: from synthetic lead rows (`bot_key='lead'`, `tg_user_id<0`) plus filtered `ph_user_id`.
  - company rows: from `user_flags.first_platform_date`.

- `learning`, `started_learning`, `not_started`:
  - `user_flags` derived from `raw_bot_users` and learning/platform flags.

- `mtt`, `spin`, `cash`, `base`:
  - lesson/course presence flags via `ph_user_mirror_replica.lessons` in SQL.
  - then overwritten/normalized in postprocess by `PokerHubLessonSummaryBuilder`.

- `completed_course`, `completed_mtt`, `completed_spin`, `completed_cash`, `completed_base`:
  - from `user_flags.did_complete` + course flags (SQL by week window).

- `interview_reached`, `offer_received`, `contract_signed`, `distance_grinding`:
  - from boolean lifecycle flags in `raw_bot_users` rolled into `user_flags`.

- `refused_interview`, `no_response_interview`:
  - from normalized text statuses in `raw_bot_users.interview_reached_status` and `raw_bot_users.offer_received_status`.
  - refused map: `мы_отказали`, `мы_отказали_арбитраж`, `отказали`, `отказался`, `отказ`, `не_назначали_арбитраж`.
  - no-response map: `не_отвечает`, `не_ответил`, `пропал`.

- `contract_mtt`, `contract_spin`, `contract_cash`:
  - `contract_signed` subset by course flags.

- `channel_subscribed`, `saloon`:
  - from `telegram_subscription_events` grouped by user/channel id.

## UI-only computed formulas

Derived KPI columns (costs/percentages) are computed in:
- [MainReportTable.tsx](/home/fervuld/prod/analytic-system/frontend/src/components/MainReportTable.tsx)

Those are not stored in DB; they are calculated from API fields.

- `offer_expected = interview_reached*0.5 + completed_course*0.026`
- `cpa_offer_expected = budget / offer_expected`
- `contract_expected = completed_course*0.024 + interview_reached*0.46`
- `cpa_contract_expected = budget / contract_expected`
- `plan_completion = contract_signed / contract_expected`

Note:
- explicit `plan_budget` source is still absent in current backend schema (`budget_weekly` stores actual spend only).
