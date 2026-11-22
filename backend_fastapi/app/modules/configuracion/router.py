from typing import Any

from fastapi import APIRouter

from app.core.database import DBSession
from app.core.security import Administrator
from app.modules.configuracion import service
from app.modules.configuracion.schemas import ConfiguracionUpdate

router = APIRouter(prefix="/configuracion", tags=["Configuración"])


@router.get("/")
async def get(db: DBSession) -> dict[str, Any]:
    return await service.get(db)


@router.put("/")
async def update(payload: ConfiguracionUpdate, db: DBSession, _admin: Administrator) -> dict[str, str]:
    await service.update(db, payload)
    return {"mensaje": "Configuración actualizada"}
