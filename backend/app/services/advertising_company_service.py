from __future__ import annotations

import uuid
from typing import Dict, List, Optional

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.analytics import AdvertisingCompany, AdvertisingCompanyBot, RawBotUser


class AdvertisingCompanyService:
    async def list_companies(self, session: AsyncSession) -> List[dict]:
        companies = (await session.execute(select(AdvertisingCompany))).scalars().all()
        bot_rows = (await session.execute(select(AdvertisingCompanyBot))).scalars().all()
        bots_map: Dict[str, List[str]] = {}
        for row in bot_rows:
            bots_map.setdefault(row.company_id, []).append(row.bot_key)
        return [
            {
                "company_id": company.company_id,
                "company_name": company.company_name,
                "is_active": company.is_active,
                "bot_keys": sorted(bots_map.get(company.company_id, [])),
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
    ) -> dict:
        if not company_id:
            company_id = str(uuid.uuid4())
        existing = (
            await session.execute(
                select(AdvertisingCompany).where(AdvertisingCompany.company_id == company_id)
            )
        ).scalar_one_or_none()
        old_name = None
        if existing:
            old_name = existing.company_name
            existing.company_name = company_name
            existing.is_active = is_active
        else:
            existing = AdvertisingCompany(
                company_id=company_id, company_name=company_name, is_active=is_active
            )
            session.add(existing)

        if bot_keys is not None:
            await self._set_company_bots(session, company_id, company_name, bot_keys)
            if old_name and old_name != company_name and bot_keys:
                await session.execute(
                    update(RawBotUser)
                    .where(RawBotUser.bot_key.in_(bot_keys))
                    .where(RawBotUser.advertising_company == old_name)
                    .values(advertising_company=company_name)
                )

        return {
            "company_id": existing.company_id,
            "company_name": existing.company_name,
            "is_active": existing.is_active,
            "bot_keys": sorted(bot_keys or []),
        }

    async def _set_company_bots(
        self, session: AsyncSession, company_id: str, company_name: str, bot_keys: List[str]
    ) -> None:
        bot_keys = sorted({key for key in bot_keys if key})
        old_rows = (
            await session.execute(
                select(AdvertisingCompanyBot.bot_key).where(
                    AdvertisingCompanyBot.company_id == company_id
                )
            )
        ).scalars().all()
        old_keys = set(old_rows)
        new_keys = set(bot_keys)
        removed_keys = sorted(old_keys - new_keys)

        if bot_keys:
            await session.execute(
                delete(AdvertisingCompanyBot).where(AdvertisingCompanyBot.bot_key.in_(bot_keys))
            )

        await session.execute(
            delete(AdvertisingCompanyBot).where(AdvertisingCompanyBot.company_id == company_id)
        )

        for bot_key in bot_keys:
            session.add(AdvertisingCompanyBot(company_id=company_id, bot_key=bot_key))

        if bot_keys:
            await session.execute(
                update(RawBotUser)
                .where(RawBotUser.bot_key.in_(bot_keys))
                .values(advertising_company=company_name)
            )
        if removed_keys:
            await session.execute(
                update(RawBotUser)
                .where(RawBotUser.bot_key.in_(removed_keys))
                .where(RawBotUser.advertising_company == company_name)
                .values(advertising_company=None)
            )

    async def bot_to_company_map(self, session: AsyncSession) -> Dict[str, str]:
        rows = (
            await session.execute(
                select(AdvertisingCompanyBot.bot_key, AdvertisingCompany.company_name)
                .join(AdvertisingCompany, AdvertisingCompany.company_id == AdvertisingCompanyBot.company_id)
                .where(AdvertisingCompany.is_active.is_(True))
            )
        ).all()
        return {row.bot_key: row.company_name for row in rows}

    async def rebuild_assignments(self, session: AsyncSession) -> None:
        mapping = await self.bot_to_company_map(session)
        if not mapping:
            await session.execute(update(RawBotUser).values(advertising_company=None))
            return
        await session.execute(update(RawBotUser).values(advertising_company=None))
        for bot_key, company_name in mapping.items():
            await session.execute(
                update(RawBotUser)
                .where(RawBotUser.bot_key == bot_key)
                .values(advertising_company=company_name)
            )
