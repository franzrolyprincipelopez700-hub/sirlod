import ssl
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends
from sqlalchemy import event
from sqlalchemy.engine import AdaptedConnection
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings

tls = (
    ssl.create_default_context(cafile=settings.postgres_tls_ca_cert, cadata=settings.postgres_tls_ca_pem)
    if settings.postgres_tls_verify
    else None
)
engine = create_async_engine(
    settings.sqlalchemy_database_url,
    pool_pre_ping=True,
    pool_size=settings.postgres_pool_size,
    max_overflow=settings.postgres_max_overflow,
    connect_args={"ssl": tls} if tls else {},
)
session_factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)


@event.listens_for(engine.sync_engine, "connect")
def configure_schema(connection: AdaptedConnection, _record: object) -> None:
    if settings.postgres_schema != "public":
        # Apply per session after connecting, including through the Supabase session pooler.
        schema = settings.postgres_schema
        connection.run_async(
            lambda driver: driver.execute(
                f"SET SESSION search_path TO \"{schema}\", pg_catalog; SET SESSION TIME ZONE 'America/Lima'"
            )
        )


async def get_db() -> AsyncIterator[AsyncSession]:
    """Proporciona una sesión y garantiza rollback ante errores."""
    async with session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


DBSession = Annotated[AsyncSession, Depends(get_db)]
