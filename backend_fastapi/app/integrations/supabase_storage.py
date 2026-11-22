from typing import Any
from urllib.parse import quote, urlsplit

import httpx

from app.core.config import settings
from app.core.exceptions import AppError


def api_url(project: str) -> str:
    host = urlsplit(project)
    if host.scheme != "https" or not (host.hostname or "").endswith(".supabase.co"):
        raise ValueError("La URL de Storage debe corresponder a un proyecto de Supabase")
    if host.username or host.password or host.path not in {"", "/"} or host.query or host.fragment:
        raise ValueError("Configura la URL base HTTPS del proyecto de Supabase")
    return f"{project.rstrip('/')}/storage/v1"


def object_path(bucket: str, key: str) -> str:
    return f"{quote(bucket, safe='')}/{quote(key, safe='/')}"


def _client() -> httpx.AsyncClient:
    if not settings.supabase_storage_secret_key:
        raise AppError("Falta la credencial del servidor para Supabase Storage", 500)
    return httpx.AsyncClient(
        base_url=api_url(settings.supabase_storage_url),
        headers={"apikey": settings.supabase_storage_secret_key},
        timeout=40.0,
    )


async def _request(method: str, path: str, **kwargs: Any) -> httpx.Response:
    try:
        async with _client() as client:
            response = await client.request(method, path, **kwargs)
            response.raise_for_status()
            return response
    except httpx.HTTPError as exc:
        raise AppError("Supabase Storage no pudo completar la operación", 502) from exc


def _path(key: str) -> str:
    return object_path(settings.supabase_storage_bucket, key)


async def upload(key: str, content: bytes, content_type: str) -> str:
    await _request(
        "POST",
        f"/object/{_path(key)}",
        content=content,
        headers={"Content-Type": content_type, "x-upsert": "false"},
    )
    return f"{api_url(settings.supabase_storage_url)}/object/authenticated/{_path(key)}"


async def delete(key: str) -> None:
    bucket = quote(settings.supabase_storage_bucket, safe="")
    await _request("DELETE", f"/object/{bucket}", json={"prefixes": [key]})


async def download(key: str, max_bytes: int) -> bytes:
    try:
        async with (
            _client() as client,
            client.stream("GET", f"/object/authenticated/{_path(key)}") as response,
        ):
            response.raise_for_status()
            content = bytearray()
            async for chunk in response.aiter_bytes(chunk_size=64 * 1024):
                if len(content) + len(chunk) > max_bytes:
                    raise AppError("El documento almacenado supera el límite permitido", 413)
                content.extend(chunk)
            return bytes(content)
    except httpx.HTTPError as exc:
        raise AppError("No se pudo descargar el archivo de Supabase Storage", 502) from exc


async def signed_url(key: str) -> str:
    response = await _request(
        "POST",
        f"/object/sign/{_path(key)}",
        json={"expiresIn": settings.s3_signed_url_expires_seconds},
    )
    signed = response.json().get("signedURL")
    if isinstance(signed, str) and signed.startswith("/object/sign/"):
        return api_url(settings.supabase_storage_url) + signed
    if isinstance(signed, str) and signed.startswith("/storage/v1/object/sign/"):
        return settings.supabase_storage_url.rstrip("/") + signed
    raise AppError("Supabase Storage devolvió una URL de descarga inválida", 502)
