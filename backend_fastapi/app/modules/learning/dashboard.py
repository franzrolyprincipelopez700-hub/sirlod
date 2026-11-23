from collections.abc import Iterable
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import LIMA, campus_now
from app.core.config import settings
from app.core.exceptions import AppError
from app.models import DetallePermiso, Losa, Permiso
from app.modules.learning.datasets import latest_attendance
from app.modules.learning.models import Attempt, Attendance, Incident
from app.modules.learning.schemas import Module
from app.modules.learning.service import forecast


def series(rows: Iterable[tuple[Any, ...]]) -> list[dict[str, Any]]:
    return [{"clave": str(key), "valor": int(value)} for key, value in rows if key is not None]


async def dashboard(db: AsyncSession, module: Module, day: date | None = None) -> dict[str, Any]:
    now = campus_now()
    today = now.date()
    start = today - timedelta(days=27)
    end = today
    result: dict[str, Any] = {
        "origen": "demostracion" if settings.is_practice else "institucional",
        "inicio": start,
        "fin": end,
    }
    if module == "demanda":
        reserved = (
            select(DetallePermiso.id_d)
            .select_from(DetallePermiso)
            .join(Permiso)
            .where(DetallePermiso.fecha.between(start, end), Permiso.estado == "Aceptado")
        )
        by_hour = (
            await db.execute(
                reserved.with_only_columns(DetallePermiso.hora_inicio, func.count())
                .group_by(DetallePermiso.hora_inicio)
                .order_by(DetallePermiso.hora_inicio)
            )
        ).all()
        by_court = (
            await db.execute(
                reserved.join(Losa, Losa.id_l == DetallePermiso.id_l)
                .with_only_columns(Losa.nombre, func.count())
                .group_by(Losa.nombre).order_by(func.count().desc(), Losa.nombre)
            )
        ).all()
        selected = day or today + timedelta(days=1)
        try:
            result["consulta"] = await forecast(db, selected, register_predictions=False)
        except AppError as exc:
            if exc.status_code not in (409, 422):
                raise
            result["error_consulta"] = exc.message
        result.update(
            fecha_consulta=selected,
            por_hora=series((hour.strftime("%H:%M"), count) for hour, count in by_hour),
            por_losa=series((name, count) for name, count in by_court),
        )
    elif module == "anomalias":
        since = datetime.combine(start, time.min)
        until = datetime.combine(end + timedelta(days=1), time.min)
        permits = (
            await db.execute(
                select(Permiso.estado, func.count())
                .where(Permiso.fecha_creacion >= since, Permiso.fecha_creacion < until)
                .group_by(Permiso.estado)
            )
        ).all()
        incidents = (
            await db.execute(select(Incident.tipo, Incident.estado, func.count()).group_by(
                Incident.tipo, Incident.estado
            ))
        ).all()
        attempts = await db.scalar(
            select(func.count()).select_from(Attempt).where(
                Attempt.ocurrido >= since.replace(tzinfo=LIMA).astimezone(UTC),
                Attempt.ocurrido < until.replace(tzinfo=LIMA).astimezone(UTC),
            )
        )
        result.update(
            por_solicitud=series((state, count) for state, count in permits),
            intentos=attempts or 0,
            casos=[{"tipo": kind, "estado": state, "cantidad": count} for kind, state, count in incidents],
        )
    else:
        end = today + timedelta(days=7)
        latest = latest_attendance()
        finished = or_(
            DetallePermiso.fecha < today,
            and_(DetallePermiso.fecha == today, DetallePermiso.hora_fin <= now.time()),
        )
        outcome = case(
            (Permiso.estado == "Cancelado", "cancelado"),
            (Attendance.resultado.is_not(None), Attendance.resultado),
            (finished, "sin_verificar"),
            else_="pendiente",
        )
        counts = (
            await db.execute(
                select(outcome, func.count())
                .select_from(DetallePermiso)
                .join(Permiso)
                .outerjoin(latest, latest.c.detalle_id == DetallePermiso.id_d)
                .outerjoin(Attendance, Attendance.id == latest.c.latest)
                .where(
                    DetallePermiso.fecha.between(start, end),
                    Permiso.estado.in_(("Aceptado", "Cancelado")),
                )
                .group_by(outcome)
            )
        ).all()
        result.update(fin=end, por_resultado=series((status, count) for status, count in counts))
    return result
