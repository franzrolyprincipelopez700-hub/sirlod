from datetime import datetime, timedelta
from hashlib import sha256
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import LIMA, utc_now
from app.core.exceptions import AppError
from app.core.security import CurrentUser
from app.core.serialization import model_dict
from app.models import DetallePermiso, Permiso, Trabajador, User
from app.modules.learning.models import Appeal, Attendance, Decision, Incident, Measure, Policy
from app.modules.learning.schemas import IncidentIn, MeasureIn, PolicyIn, ReviewIn


async def staff(db: AsyncSession, actor: CurrentUser, *, admin: bool = True) -> None:
    if actor.tipo != "trabajador" or (admin and actor.rol != "Administrador"):
        raise AppError("No autorizado", 403)
    worker = await db.get(Trabajador, actor.id)
    if worker is None or worker.estado != "Activo" or worker.rol != actor.rol:
        raise AppError("No autorizado", 403)


async def lock_user(db: AsyncSession, user_id: int) -> User:
    user = await db.scalar(
        select(User).where(User.id_u == user_id).with_for_update().execution_options(populate_existing=True)
    )
    if user is None:
        raise AppError("Usuario no encontrado", 404)
    return user


async def check_reservation_access(db: AsyncSession, user_id: int, *, lock: bool = False) -> None:
    user = await lock_user(db, user_id) if lock else await db.get(User, user_id)
    if user is None or user.estado != "Activo":
        raise AppError("Cuenta inactiva o no disponible", 403)
    now = utc_now()
    active = await db.scalar(
        select(Measure.id)
        .join(Incident)
        .where(
            Incident.usuario_id == user_id,
            Measure.estado == "confirmada",
            Measure.tipo.in_(("preventiva", "suspension")),
            Measure.inicio <= now,
            Measure.fin > now,
        )
        .limit(1)
    )
    if active is not None:
        raise AppError(
            "Hay una restricción vigente. Revisa Mi situación para ver el motivo y presentar un descargo.",
            403,
            "RESERVATION_RESTRICTED",
        )


def measure_status(measure: Measure, now: datetime) -> str:
    if measure.estado != "confirmada":
        return measure.estado
    if measure.inicio > now:
        return "pendiente"
    if measure.fin is not None and measure.fin <= now:
        return "cumplida"
    return "confirmada"


async def history(db: AsyncSession, user_id: int, *, audit: bool = False) -> dict[str, Any]:
    incident_filter = [Incident.usuario_id == user_id]
    if not audit:
        incident_filter.append(Incident.estado == "confirmado")
    incidents = (
        await db.scalars(select(Incident).where(*incident_filter).order_by(Incident.ocurrido, Incident.id))
    ).all()
    measure_filter = [Incident.usuario_id == user_id]
    if not audit:
        measure_filter.append(Measure.estado != "anulada")
    measures = (
        await db.scalars(
            select(Measure).join(Incident).where(*measure_filter).order_by(Measure.inicio, Measure.id)
        )
    ).all()
    appeals = (
        await db.scalars(
            select(Appeal).where(Appeal.medida_id.in_([m.id for m in measures])).order_by(Appeal.id.desc())
        )
    ).all()
    decisions = (
        (
            await db.scalars(
                select(Decision).join(Incident).where(Incident.usuario_id == user_id).order_by(Decision.id)
            )
        ).all()
        if audit
        else []
    )
    now = utc_now()
    return {
        "infracciones_validas": sum(i.estado == "confirmado" for i in incidents),
        "incidentes": [model_dict(i) for i in incidents] if audit else [],
        "medidas": [{**model_dict(m), "estado": measure_status(m, now)} for m in measures],
        "descargos": [model_dict(a) for a in appeals],
        "decisiones": [model_dict(d) for d in decisions],
    }


async def get_case(db: AsyncSession, incident_id: int) -> Incident:
    case = await db.get(Incident, incident_id)
    if case is None:
        raise AppError("Incidente no encontrado", 404)
    await lock_user(db, case.usuario_id)
    await db.refresh(case, with_for_update=True)
    return case


async def evidence_is_current(db: AsyncSession, attendance_id: int, user_id: int) -> Attendance:
    # Lock the parent permit used by attendance writes and cancellation, then re-read the last record.
    attendance = await db.get(Attendance, attendance_id)
    if attendance is None:
        raise AppError("Registro de asistencia inexistente", 404)
    pair = (
        await db.execute(
            select(Permiso, DetallePermiso)
            .join(DetallePermiso)
            .where(DetallePermiso.id_d == attendance.detalle_id)
            .with_for_update(of=Permiso)
        )
    ).one_or_none()
    latest = await db.scalar(
        select(func.max(Attendance.id)).where(Attendance.detalle_id == attendance.detalle_id)
    )
    if (
        pair is None
        or pair[0].id_u != user_id
        or pair[0].estado != "Aceptado"
        or latest != attendance.id
        or attendance.resultado != "inasistencia"
        or datetime.combine(pair[1].fecha, pair[1].hora_fin, LIMA) > utc_now()
    ):
        raise AppError("Se requiere una inasistencia vigente, verificable y del mismo usuario", 409)
    return attendance


async def create_case(db: AsyncSession, payload: IncidentIn, actor: int) -> Incident:
    await lock_user(db, payload.usuario_id)
    alert = None
    if payload.alerta_id is not None:
        alert = await db.get(Incident, payload.alerta_id, with_for_update=True)
        if (
            alert is None
            or alert.tipo != "anomalia"
            or alert.estado != "pendiente"
            or alert.usuario_id != payload.usuario_id
        ):
            raise AppError("La alerta debe estar pendiente y corresponder al mismo usuario", 409)
    now = utc_now()
    happened = payload.ocurrido or now
    if happened.tzinfo is None or happened > now:
        raise AppError("Indica una fecha pasada o actual con zona horaria", 422)
    identifier = " ".join((payload.referencia_hecho or "").casefold().split())
    reference = f"manual:{payload.usuario_id}:{sha256(identifier.encode()).hexdigest()}"
    kind = "otro"
    if payload.asistencia_id is not None:
        attendance = await evidence_is_current(db, payload.asistencia_id, payload.usuario_id)
        detail = await db.get(DetallePermiso, attendance.detalle_id)
        assert detail is not None
        happened = datetime.combine(detail.fecha, detail.hora_fin, LIMA)
        reference = f"inasistencia:{attendance.id}"
        kind = "inasistencia"
    if await db.scalar(select(Incident.id).where(Incident.referencia == reference)) is not None:
        raise AppError("La evidencia ya está asociada a un incidente de este usuario", 409)
    case = Incident(
        usuario_id=payload.usuario_id,
        tipo=kind,
        estado="pendiente",
        referencia=reference,
        asistencia_id=payload.asistencia_id,
        alerta_id=payload.alerta_id,
        ocurrido=happened,
        evidencia={"registro": payload.evidencia, "referencia": payload.referencia_hecho},
    )
    db.add(case)
    await db.flush()
    db.add(Decision(incidente_id=case.id, actor_id=actor, accion="registrar", motivo=payload.evidencia))
    if alert is not None:
        alert.estado = "derivado"
        db.add(
            Decision(
                incidente_id=alert.id,
                actor_id=actor,
                accion="derivar",
                motivo=payload.evidencia,
                datos={"incidente_id": case.id},
            )
        )
    return case


async def review_case(db: AsyncSession, case: Incident, payload: ReviewIn, actor: int) -> None:
    next_state = {"confirmar": "confirmado", "descartar": "descartado", "anular": "anulado"}[payload.decision]
    if payload.decision == "anular":
        if case.estado != "confirmado":
            raise AppError("Solo se puede anular una infracción confirmada", 409)
        measures = (await db.scalars(select(Measure).where(Measure.incidente_id == case.id))).all()
        for measure in measures:
            if measure.estado != "anulada":
                measure.estado = "anulada"
                db.add(
                    Decision(
                        incidente_id=case.id,
                        actor_id=actor,
                        accion="anular_medida",
                        motivo=payload.motivo,
                        datos={"medida_id": measure.id},
                    )
                )
    elif case.estado != "pendiente":
        raise AppError("La alerta o incidente ya fue revisado", 409)

    if payload.decision == "confirmar":
        if case.tipo == "anomalia":
            raise AppError("Registra un incidente separado con la evidencia objetiva de la infracción", 409)
        if case.asistencia_id is not None:
            await evidence_is_current(db, case.asistencia_id, case.usuario_id)
        case.gravedad = payload.gravedad
    if payload.decision == "descartar":
        for measure in (
            await db.scalars(
                select(Measure).where(
                    Measure.incidente_id == case.id,
                    Measure.tipo == "preventiva",
                    Measure.estado == "confirmada",
                )
            )
        ).all():
            measure.estado = "levantada"
            db.add(
                Decision(
                    incidente_id=case.id,
                    actor_id=actor,
                    accion="levantar_medida",
                    motivo=payload.motivo,
                    datos={"medida_id": measure.id},
                )
            )
    case.estado = next_state
    db.add(
        Decision(
            incidente_id=case.id,
            actor_id=actor,
            accion=payload.decision,
            motivo=payload.motivo,
            datos={"evidencia": payload.evidencia, "gravedad": case.gravedad},
        )
    )


async def create_policy(db: AsyncSession, payload: PolicyIn, actor: int) -> Policy:
    rule = Policy(**payload.model_dump(), autor_id=actor, vigente=False)
    db.add(rule)
    await db.flush()
    db.add(Decision(norma_id=rule.id, actor_id=actor, accion="redactar_norma", motivo=rule.fundamento))
    return rule


async def approve_policy(db: AsyncSession, rule_id: int, enabled: bool, legal_ref: str, actor: int) -> None:
    await db.execute(text("SELECT pg_advisory_xact_lock(670511)"))
    rule = await db.get(Policy, rule_id, with_for_update=True)
    if rule is None:
        raise AppError("Regla no encontrada", 404)
    if rule.vigente == enabled or (enabled and rule.aprobada is not None):
        raise AppError("Crea una nueva versión para volver a habilitar una regla retirada", 409)
    if enabled:
        other = await db.scalar(
            select(Policy.id)
            .where(
                Policy.id != rule.id,
                Policy.vigente.is_(True),
                Policy.tipo == rule.tipo,
                Policy.gravedad == rule.gravedad,
                (Policy.medida == "preventiva") == (rule.medida == "preventiva"),
                Policy.minimo_previas == rule.minimo_previas,
            )
            .limit(1)
        )
        if other is not None:
            raise AppError("Retira primero la regla vigente para ese nivel", 409)
        rule.aprobacion = legal_ref
        rule.aprobada = utc_now()
        rule.aprobador_id = actor
    rule.vigente = enabled
    db.add(
        Decision(
            norma_id=rule.id,
            actor_id=actor,
            accion="aprobar_norma" if enabled else "retirar_norma",
            motivo=legal_ref,
        )
    )


async def impose(db: AsyncSession, case: Incident, payload: MeasureIn, actor: int) -> Measure:
    rule = await db.get(Policy, payload.norma_id, with_for_update=True)
    if rule is None or not rule.vigente:
        raise AppError("Se necesita una regla institucional vigente y aprobada", 409)
    preventive = rule.medida == "preventiva"
    if rule.tipo != case.tipo or case.estado != ("pendiente" if preventive else "confirmado"):
        raise AppError("La regla no es aplicable al tipo o estado de este incidente", 409)
    if rule.gravedad != (case.gravedad or "ordinaria"):
        raise AppError("La regla no corresponde a la gravedad registrada", 409)
    if case.asistencia_id is not None:
        await evidence_is_current(db, case.asistencia_id, case.usuario_id)
    if case.tipo == "otro" and preventive:
        raise AppError("La prevención exige un hecho verificable mediante un registro de asistencia", 409)

    previous = (
        await db.scalar(
            select(func.count())
            .select_from(Incident)
            .where(
                Incident.usuario_id == case.usuario_id,
                Incident.estado == "confirmado",
                (Incident.ocurrido < case.ocurrido)
                | ((Incident.ocurrido == case.ocurrido) & (Incident.id < case.id)),
            )
        )
        or 0
    )
    applicable_level = await db.scalar(
        select(func.max(Policy.minimo_previas)).where(
            Policy.vigente.is_(True),
            Policy.tipo == rule.tipo,
            Policy.gravedad == rule.gravedad,
            (Policy.medida == "preventiva") == preventive,
            Policy.minimo_previas <= previous,
        )
    )
    if applicable_level != rule.minimo_previas:
        raise AppError("La regla no corresponde al nivel de reincidencia válida", 409)

    prior = await db.scalar(
        select(Measure.id)
        .where(
            Measure.incidente_id == case.id,
            (Measure.tipo == "preventiva") == preventive,
            Measure.estado != "anulada",
        )
        .limit(1)
    )
    if prior is not None:
        raise AppError("Este incidente ya tiene una medida del mismo tipo", 409)
    if rule.maximo_horas is None:
        if payload.horas is not None:
            raise AppError("La advertencia no tiene duración", 422)
    elif payload.horas is None or payload.horas > rule.maximo_horas:
        raise AppError("La duración excede la regla autorizada o falta indicar horas", 422)

    now = utc_now()
    try:
        end = now + timedelta(hours=payload.horas) if payload.horas else None
    except OverflowError as exc:
        raise AppError("La fecha de fin excede el rango representable", 422) from exc
    if not preventive:
        prior_measures = (
            await db.scalars(
                select(Measure).where(
                    Measure.incidente_id == case.id,
                    Measure.tipo == "preventiva",
                    Measure.estado == "confirmada",
                    Measure.fin > now,
                )
            )
        ).all()
        for item in prior_measures:
            item.estado = "levantada"
            db.add(
                Decision(
                    incidente_id=case.id,
                    actor_id=actor,
                    accion="levantar_medida",
                    motivo=payload.motivo,
                    datos={"medida_id": item.id, "razon": "resolucion_del_incidente"},
                )
            )
    measure = Measure(
        incidente_id=case.id,
        norma_id=rule.id,
        actor_id=actor,
        tipo=rule.medida,
        estado="confirmada",
        motivo=payload.motivo,
        inicio=now,
        fin=end,
    )
    db.add(measure)
    await db.flush()
    db.add(
        Decision(
            incidente_id=case.id,
            actor_id=actor,
            accion="aplicar_medida",
            motivo=payload.motivo,
            datos={
                "medida_id": measure.id,
                "norma_id": rule.id,
                "previas_en_decision": previous,
                "verificacion": payload.verificacion,
                "criterio": rule.criterio,
                "referencia_normativa": rule.aprobacion,
            },
        )
    )
    return measure


async def review_measure(
    db: AsyncSession, measure_id: int, decision: str, reason: str, actor: int
) -> Measure:
    measure = await db.get(Measure, measure_id)
    if measure is None:
        raise AppError("Medida no encontrada", 404)
    case = await get_case(db, measure.incidente_id)
    await db.refresh(measure, with_for_update=True)
    if measure.estado == "anulada" or (
        decision == "levantar" and measure_status(measure, utc_now()) != "confirmada"
    ):
        raise AppError("La medida se encuentra resuelta", 409)
    if decision == "anular" and measure.tipo != "preventiva":
        await review_case(db, case, ReviewIn(decision="anular", motivo=reason, evidencia=reason), actor)
    else:
        measure.estado = "anulada" if decision == "anular" else "levantada"
        db.add(
            Decision(
                incidente_id=case.id,
                actor_id=actor,
                accion=f"{decision}_medida",
                motivo=reason,
                datos={"medida_id": measure.id},
            )
        )
    return measure


async def submit_appeal(db: AsyncSession, owner: int, measure_id: int, message: str) -> Appeal:
    await lock_user(db, owner)
    measure = await db.scalar(
        select(Measure)
        .join(Incident)
        .where(
            Measure.id == measure_id,
            Incident.usuario_id == owner,
            Measure.estado != "anulada",
        )
    )
    if measure is None:
        raise AppError("Medida no encontrada", 404)
    existing = await db.scalar(
        select(Appeal.id).where(Appeal.medida_id == measure_id, Appeal.revisado.is_(None))
    )
    if existing is not None:
        raise AppError("Ya hay un descargo pendiente de revisión", 409)
    appeal = Appeal(medida_id=measure_id, usuario_id=owner, texto=message)
    db.add(appeal)
    await db.flush()
    return appeal


async def resolve_appeal(db: AsyncSession, appeal_id: int, message: str, actor: int) -> None:
    appeal = await db.get(Appeal, appeal_id)
    if appeal is None:
        raise AppError("Descargo no encontrado", 404)
    await lock_user(db, appeal.usuario_id)
    await db.refresh(appeal, with_for_update=True)
    if appeal.revisado is not None:
        raise AppError("El descargo ya fue revisado", 409)
    measure = await db.get(Measure, appeal.medida_id)
    assert measure is not None
    appeal.decision = message
    appeal.revisor_id = actor
    appeal.revisado = utc_now()
    db.add(
        Decision(
            incidente_id=measure.incidente_id,
            actor_id=actor,
            accion="resolver_descargo",
            motivo=message,
            datos={"descargo_id": appeal.id},
        )
    )
