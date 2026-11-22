from contextlib import closing
from hashlib import sha256
from io import BytesIO
from tempfile import TemporaryFile
from typing import Any
from urllib.parse import quote, urlsplit

import asyncpg
import boto3
import httpx
from botocore.config import Config
from botocore.exceptions import ClientError
from botocore.response import StreamingBody

from app.core.config import settings
from app.integrations.storage import _client, bucket_object_key
from app.integrations.supabase_storage import api_url, object_path

MISSING = {"404", "NoSuchBucket", "NoSuchKey", "NotFound"}


class StorageMigrationError(Exception):
    pass


def missing(response: httpx.Response) -> bool:
    if response.status_code == 404:
        return True
    if response.status_code != 400:
        return False
    try:
        return str(response.json().get("statusCode")) == "404"
    except (AttributeError, ValueError):
        return False


class RestBucket:
    def __init__(self, project: str, secret: str, bucket: str) -> None:
        self.client = httpx.Client(base_url=api_url(project), headers={"apikey": secret}, timeout=90)
        try:
            response = self.client.get(f"/bucket/{quote(bucket, safe='')}")
            if missing(response):
                response = self.client.post("/bucket", json={"id": bucket, "name": bucket, "public": False})
            response.raise_for_status()
        except Exception:
            self.close()
            raise

    def get_object(self, *, Bucket: str, Key: str) -> dict[str, Any]:
        with self.client.stream("GET", f"/object/authenticated/{object_path(Bucket, Key)}") as response:
            if response.status_code in {400, 404}:
                response.read()
                if missing(response):
                    raise ClientError({"Error": {"Code": "NoSuchKey"}}, "GetObject")
            response.raise_for_status()
            data = b"".join(response.iter_raw())
        return {"Body": StreamingBody(BytesIO(data), len(data))}

    def put_object(self, *, Bucket: str, Key: str, Body: Any, IfNoneMatch: str, **metadata: Any) -> None:
        if IfNoneMatch != "*":
            raise StorageMigrationError("La copia requiere proteger los objetos existentes.")
        headers = {"x-upsert": "false"}
        for key, header in (
            ("ContentType", "content-type"),
            ("CacheControl", "cache-control"),
            ("ContentDisposition", "content-disposition"),
            ("ContentEncoding", "content-encoding"),
        ):
            if metadata.get(key):
                headers[header] = metadata[key]
        response = self.client.post(
            f"/object/{object_path(Bucket, Key)}", content=Body.read(), headers=headers
        )
        response.raise_for_status()

    def close(self) -> None:
        self.client.close()


def destination_bucket(target: dict[str, str]) -> str:
    if target["STORAGE_PROVIDER"] == "supabase":
        return target["SUPABASE_STORAGE_BUCKET"]
    return target["S3_BUCKET"]


def prepare_bucket(config: dict[str, str], project_ref: str) -> tuple[Any, dict[str, str]]:
    bucket = config.get("SUPABASE_STORAGE_BUCKET", "sirlod")
    if secret_key := config.get("SUPABASE_STORAGE_SECRET_KEY"):
        project = config.get("SUPABASE_STORAGE_URL", "")
        if urlsplit(project).hostname != f"{project_ref}.supabase.co":
            raise StorageMigrationError("Storage y PostgreSQL deben corresponder al mismo proyecto.")
        return RestBucket(project, secret_key, bucket), {
            "STORAGE_PROVIDER": "supabase",
            "SUPABASE_STORAGE_URL": project,
            "SUPABASE_STORAGE_SECRET_KEY": secret_key,
            "SUPABASE_STORAGE_BUCKET": bucket,
        }
    endpoint = config.get("SUPABASE_STORAGE_ENDPOINT", "").rstrip("/")
    region = config.get("SUPABASE_STORAGE_REGION", "")
    access = config.get("SUPABASE_STORAGE_ACCESS_KEY_ID", "")
    secret = config.get("SUPABASE_STORAGE_SECRET_ACCESS_KEY", "")
    endpoint_url = urlsplit(endpoint)
    if not all((endpoint, region, access, secret, bucket)):
        raise StorageMigrationError("Faltan los parámetros S3 de Supabase Storage.")
    if endpoint_url.scheme != "https" or not (endpoint_url.hostname or "").endswith(".supabase.co"):
        raise StorageMigrationError("El endpoint S3 debe corresponder al proyecto Supabase.")
    if (endpoint_url.hostname or "").split(".")[0] != project_ref:
        raise StorageMigrationError("Storage y PostgreSQL deben corresponder al mismo proyecto.")
    destination = boto3.client(
        "s3",
        endpoint_url=endpoint,
        region_name=region,
        aws_access_key_id=access,
        aws_secret_access_key=secret,
        config=Config(
            signature_version="s3v4",
            s3={"addressing_style": "path"},
            request_checksum_calculation="when_required",
            response_checksum_validation="when_required",
        ),
    )
    try:
        destination.head_bucket(Bucket=bucket)
    except ClientError as exc:
        if str(exc.response["Error"]["Code"]) not in MISSING:
            raise
        destination.create_bucket(Bucket=bucket)
    return destination, {
        "STORAGE_PROVIDER": "s3",
        "S3_ENDPOINT": endpoint,
        "S3_REGION": region,
        "S3_BUCKET": bucket,
        "AWS_ACCESS_KEY_ID": access,
        "AWS_SECRET_ACCESS_KEY": secret,
        "S3_FORCE_PATH_STYLE": "true",
    }


async def check_private(db: asyncpg.Connection, bucket: str) -> None:
    if await db.fetchval("SELECT public FROM storage.buckets WHERE id = $1", bucket) is not False:
        raise StorageMigrationError("El bucket de destino debe existir y ser privado.")


def copy_bucket(destination: Any, bucket: str) -> set[str]:
    source = _client()
    transferred = set()
    for page in source.get_paginator("list_objects_v2").paginate(Bucket=settings.s3_bucket):
        for item in page.get("Contents", []):
            key = item["Key"]
            copy_object(source, destination, settings.s3_bucket, bucket, key)
            transferred.add(key)
    return transferred


def object_digest(client: Any, bucket: str, key: str) -> str | None:
    try:
        response = client.get_object(Bucket=bucket, Key=key)
    except ClientError as exc:
        if str(exc.response["Error"]["Code"]) in MISSING:
            return None
        raise
    with closing(response["Body"]) as body:
        digest = sha256()
        for chunk in body.iter_chunks(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def copy_object(source: Any, destination: Any, source_bucket: str, bucket: str, key: str) -> None:
    response = source.get_object(Bucket=source_bucket, Key=key)
    with closing(response["Body"]) as body, TemporaryFile() as staged:
        digest = sha256()
        for chunk in body.iter_chunks(1024 * 1024):
            digest.update(chunk)
            staged.write(chunk)
        expected = digest.hexdigest()
        actual = object_digest(destination, bucket, key)
        if actual is not None and actual != expected:
            raise StorageMigrationError("Un objeto existente en el destino tiene contenido distinto.")
        if actual is None:
            staged.seek(0)
            headers = {
                field: response[field]
                for field in (
                    "ContentType",
                    "CacheControl",
                    "ContentDisposition",
                    "ContentEncoding",
                    "Metadata",
                )
                if field in response
            }
            destination.put_object(Bucket=bucket, Key=key, Body=staged, IfNoneMatch="*", **headers)
            if object_digest(destination, bucket, key) != expected:
                raise StorageMigrationError("Falló la comprobación SHA-256 de un objeto transferido.")


async def update_references(db: asyncpg.Connection, objects: set[str], target: dict[str, str]) -> None:
    bucket = destination_bucket(target)
    endpoint = (
        api_url(target["SUPABASE_STORAGE_URL"]) + "/object/authenticated"
        if target["STORAGE_PROVIDER"] == "supabase"
        else target["S3_ENDPOINT"]
    )
    async with db.transaction():
        await check_private(db, bucket)
        for table, column in (("archivos", "id_arch"), ("imagenes", "id_img")):
            rows = await db.fetch(f"SELECT {column}, url FROM sirlod.{table}")
            for row in rows:
                key = bucket_object_key(row["url"], settings.s3_endpoint, settings.s3_bucket)
                if key is None:
                    continue
                if key not in objects:
                    raise StorageMigrationError(f"Hay un objeto referenciado en {table} que falta en origen.")
                new_url = f"{endpoint}/{object_path(bucket, key)}"
                await db.execute(
                    f"UPDATE sirlod.{table} SET url = $1 WHERE {column} = $2", new_url, row[column]
                )
        report_keys = {
            row["s3_key"] for row in await db.fetch("SELECT s3_key FROM sirlod.reportes_generados")
        }
        if not report_keys <= objects:
            raise StorageMigrationError("Hay reportes cuyo archivo falta en el origen.")
