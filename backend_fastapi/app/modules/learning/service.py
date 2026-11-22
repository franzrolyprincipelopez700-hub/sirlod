from collections import defaultdict
from datetime import date, datetime, time, timedelta
from math import expm1
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import LIMA, campus_now, utc_now
from app.core.exceptions import AppError
from app.models import ConfiguracionGlobal, DetallePermiso, DiaBloqueado, Disciplina, Losa, Permiso, User
from app.modules.learning.datasets import (
    anomaly_samples,
    confirmation,
    demand_samples,
    demo_samples,
    latest_attendance,
)
from app.modules.learning.discipline import check_reservation_access
from app.modules.learning.features import Features, calendar, hours, no_show_features, week_start
from app.modules.learning.models import Attendance, Incident, ModelVersion, Prediction
from app.modules.learning.registry import active_model, model_artifact, scores
from app.modules.learning.schemas import AttendanceIn, Kind, Module
from app.modules.learning.training import newer_than_fit
from app.modules.permisos import service as booking
from app.modules.permisos.schemas import DetallePermisoIn


async def save_scores(
    db: AsyncSession,
    model: ModelVersion,
    items: list[tuple[str, float]],
) -> None:
    if model.modo != "real" or not model.activo:
        raise ValueError("Las predicciones operativas requieren un modelo real activo")
    for offset in range(0, len(items), 1000):
        await db.execute(
            insert(Prediction)
            .values(
                [
                    {"version": model.version, "referencia": ref, "puntuacion": score}
                    for ref, score in items[offset : offset + 1000]
                ]
            )
            .on_conflict_do_nothing(index_elements=["version", "referencia"])
        )


async def forecast(
    db: AsyncSession,
    day: date,
    *,
    owner: int | None = None,
    kind: Kind = "Normal",
    discipline: int | None = None,
) -> dict[str, Any]:
    now = campus_now()
    if not now.date() <= day <= now.date() + timedelta(days=30):
        raise AppError("Consulta una fecha dentro de los próximos 30 días", 422)
    if owner is not None:
        await check_reservation_access(db, owner)
        if kind == "Normal" and day != now.date():
            raise AppError("Las reservas normales se solicitan para el mismo día", 400)

    config = await db.get(ConfiguracionGlobal, 1)
    if config is None:
        raise AppError("Configura primero el horario de la instalación", 409)
    courts_query = (
        select(Losa)
        .join(Disciplina)
        .where(Losa.estado == "Disponible", Disciplina.estado == "Activo")
        .order_by(Losa.id_l)
    )
    if discipline is not None:
        courts_query = courts_query.where(Losa.id_d == discipline)
    courts = {court.id_l: court for court in (await db.scalars(courts_query)).all()}
    slots = [
        DetallePermisoIn(id_l=court, fecha=day, hora_inicio=time(hour), hora_fin=time(hour + 1), duracion=1)
        for court in courts
        for hour in hours(config.hora_min_apertura, config.hora_max_apertura)
        if datetime.combine(day, time(hour), LIMA) >= now
    ]
    if not slots:
        return {"fuente": "sin_datos", "turnos": [], "mensaje": "No quedan turnos futuros para consultar"}
    if owner is not None:
        await booking._validate_details(db, slots, enforce_request_window=True)
        if kind == "Normal":
            await booking._check_group_restriction(db, owner, slots[:1], config, lock=False)
    elif await db.scalar(select(DiaBloqueado.id).where(DiaBloqueado.fecha == day)):
        return {"fuente": "sin_datos", "turnos": [], "mensaje": "La fecha está bloqueada"}

    conflicts = await booking._conflicts(db, slots, lock=False)
    unavailable = {(row["detalle"]["id_l"], row["detalle"]["hora_inicio"]) for row in conflicts}
    candidates = [(slot, (slot.id_l, slot.hora_inicio.isoformat()) not in unavailable) for slot in slots]
    if owner is not None:
        candidates = [(slot, free) for slot, free in candidates if free]
    if not candidates:
        return {
            "fuente": "sin_datos",
            "turnos": [],
            "mensaje": "No hay turnos reservables para esta consulta",
        }

    model, estimator = await active_model(db, "demanda")
    occupied_counts: dict[tuple[int, str, int], list[int]] = defaultdict(list)
    if model is None or any(s.id_l not in model.evaluacion["losas_entrenadas"] for s, _ in candidates):
        for item in await demand_samples(db):
            cohort = int(item.features["losa"]), str(item.features["dia_semana"]), int(item.features["hora"])
            occupied_counts[cohort].append(int(item.label == 1))
    modeled = [slot for slot, _ in candidates if model and slot.id_l in model.evaluacion["losas_entrenadas"]]
    probabilities = await scores(
        estimator,
        "demanda",
        [calendar(day, slot.hora_inicio.hour, slot.id_l, courts[slot.id_l].id_d) for slot in modeled],
    )
    predictions = dict(zip(((slot.id_l, slot.hora_inicio) for slot in modeled), probabilities, strict=True))
    result = []
    for slot, free in candidates:
        key = slot.id_l, slot.hora_inicio
        samples = occupied_counts[(slot.id_l, str(day.weekday()), slot.hora_inicio.hour)]
        rate = predictions.get(key)
        source = "modelo_real"
        if rate is None:
            rate = sum(samples) / len(samples) if len(samples) >= 4 else None
            source = "frecuencia_historica" if rate is not None else "disponibilidad"
        result.append(
            {
                **slot.model_dump(mode="json"),
                "losa": courts[slot.id_l].nombre,
                "disciplina_id": courts[slot.id_l].id_d,
                "disponible": free,
                "demanda": rate,
                "fuente": source,
                "version": model.version if model and source == "modelo_real" else None,
            }
        )

    if owner is not None:
        result.sort(
            key=lambda row: (row["demanda"] is None, row["demanda"] or 0, row["hora_inicio"], row["id_l"])
        )
        result = result[:6]
    elif model:
        await save_scores(
            db,
            model,
            [
                (f"{day}:{slot.id_l}:{slot.hora_inicio.isoformat()}", val)
                for slot, val in zip(modeled, probabilities, strict=True)
            ],
        )
    return {
        "fuente": "modelo_real" if predictions else "alternativa",
        "mensaje": "Ocupación estimada e intervalos en hora de Lima"
        if predictions
        else "Modelo real no disponible para esta consulta. Se muestran frecuencias o disponibilidad.",
        "turnos": result,
    }


async def attendance_context(
    db: AsyncSession, detail_id: int, *, lock: bool = False
) -> tuple[DetallePermiso, Permiso, Losa]:
    query = (
        select(DetallePermiso, Permiso, Losa).join(Permiso).join(Losa).where(DetallePermiso.id_d == detail_id)
    )
    if lock:
        query = query.with_for_update(of=Permiso)
    row = (await db.execute(query)).one_or_none()
    if row is None:
        raise AppError("Turno inexistente", 404)
    return row[0], row[1], row[2]


async def register_attendance(
    db: AsyncSession, detail_id: int, payload: AttendanceIn, actor: int
) -> Attendance:
    detail, permit, _ = await attendance_context(db, detail_id, lock=True)
    if permit.estado != "Aceptado":
        raise AppError("El turno debe pertenecer a un permiso confirmado", 409)
    if datetime.combine(detail.fecha, detail.hora_fin, LIMA) > utc_now():
        raise AppError("El turno debe haber concluido antes de registrar el resultado", 409)
    previous = await db.scalar(
        select(Attendance).where(Attendance.detalle_id == detail_id).order_by(Attendance.id.desc()).limit(1)
    )
    if previous and previous.resultado == payload.resultado and previous.evidencia == payload.evidencia:
        return previous
    if previous and await db.scalar(
        select(Incident.id)
        .where(Incident.asistencia_id == previous.id, Incident.estado.in_(("pendiente", "confirmado")))
        .limit(1)
    ):
        raise AppError("Resuelve primero el incidente asociado al registro anterior", 409)
    record = Attendance(detalle_id=detail_id, actor_id=actor, **payload.model_dump())
    db.add(record)
    await db.flush()
    return record


async def list_attendance(
    db: AsyncSession,
    start: date,
    end: date,
    *,
    search: str = "",
    offset: int = 0,
) -> list[dict[str, Any]]:
    if start > end or (end - start).days > 31:
        raise AppError("Usa un intervalo de hasta 32 días", 422)
    latest = latest_attendance()
    query = (
        select(DetallePermiso, Permiso, Losa.nombre, User.codigo, Attendance)
        .select_from(DetallePermiso)
        .join(Permiso, Permiso.id_p == DetallePermiso.id_p)
        .join(Losa, Losa.id_l == DetallePermiso.id_l)
        .outerjoin(User, User.id_u == Permiso.id_u)
        .outerjoin(latest, latest.c.detalle_id == DetallePermiso.id_d)
        .outerjoin(Attendance, Attendance.id == latest.c.latest)
        .where(DetallePermiso.fecha.between(start, end), Permiso.estado.in_(("Aceptado", "Cancelado")))
        .order_by(DetallePermiso.fecha.desc(), DetallePermiso.hora_inicio, DetallePermiso.id_d)
        .offset(offset)
        .limit(100)
    )
    if search:
        query = query.where(User.codigo.contains(search, autoescape=True))
    result = []
    now = campus_now()
    for detail, permit, court_name, code, attendance in (await db.execute(query)).all():
        finished = datetime.combine(detail.fecha, detail.hora_fin, LIMA) <= now
        status = "pendiente" if not finished else "sin_verificar"
        if permit.estado == "Cancelado":
            status = "cancelado"
        elif attendance:
            status = attendance.resultado
        result.append(
            {
                "detalle_id": detail.id_d,
                "permiso_id": permit.id_p,
                "usuario_id": permit.id_u,
                "codigo": code,
                "losa": court_name,
                "fecha": detail.fecha,
                "hora_inicio": detail.hora_inicio,
                "hora_fin": detail.hora_fin,
                "resultado": status,
                "asistencia_id": attendance.id if attendance else None,
                "evidencia": attendance.evidencia if attendance else None,
                "actor_id": attendance.actor_id if attendance else None,
                "registrado": attendance.registrado if attendance else None,
                "registrable": finished and permit.estado == "Aceptado",
                "predecible": permit.estado == "Aceptado"
                and now < datetime.combine(detail.fecha, detail.hora_inicio, LIMA),
            }
        )
    return result


async def risk(db: AsyncSession, detail_id: int) -> dict[str, Any]:
    detail, permit, court = await attendance_context(db, detail_id, lock=True)
    starts = datetime.combine(detail.fecha, detail.hora_inicio, LIMA)
    if permit.estado != "Aceptado" or starts <= utc_now():
        raise AppError("El riesgo solo se calcula para turnos confirmados que aún no comienzan", 409)
    confirmed = confirmation(permit.fecha_creacion, permit.fecha_decision, permit.tipo)
    model, estimator = await active_model(db, "inasistencia")
    if (
        not model
        or not confirmed
        or not confirmed < starts
        or court.id_l not in model.evaluacion["losas_entrenadas"]
    ):
        return {"disponible": False, "mensaje": "Sin modelo real validado o sin cobertura para este turno."}
    feature = no_show_features(
        detail.fecha, detail.hora_inicio, court.id_l, court.id_d, detail.duracion, permit.tipo, confirmed
    )
    (probability,) = await scores(estimator, "inasistencia", [feature])
    await save_scores(db, model, [(risk_ref(detail_id, confirmed), probability)])
    return risk_result(model, probability)


def risk_ref(detail_id: int, confirmed: datetime) -> str:
    return f"turno:{detail_id}:{confirmed.isoformat()}"


def risk_result(model: ModelVersion, probability: float) -> dict[str, Any]:
    high = model.evaluacion["umbral_alto"]
    medium = model.evaluacion["umbral_medio"]
    level = "alto" if probability >= high else "medio" if probability >= medium else "bajo"
    return {
        "disponible": True,
        "riesgo": probability,
        "nivel": level,
        "version": model.version,
        "mensaje": {
            "alto": "Seguimiento prioritario. Verifica el turno con el titular "
            "y registra la asistencia al cierre.",
            "medio": "Considera recordar el turno y confirmar los datos de la reserva.",
            "bajo": "Continúa con el seguimiento habitual.",
        }[level],
    }


async def risk_queue(db: AsyncSession) -> dict[str, Any]:
    model, estimator = await active_model(db, "inasistencia")
    if model is None:
        return {"mensaje": "Sin modelo real validado para generar alertas preventivas.", "alertas": []}
    now = campus_now()
    rows = (
        await db.execute(
            select(DetallePermiso, Permiso, Losa)
            .join(Permiso)
            .join(Losa)
            .where(
                Permiso.estado == "Aceptado",
                DetallePermiso.fecha.between(now.date(), now.date() + timedelta(days=7)),
                DetallePermiso.id_l.in_(model.evaluacion["losas_entrenadas"]),
            )
            .order_by(DetallePermiso.fecha, DetallePermiso.hora_inicio, DetallePermiso.id_d)
        )
    ).all()
    records = []
    features = []
    for detail, permit, court in rows:
        confirmed = confirmation(permit.fecha_creacion, permit.fecha_decision, permit.tipo)
        starts = datetime.combine(detail.fecha, detail.hora_inicio, LIMA)
        if confirmed is None or not (confirmed < starts and now < starts):
            continue
        records.append((detail, permit, court, confirmed))
        features.append(
            no_show_features(
                detail.fecha,
                detail.hora_inicio,
                court.id_l,
                court.id_d,
                detail.duracion,
                permit.tipo,
                confirmed,
            )
        )
    estimates = await scores(estimator, "inasistencia", features)
    await save_scores(
        db,
        model,
        [
            (risk_ref(detail.id_d, confirmed), estimate)
            for (detail, _, _, confirmed), estimate in zip(records, estimates, strict=True)
        ],
    )
    alerts = [
        {
            **risk_result(model, estimate),
            "detalle_id": detail.id_d,
            "permiso_id": permit.id_p,
            "losa": court.nombre,
            "fecha": detail.fecha,
            "hora": detail.hora_inicio,
        }
        for (detail, permit, court, _), estimate in zip(records, estimates, strict=True)
        if estimate >= model.evaluacion["umbral_alto"]
    ]
    alerts.sort(key=lambda alert: (-alert["riesgo"], alert["fecha"], alert["hora"]))
    return {
        "mensaje": f"{len(alerts)} alertas prioritarias en {len(records)} turnos con cobertura.",
        "alertas": alerts[:100],
    }


async def scan_anomalies(db: AsyncSession) -> dict[str, Any]:
    if not await db.scalar(text("SELECT pg_try_advisory_xact_lock(670551)")):
        raise AppError("Ya hay un análisis en curso", 409)
    model, estimator = await active_model(db, "anomalias")
    if model is None:
        return {"disponible": False, "alertas": 0, "mensaje": "Se requiere un modelo real activo"}
    since = week_start(campus_now().date()) - timedelta(weeks=3)
    samples = [
        row
        for row in await anomaly_samples(db)
        if row.subject is not None
        and row.moment.date() >= since
        and newer_than_fit(row.moment, model.evaluacion)
    ]
    probabilities = await scores(estimator, "anomalias", [row.features for row in samples])
    scored = [
        (row, f"semana:{row.subject}:{row.moment.date().isoformat()}", score)
        for row, score in zip(samples, probabilities, strict=True)
    ]
    await save_scores(db, model, [(ref, value) for _, ref, value in scored])
    total = 0
    for row, ref, value in scored:
        if value > model.evaluacion["umbral"]:
            created = await db.scalar(
                insert(Incident)
                .values(
                    usuario_id=row.subject,
                    tipo="anomalia",
                    referencia=ref,
                    version=model.version,
                    ocurrido=row.moment,
                    estado="pendiente",
                    evidencia={
                        "variables": row.features,
                        "puntuacion": value,
                        "umbral": model.evaluacion["umbral"],
                        "periodo_fin_exclusivo": row.moment.isoformat(),
                    },
                )
                .on_conflict_do_nothing(index_elements=["referencia"])
                .returning(Incident.id)
            )
            total += int(created is not None)
    return {"disponible": True, "alertas": total, "muestras": len(scored), "version": str(model.version)}


async def demo_prediction(db: AsyncSession, module: Module) -> dict[str, Any]:
    version = await db.scalar(
        select(ModelVersion)
        .where(
            ModelVersion.modulo == module,
            ModelVersion.modo == "demo",
            ModelVersion.sha256.is_not(None),
        )
        .order_by(ModelVersion.creado.desc())
        .limit(1)
    )
    if version is None:
        raise AppError("Entrena primero una versión para el entorno de práctica", 409)
    estimator = await model_artifact(db, version)
    if estimator is None:
        raise AppError("La versión de práctica requiere un nuevo entrenamiento", 409)
    size = {"demanda": 84, "anomalias": 60, "inasistencia": 56}[module]
    examples = demo_samples(module)[-size:]
    features: list[Features] = [row.features for row in examples]
    probabilities = await scores(estimator, module, features)
    samples = []
    for index, (row, value) in enumerate(zip(examples, probabilities, strict=True), 1):
        event_date = row.moment.date()
        if module == "inasistencia":
            lead = round(expm1(float(row.features["anticipacion_log_horas"])))
            event_date = (row.moment + timedelta(hours=lead)).date()
        samples.append({
            "id": index,
            "fecha": event_date,
            "cuenta": f"C-{1400 + row.subject}" if row.subject is not None else None,
            "variables": row.features,
            "objetivo": row.label,
            "puntuacion": value,
        })
    return {
        "modo": "demo",
        "version": version.version,
        "umbrales": {
            key: version.evaluacion[key]
            for key in ("umbral", "umbral_medio", "umbral_alto")
            if key in version.evaluacion
        },
        "muestras": samples,
    }
