from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.analytics import RawBotUser
from app.services.employee_registry_service import apply_employee_exclusion


class GoogleSheetsIngestorApplyMixin:
    @staticmethod
    def _parse_int_id(row: dict, keys: list[str]) -> Optional[int]:
        for key in keys:
            value = row.get(key)
            if value is None:
                continue
            text_value = str(value).strip()
            if not text_value:
                continue
            try:
                return int(text_value)
            except Exception:
                continue
        return None

    async def _apply(self, session: AsyncSession, rows: List[dict], is_sm: bool = False) -> None:
        lead_tg_ids = set()
        lead_ph_ids = set()
        lead_result = await session.execute(
            select(RawBotUser.tg_user_id, RawBotUser.ph_user_id).where(RawBotUser.bot_key == "lead")
        )
        for row in lead_result.fetchall():
            if row.tg_user_id is not None:
                lead_tg_ids.add(int(row.tg_user_id))
            if row.ph_user_id is not None:
                lead_ph_ids.add(int(row.ph_user_id))
        if is_sm:
            await self._execute_with_retry(
                session,
                update(RawBotUser)
                .where(RawBotUser.bot_key == "lead")
                .values(
                    interview_reached=False,
                    interview_passed=False,
                    offer_received=False,
                    contract_signed=False,
                    interview_reached_at=None,
                    interview_passed_at=None,
                    offer_received_at=None,
                    contract_signed_at=None,
                    distance_grinding=False,
                    community_member=False,
                    interview_reached_status=None,
                    interview_passed_status=None,
                    offer_received_status=None,
                    contract_signed_status=None,
                    community_member_status=None,
                )
                .execution_options(synchronize_session=False),
            )
            # Important: do not commit reset early.
            # Reset + row updates must be one atomic transaction; otherwise
            # interrupted jobs leave all lead stage flags/date fields as zeros/nulls.
        processed = 0
        matched_predicates = 0
        updated_rows = 0
        for row in rows:
            processed += 1
            tg_id = self._parse_int_id(
                row,
                ["telegram_id", "tg_user_id", "tg_id", "user_id", "id", "__col_2", "__col_1"],
            )
            ph_id = self._parse_int_id(
                row,
                ["pokerhub_id", "poker_hub_id", "ph_user_id", "ph_id", "__col_3"],
            )
            username = self._normalize_username(
                row.get("tg_юзернейм")
                or row.get("tg_username")
                or row.get("username")
                or row.get("__col_4")
            )

            if tg_id is None and ph_id is None and not username:
                continue
            if ph_id is not None:
                if lead_ph_ids and ph_id not in lead_ph_ids:
                    continue
                predicates = [RawBotUser.ph_user_id == ph_id]
            elif tg_id is not None:
                if lead_tg_ids and tg_id not in lead_tg_ids:
                    continue
                predicates = [RawBotUser.tg_user_id == tg_id]
            elif username:
                predicates = [func.lower(func.trim(RawBotUser.username)) == username]
            else:
                continue
            matched_predicates += 1

            values = {}
            if is_sm:
                interview_reached = self._get_status(
                    row,
                    [
                        "interview_reached",
                        "interview",
                        "interview_reach",
                        "sobes",
                        "sobes_reached",
                        "собеседование",
                        "собес",
                        "собес_достиг",
                        "дошел_до_собеседования",
                    ],
                    true_values=self._true_status_values,
                    false_values=self._false_status_values,
                )
                interview_reached_status = self._get_raw_value(
                    row,
                    [
                        "interview_reached",
                        "interview",
                        "interview_reach",
                        "sobes",
                        "sobes_reached",
                        "собеседование",
                        "собес",
                        "собес_достиг",
                        "дошел_до_собеседования",
                    ],
                )
                if interview_reached is not None:
                    values["interview_reached"] = interview_reached
                if interview_reached_status is not None:
                    values["interview_reached_status"] = interview_reached_status
                    normalized_interview = self._normalize_cell(interview_reached_status)
                    if normalized_interview in {"наигрывают_дистанцию", "нагрывают_дистанцию"}:
                        values["distance_grinding"] = True
                interview_reached_at = self._get_datetime(
                    row,
                    [
                        "дата_передачи_направлению",
                        "дата_передачи_направлению_",
                        "date_transfer_to_direction",
                        "transfer_to_direction_date",
                    ],
                )
                if interview_reached_at is not None:
                    values["interview_reached_at"] = interview_reached_at

                interview_passed = self._get_status(
                    row,
                    [
                        "interview_passed",
                        "interview_ok",
                        "sobes_passed",
                        "собеседование_пройдено",
                        "собес_пройден",
                        "прошел_собеседование",
                    ],
                    true_values=self._true_status_values,
                    false_values=self._false_status_values,
                )
                interview_passed_status = self._get_raw_value(
                    row,
                    [
                        "interview_passed",
                        "interview_ok",
                        "sobes_passed",
                        "собеседование_пройдено",
                        "собес_пройден",
                        "прошел_собеседование",
                    ],
                )
                if interview_passed is not None:
                    values["interview_passed"] = interview_passed
                if interview_passed_status is not None:
                    values["interview_passed_status"] = interview_passed_status
                interview_passed_at = self._get_datetime(
                    row,
                    [
                        "дата_выхода_на_собес",
                        "дата_выхода_на_собеседование",
                        "interview_date",
                        "interview_at",
                    ],
                )
                if interview_passed_at is not None:
                    values["interview_passed_at"] = interview_passed_at

                offer_received = self._get_status(
                    row,
                    [
                        "offer_received",
                        "offer",
                        "offer_get",
                        "оффер",
                        "офер",
                        "offer_получен",
                        "дали_оффер",
                    ],
                    true_values=self._true_status_values,
                    false_values=self._false_status_values,
                )
                offer_received_status = self._get_raw_value(
                    row,
                    [
                        "offer_received",
                        "offer",
                        "offer_get",
                        "оффер",
                        "офер",
                        "offer_получен",
                        "дали_оффер",
                    ],
                )
                if offer_received is not None:
                    values["offer_received"] = offer_received
                if offer_received_status is not None:
                    values["offer_received_status"] = offer_received_status
                    normalized_offer = self._normalize_cell(offer_received_status)
                    if normalized_offer in {"наигрывают_дистанцию", "нагрывают_дистанцию"}:
                        values["distance_grinding"] = True
                offer_received_at = self._get_datetime(
                    row,
                    [
                        "дата_оффера",
                        "дата_офера",
                        "offer_date",
                        "offer_at",
                    ],
                )
                if offer_received_at is None and offer_received:
                    # In current SM sheet offer date may be absent. Fallback to interview/contract dates.
                    offer_received_at = interview_passed_at or interview_reached_at
                if offer_received_at is not None:
                    values["offer_received_at"] = offer_received_at

                contract_signed = self._get_status(
                    row,
                    [
                        "contract_signed",
                        "contract",
                        "контракт",
                        "contract_подписан",
                        "подписал_контракт",
                    ],
                    true_values=self._true_status_values,
                    false_values=self._false_status_values,
                )
                contract_signed_status = self._get_raw_value(
                    row,
                    [
                        "contract_signed",
                        "contract",
                        "контракт",
                        "contract_подписан",
                        "подписал_контракт",
                    ],
                )
                if contract_signed is not None:
                    values["contract_signed"] = contract_signed
                if contract_signed_status is not None:
                    values["contract_signed_status"] = contract_signed_status
                contract_signed_at = self._get_datetime(
                    row,
                    [
                        "дата_подписания_контракта",
                        "contract_signed_date",
                        "contract_date",
                        "contract_signed_at",
                    ],
                )
                if contract_signed_at is not None:
                    values["contract_signed_at"] = contract_signed_at

                saloon_member = self._get_status(
                    row,
                    [
                        "есть_в_салуне",
                        "saloon",
                        "saloon_member",
                    ],
                    true_values=self._true_status_values,
                    false_values=self._false_status_values,
                )
                saloon_member_status = self._get_raw_value(
                    row,
                    [
                        "есть_в_салуне",
                        "saloon",
                        "saloon_member",
                    ],
                )
                if saloon_member is not None:
                    values["community_member"] = saloon_member
                if saloon_member_status is not None:
                    values["community_member_status"] = saloon_member_status

                # completed_course is sourced from PokerHub API only.
            else:
                # Intentionally do not write started_learning from Google Sheets.
                # "Started learning" is derived from PokerHub first-lesson timestamp (learn_start_date).
                pass

            if not values:
                continue

            stmt = (
                update(RawBotUser)
                .where(and_(RawBotUser.bot_key == "lead", or_(*predicates)))
                .values(**values)
                .execution_options(synchronize_session=False)
            )
            result = await self._execute_with_retry(session, stmt)
            try:
                updated_rows += int(result.rowcount or 0)
            except Exception:
                pass
            if processed % 200 == 0:
                self._logger.warning(
                    "GoogleSheets apply progress: processed=%s matched=%s updated=%s",
                    processed,
                    matched_predicates,
                    updated_rows,
                )
        self._logger.warning(
            "GoogleSheets apply done: processed=%s matched=%s updated=%s",
            processed,
            matched_predicates,
            updated_rows,
        )
