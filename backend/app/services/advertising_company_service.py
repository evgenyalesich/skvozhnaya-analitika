from __future__ import annotations

import asyncio
from datetime import date
import uuid
from typing import Any, Dict, List, Optional

from sqlalchemy import Date, String, and_, cast, delete, func, literal, or_, select, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.models.analytics import AdvertisingCompany, AdvertisingCompanyBot, RawBotUser


class AdvertisingCompanyService:
    UTM_FIELD_NAMES = [
        "utm_source",
        "utm_campaign",
        "utm_medium",
        "utm_content",
        "utm_term",
    ]

    def _normalize_text(self, value: Any) -> Optional[str]:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    def _normalize_date(self, value: Any) -> Optional[str]:
        text = self._normalize_text(value)
        if not text:
            return None
        try:
            return date.fromisoformat(text).isoformat()
        except ValueError:
            return None

    def _normalize_priority(self, value: Any) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0

    def _normalize_utm_rule(self, rule: Any) -> dict[str, Any]:
        if hasattr(rule, "model_dump"):
            rule = rule.model_dump()
        clean_rule = {
            key: self._normalize_text(rule.get(key))
            for key in self.UTM_FIELD_NAMES
        }
        clean_rule["bot_keys"] = sorted({
            bot_key.strip()
            for bot_key in (rule.get("bot_keys") or [])
            if isinstance(bot_key, str) and bot_key.strip()
        })
        clean_rule["date_from"] = self._normalize_date(rule.get("date_from"))
        clean_rule["date_to"] = self._normalize_date(rule.get("date_to"))
        clean_rule["priority"] = self._normalize_priority(rule.get("priority"))
        match_mode = self._normalize_text(rule.get("match_mode")) or "all"
        clean_rule["match_mode"] = match_mode if match_mode in {"all", "any"} else "all"
        return clean_rule

    def _rule_has_matchers(self, rule: dict[str, Any]) -> bool:
        return bool(
            rule.get("bot_keys")
            or rule.get("date_from")
            or rule.get("date_to")
            or any(rule.get(field) for field in self.UTM_FIELD_NAMES)
        )

    def _rule_specificity(self, rule: dict[str, Any], kind: str) -> tuple[int, int, int, int]:
        utm_count = sum(1 for field in self.UTM_FIELD_NAMES if rule.get(field))
        bot_bonus = 1 if rule.get("bot_keys") else 0
        date_bonus = int(bool(rule.get("date_from"))) + int(bool(rule.get("date_to")))
        kind_bonus = 0 if kind == "bot" else 1
        return (utm_count, bot_bonus, date_bonus, kind_bonus)

    def _normalized_field_match(self, platform_col, bot_col, value: str):
        normalized_value = value.strip().lower()
        return func.lower(
            func.trim(func.coalesce(platform_col, bot_col, literal("", String)))
        ) == literal(normalized_value, String)

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

    async def _execute_with_retry(self, session: AsyncSession, stmt, retries: int = 3):
        for attempt in range(retries):
            try:
                return await session.execute(stmt)
            except DBAPIError as exc:
                if self._is_deadlock(exc) and attempt < retries - 1:
                    await session.rollback()
                    await asyncio.sleep(0.4 * (2 ** attempt))
                    continue
                raise

    async def list_companies(self, session: AsyncSession) -> List[dict]:
        companies = (await session.execute(
            select(AdvertisingCompany).order_by(AdvertisingCompany.created_at.asc())
        )).scalars().all()
        bot_rows = (await session.execute(select(AdvertisingCompanyBot))).scalars().all()
        bots_map: Dict[str, List[str]] = {}
        for row in bot_rows:
            bots_map.setdefault(row.company_id, []).append(row.bot_key)
        return [
            {
                "company_id": company.company_id,
                "company_name": company.company_name,
                "platform": company.platform,
                "is_active": company.is_active,
                "bot_keys": sorted(bots_map.get(company.company_id, [])),
                "utm_rules": [self._normalize_utm_rule(rule) for rule in (company.utm_rules or [])],
            }
            for company in companies
        ]

    async def upsert_company(
        self,
        session: AsyncSession,
        company_id: Optional[str],
        company_name: str,
        is_active: bool,
        bot_keys: Optional[List[str]] = None,
        platform: Optional[str] = None,
        utm_rules: Optional[List[dict]] = None,
    ) -> dict:
        company_name = company_name.strip()
        if not company_id:
            existing_by_name = (
                await session.execute(
                    select(AdvertisingCompany).where(AdvertisingCompany.company_name == company_name)
                )
            ).scalar_one_or_none()
            if existing_by_name:
                company_id = existing_by_name.company_id
            else:
                company_id = str(uuid.uuid4())
        existing = (
            await session.execute(
                select(AdvertisingCompany).where(AdvertisingCompany.company_id == company_id)
            )
        ).scalar_one_or_none()
        old_name = None
        clean_utm_rules = [
            self._normalize_utm_rule(rule)
            for rule in (utm_rules or [])
            if self._rule_has_matchers(self._normalize_utm_rule(rule))
        ]
        if existing:
            old_name = existing.company_name
            existing.company_name = company_name
            existing.is_active = is_active
            existing.platform = platform
            existing.utm_rules = clean_utm_rules
            flag_modified(existing, "utm_rules")
        else:
            existing = AdvertisingCompany(
                company_id=company_id, company_name=company_name, is_active=is_active,
                platform=platform, utm_rules=clean_utm_rules,
            )
            session.add(existing)

        if bot_keys is not None:
            await self._set_company_bots(session, company_id, company_name, bot_keys)

        return {
            "company_id": existing.company_id,
            "company_name": existing.company_name,
            "platform": existing.platform,
            "is_active": existing.is_active,
            "bot_keys": sorted(bot_keys or []),
            "utm_rules": clean_utm_rules,
        }

    async def _set_company_bots(
        self, session: AsyncSession, company_id: str, company_name: str, bot_keys: List[str]
    ) -> None:
        bot_keys = sorted({key for key in bot_keys if key})

        if bot_keys:
            await self._execute_with_retry(
                session,
                delete(AdvertisingCompanyBot).where(AdvertisingCompanyBot.bot_key.in_(bot_keys))
            )

        await self._execute_with_retry(
            session,
            delete(AdvertisingCompanyBot).where(AdvertisingCompanyBot.company_id == company_id)
        )

        for bot_key in bot_keys:
            session.add(AdvertisingCompanyBot(company_id=company_id, bot_key=bot_key))

    async def bot_to_company_map(self, session: AsyncSession) -> Dict[str, str]:
        rows = (
            await session.execute(
                select(AdvertisingCompanyBot.bot_key, AdvertisingCompany.company_name)
                .join(AdvertisingCompany, AdvertisingCompany.company_id == AdvertisingCompanyBot.company_id)
                .where(AdvertisingCompany.is_active.is_(True))
            )
        ).all()
        return {row.bot_key: row.company_name for row in rows}

    async def delete_company(self, session: AsyncSession, company_id: str) -> bool:
        company = (
            await session.execute(
                select(AdvertisingCompany).where(AdvertisingCompany.company_id == company_id)
            )
        ).scalar_one_or_none()
        if not company:
            return False
        bot_keys = (
            await session.execute(
                select(AdvertisingCompanyBot.bot_key).where(
                    AdvertisingCompanyBot.company_id == company_id
                )
            )
        ).scalars().all()
        await self._execute_with_retry(
            session,
            delete(AdvertisingCompanyBot).where(AdvertisingCompanyBot.company_id == company_id)
        )
        await self._execute_with_retry(
            session,
            delete(AdvertisingCompany).where(AdvertisingCompany.company_id == company_id)
        )
        return True

    async def rebuild_assignments(self, session: AsyncSession) -> None:
        await self._execute_with_retry(
            session,
            update(RawBotUser).values(advertising_company=None)
        )

        companies = (
            await session.execute(
                select(AdvertisingCompany).where(
                    AdvertisingCompany.is_active.is_(True),
                )
            )
        ).scalars().all()

        utm_fields = [
            ("utm_source", RawBotUser.utm_source, RawBotUser.platform_utm_source),
            ("utm_campaign", RawBotUser.utm_campaign, RawBotUser.platform_utm_campaign),
            ("utm_medium", RawBotUser.utm_medium, RawBotUser.platform_utm_medium),
            ("utm_content", RawBotUser.utm_content, RawBotUser.platform_utm_content),
            ("utm_term", RawBotUser.utm_term, RawBotUser.platform_utm_term),
        ]

        bot_rows = (
            await session.execute(
                select(AdvertisingCompanyBot.bot_key, AdvertisingCompany.company_name)
                .join(AdvertisingCompany, AdvertisingCompany.company_id == AdvertisingCompanyBot.company_id)
                .where(AdvertisingCompany.is_active.is_(True))
            )
        ).all()

        assignment_rules: list[dict[str, Any]] = [
            {
                "kind": "bot",
                "company_name": row.company_name,
                "bot_keys": [row.bot_key],
                "priority": 0,
            }
            for row in bot_rows
        ]

        for company in companies:
            rules = [self._normalize_utm_rule(rule) for rule in (company.utm_rules or [])]
            for rule in rules:
                if not self._rule_has_matchers(rule):
                    continue
                assignment_rules.append(
                    {
                        **rule,
                        "kind": "utm",
                        "company_name": company.company_name,
                    }
                )

        assignment_rules.sort(
            key=lambda rule: (
                int(rule.get("priority") or 0),
                *self._rule_specificity(rule, str(rule.get("kind") or "utm")),
                str(rule.get("company_name") or ""),
            )
        )

        for rule in assignment_rules:
            field_conditions = []
            bot_keys = rule.get("bot_keys") or []
            if bot_keys:
                field_conditions.append(RawBotUser.bot_key.in_(bot_keys))

            if rule.get("date_from"):
                field_conditions.append(RawBotUser.created_at.is_not(None))
                field_conditions.append(func.date(RawBotUser.created_at) >= date.fromisoformat(rule["date_from"]))
            if rule.get("date_to"):
                field_conditions.append(RawBotUser.created_at.is_not(None))
                field_conditions.append(func.date(RawBotUser.created_at) <= date.fromisoformat(rule["date_to"]))

            utm_matchers = []
            for field_name, bot_col, platform_col in utm_fields:
                val = rule.get(field_name)
                if val:
                    utm_matchers.append(self._normalized_field_match(platform_col, bot_col, val))

            match_mode = rule.get("match_mode") or "all"
            if utm_matchers:
                field_conditions.append(and_(*utm_matchers) if match_mode != "any" else or_(*utm_matchers))

            if not field_conditions:
                continue

            await self._execute_with_retry(
                session,
                update(RawBotUser)
                .where(*field_conditions)
                .values(advertising_company=rule["company_name"])
                .execution_options(synchronize_session=False)
            )
