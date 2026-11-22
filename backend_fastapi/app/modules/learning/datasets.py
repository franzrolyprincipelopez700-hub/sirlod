from collections import Counter, defaultdict
from datetime import UTC, date, datetime, time, timedelta
from random import Random

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.selectable import Subquery

from app.core.clock import LIMA, campus_now
from app.models import ConfiguracionGlobal, DetallePermiso, DiaBloqueado, Disciplina, Losa, Permiso
from app.modules.learning.features import (
    LOOKBACK_DAYS,
    SEED,
    Features,
    Sample,
    calendar,
    hours,
    no_show_features,
    utc_assumed,
    week_start,
)
from app.modules.learning.models import Attempt, Attendance
from app.modules.learning.schemas import Module


async def demand_samples(db: AsyncSession) -> list[Sample]:
    today = campus_now().date()
    start = today - timedelta(days=LOOKBACK_DAYS)
    config = await db.get(ConfiguracionGlobal, 1)
    if config is None:
        return []
    courts = {
        court: discipline
        for court, discipline in (
            await db.execute(
                select(Losa.id_l, Losa.id_d)
                .join(Disciplina)
                .where(Losa.estado == "Disponible", Disciplina.estado == "Activo")
            )
        ).all()
    }
    blocked = set((await db.scalars(select(DiaBloqueado.fecha).where(DiaBloqueado.fecha >= start))).all())
    rows = (
        await db.execute(
            select(
                DetallePermiso.id_l, DetallePermiso.fecha, DetallePermiso.hora_inicio, DetallePermiso.hora_fin
            )
            .join(Permiso)
            .where(
                Permiso.estado == "Aceptado",
                DetallePermiso.fecha.between(start, today - timedelta(days=1)),
                DetallePermiso.id_l.in_(courts),
            )
        )
    ).all()
    first_observed: dict[int, date] = {}
    occupied: set[tuple[int, date, int]] = set()
    slots = hours(config.hora_min_apertura, config.hora_max_apertura)
    for court, day, begins, ends in rows:
        if day in blocked:
            continue
        first_observed[court] = min(first_observed.get(court, day), day)
        for hour in slots:
            if begins < time(hour + 1) and ends > time(hour):
                occupied.add((court, day, hour))
    samples: list[Sample] = []
    for court, day in first_observed.items():
        while day < today:
            if day not in blocked:
                for hour in slots:
                    moment = datetime.combine(day, time(hour), LIMA)
                    samples.append(
                        Sample(
                            moment,
                            calendar(day, hour, court, courts[court]),
                            int((court, day, hour) in occupied),
                            moment + timedelta(hours=1),
                        )
                    )
            day += timedelta(days=1)
    return samples


def confirmation(created: datetime | None, decided: datetime | None, kind: str) -> datetime | None:
    if decided is not None:
        return utc_assumed(decided)
    if created is not None and kind == "Normal":
        return created.replace(tzinfo=LIMA) if created.tzinfo is None else created
    return None


def latest_attendance() -> Subquery:
    return (
        select(Attendance.detalle_id, func.max(Attendance.id).label("latest"))
        .group_by(Attendance.detalle_id)
        .subquery()
    )


async def no_show_samples(db: AsyncSession) -> list[Sample]:
    now = campus_now()
    latest = latest_attendance()
    rows = (
        await db.execute(
            select(DetallePermiso, Losa.id_d, Permiso, Attendance)
            .join(Permiso)
            .join(Losa)
            .join(latest, latest.c.detalle_id == DetallePermiso.id_d)
            .join(Attendance, Attendance.id == latest.c.latest)
            .where(
                Permiso.estado == "Aceptado",
                Attendance.resultado.in_(("asistio", "inasistencia")),
                DetallePermiso.fecha.between(now.date() - timedelta(days=LOOKBACK_DAYS), now.date()),
            )
        )
    ).all()
    result = []
    for detail, discipline, permission, attendance in rows:
        start = datetime.combine(detail.fecha, detail.hora_inicio, LIMA)
        end = datetime.combine(detail.fecha, detail.hora_fin, LIMA)
        confirmed = confirmation(permission.fecha_creacion, permission.fecha_decision, permission.tipo)
        if confirmed is None or not confirmed < start or not end <= attendance.registrado <= now:
            continue
        features = no_show_features(
            detail.fecha,
            detail.hora_inicio,
            detail.id_l,
            discipline,
            detail.duracion,
            permission.tipo,
            confirmed,
        )
        result.append(
            Sample(
                confirmed,
                features,
                int(attendance.resultado == "inasistencia"),
                attendance.registrado,
                permission.id_u,
            )
        )
    return result


async def anomaly_samples(db: AsyncSession) -> list[Sample]:
    today = campus_now().date()
    end = week_start(today)
    start = end - timedelta(weeks=52)
    events: dict[tuple[int, date], Counter[str]] = defaultdict(Counter)
    slots: dict[tuple[int, date], Counter[str]] = defaultdict(Counter)

    def key(owner: int, instant: datetime) -> tuple[int, date]:
        return owner, week_start(instant.astimezone(LIMA).date())

    rows = (
        await db.execute(
            select(Attempt.usuario_id, Attempt.ocurrido, Attempt.resultado, Attempt.franja).where(
                Attempt.ocurrido >= datetime.combine(start, time.min, LIMA),
                Attempt.ocurrido < datetime.combine(end, time.min, LIMA),
            )
        )
    ).all()
    for owner, instant, outcome, slot in rows:
        bucket = key(owner, instant)
        events[bucket]["intentos"] += 1
        if outcome != "registrado":
            events[bucket]["intentos_rechazados"] += 1
        slots[bucket][slot] += 1

    # fecha_creacion predates instrumentation and is a local civil timestamp.
    reservations = (
        await db.execute(
            select(Permiso.id_u, Permiso.fecha_creacion, Permiso.fecha_decision, Permiso.estado).where(
                Permiso.id_u.is_not(None),
                (
                    and_(
                        Permiso.fecha_creacion >= datetime.combine(start, time.min),
                        Permiso.fecha_creacion < datetime.combine(end, time.min),
                    )
                    | and_(
                        Permiso.estado == "Cancelado",
                        Permiso.fecha_decision
                        >= datetime.combine(start, time.min, LIMA).astimezone(UTC).replace(tzinfo=None),
                    )
                ),
            )
        )
    ).all()
    for applicant, created, decided, status in reservations:
        if applicant is None:
            continue
        if created and start <= created.date() < end:
            events[(applicant, week_start(created.date()))]["solicitudes"] += 1
        if status == "Cancelado" and decided:
            bucket = key(applicant, utc_assumed(decided))
            if start <= bucket[1] < end:
                events[bucket]["cancelaciones"] += 1

    return [
        Sample(
            datetime.combine(week + timedelta(days=7), time.min, LIMA),
            anomaly_features(
                counts,
                max(slots[(owner, week)].values(), default=0),
                [
                    events.get((owner, week - timedelta(weeks=lag)), Counter())["solicitudes"]
                    for lag in range(1, 5)
                ],
            ),
            subject=owner,
        )
        for (owner, week), counts in events.items()
    ]


def anomaly_features(counts: Counter[str], repeated: int, previous: list[int]) -> Features:
    typical = sum(previous) / len(previous) if previous else 0.0
    return {
        "solicitudes": counts["solicitudes"],
        "cancelaciones": counts["cancelaciones"],
        "intentos": counts["intentos"],
        "intentos_rechazados": counts["intentos_rechazados"],
        "repeticiones_franja": repeated,
        "solicitudes_media_previa": typical,
        "aumento_solicitudes": max(0, counts["solicitudes"] - typical),
    }


async def real_samples(db: AsyncSession, module: Module) -> list[Sample]:
    extractor = {"demanda": demand_samples, "anomalias": anomaly_samples, "inasistencia": no_show_samples}
    return await extractor[module](db)


def demo_samples(module: Module) -> list[Sample]:
    rng = Random(SEED)
    result = []
    first = date(2025, 1, 6)
    if module == "anomalias":
        history: dict[int, list[int]] = defaultdict(list)
        for i in range(32):
            week = datetime.combine(first + timedelta(weeks=i), time.min, LIMA)
            for owner in range(1, 31):
                anomalous = rng.random() < 0.045
                attempts = rng.randint(20, 65) if anomalous else rng.randint(1, 9)
                counts = Counter(
                    {
                        "solicitudes": rng.randint(8, 17) if anomalous else rng.randint(1, 4),
                        "cancelaciones": rng.randint(4, 8) if anomalous else rng.randint(0, 2),
                        "intentos": attempts,
                        "intentos_rechazados": rng.randrange(attempts),
                    }
                )
                repeated = min(attempts, rng.randint(10, 17) if anomalous else rng.randint(1, 4))
                features = anomaly_features(counts, repeated, history[owner][-4:])
                result.append(Sample(week, features, int(anomalous), subject=owner))
                history[owner].append(counts["solicitudes"])
        return result
    for i in range(168):
        day = first + timedelta(days=i)
        for court in range(1, 5):
            for hour in (8, 9, 11, 13, 15, 17, 18):
                begins = datetime.combine(day, time(hour), LIMA)
                if module == "demanda":
                    chance = 0.08 + 0.46 * (hour >= 15) + 0.19 * (day.weekday() >= 4) + 0.05 * court
                    result.append(
                        Sample(
                            begins,
                            calendar(day, hour, court, (court % 3) + 1),
                            int(rng.random() < chance),
                            begins + timedelta(hours=1),
                        )
                    )
                else:
                    lead = rng.choice((1, 2, 4, 16, 32, 72, 120))
                    confirmed = begins - timedelta(hours=lead)
                    kind = "Normal" if lead <= 4 else "Especial"
                    chance = 0.04 + 0.52 * (lead >= 32) + 0.13 * (hour < 11)
                    features = no_show_features(
                        day, begins.time(), court, (court % 3) + 1, 1, kind, confirmed
                    )
                    result.append(
                        Sample(
                            confirmed,
                            features,
                            int(rng.random() < chance),
                            begins + timedelta(hours=2),
                            subject=1 + rng.randrange(90),
                        )
                    )
    return result
