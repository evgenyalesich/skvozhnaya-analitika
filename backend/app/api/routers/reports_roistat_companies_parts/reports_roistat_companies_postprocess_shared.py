# Разделяемые утилиты постобработки Roistat companies:
#   build_payload_rows — конвертирует SQLAlchemy rows → dict[]
#   upsert_row         — находит или создаёт строку по ключевым полям (применяется при добавлении lesson данных)
#   apply_reg_maps     — записывает lesson-метрики (mtt/spin/cash/base) в payload по company/bot/week ключам
#   reset_course_registration_metrics — обнуляет исторические start_course метрики перед перезаписью из PH Lessons

from typing import Any


METRIC_KEYS = [
    "almanah_starts", "direct_source_cnt", "new_in_system", "old_in_system", "platform_cnt", "learning", "started_learning", "mtt", "spin", "cash", "base",
    "not_started", "channel_subscribed", "saloon",
    "completed_course", "completed_mtt", "completed_spin", "completed_cash", "completed_base",
    "interview_reached", "offer_received", "contract_signed",
    "refused_interview", "no_response_interview",
    "contract_mtt", "contract_spin", "contract_cash", "distance_grinding",
]

EVENT_METRIC_KEYS = [
    "platform_cnt",
    "learning",
    "started_learning",
    "mtt",
    "spin",
    "cash",
    "base",
    "not_started",
    "completed_course",
    "completed_mtt",
    "completed_spin",
    "completed_cash",
    "completed_base",
    "interview_reached",
    "offer_received",
    "contract_signed",
]


def build_payload_rows(*, db_rows, db_bot_rows, db_week_totals_rows) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    rows_payload = [
        {
            "week_start": row.week_start.isoformat(),
            "company": row.company,
            "entered_all": int(row.entered_all or 0),
            "budget": float(row.budget or 0.0),
            **{k: int(getattr(row, k) or 0) for k in METRIC_KEYS},
        }
        for row in db_rows
    ]
    bot_rows_payload = [
        {
            "week_start": row.week_start.isoformat(),
            "company": row.company,
            "bot_key": row.bot_key,
            "entered_all": int(row.entered_all or 0),
            "budget": float(row.budget or 0.0),
            **{k: int(getattr(row, k) or 0) for k in METRIC_KEYS},
        }
        for row in db_bot_rows
    ]
    week_totals_payload = [
        {
            "week_start": row.week_start.isoformat(),
            "entered_all": int(row.entered_all or 0),
            "budget": float(row.budget or 0.0),
            **{k: int(getattr(row, k) or 0) for k in METRIC_KEYS},
        }
        for row in db_week_totals_rows
    ]
    return rows_payload, bot_rows_payload, week_totals_payload


def upsert_row(
    rows: list[dict[str, Any]],
    key_fields: tuple[str, ...],
    key_values: tuple[str, ...],
) -> dict[str, Any]:
    for row in rows:
        if tuple(str(row.get(field) or "") for field in key_fields) == key_values:
            return row
    row: dict[str, Any] = {"entered_all": 0, "budget": 0.0, **{k: 0 for k in METRIC_KEYS}}
    for field, value in zip(key_fields, key_values):
        row[field] = value
    rows.append(row)
    return row


def apply_reg_maps(
    *,
    rows_payload: list[dict[str, Any]],
    bot_rows_payload: list[dict[str, Any]],
    week_totals_payload: list[dict[str, Any]],
    company_reg_map: dict[tuple[str, str], dict[str, int]],
    bot_reg_map: dict[tuple[str, str, str], dict[str, int]],
    week_reg_map: dict[str, dict[str, int]],
) -> None:
    for (week_key, company), metrics in company_reg_map.items():
        row = upsert_row(rows_payload, ("week_start", "company"), (week_key, company))
        row.update(metrics)

    for (week_key, company, bot_key), metrics in bot_reg_map.items():
        row = upsert_row(bot_rows_payload, ("week_start", "company", "bot_key"), (week_key, company, bot_key))
        row.update(metrics)

    for week_key, metrics in week_reg_map.items():
        row = upsert_row(week_totals_payload, ("week_start",), (week_key,))
        row.update(metrics)


def reset_course_registration_metrics(
    *,
    rows_payload: list[dict[str, Any]],
    bot_rows_payload: list[dict[str, Any]],
    week_totals_payload: list[dict[str, Any]],
) -> None:
    for row in rows_payload:
        row["base"] = row["mtt"] = row["spin"] = row["cash"] = 0
    for row in bot_rows_payload:
        row["base"] = row["mtt"] = row["spin"] = row["cash"] = 0
    for row in week_totals_payload:
        row["base"] = row["mtt"] = row["spin"] = row["cash"] = 0
