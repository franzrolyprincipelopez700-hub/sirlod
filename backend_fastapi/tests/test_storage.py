import pytest

from app.core.config import settings
from app.integrations import storage
from app.integrations.storage import _object_url, object_key


@pytest.fixture(autouse=True)
def s3_provider(monkeypatch) -> None:
    monkeypatch.setattr(settings, "storage_provider", "s3")


def test_virtual_hosted_object_url(monkeypatch) -> None:
    monkeypatch.setattr(settings, "s3_endpoint", "https://s3.us-west-004.backblazeb2.com")
    monkeypatch.setattr(settings, "s3_bucket", "mi-bucket")
    monkeypatch.setattr(settings, "s3_force_path_style", False)

    assert (
        _object_url("documentos/archivo de prueba.pdf")
        == "https://mi-bucket.s3.us-west-004.backblazeb2.com/documentos/archivo%20de%20prueba.pdf"
    )


def test_path_style_object_url(monkeypatch) -> None:
    monkeypatch.setattr(settings, "s3_endpoint", "https://s3.us-west-004.backblazeb2.com")
    monkeypatch.setattr(settings, "s3_bucket", "mi-bucket")
    monkeypatch.setattr(settings, "s3_force_path_style", True)

    assert (
        _object_url("documentos/prueba.pdf")
        == "https://s3.us-west-004.backblazeb2.com/mi-bucket/documentos/prueba.pdf"
    )


def test_object_key_from_virtual_hosted_url(monkeypatch) -> None:
    monkeypatch.setattr(settings, "s3_endpoint", "https://s3.us-east-005.backblazeb2.com")
    monkeypatch.setattr(settings, "s3_bucket", "mi-bucket")

    assert (
        object_key("https://mi-bucket.s3.us-east-005.backblazeb2.com/imagenes/losa%201.jpg")
        == "imagenes/losa 1.jpg"
    )


def test_object_key_preserves_key_and_rejects_external_url(monkeypatch) -> None:
    monkeypatch.setattr(settings, "s3_endpoint", "https://s3.us-east-005.backblazeb2.com")
    monkeypatch.setattr(settings, "s3_bucket", "mi-bucket")

    assert object_key("documentos/permiso.pdf") == "documentos/permiso.pdf"
    assert object_key("https://example.com/imagen.jpg") is None


def test_supabase_object_roundtrip_with_endpoint_path(monkeypatch) -> None:
    monkeypatch.setattr(settings, "s3_endpoint", "https://example.storage.supabase.co/storage/v1/s3")
    monkeypatch.setattr(settings, "s3_bucket", "sirlod")
    monkeypatch.setattr(settings, "s3_force_path_style", True)
    key = "imagenes/Losas del campus.jpg"
    url = _object_url(key)
    assert url.endswith("/storage/v1/s3/sirlod/imagenes/Losas%20del%20campus.jpg")
    assert object_key(url) == key
    assert object_key("https://example.storage.supabase.co/public/sirlod/extra.jpg") is None


@pytest.mark.asyncio
async def test_signed_download_url_uses_configured_expiration(monkeypatch) -> None:
    calls: list[tuple[str, dict[str, object], int]] = []

    class FakeClient:
        def generate_presigned_url(
            self, operation: str, *, Params: dict[str, object], ExpiresIn: int
        ) -> str:
            calls.append((operation, Params, ExpiresIn))
            return "https://signed.example/document"

    monkeypatch.setattr(storage, "_client", lambda: FakeClient())
    monkeypatch.setattr(settings, "s3_bucket", "mi-bucket")
    monkeypatch.setattr(settings, "s3_signed_url_expires_seconds", 900)

    result = await storage.signed_download_url("documentos/test.pdf")

    assert result == "https://signed.example/document"
    assert calls == [
        ("get_object", {"Bucket": "mi-bucket", "Key": "documentos/test.pdf"}, 900)
    ]
