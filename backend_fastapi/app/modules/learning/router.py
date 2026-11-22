from datetime import date, timedelta
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import func, select

from app.core.clock import campus_now
from app.core.database import DBSession
from app.core.exceptions import AppError
from app.core.security import AuthenticatedUser, CurrentUser
from app.core.serialization import model_dict
from app.models import User
from app.modules.learning import discipline, registry, service
from app.modules.learning.models import Incident, ModelVersion, Policy, Prediction
from app.modules.learning.schemas import (
    AttendanceIn,
    ExplanationIn,
    IncidentIn,
    Kind,
    MeasureIn,
    MeasureReviewIn,
    Module,
    PolicyIn,
    PolicyReviewIn,
    ReviewIn,
)


async def admin_check(db: DBSession, actor: AuthenticatedUser) -> CurrentUser:
    await discipline.staff(db, actor)
    return actor


async def staff_check(db: DBSession, actor: AuthenticatedUser) -> CurrentUser:
    await discipline.staff(db, actor, admin=False)
    return actor


async def member_check(actor: AuthenticatedUser) -> CurrentUser:
    if actor.tipo != "usuario":
        raise AppError("No autorizado", 403)
    return actor


async def private(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


Admin = Annotated[CurrentUser, Depends(admin_check)]
Staff = Annotated[CurrentUser, Depends(staff_check)]
Member = Annotated[CurrentUser, Depends(member_check)]

router = APIRouter(prefix="/aprendizaje", tags=["Aprendizaje automático"], dependencies=[Depends(private)])


@router.get("/modelos")
async def models(db: DBSession, _actor: Admin) -> dict[str, Any]:
    groups = []
    for module in registry.MODULES:
        rows = (
            await db.scalars(
                select(ModelVersion)
                .where(ModelVersion.modulo == module)
                .order_by(ModelVersion.creado.desc())
                .limit(15)
            )
        ).all()
        active = await db.scalar(
            select(ModelVersion).where(ModelVersion.modulo == module, ModelVersion.activo.is_(True))
        )
        stats = (
            await db.execute(
                select(ModelVersion.version, func.count(Prediction.id))
                .join(Prediction)
                .where(ModelVersion.modulo == module)
                .group_by(ModelVersion.version)
            )
        ).all()
        groups.append(
            {
                "modulo": module,
                "activo": registry.metadata(active) if active else None,
                "compatible": await registry.model_artifact(db, active) is not None if active else None,
                "versiones": [registry.metadata(row) for row in rows],
                "predicciones_registradas": sum(total for _, total in stats),
            }
        )
    return {"modelos": groups}


@router.post("/modelos/{version}/activar")
async def activate_model(db: DBSession, _actor: Admin, version: UUID) -> dict[str, Any]:
    model = await registry.activate(db, version)
    await db.commit()
    return registry.metadata(model)


@router.get("/demo/{modulo}")
async def demo(db: DBSession, _actor: Admin, modulo: Module) -> dict[str, Any]:
    return await service.demo_prediction(db, modulo)


@router.get("/recomendaciones")
async def recommendations(
    db: DBSession,
    actor: Member,
    fecha: date,
    tipo: Kind = "Normal",
    disciplina: Annotated[int | None, Query(gt=0)] = None,
) -> dict[str, Any]:
    return await service.forecast(db, fecha, owner=actor.id, kind=tipo, discipline=disciplina)


@router.post("/demanda")
async def demand(db: DBSession, _actor: Admin, fecha: date) -> dict[str, Any]:
    result = await service.forecast(db, fecha)
    await db.commit()
    return result


@router.get("/asistencias")
async def attendance_list(
    db: DBSession,
    _actor: Staff,
    inicio: date | None = None,
    fin: date | None = None,
    codigo: Annotated[str, Query(max_length=15)] = "",
    offset: Annotated[int, Query(ge=0, le=10_000)] = 0,
) -> dict[str, Any]:
    today = campus_now().date()
    return {
        "turnos": await service.list_attendance(
            db,
            inicio or today - timedelta(days=7),
            fin or today + timedelta(days=7),
            search=codigo,
            offset=offset,
        )
    }


@router.post("/asistencias/{detalle_id}", status_code=201)
async def attendance_record(
    db: DBSession, actor: Staff, detalle_id: int, payload: AttendanceIn
) -> dict[str, Any]:
    result = await service.register_attendance(db, detalle_id, payload, actor.id)
    await db.commit()
    return model_dict(result)


@router.post("/riesgo")
async def risk_alerts(db: DBSession, _actor: Admin) -> dict[str, Any]:
    result = await service.risk_queue(db)
    await db.commit()
    return result


@router.post("/riesgo/{detalle_id}")
async def risk_forecast(db: DBSession, _actor: Admin, detalle_id: int) -> dict[str, Any]:
    result = await service.risk(db, detalle_id)
    await db.commit()
    return result


@router.post("/anomalias")
async def anomaly_scan(db: DBSession, _actor: Admin) -> dict[str, Any]:
    result = await service.scan_anomalies(db)
    await db.commit()
    return result


@router.get("/incidentes")
async def incident_list(
    db: DBSession,
    _actor: Admin,
    estado: Literal["pendiente", "confirmado", "descartado", "anulado", "derivado"] | None = None,
    codigo: Annotated[str, Query(max_length=15)] = "",
    offset: Annotated[int, Query(ge=0, le=10_000)] = 0,
) -> dict[str, Any]:
    query = (
        select(Incident, User.codigo)
        .join(User)
        .order_by(Incident.ocurrido.desc(), Incident.id.desc())
        .offset(offset)
        .limit(100)
    )
    if estado:
        query = query.where(Incident.estado == estado)
    else:
        query = query.where(Incident.estado != "anulado")
    if codigo:
        query = query.where(User.codigo.contains(codigo, autoescape=True))
    return {
        "incidentes": [
            {**model_dict(incident), "codigo": code} for incident, code in (await db.execute(query)).all()
        ]
    }


@router.post("/incidentes", status_code=201)
async def incident_create(db: DBSession, actor: Admin, payload: IncidentIn) -> dict[str, Any]:
    result = await discipline.create_case(db, payload, actor.id)
    await db.commit()
    return model_dict(result)


@router.post("/incidentes/{incidente_id}/revision")
async def incident_review(
    db: DBSession, actor: Admin, incidente_id: int, payload: ReviewIn
) -> dict[str, Any]:
    incident = await discipline.get_case(db, incidente_id)
    await discipline.review_case(db, incident, payload, actor.id)
    await db.commit()
    return model_dict(incident)


@router.get("/expedientes/{usuario_id}")
async def dossier(db: DBSession, _actor: Admin, usuario_id: int) -> dict[str, Any]:
    if await db.get(User, usuario_id) is None:
        raise AppError("Usuario no encontrado", 404)
    return await discipline.history(db, usuario_id, audit=True)


@router.get("/normas")
async def policies(db: DBSession, _actor: Admin) -> dict[str, Any]:
    rows = (await db.scalars(select(Policy).order_by(Policy.id.desc()))).all()
    return {"normas": [model_dict(p) for p in rows]}


@router.post("/normas", status_code=201)
async def policy_create(db: DBSession, actor: Admin, payload: PolicyIn) -> dict[str, Any]:
    result = await discipline.create_policy(db, payload, actor.id)
    await db.commit()
    return model_dict(result)


@router.post("/normas/{norma_id}/revision")
async def policy_review(
    db: DBSession, actor: Admin, norma_id: int, payload: PolicyReviewIn
) -> dict[str, Any]:
    await discipline.approve_policy(db, norma_id, payload.vigente, payload.fundamento, actor.id)
    await db.commit()
    return {"ok": True}


@router.post("/incidentes/{incidente_id}/medidas", status_code=201)
async def measure_create(
    db: DBSession, actor: Admin, incidente_id: int, payload: MeasureIn
) -> dict[str, Any]:
    case = await discipline.get_case(db, incidente_id)
    measure = await discipline.impose(db, case, payload, actor.id)
    await db.commit()
    return model_dict(measure)


@router.post("/medidas/{medida_id}/revision")
async def measure_review(
    db: DBSession, actor: Admin, medida_id: int, payload: MeasureReviewIn
) -> dict[str, Any]:
    measure = await discipline.review_measure(db, medida_id, payload.decision, payload.motivo, actor.id)
    await db.commit()
    return model_dict(measure)


@router.get("/mi-situacion")
async def my_situation(db: DBSession, actor: Member) -> dict[str, Any]:
    return await discipline.history(db, actor.id)


@router.post("/mi-situacion/{medida_id}/descargos", status_code=201)
async def submit_appeal(
    db: DBSession, actor: Member, medida_id: int, payload: ExplanationIn
) -> dict[str, Any]:
    appeal = await discipline.submit_appeal(db, actor.id, medida_id, payload.texto)
    await db.commit()
    return model_dict(appeal)


@router.post("/descargos/{descargo_id}/revision")
async def appeal_review(
    db: DBSession, actor: Admin, descargo_id: int, payload: ExplanationIn
) -> dict[str, Any]:
    await discipline.resolve_appeal(db, descargo_id, payload.texto, actor.id)
    await db.commit()
    return {"ok": True}
