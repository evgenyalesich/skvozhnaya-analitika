from datetime import datetime
from typing import Any, List, Optional

from sqlalchemy import func, or_, select

from app.db.session import async_session
from app.models.analytics import EmployeeRegistryEntry, RawBotUser


def excluded_tg_user_ids_subquery():
    return select(EmployeeRegistryEntry.tg_user_id)


def apply_employee_exclusion(stmt, tg_user_id_col):
    return stmt.where(
        or_(
            tg_user_id_col.is_(None),
            ~tg_user_id_col.in_(excluded_tg_user_ids_subquery()),
        )
    )


class EmployeeRegistryService:
    def _username_subquery(self):
        return (
            select(
                RawBotUser.tg_user_id.label("tg_user_id"),
                func.max(RawBotUser.username).label("username"),
            )
            .where(RawBotUser.tg_user_id.is_not(None))
            .group_by(RawBotUser.tg_user_id)
            .subquery()
        )

    async def _fetch_entries(self, session, tg_user_ids: Optional[list[int]] = None) -> List[dict[str, Any]]:
        username_sq = self._username_subquery()
        stmt = (
            select(
                EmployeeRegistryEntry.tg_user_id,
                EmployeeRegistryEntry.created_at,
                EmployeeRegistryEntry.created_by,
                username_sq.c.username,
            )
            .outerjoin(username_sq, username_sq.c.tg_user_id == EmployeeRegistryEntry.tg_user_id)
            .order_by(EmployeeRegistryEntry.created_at.desc())
        )
        if tg_user_ids:
            stmt = stmt.where(EmployeeRegistryEntry.tg_user_id.in_(tg_user_ids))
        result = await session.execute(stmt)
        return [
            {
                "tg_user_id": int(row.tg_user_id),
                "username": row.username,
                "created_at": row.created_at,
                "created_by": row.created_by,
            }
            for row in result.fetchall()
            if row.tg_user_id is not None
        ]

    async def list_entries(self) -> List[dict[str, Any]]:
        async with async_session() as session:
            return await self._fetch_entries(session)

    async def add_entry(self, tg_user_id: int, created_by: Optional[str] = None) -> dict[str, Any]:
        async with async_session() as session:
            exists = await session.execute(
                select(EmployeeRegistryEntry).where(EmployeeRegistryEntry.tg_user_id == tg_user_id)
            )
            existing = exists.scalar_one_or_none()
            if not existing:
                entry = EmployeeRegistryEntry(
                    tg_user_id=tg_user_id,
                    created_by=created_by,
                    created_at=datetime.utcnow(),
                )
                session.add(entry)
                await session.commit()
            rows = await self._fetch_entries(session, [tg_user_id])
            return rows[0]

    async def add_entries(self, tg_user_ids: list[int], created_by: Optional[str] = None) -> list[dict[str, Any]]:
        cleaned_ids = sorted({int(tg_user_id) for tg_user_id in tg_user_ids if int(tg_user_id) > 0})
        if not cleaned_ids:
            return []
        async with async_session() as session:
            existing_ids = set(
                (
                    await session.execute(
                        select(EmployeeRegistryEntry.tg_user_id).where(EmployeeRegistryEntry.tg_user_id.in_(cleaned_ids))
                    )
                ).scalars().all()
            )
            for tg_user_id in cleaned_ids:
                if tg_user_id in existing_ids:
                    continue
                session.add(
                    EmployeeRegistryEntry(
                        tg_user_id=tg_user_id,
                        created_by=created_by,
                        created_at=datetime.utcnow(),
                    )
                )
            await session.commit()
            return await self._fetch_entries(session, cleaned_ids)

    async def replace_entries(self, tg_user_ids: list[int], created_by: Optional[str] = None) -> list[dict[str, Any]]:
        cleaned_ids = sorted({int(tg_user_id) for tg_user_id in tg_user_ids if int(tg_user_id) > 0})
        async with async_session() as session:
            existing_ids = set((await session.execute(select(EmployeeRegistryEntry.tg_user_id))).scalars().all())
            target_ids = set(cleaned_ids)

            if existing_ids - target_ids:
                result = await session.execute(
                    select(EmployeeRegistryEntry).where(EmployeeRegistryEntry.tg_user_id.in_(sorted(existing_ids - target_ids)))
                )
                for entry in result.scalars().all():
                    await session.delete(entry)

            for tg_user_id in sorted(target_ids - existing_ids):
                session.add(
                    EmployeeRegistryEntry(
                        tg_user_id=tg_user_id,
                        created_by=created_by,
                        created_at=datetime.utcnow(),
                    )
                )

            await session.commit()
            return await self._fetch_entries(session)

    async def remove_entry(self, tg_user_id: int) -> None:
        async with async_session() as session:
            stmt = select(EmployeeRegistryEntry).where(EmployeeRegistryEntry.tg_user_id == tg_user_id)
            result = await session.execute(stmt)
            entry = result.scalar_one_or_none()
            if entry:
                await session.delete(entry)
                await session.commit()
