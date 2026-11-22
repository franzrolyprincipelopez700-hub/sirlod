"""Provisiona un entorno de práctica en esquemas privados, con acceso limitado."""

import argparse
import asyncio
import io
import json
import secrets
from collections import Counter
from datetime import UTC, datetime, time, timedelta
from pathlib import Path
from random import Random
from tempfile import NamedTemporaryFile
from typing import Any

import asyncpg
from dotenv import dotenv_values, set_key
from reportlab.pdfgen import canvas
from sqlalchemy.engine import make_url

from app.core.clock import LIMA, campus_now
from app.core.config import settings
from app.core.security import hash_password
from scripts.migrate_supabase import ROOT, configuration, connect, ident, initialize
from scripts.supabase_storage import RestBucket, check_private

APP = "sirlod_practica"
ROSTER = "padron_practica"
ROLE = "sirlod_practica_app"
BUCKET = "sirlod-practica"
ENV = ROOT / "backend_fastapi" / ".env.practice"
ADMIN_EMAIL = "operaciones@example.com"
SECURITY_EMAIL = "garita@example.com"
FIRST_STUDENT = "20241001"

NAMES = ("Ana", "Bruno", "Camila", "Diego", "Elena", "Fabio", "Gabriela", "Hugo", "Inés", "Joaquín")
SURNAMES = ("Alarcón", "Benavides", "Cárdenas", "Delgado", "Espinoza", "Flores", "Gálvez", "Huamán")
SECOND = ("Ibarra", "León", "Mendoza", "Núñez", "Ortega", "Paredes", "Quiroz", "Salazar")


async def copy(
    db: asyncpg.Connection,
    schema: str,
    table: str,
    fields: str,
    records: list[tuple[Any, ...]],
) -> None:
    columns = fields.split()
    await db.copy_records_to_table(table, schema_name=schema, records=records, columns=columns)
    relation = f"{ident(schema)}.{ident(table)}"
    sequence = await db.fetchval("SELECT pg_get_serial_sequence($1, $2)", relation, columns[0])
    if sequence and records:
        await db.execute("SELECT setval($1::regclass, $2)", sequence, max(row[0] for row in records))


def request_documents(config: dict[str, str]) -> list[tuple[Any, ...]]:
    project = config["SUPABASE_STORAGE_URL"]
    store = RestBucket(project, config["SUPABASE_STORAGE_SECRET_KEY"], BUCKET)
    records = []
    try:
        for number in range(1, 6):
            content = io.BytesIO()
            pdf = canvas.Canvas(content, invariant=True)
            pdf.setTitle("Solicitud de uso de instalaciones")
            pdf.drawString(62, 770, "SIRLOD | Entorno de práctica")
            pdf.drawString(62, 727, f"Solicitud de uso deportivo | Referencia {number:02d}")
            pdf.drawString(62, 701, "Coordinación de turnos para actividades académicas y deportivas.")
            pdf.save()
            size = content.tell()
            content.seek(0)
            key = f"documentos/practica/solicitud-{number:02d}.pdf"
            existing = store.client.get(f"/object/info/{BUCKET}/{key}")
            if existing.status_code in {400, 404}:
                store.put_object(
                    Bucket=BUCKET, Key=key, Body=content, IfNoneMatch="*", ContentType="application/pdf"
                )
            else:
                existing.raise_for_status()
            url = f"{project.rstrip('/')}/storage/v1/object/authenticated/{BUCKET}/{key}"
            records.append((number, f"Solicitud de uso {number:02d}.pdf", key, "application/pdf", url, size))
    finally:
        store.close()
    return records


def activity(now: datetime, courts: list[int], student_count: int) -> dict[str, list[tuple[Any, ...]]]:
    rng = Random(928)
    today = now.date()
    start = today - timedelta(days=119)
    blocked = {start + timedelta(days=34), start + timedelta(days=72), today + timedelta(days=5)}
    permits: list[tuple[Any, ...]] = []
    details: list[tuple[Any, ...]] = []
    attendance: list[tuple[Any, ...]] = []
    attempts: list[tuple[Any, ...]] = []
    notifications: list[tuple[Any, ...]] = []
    weekly: Counter[tuple[int, int, int]] = Counter()
    names = {
        "Aceptado": "Reserva confirmada",
        "Pendiente": "Solicitud pendiente de revisión",
        "Cancelado": "Reserva cancelada",
        "Rechazado": "Solicitud rechazada",
    }

    for offset in range(127):
        day = start + timedelta(days=offset)
        if day in blocked:
            continue
        for hour in (9, 10, 11, 12, 14, 15, 16, 17, 18):
            begins = datetime.combine(day, time(hour), LIMA)
            ends = begins + timedelta(hours=1)
            for court in courts:
                if day == today or rng.random() > (0.45 if hour >= 15 else 0.25):
                    continue
                special = day > today or rng.random() < 0.21
                kind = "Especial" if special else "Normal"
                owner = rng.randint(1, student_count)
                week = day.isocalendar()
                group = (week.year * 100 + week.week, (owner - 1) % 15, (owner - 1) // 15 % 5)
                if not special and weekly[group] >= 3:
                    continue
                if special:
                    created = min(begins - timedelta(days=rng.randint(2, 5)), now - timedelta(hours=4))
                    state = rng.choices(
                        ["Aceptado", "Pendiente", "Rechazado", "Cancelado"]
                        if day > today
                        else ["Aceptado", "Rechazado", "Cancelado"],
                        [6, 5, 1, 1] if day > today else [18, 3, 2],
                    )[0]
                    decided = created + timedelta(hours=2) if state != "Pendiente" else None
                else:
                    created = begins - timedelta(minutes=rng.choice((25, 40, 65, 85)))
                    state = "Cancelado" if rng.random() < 0.10 else "Aceptado"
                    decided = None
                    weekly[group] += int(state == "Aceptado")
                permission = len(permits) + 1
                permits.append(
                    (
                        permission,
                        owner,
                        1 if decided else None,
                        kind,
                        (owner - 1) % 5 + 1 if special else None,
                        state,
                        created.astimezone(LIMA).replace(tzinfo=None),
                        decided.astimezone(UTC).replace(tzinfo=None) if decided else None,
                    )
                )
                details.append((permission, permission, court, day, begins.time(), ends.time()))
                attempts.append(
                    (len(attempts) + 1, owner, permission, "creado", f"{court}:{hour:02d}:00", created)
                )
                if rng.random() < 0.11:
                    attempts.append(
                        (
                            len(attempts) + 1,
                            owner,
                            None,
                            "SCHEDULE_CONFLICT",
                            f"{court}:{hour:02d}:00",
                            created - timedelta(minutes=5),
                        )
                    )
                sent = decided or min(created + timedelta(minutes=8), now)
                notifications.append(
                    (
                        permission,
                        f"{names[state]} · {day:%d/%m} a las {hour:02d}:00",
                        sent.astimezone(LIMA).replace(tzinfo=None),
                        state,
                        permission,
                        day < today,
                    )
                )
                checked = ends + timedelta(minutes=15)
                if state == "Aceptado" and checked < now:
                    outcome = rng.choices(["asistio", "inasistencia", "sin_verificar"], [84, 13, 3])[0]
                    attendance.append(
                        (
                            len(attendance) + 1,
                            permission,
                            2,
                            outcome,
                            f"Control de garita · {day:%d/%m/%Y} · turno {permission}",
                            checked,
                        )
                    )
    return {
        "dias_bloqueados": [(i, day, "Mantenimiento programado") for i, day in enumerate(sorted(blocked), 1)],
        "permisos": permits,
        "detalle_permisos": details,
        "ml_asistencias": attendance,
        "ml_intentos": attempts,
        "notificacion": notifications,
    }


async def populate(db: asyncpg.Connection, password: str, documents: list[tuple[Any, ...]]) -> None:
    await db.execute("INSERT INTO configuracion_global (id) VALUES (1)")
    await db.execute(
        "INSERT INTO disciplinas (nombre) VALUES ('Futsal'), ('Vóley'), ('Básquet'), ('Multiuso')"
    )
    await db.execute("""
        INSERT INTO losas (nombre, numero_l, ubicacion, dimensiones, superficie, iluminacion, id_d)
        VALUES ('Losa Juan de la Cruz', '01', 'Campus Cayhuayna · sector norte',
                '32 × 18 m', 'Concreto', 'LED', 1),
               ('Losa Valle del Huallaga', '02', 'Campus Cayhuayna · sector central',
                '18 × 9 m', 'Concreto', 'LED', 2),
               ('Losa Kotosh', '03', 'Campus Cayhuayna · sector central', '28 × 15 m', 'Concreto', 'LED', 3),
               ('Losa Universitaria', '04', 'Campus Cayhuayna · sector sur',
                '30 × 17 m', 'Concreto', 'LED', 4),
               ('Losa Los Laureles', '05', 'Campus Cayhuayna · sector sur', '32 × 18 m', 'Concreto', 'LED', 1)
    """)
    await db.execute(f"""
        INSERT INTO {ROSTER}.facultad (nombre) VALUES
            ('Ingeniería'), ('Ciencias de la Salud'), ('Ciencias Sociales'),
            ('Ciencias Administrativas'), ('Educación y Humanidades');
        INSERT INTO {ROSTER}.escuela_profesional (codigo, nombre, id_fac) VALUES
            ('SIS', 'Ingeniería de Sistemas', 1), ('CIV', 'Ingeniería Civil', 1), ('AGR', 'Agronomía', 1),
            ('ENF', 'Enfermería', 2), ('PSI', 'Psicología', 2), ('MED', 'Medicina', 2),
            ('SOC', 'Sociología', 3), ('COM', 'Ciencias de la Comunicación', 3), ('DER', 'Derecho', 3),
            ('ADM', 'Administración', 4), ('CON', 'Contabilidad', 4), ('ECO', 'Economía', 4),
            ('EDU', 'Educación Primaria', 5), ('LEN', 'Lengua y Literatura', 5),
            ('HIS', 'Historia y Geografía', 5);
    """)

    students: list[tuple[Any, ...]] = []
    users: list[tuple[Any, ...]] = []
    password_hash = await hash_password(password)
    inaccessible_hash = await hash_password(secrets.token_urlsafe(32))
    for index in range(180):
        user_id = index + 1
        code = str(int(FIRST_STUDENT) + index)
        school = index % 15 + 1
        students.append(
            (
                user_id,
                code,
                f"{1700 + index:08d}",
                NAMES[index % 10],
                SURNAMES[index // 10 % 8],
                SECOND[index // 80 % 8],
                f"{code}@example.com",
                index // 15 % 5 + 1,
                school,
            )
        )
        users.append((user_id, code, password_hash if index == 0 else inaccessible_hash, "Alumno"))
    await copy(
        db,
        ROSTER,
        "alumno",
        "id_al codigo dni nombres apellido_p apellido_m email año_academico id_esc",
        students,
    )
    await copy(db, APP, "users", "id_u codigo password rol", users)
    await copy(
        db,
        APP,
        "trabajadores",
        "id_t dni nombres apellido_p apellido_m rol email password",
        [
            (1, "00002001", "Valeria", "Torres", "Mendoza", "Administrador", ADMIN_EMAIL, password_hash),
            (2, "00002002", "Ricardo", "Vega", "Rojas", "Seguridad", SECURITY_EMAIL, password_hash),
        ],
    )
    await copy(db, APP, "archivos", "id_arch nombre_original nombre_unico mimetype url tamanio", documents)
    now = campus_now()
    rows = activity(now, list(range(1, 6)), len(students))
    await copy(db, APP, "dias_bloqueados", "id fecha motivo", rows["dias_bloqueados"])
    await db.execute("ALTER TABLE permisos ALTER COLUMN duracion_t SET DEFAULT 1")
    await db.execute("ALTER TABLE detalle_permisos ALTER COLUMN duracion SET DEFAULT 1")
    await copy(
        db,
        APP,
        "permisos",
        "id_p id_u id_t_decision tipo id_arch estado fecha_creacion fecha_decision",
        rows["permisos"],
    )
    await copy(
        db, APP, "detalle_permisos", "id_d id_p id_l fecha hora_inicio hora_fin", rows["detalle_permisos"]
    )
    await db.execute("ALTER TABLE permisos ALTER COLUMN duracion_t DROP DEFAULT")
    await db.execute("ALTER TABLE detalle_permisos ALTER COLUMN duracion DROP DEFAULT")
    await copy(
        db,
        APP,
        "ml_asistencias",
        "id detalle_id actor_id resultado evidencia registrado",
        rows["ml_asistencias"],
    )
    await copy(
        db, APP, "ml_intentos", "id usuario_id permiso_id resultado franja ocurrido", rows["ml_intentos"]
    )
    await copy(db, APP, "notificacion", "id_n mensaje fecha_envio tipo id_p leido", rows["notificacion"])


def write_profile(path: Path, values: dict[str, str]) -> None:
    with NamedTemporaryFile(dir=path.parent, delete=False) as output:
        temporary = Path(output.name)
    try:
        for key, value in values.items():
            set_key(temporary, key, value)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


async def seed(local_url: str | None) -> None:
    url = make_url(local_url or settings.sqlalchemy_database_url)
    practice_env = dotenv_values(ENV)
    db_password = str(practice_env.get("PRACTICE_DB_PASSWORD") or secrets.token_urlsafe(32))
    login = str(practice_env.get("PRACTICE_LOGIN_PASSWORD") or secrets.token_urlsafe(15))
    if not local_url and settings.postgres_tls_ca_cert:
        url = url.update_query_dict({"sslrootcert": str(settings.postgres_tls_ca_cert)})
    config = configuration()
    db = await connect(url.render_as_string(hide_password=False), target=True, local_test=bool(local_url))
    try:
        async with db.transaction():
            await db.execute("SELECT pg_advisory_xact_lock(11620017)")
            existing = await db.fetchval("SELECT to_regnamespace($1)", APP)
            role_exists = await db.fetchval("SELECT EXISTS(SELECT FROM pg_roles WHERE rolname=$1)", ROLE)
            if bool(existing) != role_exists or (
                existing and not local_url and not practice_env.get("PRACTICE_DB_PASSWORD")
            ):
                raise ValueError(
                    "Se encontró una instalación de práctica sin las credenciales locales correspondientes."
                )
            if not existing:
                documents = (
                    [
                        (
                            n,
                            f"Solicitud {n}.pdf",
                            f"local-{n}",
                            "application/pdf",
                            f"https://example.com/solicitud-{n}.pdf",
                            1,
                        )
                        for n in range(1, 6)
                    ]
                    if local_url
                    else await asyncio.to_thread(request_documents, config)
                )
                if not local_url:
                    await check_private(db, BUCKET)
                await initialize(db, APP, ROSTER)
                await db.execute("ALTER TABLE ml_modelos ADD CONSTRAINT solo_practica CHECK (modo = 'demo')")
                await populate(db, login, documents)
                statement = await db.fetchval(
                    "SELECT format('CREATE ROLE %I LOGIN PASSWORD %L', $1::text, $2::text)", ROLE, db_password
                )
                await db.execute(statement)
                await db.execute(f"GRANT USAGE ON SCHEMA {APP}, {ROSTER} TO {ROLE}")
                await db.execute(
                    f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA {APP} TO {ROLE}"
                )
                await db.execute(f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA {APP} TO {ROLE}")
                await db.execute(f"GRANT SELECT ON ALL TABLES IN SCHEMA {ROSTER} TO {ROLE}")
            else:
                await db.execute(f"SET LOCAL search_path TO {APP}, pg_catalog")
            totals = dict(
                await db.fetchrow(f"""
                SELECT (SELECT count(*) FROM {ROSTER}.alumno) AS alumnos,
                       (SELECT count(*) FROM permisos) AS solicitudes,
                       (SELECT count(*) FROM permisos WHERE estado = 'Pendiente') AS pendientes,
                       (SELECT count(*) FROM ml_asistencias) AS asistencias,
                       (SELECT count(*) FROM ml_intentos) AS intentos
            """)
            )
    finally:
        await db.close()
    if not local_url:
        _, _, ref = (url.username or "").partition(".")
        server_user = f"{ROLE}.{ref}" if ref else ROLE
        application_url = url.difference_update_query(["sslrootcert"]).set(
            username=server_user, password=db_password
        )
        session_secret = str(practice_env.get("SESSION_SECRET") or secrets.token_urlsafe(32))
        write_profile(
            ENV,
            {
                "DATABASE_URL": application_url.render_as_string(hide_password=False),
                "POSTGRES_SCHEMA": APP,
                "PRACTICE_DB_PASSWORD": db_password,
                "PRACTICE_LOGIN_PASSWORD": login,
                "JWT_SECRET": str(practice_env.get("JWT_SECRET") or secrets.token_urlsafe(32)),
                "JWT_REFRESH_SECRET": str(
                    practice_env.get("JWT_REFRESH_SECRET") or secrets.token_urlsafe(32)
                ),
                "ML_ARTIFACT_SECRET": str(
                    practice_env.get("ML_ARTIFACT_SECRET") or secrets.token_urlsafe(32)
                ),
                "SESSION_SECRET": session_secret,
                "SUPABASE_STORAGE_BUCKET": BUCKET,
                "FRONTEND_URL": "http://localhost:5174",
                "APP_PORT": "3005",
                "MAIL_HOST": "",
                "RENIEC_API_TOKEN": "",
            }
        )
        write_profile(ROOT / "frontend" / ".env.practica", {
            "VITE_DEV_API_SERVER_URL": "http://127.0.0.1:3005/api",
            "VITE_API_BASE_URL": "/api/servicio",
            "VITE_SIRLOD_PRACTICE": "1",
            "SESSION_SECRET": session_secret,
        })
        write_profile(ROOT / "database" / ".env.practice-access", {
            "ADMINISTRACION": ADMIN_EMAIL,
            "SEGURIDAD": SECURITY_EMAIL,
            "ALUMNO": FIRST_STUDENT,
            "CLAVE": login,
        })
    print(json.dumps(totals))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--local-test-url", help="Conexión PostgreSQL desechable en localhost")
    arguments = parser.parse_args()
    if arguments.local_test_url and make_url(arguments.local_test_url).host not in {
        "localhost",
        "127.0.0.1",
        "::1",
    }:
        parser.error("El destino de pruebas debe estar en localhost.")
    try:
        asyncio.run(seed(arguments.local_test_url))
    except Exception as exc:
        parser.exit(1, f"No se pudo preparar la base de práctica ({type(exc).__name__}).\n")
