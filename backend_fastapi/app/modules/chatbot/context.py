import re
from datetime import date, datetime, time, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import campus_now
from app.models import ConfiguracionGlobal, DiaBloqueado, Disciplina, Losa
from app.modules.permisos import service as booking
from app.modules.permisos.schemas import DetallePermisoIn

WEEKDAYS = ("lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo")


def requested_days(text: str, today: date) -> list[date]:
    """Interpreta fechas comunes sin resolver horarios fuera del rango consultado."""
    dates: set[date] = set()
    explicit = re.findall(r"\b(?:\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}(?:/\d{4})?)\b", text)
    for value in explicit:
        try:
            if "-" in value:
                dates.add(date.fromisoformat(value))
            else:
                day, month, *year = map(int, value.split("/"))
                dates.add(date(year[0] if year else today.year, month, day))
        except ValueError:
            continue
    if re.search(r"\b(?:hoy|esta tarde|esta noche)\b", text):
        dates.add(today)
    relative_text = re.sub(r"\b(?:por|en|de) la manana\b", "", text)
    if re.search(r"\bmanana\b", relative_text):
        dates.add(today + timedelta(days=2 if "pasado manana" in text else 1))
    for weekday, name in enumerate(WEEKDAYS):
        if re.search(rf"\b{name}\b", text):
            delta = (weekday - today.weekday()) % 7
            dates.add(today + timedelta(days=delta or (7 if "proximo" in text else 0)))
    if not dates and not explicit:
        dates = {today, today + timedelta(days=1)}
    return sorted(dates)[:3]


async def booking_context(db: AsyncSession, config: ConfiguracionGlobal | None, text: str) -> dict[str, Any]:
    """Solo expone a la IA datos de horarios, canchas y franjas consultables."""
    now = campus_now()
    today = now.date()
    days = requested_days(text, today)
    horizon = today + timedelta(days=30)
    checked_days = [day for day in days if today <= day <= horizon]
    opening = config.hora_min_apertura if config else time(7)
    closing = config.hora_max_apertura if config else time(19)
    courts = (
        await db.execute(
            select(Losa.id_l, Losa.nombre, Disciplina.nombre)
            .join(Disciplina)
            .where(Losa.estado == "Disponible", Disciplina.estado == "Activo")
            .order_by(Losa.id_l)
            .limit(20)
        )
    ).all()
    blocked = set(
        (await db.scalars(select(DiaBloqueado.fecha).where(DiaBloqueado.fecha.in_(checked_days)))).all()
    )

    slots: list[DetallePermisoIn] = []
    for day in checked_days:
        if day in blocked:
            continue
        start = datetime.combine(day, opening)
        end = datetime.combine(day, closing)
        while start + timedelta(hours=1) <= end:
            finish = start + timedelta(hours=1)
            if day != today or start.time() > now.time():
                slots.extend(
                    DetallePermisoIn(
                        id_l=court_id, fecha=day, hora_inicio=start.time(), hora_fin=finish.time(), duracion=1
                    )
                    for court_id, _, _ in courts
                )
            start = finish
    conflicts = await booking._conflicts(db, slots, lock=False)
    unavailable = {
        (item["detalle"]["id_l"], item["detalle"]["fecha"], item["detalle"]["hora_inicio"])
        for item in conflicts
    }
    free: dict[tuple[int, date], list[str]] = {}
    for slot in slots:
        if (slot.id_l, slot.fecha.isoformat(), slot.hora_inicio.isoformat()) not in unavailable:
            free.setdefault((slot.id_l, slot.fecha), []).append(slot.hora_inicio.strftime("%H:%M"))

    return {
        "fecha_hora_lima": now.strftime("%Y-%m-%d %H:%M"),
        "apertura": opening.strftime("%H:%M"),
        "cierre": closing.strftime("%H:%M"),
        "ventana_solicitudes": (
            [config.hora_min_solicitud.strftime("%H:%M"), config.hora_max_solicitud.strftime("%H:%M")]
            if config else ["07:00", "19:00"]
        ),
        "turno_minutos": 60,
        "limite_semanal_horas_cuando_corresponde": float(config.max_horas_semana) if config else None,
        "fechas_sin_consultar": [day.isoformat() for day in days if day not in checked_days],
        "fechas_bloqueadas": sorted(day.isoformat() for day in blocked),
        "losas": [
            {
                "nombre": name,
                "disciplina": discipline,
                "inicios_libres": {
                    day.isoformat(): free.get((court_id, day), [])
                    for day in checked_days if day not in blocked
                },
            }
            for court_id, name, discipline in courts
        ],
    }
