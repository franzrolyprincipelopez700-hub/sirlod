from typing import Annotated, Any

from fastapi import APIRouter, Depends
from sqlalchemy import String, func, select

from app.core.config import settings
from app.core.database import DBSession
from app.core.security import CurrentUser, require_roles
from app.core.serialization import model_dict
from app.models import Losa, Notificacion, Permiso, ReporteGenerado, Trabajador, User

router = APIRouter(prefix="/administracion", tags=["Administración"])
Admin = Annotated[CurrentUser, Depends(require_roles("Administrador"))]


@router.get("/inicio")
async def overview(db: DBSession, _admin: Admin) -> dict[str, Any]:
    counts = (await db.execute(select(
        select(func.count()).select_from(User).scalar_subquery().label("totalUsuarios"),
        select(func.count()).select_from(Trabajador).scalar_subquery().label("totalTrabajadores"),
        select(func.count()).select_from(Losa).scalar_subquery().label("totalLosas"),
        select(func.count()).select_from(Losa).where(Losa.estado == "Disponible")
        .scalar_subquery().label("losasActivas"),
        select(func.count()).select_from(ReporteGenerado).scalar_subquery().label("totalReportes"),
    ))).mappings().one()
    states = dict((await db.execute(select(Permiso.estado, func.count()).group_by(Permiso.estado))).all())
    pending = (await db.execute(
        select(Permiso.id_p, Permiso.tipo, Permiso.estado, Permiso.fecha_creacion,
               func.coalesce(User.codigo, Permiso.autor.cast(String)).label("autor"))
        .outerjoin(User, Permiso.id_u == User.id_u)
        .where(Permiso.estado == "Pendiente")
        .order_by(Permiso.fecha_creacion.desc(), Permiso.id_p.desc())
        .limit(5)
    )).mappings().all()
    notifications = (await db.scalars(
        select(Notificacion).order_by(Notificacion.fecha_envio.desc(), Notificacion.id_n.desc()).limit(6)
    )).all()
    return {
        **counts,
        "entorno": "practica" if settings.is_practice else "institucional",
        "pendientes": states.get("Pendiente", 0),
        "aprobados": states.get("Aceptado", 0),
        "rechazados": states.get("Rechazado", 0),
        "ultimosPendientes": [dict(item) for item in pending],
        "ultimasNotifs": [model_dict(item) for item in notifications],
    }
