import asyncio
import os
from collections import Counter
from datetime import datetime, time, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.clock import LIMA, campus_now, utc_now
from app.core.database import get_db
from app.core.security import create_tokens
from app.main import app
from app.modules.learning import datasets, discipline, registry
from app.modules.learning.models import Attendance, Incident, Measure, ModelVersion, Prediction
from app.modules.permisos import service as booking

PG = Path(__file__).resolve().parents[2] / "database" / "postgres"
PREFIX = "/api/aprendizaje"


def auth(user_id, role="Administrador", kind="trabajador"):
    token, _ = create_tokens({"id": user_id, "rol": role, "tipo": kind})
    return {"Authorization": f"Bearer {token}"}


ADMIN = auth(1)
SECURITY = auth(2, "Seguridad")
STUDENT = auth(1, "Alumno", "usuario")
OTHER = auth(2, "Alumno", "usuario")


@pytest.fixture
async def pg():
    url = os.environ.get("SIRLOD_TEST_DATABASE_URL")
    if not url:
        pytest.skip("Configura SIRLOD_TEST_DATABASE_URL con una base PostgreSQL desechable")
    schema = f"learning_test_{uuid4().hex}"
    root = create_async_engine(url)
    async with root.begin() as conn:
        await conn.execute(text(f"CREATE SCHEMA {schema}"))
    engine = create_async_engine(url, connect_args={"server_settings": {"search_path": schema}})
    factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)

    async def override_db():
        async with factory() as session:
            yield session

    try:
        async with engine.connect() as conn:
            raw = (await conn.get_raw_connection()).driver_connection
            files = [PG / "sistema_losa_schema.sql", *sorted((PG / "migrations").glob("*.sql"))]
            for file in [*files, PG / "migrations" / "20261122_learning.sql"]:
                await raw.execute(file.read_text(encoding="utf-8"))
            await raw.execute("""
                INSERT INTO users(codigo, password, rol) VALUES ('10000001','fixture','Alumno'),
                    ('10000002','fixture','Alumno');
                INSERT INTO trabajadores(dni,nombres,apellido_p,apellido_m,rol,email,password) VALUES
                    ('10000001','Admin','Test','Test','Administrador','admin@example.test','fixture'),
                    ('10000002','Guardia','Test','Test','Seguridad','guard@example.test','fixture');
                INSERT INTO disciplinas(nombre,estado) VALUES ('Fútbol','Activo'),('Tenis','Inactivo');
                INSERT INTO losas(nombre,numero_l,ubicacion,id_d,estado) VALUES
                    ('Losa uno','01','Prueba',1,'Disponible'),
                    ('Losa dos','02','Prueba',1,'Mantenimiento'),
                    ('Losa tres','03','Prueba',2,'Disponible');
                INSERT INTO configuracion_global VALUES (1,'00:00','23:59','06:00','22:00','09:00',3);
            """)
        app.dependency_overrides[get_db] = override_db
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
            yield factory, client
    finally:
        app.dependency_overrides.pop(get_db, None)
        await engine.dispose()
        async with root.begin() as conn:
            await conn.execute(text(f"DROP SCHEMA {schema} CASCADE"))
        await root.dispose()


async def ok(client, method, path, data=None, headers=ADMIN):
    result = await client.request(method, PREFIX + path, headers=headers, json=data)
    assert result.is_success, (result.status_code, result.text)
    return result.json()


async def permit(factory, day, begins, ends, status="Aceptado", user=1):
    async with factory.begin() as db:
        await db.execute(
            text("""
            INSERT INTO permisos (id_u, tipo, duracion_t, estado, fecha_decision)
            VALUES (:user,'Normal',1,CAST(:status AS permisos_estado_enum),:confirmed)
        """),
            {"user": user, "status": status, "confirmed": datetime.combine(day, begins) - timedelta(days=1)},
        )
        return await db.scalar(
            text("""
            INSERT INTO detalle_permisos(id_p,id_l,fecha,hora_inicio,hora_fin,duracion)
            VALUES (currval(pg_get_serial_sequence('permisos','id_p')),1,:day,:begins,:ends,1)
            RETURNING id_d
        """),
            {"day": day, "begins": begins, "ends": ends},
        )


async def test_available_recommendations_auth_and_concurrent_booking(pg, monkeypatch):
    factory, client = pg
    today = campus_now().date()
    fixed_now = datetime.combine(today, time(10), LIMA)
    monkeypatch.setattr(booking, "campus_now", lambda: fixed_now)
    from app.modules.learning import service

    monkeypatch.setattr(service, "campus_now", lambda: fixed_now)

    async def roster(code, *, db):
        return {"rol": "Docente"}

    monkeypatch.setattr(booking, "get_usuario", roster)
    assert (await client.get(PREFIX + "/modelos")).status_code == 401
    assert (await client.get(PREFIX + "/modelos", headers=STUDENT)).status_code == 403
    assert (await client.get(PREFIX + "/modelos", headers=SECURITY)).status_code == 403
    assert (await client.get(PREFIX + "/modelos", headers=auth(999))).status_code == 403
    assert (await client.get(PREFIX + "/expedientes/2", headers=STUDENT)).status_code == 403
    assert (await client.get(PREFIX + "/asistencias", headers=STUDENT)).status_code == 403
    await permit(factory, today, time(10, 30), time(11, 30), "Pendiente")
    result = await ok(client, "GET", f"/recomendaciones?fecha={today}", headers=STUDENT)
    assert result["turnos"]
    assert {turn["id_l"] for turn in result["turnos"]} == {1}
    assert all(turn["hora_inicio"] >= "12:00:00" and turn["demanda"] is None for turn in result["turnos"])

    payload = {
        "tipo": "Normal",
        "duracion_t": 1,
        "detalles": [
            {"id_l": 1, "fecha": str(today), "hora_inicio": "13:00", "hora_fin": "14:00", "duracion": 1},
        ],
    }
    results = await asyncio.gather(
        *(client.post("/api/permisos/", json=payload, headers=actor) for actor in (STUDENT, OTHER))
    )
    assert sorted(response.status_code for response in results) == [201, 409]

    async def pupil(code, *, db):
        return {"rol": "Alumno", "año_academico": "1", "escuela": "Prueba", "codigo": code}

    async def roster_group(*, db):
        return [await pupil("10000001", db=db), await pupil("10000002", db=db)]

    monkeypatch.setattr(booking, "get_usuario", pupil)
    monkeypatch.setattr(booking, "list_usuarios", roster_group)
    group = await client.get(PREFIX + f"/recomendaciones?fecha={today}", headers=STUDENT)
    assert group.json()["code"] == "GROUP_DAILY_LIMIT"
    async with factory.begin() as db:
        await db.execute(text("INSERT INTO dias_bloqueados(fecha,motivo) VALUES (:d,'Prueba')"), {"d": today})
    blocked = await client.get(PREFIX + f"/recomendaciones?fecha={today}", headers=STUDENT)
    assert blocked.json()["code"] == "BLOCKED_DATE"


async def register(client, date_id, value="inasistencia"):
    return await ok(
        client,
        "POST",
        f"/asistencias/{date_id}",
        {
            "resultado": value,
            "evidencia": "Registro presencial de garita",
        },
        headers=SECURITY,
    )


async def test_dashboard_counts_observed_activity_and_previews_without_writes(pg):
    factory, client = pg
    today = campus_now().date()
    yesterday = today - timedelta(days=1)
    tomorrow = today + timedelta(days=1)
    completed = await permit(factory, yesterday, time(8), time(9))
    await permit(factory, yesterday, time(10), time(11))
    await permit(factory, yesterday, time(14), time(15), "Cancelado")
    await permit(factory, tomorrow, time(8), time(9))
    await register(client, completed)

    assert (await client.get(PREFIX + "/panel/demanda")).status_code == 401
    assert (await client.get(PREFIX + "/panel/anomalias", headers=STUDENT)).status_code == 403
    demand = await ok(client, "GET", f"/panel/demanda?fecha={tomorrow}")
    assert demand["por_hora"] == [{"clave": "08:00", "valor": 1}, {"clave": "10:00", "valor": 1}]
    assert demand["por_losa"] == [{"clave": "Losa uno", "valor": 2}]
    assert all(
        not slot["disponible"] for slot in demand["consulta"]["turnos"] if slot["hora_inicio"] == "08:00:00"
    )
    async with factory() as db:
        assert await db.scalar(select(func.count()).select_from(Prediction)) == 0

    risk = await ok(client, "GET", "/panel/inasistencia")
    assert {row["clave"]: row["valor"] for row in risk["por_resultado"]} == {
        "inasistencia": 1,
        "sin_verificar": 1,
        "pendiente": 1,
        "cancelado": 1,
    }
    anomalies = await ok(client, "GET", "/panel/anomalias")
    requests = {row["clave"]: row["valor"] for row in anomalies["por_solicitud"]}
    assert requests == {"Aceptado": 3, "Cancelado": 1}


async def new_case(client, attendance_id=None):
    return await ok(
        client,
        "POST",
        "/incidentes",
        {
            "usuario_id": 1,
            "asistencia_id": attendance_id,
            "evidencia": "Acta verificable de hechos",
        },
    )


async def review(client, case, decision="confirmar"):
    return await ok(
        client,
        "POST",
        f"/incidentes/{case['id']}/revision",
        {
            "decision": decision,
            "motivo": "Acta de revisión firmada",
            "evidencia": "Fuente independiente revisada",
        },
    )


async def policy(client, *, kind="inasistencia", measure="advertencia", hours=None, prior=0):
    return await ok(
        client,
        "POST",
        "/normas",
        {
            "tipo": kind,
            "gravedad": "ordinaria",
            "medida": measure,
            "minimo_previas": prior,
            "maximo_horas": hours,
            "fundamento": "Regla ficticia para prueba",
            "criterio": "Comprobación documental",
        },
    )


async def approve(client, rule):
    await ok(
        client,
        "POST",
        f"/normas/{rule['id']}/revision",
        {
            "vigente": True,
            "fundamento": "Referencia ficticia de pruebas",
        },
    )


def penalty(rule, hours=None):
    return {
        "norma_id": rule["id"],
        "horas": hours,
        "motivo": "Motivo individual revisado",
        "verificacion": "Criterio verificado con el expediente",
    }


async def test_attendance_restriction_expiry_and_unjust_penalty_correction(pg):
    factory, client = pg
    today = campus_now().date()
    future = await permit(factory, today + timedelta(days=1), time(8), time(9))
    old = [await permit(factory, today - timedelta(days=offset), time(8), time(9)) for offset in (5, 4, 3)]
    cancelled = await permit(factory, today - timedelta(days=6), time(8), time(9), "Cancelado")
    turns = (await ok(client, "GET", "/asistencias?codigo=10000001", headers=SECURITY))["turnos"]
    roll = {turn["detalle_id"]: turn["resultado"] for turn in turns}
    assert roll[future] == "pendiente"
    assert roll[cancelled] == "cancelado"
    assert roll[old[0]] == "sin_verificar"
    for detail in (future, cancelled):
        fail = await client.post(
            PREFIX + f"/asistencias/{detail}",
            headers=SECURITY,
            json={
                "resultado": "inasistencia",
                "evidencia": "Planilla comprobada",
            },
        )
        assert fail.status_code == 409
    same = await asyncio.gather(register(client, old[0]), register(client, old[0]))
    assert same[0]["id"] == same[1]["id"]
    presence = [same[0], await register(client, old[1]), await register(client, old[2])]
    turns = (await ok(client, "GET", "/asistencias", headers=SECURITY))["turnos"]
    assert next(turn for turn in turns if turn["detalle_id"] == old[0])["asistencia_id"] == same[0]["id"]
    cases = [await new_case(client, result["id"]) for result in presence]
    preventive = await policy(client, measure="preventiva", hours=2)
    case_path = f"/incidentes/{cases[0]['id']}/medidas"
    draft = await client.post(PREFIX + case_path, headers=ADMIN, json=penalty(preventive, 1))
    assert draft.status_code == 409
    await approve(client, preventive)
    measure = await ok(client, "POST", case_path, penalty(preventive, 1))
    assert (await client.get(PREFIX + f"/recomendaciones?fecha={today}", headers=STUDENT)).json()["code"] == (
        "RESERVATION_RESTRICTED"
    )
    situation = await ok(client, "GET", "/mi-situacion", headers=STUDENT)
    assert len(situation["medidas"]) == 1 and situation["infracciones_validas"] == 0
    private_url = f"/mi-situacion/{measure['id']}/descargos"
    assert (
        await client.post(PREFIX + private_url, headers=OTHER, json={"texto": "Descargo de otra persona"})
    ).status_code == 404
    appeal = await ok(client, "POST", private_url, {"texto": "Solicito contrastar la evidencia"}, STUDENT)
    await ok(
        client, "POST", f"/descargos/{appeal['id']}/revision", {"texto": "Revisión administrativa efectuada"}
    )
    async with factory.begin() as db:
        previous = await db.get(Measure, measure["id"])
        previous.inicio = utc_now() - timedelta(hours=2)
        previous.fin = utc_now() - timedelta(hours=1)
    assert (await ok(client, "GET", "/mi-situacion", headers=STUDENT))["medidas"][0]["estado"] == "cumplida"
    async with factory() as db:
        await discipline.check_reservation_access(db, 1)

    warning = await policy(client)
    await approve(client, warning)
    for case in cases[:2]:
        await review(client, case)
        warning_result = await ok(client, "POST", f"/incidentes/{case['id']}/medidas", penalty(warning))
    await ok(
        client,
        "POST",
        f"/medidas/{warning_result['id']}/revision",
        {
            "decision": "anular",
            "motivo": "Se comprobó un error en la segunda acta",
        },
    )
    await register(client, old[1], "asistio")
    history = await ok(client, "GET", "/expedientes/1")
    assert history["infracciones_validas"] == 1
    assert any(m["estado"] == "anulada" for m in history["medidas"])
    assert any(d["accion"] == "anular" for d in history["decisiones"])
    assert all(
        m["estado"] != "anulada"
        for m in (await ok(client, "GET", "/mi-situacion", headers=STUDENT))["medidas"]
    )

    await review(client, cases[2])
    actual_rule = await policy(client, measure="suspension", hours=6, prior=1)
    excessive_rule = await policy(client, measure="suspension", hours=12, prior=2)
    await approve(client, actual_rule)
    await approve(client, excessive_rule)
    third_path = f"/incidentes/{cases[2]['id']}/medidas"
    assert (
        await client.post(PREFIX + third_path, headers=ADMIN, json=penalty(excessive_rule, 2))
    ).status_code == 409
    suspension = await ok(client, "POST", third_path, penalty(actual_rule, 2))
    await ok(
        client,
        "POST",
        f"/medidas/{suspension['id']}/revision",
        {
            "decision": "levantar",
            "motivo": "Revisión concluyó y autoriza el levantamiento",
        },
    )
    assert (await ok(client, "GET", "/expedientes/1"))["infracciones_validas"] == 2
    async with factory() as db:
        rows = await datasets.no_show_samples(db)
        assert Counter(row.label for row in rows) == {1: 2, 0: 1}
        await discipline.check_reservation_access(db, 1)


async def test_registry_demo_isolation_and_no_show_fallback(pg):
    factory, client = pg
    async with factory.begin() as db:
        insufficient = await registry.train(db, "inasistencia", "real")
        demo = await registry.train(db, "inasistencia", "demo")
        assert insufficient.estado == "insuficiente" and demo.estado == "evaluado"
        demo_version = demo.version
    result = await ok(client, "GET", "/demo/inasistencia")
    assert result["modo"] == "demo" and len(result["muestras"]) == 56
    assert len({row["fecha"] for row in result["muestras"]}) == 2
    assert {row["objetivo"] for row in result["muestras"]} == {0, 1}
    assert all(row["cuenta"].startswith("C-") and 0 <= row["puntuacion"] <= 1 for row in result["muestras"])
    assert 0 <= result["umbrales"]["umbral_medio"] < result["umbrales"]["umbral_alto"] <= 1
    assert (await client.post(PREFIX + f"/modelos/{demo_version}/activar", headers=ADMIN)).status_code == 409
    async with factory.begin() as db:
        stored = await db.get(ModelVersion, demo_version)
        stored.evaluacion = {**stored.evaluacion, "umbral_alto": 0}
    assert (await client.get(PREFIX + "/demo/inasistencia", headers=ADMIN)).status_code == 409
    future = await permit(factory, campus_now().date() + timedelta(days=1), time(8), time(9))
    assert (await ok(client, "POST", f"/riesgo/{future}"))["disponible"] is False
    assert (await ok(client, "POST", "/anomalias"))["disponible"] is False
    async with factory() as db:
        assert await db.scalar(select(func.count()).select_from(Attendance)) == 0
        assert await db.scalar(select(func.count()).select_from(Incident)) == 0
        assert await db.scalar(select(func.count()).select_from(Prediction)) == 0
        assert await db.scalar(select(func.count()).select_from(ModelVersion).where(ModelVersion.activo)) == 0


async def test_real_extraction_activation_and_operational_predictions(pg):
    factory, client = pg
    today = campus_now().date()
    async with factory.begin() as db:
        await db.execute(
            text("""
            INSERT INTO users(codigo,password,rol)
            SELECT 'test' || n,'fixture','Alumno' FROM generate_series(3,24) n
        """)
        )
        await db.execute(
            text("""
            WITH history AS (
                SELECT 100 + i*24 + h AS id, 3 + (i*5+h)%22 AS owner,
                       CAST(:today AS date) - i AS day, h AS hour
                FROM generate_series(1,135) i CROSS JOIN generate_series(6,21) h
                WHERE h >= 16 OR (i*13+h*7)%19 < 2
            ), bookings AS (
                INSERT INTO permisos(id_p,id_u,tipo,duracion_t,estado,fecha_creacion,fecha_decision)
                SELECT id,owner,'Especial',1,'Aceptado', day - (1 + hour%5) + time '10:00',
                       day - (1 + hour%5) + time '15:00' FROM history RETURNING id_p
            ), slots AS (
                INSERT INTO detalle_permisos(id_d,id_p,id_l,fecha,hora_inicio,hora_fin,duracion)
                SELECT id,id,1,day,make_time(hour,0,0),make_time(hour+1,0,0),1
                FROM history JOIN bookings ON id_p=id RETURNING id_d
            )
            INSERT INTO ml_asistencias(detalle_id,actor_id,resultado,evidencia,registrado)
            SELECT id,2,
                   CASE WHEN (hour >= 19 AND (id/24)%5 <> 0) OR (id/24)%17 = 0
                        THEN 'inasistencia' ELSE 'asistio' END,
                   'Planilla de prueba por turno', (day + time '23:01') AT TIME ZONE 'America/Lima'
            FROM history JOIN slots ON id_d=id
        """),
            {"today": today},
        )
        await db.execute(
            text("""
            INSERT INTO ml_intentos(usuario_id,resultado,franja,ocurrido)
            SELECT u, CASE WHEN i%3 = 0 THEN 'SCHEDULE_CONFLICT' ELSE 'registrado' END,
                   (i%4)::text,
                   date_trunc('week', CURRENT_TIMESTAMP) - w*interval '7 days' + interval '2 days'
            FROM generate_series(3,24) u CROSS JOIN generate_series(2,23) w
            CROSS JOIN LATERAL generate_series(1, 2 + (u+w)%8) i
        """)
        )
        await db.execute(
            text("""
            INSERT INTO ml_intentos(usuario_id,resultado,franja,ocurrido)
            SELECT 1,'SCHEDULE_CONFLICT','misma-franja',
                   date_trunc('week', CURRENT_TIMESTAMP) - interval '4 days'
            FROM generate_series(1,350)
        """)
        )

    versions = {}
    for module in registry.MODULES:
        async with factory.begin() as db:
            result = await registry.train(db, module, "real")
            assert result.estado == "evaluado", (module, result.evaluacion)
            versions[module] = result.version
        await ok(client, "POST", f"/modelos/{versions[module]}/activar")
    next_day = today + timedelta(days=1)
    upcoming = await permit(factory, next_day, time(19), time(20))
    demand = await ok(client, "POST", f"/demanda?fecha={next_day}")
    assert demand["turnos"] and all(s["fuente"] == "modelo_real" for s in demand["turnos"])
    output = await ok(client, "POST", f"/riesgo/{upcoming}")
    assert output["disponible"] and 0 <= output["riesgo"] <= 1
    await ok(client, "POST", "/riesgo")
    alert_scan = await ok(client, "POST", "/anomalias")
    assert alert_scan["disponible"] and alert_scan["alertas"] > 0
    assert (await ok(client, "POST", "/anomalias"))["alertas"] == 0
    alerts = (await ok(client, "GET", "/incidentes?estado=pendiente"))["incidentes"]
    alert = alerts[0]
    assert alert["tipo"] == "anomalia" and "puntuacion" in alert["evidencia"]
    confirm = await client.post(
        PREFIX + f"/incidentes/{alert['id']}/revision",
        headers=ADMIN,
        json={
            "decision": "confirmar",
            "motivo": "Se revisó el comportamiento",
            "evidencia": "Solo puntuación del modelo",
        },
    )
    assert confirm.status_code == 409
    if len(alerts) >= 2:
        derived = await ok(
            client,
            "POST",
            "/incidentes",
            {
                "usuario_id": alerts[1]["usuario_id"],
                "alerta_id": alerts[1]["id"],
                "referencia_hecho": "Acta independiente de prueba 42",
                "evidencia": "Verificación ajena al puntaje",
            },
        )
        assert derived["tipo"] == "otro" and derived["estado"] == "pendiente"
    await review(client, alert, "descartar")
    async with factory() as db:
        assert await db.scalar(select(func.count()).select_from(Prediction)) > 0
        assert await db.scalar(select(func.count()).select_from(Measure)) == 0
        assert (await db.get(Incident, alert["id"])).estado == "descartado"
