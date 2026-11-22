import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote, unquote, urlsplit, urlunsplit
from uuid import uuid4

import boto3
from botocore.config import Config

from app.core.config import settings
from app.core.exceptions import AppError
from app.integrations import supabase_storage


@dataclass(frozen=True, slots=True)
class StoredFile:
    url: str
    key: str


async def upload_file(
    content: bytes,
    filename: str,
    content_type: str,
    key_prefix: str | None = None,
) -> StoredFile:
    """Sube un archivo a un almacenamiento compatible con S3 sin bloquear el event loop."""
    suffix = Path(filename).suffix.lower()
    prefix = (key_prefix or settings.s3_key_prefix).strip("/")
    key = f"{prefix + '/' if prefix else ''}{uuid4()}{suffix}"
    if settings.storage_provider == "supabase":
        url = await supabase_storage.upload(key, content, content_type or "application/octet-stream")
        return StoredFile(url=url, key=key)
    required = (
        settings.s3_endpoint,
        settings.aws_access_key_id,
        settings.aws_secret_access_key,
        settings.s3_bucket,
    )
    if not all(required):
        raise AppError(
            "S3 no configurado. Define S3_ENDPOINT, AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY y S3_BUCKET",
            500,
        )

    def put_object() -> None:
        client = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint,
            region_name=settings.s3_region,
            aws_access_key_id=settings.aws_access_key_id,
            aws_secret_access_key=settings.aws_secret_access_key,
            config=Config(
                signature_version="s3v4",
                s3={"addressing_style": "path" if settings.s3_force_path_style else "virtual"},
            ),
        )
        client.put_object(
            Bucket=settings.s3_bucket,
            Key=key,
            Body=content,
            ContentType=content_type or "application/octet-stream",
        )

    await asyncio.to_thread(put_object)
    return StoredFile(url=_object_url(key), key=key)


def _client() -> Any:
    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint,
        region_name=settings.s3_region,
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
        config=Config(
            signature_version="s3v4",
            s3={"addressing_style": "path" if settings.s3_force_path_style else "virtual"},
        ),
    )


async def delete_file(key: str) -> None:
    """Elimina un objeto que quedó huérfano después de un rollback."""
    if settings.storage_provider == "supabase":
        await supabase_storage.delete(key)
        return
    await asyncio.to_thread(lambda: _client().delete_object(Bucket=settings.s3_bucket, Key=key))


async def download_file(key: str, max_bytes: int = 10 * 1024 * 1024) -> bytes:
    """Descarga un objeto privado y limita su tamaño antes de enviarlo al analizador."""
    if settings.storage_provider == "supabase":
        return await supabase_storage.download(key, max_bytes)

    def get_object() -> bytes:
        response = _client().get_object(Bucket=settings.s3_bucket, Key=key)
        content = response["Body"].read(max_bytes + 1)
        if len(content) > max_bytes:
            raise AppError("El documento almacenado supera el límite permitido", 413)
        return bytes(content)

    return await asyncio.to_thread(get_object)


async def signed_download_url(key: str) -> str:
    """Genera una URL temporal para descargar un documento privado."""
    if settings.storage_provider == "supabase":
        return await supabase_storage.signed_url(key)
    return await asyncio.to_thread(
        lambda: _client().generate_presigned_url(
            "get_object",
            Params={"Bucket": settings.s3_bucket, "Key": key},
            ExpiresIn=settings.s3_signed_url_expires_seconds,
        )
    )


def object_key(stored_value: str) -> str | None:
    """Obtiene la clave S3 desde una clave simple o una URL generada por este bucket."""
    if settings.storage_provider == "supabase":
        endpoint = supabase_storage.api_url(settings.supabase_storage_url) + "/object/authenticated"
        return bucket_object_key(stored_value, endpoint, settings.supabase_storage_bucket)
    return bucket_object_key(stored_value, settings.s3_endpoint, settings.s3_bucket)


def bucket_object_key(stored_value: str, endpoint: str, bucket: str) -> str | None:
    if not stored_value:
        return None
    if not stored_value.lower().startswith(("http://", "https://")):
        return stored_value.lstrip("/")

    stored_parts = urlsplit(stored_value)
    endpoint_parts = urlsplit(endpoint)
    path = unquote(stored_parts.path)
    endpoint_path = unquote(endpoint_parts.path).rstrip("/")
    if endpoint_path and not path.startswith(f"{endpoint_path}/"):
        return None
    path = path.removeprefix(endpoint_path).lstrip("/")
    virtual_host = f"{bucket}.{endpoint_parts.hostname}"

    if stored_parts.hostname == virtual_host:
        return path
    if stored_parts.hostname == endpoint_parts.hostname:
        bucket_prefix = f"{bucket}/"
        return path.removeprefix(bucket_prefix) if path.startswith(bucket_prefix) else None
    return None


async def signed_stored_object_url(stored_value: str) -> str:
    """Firma objetos del bucket y conserva sin cambios las URLs externas heredadas."""
    key = object_key(stored_value)
    return await signed_download_url(key) if key else stored_value


def _object_url(key: str) -> str:
    endpoint = settings.s3_endpoint.rstrip("/")
    encoded_key = quote(key, safe="/")
    if settings.s3_force_path_style:
        return f"{endpoint}/{settings.s3_bucket}/{encoded_key}"
    parts = urlsplit(endpoint)
    return urlunsplit(
        (parts.scheme, f"{settings.s3_bucket}.{parts.netloc}", f"{parts.path}/{encoded_key}", "", "")
    )
