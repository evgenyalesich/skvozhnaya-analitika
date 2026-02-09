import asyncio
import os
from typing import List, Dict, Any

import pymongo
from pymongo.errors import PyMongoError
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config_loader import ConfigLoader
from app.models.analytics import RawBotUser


class MongoIngestor:
    def __init__(self, loader: ConfigLoader):
        self.loader = loader

    async def ingest(self, session: AsyncSession) -> None:
        config = self.loader.data_sources().get("mongodb", {})
        conn_env = config.get("connection_string_env")
        connection_string = os.environ.get(conn_env or "")
        if not connection_string:
            return
        database = config.get("database")
        collection_name = config.get("collection")
        if not database or not collection_name:
            return
        try:
            documents = await asyncio.to_thread(
                self._fetch_documents, connection_string, database, collection_name
            )
        except PyMongoError:
            # Mongo может быть недоступен — не роняем общий ingestion
            return
        await self._apply(session, documents)

    def _fetch_documents(self, conn_str: str, db_name: str, collection_name: str) -> List[Dict[str, Any]]:
        client = pymongo.MongoClient(conn_str, serverSelectionTimeoutMS=3000)
        collection = client[db_name][collection_name]
        documents = list(collection.find({}))
        client.close()
        return documents

    async def _apply(self, session: AsyncSession, documents: List[Dict[str, Any]]) -> None:
        for doc in documents:
            tg_user_id = doc.get("tg_user_id")
            if not tg_user_id:
                continue
            try:
                user_id = int(tg_user_id)
            except ValueError:
                continue
            stmt = (
                update(RawBotUser)
                .where(RawBotUser.tg_user_id == user_id)
                .values(
                    team_member=doc.get("team_member", False),
                    internal_status=doc.get("internal_status"),
                )
            )
            await session.execute(stmt)
