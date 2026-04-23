from __future__ import with_statement

from pathlib import Path
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy import create_engine

ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT))

from app.core.config import settings
from app.db.base import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

section = config.get_section(config.config_ini_section) or {}
analytics_url = str(settings.analytics_db_dsn)
if analytics_url.startswith("postgresql+asyncpg"):
    section["sqlalchemy.url"] = analytics_url.replace("+asyncpg", "")
else:
    section["sqlalchemy.url"] = analytics_url

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=section["sqlalchemy.url"],
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = create_engine(section["sqlalchemy.url"], poolclass=pool.NullPool)

    with connectable.connect() as connection:
        do_run_migrations(connection)


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
