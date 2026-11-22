import asyncio
from pathlib import Path
from typing import cast

import asyncpg

from app.core.database import engine


async def migrate() -> None:
    migrations = Path(__file__).resolve().parents[2] / "database" / "postgres" / "migrations"
    sql = migrations / "20261122_learning.sql"
    try:
        async with engine.connect() as connection:
            raw = await connection.get_raw_connection()
            driver = cast(asyncpg.Connection, raw.driver_connection)
            await driver.execute(sql.read_text(encoding="utf-8"))
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(migrate())
    print("Migración RF-04, RF-05 y RF-06 aplicada")
