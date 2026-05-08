import argparse
import asyncio
import csv
import re
import sys
from datetime import datetime
from pathlib import Path

import asyncpg
from sqlalchemy.engine import make_url


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.core.config import settings  # noqa: E402


def _safe_name(value: str) -> str:
    cleaned = re.sub(r"[^0-9A-Za-z._-]+", "_", value.strip())
    return cleaned.strip("._-") or "unknown_bot"


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export raw_bot_users to per-bot CSV files (all fields, all rows)."
    )
    parser.add_argument(
        "--out-dir",
        default=f"/tmp/raw_bot_users_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
        help="Output directory for CSV files.",
    )
    args = parser.parse_args()

    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    analytics_url = make_url(str(settings.analytics_db_dsn))
    conn = await asyncpg.connect(
        user=analytics_url.username,
        password=analytics_url.password,
        host=analytics_url.host or "localhost",
        port=analytics_url.port or 5432,
        database=analytics_url.database,
    )

    try:
        columns_rows = await conn.fetch(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema='public' AND table_name='raw_bot_users'
            ORDER BY ordinal_position
            """
        )
        columns = [row["column_name"] for row in columns_rows]
        if not columns:
            raise RuntimeError("No columns found for raw_bot_users")

        bots_rows = await conn.fetch(
            """
            SELECT bot_key, COUNT(*) AS rows_cnt
            FROM raw_bot_users
            GROUP BY bot_key
            ORDER BY bot_key
            """
        )
        if not bots_rows:
            raise RuntimeError("raw_bot_users is empty: nothing to export")

        select_cols = ", ".join(f'"{col}"' for col in columns)
        manifest_path = out_dir / "_manifest.csv"

        with manifest_path.open("w", encoding="utf-8", newline="") as manifest_file:
            writer = csv.writer(manifest_file)
            writer.writerow(["bot_key", "rows", "file"])

            for row in bots_rows:
                bot_key = str(row["bot_key"] or "")
                rows_cnt = int(row["rows_cnt"] or 0)
                file_name = f"{_safe_name(bot_key)}.csv"
                file_path = out_dir / file_name

                query = f"""
                    SELECT {select_cols}
                    FROM raw_bot_users
                    WHERE bot_key = $1
                    ORDER BY id
                """

                with file_path.open("wb") as out_file:
                    await conn.copy_from_query(
                        query,
                        bot_key,
                        output=out_file,
                        format="csv",
                        header=True,
                    )

                writer.writerow([bot_key, rows_cnt, file_name])
                print(f"exported {bot_key}: {rows_cnt} rows -> {file_path}")

        print(f"\nDone. Output directory: {out_dir}")
        print(f"Manifest: {manifest_path}")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
