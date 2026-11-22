from json import loads

import httpx
import pytest

from app.core.config import settings
from app.core.exceptions import AppError
from app.integrations import storage, supabase_storage


def setup(monkeypatch, handler) -> None:
    monkeypatch.setattr(settings, "storage_provider", "supabase")
    monkeypatch.setattr(settings, "supabase_storage_url", "https://project.supabase.co")
    monkeypatch.setattr(settings, "supabase_storage_bucket", "sirlod")
    monkeypatch.setattr(settings, "supabase_storage_secret_key", "test-secret")
    monkeypatch.setattr(
        supabase_storage,
        "_client",
        lambda: httpx.AsyncClient(
            base_url="https://project.supabase.co/storage/v1", headers={"apikey": "test-secret"},
            transport=httpx.MockTransport(handler),
        ),
    )


async def test_private_upload_signed_url_and_delete(monkeypatch):
    def handler(request):
        assert request.headers["apikey"] == "test-secret"
        if request.url.path == "/storage/v1/object/sign/sirlod/documentos/prueba.pdf":
            assert loads(request.content) == {"expiresIn": settings.s3_signed_url_expires_seconds}
            return httpx.Response(
                200, json={"signedURL": "/object/sign/sirlod/documentos/prueba.pdf?token=demo"}
            )
        if request.method == "DELETE":
            assert loads(request.content) == {"prefixes": ["documentos/prueba.pdf"]}
            return httpx.Response(200, json=[])
        assert request.url.path.startswith("/storage/v1/object/sirlod/documentos/")
        assert request.headers["x-upsert"] == "false"
        return httpx.Response(200, json={})

    setup(monkeypatch, handler)
    uploaded = await storage.upload_file(b"demo", "prueba.pdf", "application/pdf", "documentos")
    assert storage.object_key(uploaded.url) == uploaded.key
    signed = await storage.signed_download_url("documentos/prueba.pdf")
    assert signed == "https://project.supabase.co/storage/v1/object/sign/sirlod/documentos/prueba.pdf?token=demo"
    await storage.delete_file("documentos/prueba.pdf")


async def test_download_limits_and_rejects_external_signature(monkeypatch):
    def handler(request):
        if request.method == "GET":
            return httpx.Response(200, content=b"contenido")
        return httpx.Response(200, json={"signedURL": "https://other.example/object/sign/external"})

    setup(monkeypatch, handler)
    with pytest.raises(AppError, match="límite"):
        await storage.download_file("documentos/prueba.pdf", max_bytes=3)
    with pytest.raises(AppError, match="inválida"):
        await storage.signed_download_url("documentos/prueba.pdf")

