from sqlalchemy.engine import make_url

from app.core.config import settings


class PostgresRegistry:
    def __init__(self, admin_dsn: str | None = None):
        dsn = str(admin_dsn or settings.postgres_admin_dsn)
        if dsn.startswith("postgresql+asyncpg://"):
            dsn = dsn.replace("postgresql+asyncpg://", "postgresql://", 1)
        self._base = make_url(dsn)

    def dsn_for(self, database_name: str) -> str:
        if not database_name:
            raise ValueError("bot database_name is required")
        base = self._base.set(database=database_name)
        # Build DSN manually to avoid password masking in some SQLAlchemy versions.
        user = base.username or ""
        password = base.password or ""
        host = base.host or "localhost"
        port = base.port or 5432
        if user and password:
            auth = f"{user}:{password}@"
        elif user:
            auth = f"{user}@"
        else:
            auth = ""
        return f"postgresql://{auth}{host}:{port}/{database_name}"
