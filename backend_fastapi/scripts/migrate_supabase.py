"""Initialize the private SIRLOD and roster schemas, then copy recoverable records."""

import argparse
import asyncio
import json
import os
import re
import ssl
import subprocess
from datetime import datetime, time
from decimal import Decimal
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

import asyncpg
from dotenv import dotenv_values, set_key
from sqlalchemy.engine import make_url

from app.models import Base
from app.modules.learning.models import ModelVersion
from scripts import supabase_storage

ROOT = Path(__file__).resolve().parents[2]
ENV = ROOT / ".env.supabase"
APP_SCHEMA = "sirlod"
ROSTER_SCHEMA = "padron_unheval"
ROSTER_TABLES = ("facultad", "escuela_profesional", "alumno", "docente", "personal_administrativo")
LEGACY_TABLES = ("disciplinas", "losas", "configuracion_global", "users", "trabajadores")
APP_TABLES = (
    "disciplinas",
    "losas",
    "configuracion_global",
    "users",
    "trabajadores",
    "archivos",
    "dias_bloqueados",
    "imagenes",
    "permisos",
    "detalle_permisos",
    "notificacion",
    "cola_notificaciones",
    "reportes_generados",
    "ml_modelos",
    "ml_asistencias",
    "ml_intentos",
    "ml_incidentes",
    "ml_normas",
    "ml_medidas",
    "ml_descargos",
    "ml_decisiones",
    "ml_predicciones",
)


class MigrationError(Exception):
    pass


def ident(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def configuration() -> dict[str, str]:
    return {
        **{key: value for key, value in dotenv_values(ENV).items() if value is not None},
        **{
            key: value for key, value in os.environ.items() if key.startswith(("SUPABASE_", "SIRLOD_SOURCE_"))
        },
    }


async def connect(url: str, *, target: bool = False, local_test: bool = False) -> asyncpg.Connection:
    parsed = make_url(url)
    if parsed.drivername not in {"postgres", "postgresql", "postgresql+asyncpg"}:
        raise MigrationError("Se requiere una URL PostgreSQL.")
    host = parsed.host or ""
    local = host in {"localhost", "127.0.0.1", "::1"}
    if target and not (host.endswith((".supabase.com", ".supabase.co")) or local_test and local):
        raise MigrationError("El destino debe ser el PostgreSQL de tu proyecto Supabase.")
    ca_file = dict(parsed.query).get("sslrootcert")
    tls: ssl.SSLContext | bool = False if local else ssl.create_default_context(cafile=ca_file)
    return await asyncpg.connect(
        host=host,
        port=parsed.port or 5432,
        database=parsed.database,
        user=parsed.username,
        password=parsed.password,
        ssl=tls,
        timeout=12,
        command_timeout=90,
    )


def mysql_records(include_legacy: bool) -> dict[str, dict[str, list[dict[str, Any]]]]:
    arguments = ["node", str(ROOT / "backend_api" / "scripts" / "export-migration.cjs")]
    if include_legacy:
        arguments.append("--legacy")
    result = subprocess.run(arguments, capture_output=True, check=False, timeout=60)
    if result.returncode:
        raise MigrationError("La lectura de MySQL falló. Revisa la conexión local de backend_api y backend.")
    payload: dict[str, dict[str, list[dict[str, Any]]]] = json.loads(result.stdout)
    return payload


def sql_body(path: Path) -> str:
    sql = path.read_text(encoding="utf-8-sig")
    return re.sub(r"(?im)^(?:BEGIN|COMMIT);[ \t]*$", "", sql)


async def initialize(
    db: asyncpg.Connection, app_schema: str = APP_SCHEMA, roster_schema: str = ROSTER_SCHEMA
) -> None:
    application = ident(app_schema)
    roster = ident(roster_schema)
    await db.execute(f"CREATE SCHEMA IF NOT EXISTS {application}")
    await db.execute(f"REVOKE ALL ON SCHEMA {application} FROM PUBLIC")
    await db.execute(f"SET LOCAL search_path TO {application}, pg_catalog")
    await db.execute("SET LOCAL TIME ZONE 'America/Lima'")
    pg = ROOT / "database" / "postgres"
    if not await db.fetchval("SELECT to_regclass($1)", f"{application}.users"):
        await db.execute(sql_body(pg / "sistema_losa_schema.sql"))
    for path in sorted((pg / "migrations").glob("*.sql")):
        await db.execute(sql_body(path))
    await db.execute(sql_body(pg / "padron_unheval_schema.sql").replace(ROSTER_SCHEMA, roster))
    roles = await db.fetch(
        "SELECT rolname FROM pg_roles WHERE rolname IN ('anon', 'authenticated', 'service_role')"
    )
    for row in roles:
        await db.execute(f"REVOKE ALL ON SCHEMA {application}, {roster} FROM {ident(row['rolname'])}")


async def columns(db: asyncpg.Connection, schema: str, table: str) -> dict[str, str]:
    rows = await db.fetch(
        """SELECT column_name, data_type
           FROM information_schema.columns
           WHERE table_schema = $1 AND table_name = $2
           ORDER BY ordinal_position""",
        schema,
        table,
    )
    return {row["column_name"]: row["data_type"] for row in rows}


async def verify_target(db: asyncpg.Connection) -> None:
    tables = {ModelVersion.__tablename__, *Base.metadata.tables}
    for table in sorted(tables):
        available = await columns(db, APP_SCHEMA, table)
        missing = set(Base.metadata.tables[table].columns.keys()) - available.keys()
        if missing:
            raise MigrationError(f"El destino carece de columnas requeridas de {table}.")
    if not await db.fetchval("SELECT EXISTS (SELECT 1 FROM padron_unheval.vista_usuario)"):
        raise MigrationError("La vista del padrón de destino está vacía.")


def adapt(value: Any, kind: str) -> Any:
    if isinstance(value, str):
        if kind == "time without time zone":
            return time.fromisoformat(value)
        if kind == "timestamp without time zone":
            return datetime.fromisoformat(value)
        if kind == "numeric":
            return Decimal(value)
    return value


async def import_rows(
    db: asyncpg.Connection,
    schema: str,
    table: str,
    records: list[dict[str, Any]],
) -> int:
    if not records:
        return 0
    kinds = await columns(db, schema, table)
    fields = [key for key in kinds if key in records[0]]
    pk = next(iter(kinds))
    if pk not in fields:
        raise MigrationError(f"La fuente no trae una clave primaria compatible para {table}.")
    names = ", ".join(map(ident, fields))
    relation = f"{ident(schema)}.{ident(table)}"
    parameters = ", ".join(f"${i}" for i in range(1, len(fields) + 1))
    insert = f"INSERT INTO {relation} ({names}) VALUES ({parameters}) ON CONFLICT DO NOTHING"
    select = f"SELECT {names} FROM {relation} WHERE {ident(pk)} = $1"
    for record in records:
        values = tuple(adapt(record[key], kinds[key]) for key in fields)
        try:
            await db.execute(insert, *values)
        except (ValueError, asyncpg.PostgresError) as exc:
            raise MigrationError(f"El registro de origen es incompatible con la tabla {table}.") from exc
        stored = await db.fetchrow(select, record[pk])
        if stored is None or tuple(stored.values()) != values:
            raise MigrationError(f"La tabla {table} tiene datos distintos para una clave del origen.")
    sequence = await db.fetchval("SELECT pg_get_serial_sequence($1, $2)", relation, pk)
    if sequence:
        maximum = await db.fetchval(f"SELECT MAX({ident(pk)}) FROM {relation}")
        await db.execute(
            "SELECT setval($1::regclass, GREATEST($2, nextval($1::regclass)))", sequence, maximum
        )
    return len(records)


async def copy_primary(source: asyncpg.Connection, target: asyncpg.Connection, schema: str) -> dict[str, int]:
    totals = {}
    async with source.transaction(readonly=True, isolation="repeatable_read"):
        for table in APP_TABLES:
            available = await columns(source, schema, table)
            if not available:
                continue
            pk = ident(next(iter(available)))
            query = f"SELECT * FROM {ident(schema)}.{ident(table)} ORDER BY {pk}"
            rows = [dict(row) for row in await source.fetch(query)]
            totals[table] = await import_rows(target, APP_SCHEMA, table, rows)
    return totals


async def migrate(
    target: asyncpg.Connection,
    source: asyncpg.Connection | None,
    source_schema: str,
    snapshot: dict[str, dict[str, list[dict[str, Any]]]],
) -> dict[str, Any]:
    async with target.transaction():
        await target.execute("SELECT pg_advisory_xact_lock(11620016)")
        await initialize(target)
        if source:
            main = await copy_primary(source, target, source_schema)
        else:
            main = {}
            for table, records in snapshot["legacy"].items():
                # Test accounts with unreadable password formats cannot log in to FastAPI.
                if table in {"users", "trabajadores"}:
                    records = [row for row in records if re.match(r"^\$2[aby]\$", row["password"])]
                main[table] = await import_rows(target, APP_SCHEMA, table, records)
        padron = {
            table: await import_rows(target, ROSTER_SCHEMA, table, snapshot["roster"][table])
            for table in ROSTER_TABLES
        }
        total = await target.fetchval("SELECT COUNT(*) FROM padron_unheval.vista_usuario")
        if total != sum(len(snapshot["roster"][table]) for table in ROSTER_TABLES[2:]):
            raise MigrationError("La vista del padrón tiene una cantidad distinta de la fuente MySQL.")
        return {"sirlod": main, "padron": padron, "vista_usuario": total}


def configure_fastapi(url: str, storage: dict[str, str]) -> None:
    target = ROOT / "backend_fastapi" / ".env"
    backup = target.with_name(".env.pre_supabase")
    original = target.read_bytes() if target.exists() else b""
    if target.exists() and not backup.exists():
        backup.write_bytes(original)
    parsed = make_url(url)
    ca_file = parsed.query.get("sslrootcert")
    settings = {
        "DATABASE_URL": parsed.difference_update_query(["sslrootcert"])
        .set(drivername="postgresql+asyncpg")
        .render_as_string(hide_password=False),
        "POSTGRES_SCHEMA": APP_SCHEMA,
        "POSTGRES_TLS_VERIFY": "true",
        "UNHEVAL_SOURCE": "postgresql",
        **storage,
    }
    if isinstance(ca_file, str):
        settings["POSTGRES_TLS_CA_CERT"] = ca_file
    with NamedTemporaryFile(prefix=".env.supabase-", dir=target.parent, delete=False) as stream:
        staged = Path(stream.name)
        stream.write(original)
    try:
        for key, value in settings.items():
            set_key(str(staged), key, value)
        staged.replace(target)
    finally:
        staged.unlink(missing_ok=True)


async def run(args: argparse.Namespace) -> None:
    config = configuration()
    url = config.get("SUPABASE_DATABASE_URL")
    if not url:
        raise MigrationError("Falta SUPABASE_DATABASE_URL en el archivo local .env.supabase.")
    parsed_target = make_url(url)
    placeholders = (None, "[YOUR-PASSWORD]", "YOUR-PASSWORD", "[YOUR-DATABASE-PASSWORD]")
    if not args.local_test and parsed_target.password in placeholders:
        password = config.get("SUPABASE_DATABASE_PASSWORD")
        if password:
            url = parsed_target.set(password=password).render_as_string(hide_password=False)
        else:
            raise MigrationError("Falta la contraseña de PostgreSQL en .env.supabase.")
    if args.local_test and (args.switch or args.copy_storage):
        raise MigrationError("La prueba local solo ejecuta la migración de datos.")
    source_url = config.get("SIRLOD_SOURCE_DATABASE_URL")
    snapshot = {} if args.storage_only else await asyncio.to_thread(mysql_records, not source_url)
    source = await connect(source_url) if source_url and not args.storage_only else None
    storage: dict[str, str] = {}
    try:
        target = await connect(url, target=True, local_test=args.local_test)
        try:
            if not args.storage_only:
                totals = await migrate(target, source, config.get("SIRLOD_SOURCE_SCHEMA", "public"), snapshot)
                print(json.dumps(totals, ensure_ascii=True))
            await verify_target(target)
            if args.copy_storage:
                parsed = make_url(url)
                host = parsed.host or ""
                if host.startswith("db.") and host.endswith(".supabase.co"):
                    ref = host.split(".")[1]
                else:
                    ref = (parsed.username or "").partition(".")[2]
                client, storage = await asyncio.to_thread(supabase_storage.prepare_bucket, config, ref)
                bucket = supabase_storage.destination_bucket(storage)
                try:
                    await supabase_storage.check_private(target, bucket)
                    objects = await asyncio.to_thread(supabase_storage.copy_bucket, client, bucket)
                finally:
                    await asyncio.to_thread(client.close)
                if args.switch:
                    await supabase_storage.update_references(target, objects, storage)
                print(f"Storage: {len(objects)} objetos comprobados por SHA-256.")
        finally:
            await target.close()
    finally:
        if source:
            await source.close()
    if args.switch:
        configure_fastapi(url, storage)
        print("FastAPI configurado para consultar SIRLOD y el padrón en Supabase.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--switch", action="store_true", help="Activa el destino en el .env de FastAPI")
    parser.add_argument("--local-test", action="store_true", help="Admite un destino de prueba en localhost")
    parser.add_argument("--copy-storage", action="store_true", help="Copia y comprueba el bucket S3")
    parser.add_argument("--storage-only", action="store_true", help="Omite la importación de tablas")
    try:
        asyncio.run(run(parser.parse_args()))
    except (MigrationError, supabase_storage.StorageMigrationError) as exc:
        parser.exit(1, f"{exc}\n")
    except Exception as exc:
        parser.exit(1, f"Migración interrumpida ({type(exc).__name__}).\n")


if __name__ == "__main__":
    main()
