from typing import Any

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import session_factory


async def _postgres_rows(
    query: str, parameters: dict[str, str], db: AsyncSession | None
) -> list[dict[str, Any]]:
    if db is None:
        async with session_factory() as session:
            return await _postgres_rows(query, parameters, session)
    return [dict(row) for row in (await db.execute(text(query), parameters)).mappings()]


async def get_usuario(codigo: str, *, db: AsyncSession | None = None) -> dict[str, Any] | None:
    """Consulta un usuario académico por código."""
    if settings.is_practice or settings.unheval_source == "postgresql":
        rows = await _postgres_rows(
            f"SELECT * FROM {settings.unheval_view} WHERE codigo = :codigo LIMIT 1",
            {"codigo": codigo},
            db,
        )
        return rows[0] if rows else None
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            response = await client.get(f"{settings.unheval_api_url}/usuario/{codigo}")
            response.raise_for_status()
            raw_payload = response.json()
        if not isinstance(raw_payload, dict):
            return None
        payload: dict[str, Any] = raw_payload
        data = payload.get("data")
        if payload.get("success") and isinstance(data, dict):
            return {str(key): value for key, value in data.items()}
    except (httpx.HTTPError, ValueError, TypeError):
        return None
    return None


async def list_usuarios(*, db: AsyncSession | None = None) -> list[dict[str, Any]]:
    """Obtiene la vista consolidada de usuarios de la API académica."""
    if settings.is_practice or settings.unheval_source == "postgresql":
        return await _postgres_rows(
            f"SELECT * FROM {settings.unheval_view} ORDER BY nombre_completo", {}, db
        )
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.get(f"{settings.unheval_api_url}/usuarios")
        response.raise_for_status()
        raw_payload = response.json()
    if not isinstance(raw_payload, dict):
        return []
    data = raw_payload.get("data", [])
    if not isinstance(data, list):
        return []
    return [{str(key): value for key, value in item.items()} for item in data if isinstance(item, dict)]
