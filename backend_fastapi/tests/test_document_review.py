import pytest

from app.core.config import settings
from app.modules.permisos.document_review import DocumentAssessment, rejection_reasons


def assessment(**overrides: object) -> DocumentAssessment:
    values: dict[str, object] = {
        "readable": True,
        "mentions_unheval": True,
        "student_identity_matches": True,
        "allowed_category": "campeonato_estudiantil",
        "activity_organized_by_students": True,
        "has_visible_signature": True,
        "schedule_matches": True,
        "confidence": 0.95,
        "summary": "Campeonato estudiantil UNHEVAL firmado y con horario coincidente.",
    }
    values.update(overrides)
    return DocumentAssessment.model_validate(values)


def test_accepts_signed_student_championship() -> None:
    assert rejection_reasons(assessment()) == []


def test_anniversary_does_not_require_student_organization() -> None:
    result = assessment(
        allowed_category="aniversario_facultad",
        activity_organized_by_students=False,
    )
    assert rejection_reasons(result) == []


def test_rejects_unsigned_or_non_allowed_activity() -> None:
    reasons = rejection_reasons(
        assessment(
            allowed_category="no_permitida",
            has_visible_signature=False,
        )
    )
    assert "La actividad no pertenece a una categoría especial permitida" in reasons
    assert "El documento no contiene una firma visible" in reasons


def test_rejects_identity_mismatch_and_low_confidence(monkeypatch) -> None:
    monkeypatch.setattr(settings, "document_ai_min_confidence", 0.85)
    reasons = rejection_reasons(
        assessment(
            student_identity_matches=False,
            confidence=0.60,
        )
    )
    assert "La identidad o código del estudiante no coincide con el solicitante" in reasons
    assert "La confianza del análisis documental es insuficiente" in reasons


@pytest.mark.asyncio
async def test_analyze_document_uses_openai(monkeypatch) -> None:
    import json
    from typing import Any

    from app.modules.permisos.document_review import analyze_document

    captured: dict[str, Any] = {}

    class FakeResponse:
        status_code = 200

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, Any]:
            return {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "readable": True,
                                    "mentions_unheval": True,
                                    "student_identity_matches": True,
                                    "allowed_category": "campeonato_estudiantil",
                                    "activity_organized_by_students": True,
                                    "has_visible_signature": True,
                                    "schedule_matches": True,
                                    "confidence": 0.95,
                                    "summary": "Documento validado con ChatGPT OpenAI.",
                                }
                            )
                        }
                    }
                ]
            }

    class FakeClient:
        def __init__(self, **kwargs: object) -> None:
            pass

        async def __aenter__(self) -> "FakeClient":
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        async def post(self, url: str, **kwargs: object) -> FakeResponse:
            captured["url"] = url
            captured["json"] = kwargs["json"]
            captured["headers"] = kwargs.get("headers")
            return FakeResponse()

    monkeypatch.setattr(settings, "document_ai_provider", "openai")
    monkeypatch.setattr(settings, "openai_api_key", "sk-openai-doc-key")
    monkeypatch.setattr(settings, "document_ai_model", "gpt-4o-mini")
    monkeypatch.setattr("app.modules.permisos.document_review.httpx.AsyncClient", FakeClient)

    result = await analyze_document(
        b"%PDF-1.4 test dummy pdf content",
        student={"codigo": "2020123456", "nombre_completo": "Juan Perez"},
        requested_schedule="2026-10-15 10:00 - 12:00",
    )

    assert result.readable is True
    assert result.allowed_category == "campeonato_estudiantil"
    assert result.summary == "Documento validado con ChatGPT OpenAI."
    assert captured["url"] == "https://api.openai.com/v1/chat/completions"
    assert captured["json"]["model"] == "gpt-4o-mini"
    assert captured["headers"] == {"Authorization": "Bearer sk-openai-doc-key"}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("outcome", "expected", "notices"),
    [
        ("unavailable", "Pendiente", 0),
        ("uncertain", "Pendiente", 0),
        ("signed", "Aceptado", 1),
        ("unsigned", "Rechazado", 1),
    ],
)
async def test_automatic_review_keeps_uncertain_requests_pending(
    monkeypatch: pytest.MonkeyPatch, outcome: str, expected: str, notices: int
) -> None:
    from datetime import time, timedelta
    from unittest.mock import AsyncMock

    from sqlalchemy import func, select
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.core.clock import campus_now
    from app.models import (
        Archivo,
        Base,
        DetallePermiso,
        Disciplina,
        Losa,
        Notificacion,
        Permiso,
        Trabajador,
        User,
    )
    from app.modules.permisos import service

    pdf = b"%PDF-1.4 fixture"
    student = {"codigo": "QA92713", "rol": "Alumno", "nombre_completo": "Equipo QA"}
    date = campus_now().date() + timedelta(days=1)
    reviewer = AsyncMock()
    if outcome == "unavailable":
        reviewer.side_effect = RuntimeError("Provider offline")
    else:
        reviewer.return_value = assessment(
            confidence=0.6 if outcome == "uncertain" else 0.98,
            has_visible_signature=outcome != "unsigned",
        )
    monkeypatch.setattr(service, "analyze_document", reviewer)
    monkeypatch.setattr(service, "get_usuario", AsyncMock(return_value=student))
    monkeypatch.setattr(service, "download_file", AsyncMock(return_value=pdf))
    monkeypatch.setattr(service, "object_key", lambda name: name)
    monkeypatch.setattr(settings, "document_ai_min_confidence", 0.85)

    engine = create_async_engine("sqlite+aiosqlite://")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with async_sessionmaker(engine, expire_on_commit=False)() as db:
            db.add_all([
                Trabajador(
                    id_t=1, dni="99999123", nombres="QA", apellido_p="Prueba", apellido_m="Control",
                    rol="Administrador", email="qa@example.com", password="unused",
                ),
                User(id_u=1, codigo=student["codigo"], password="unused", rol="Alumno"),
                Disciplina(id_d=1, nombre="Deporte de prueba"),
                Losa(id_l=1, numero_l="99", nombre="Losa QA", ubicacion="QA", id_d=1),
                Archivo(
                    id_arch=1, nombre_original="sustento-qa.pdf", nombre_unico="documentos/sustento-qa.pdf",
                    mimetype="application/pdf", url="documentos/sustento-qa.pdf",
                ),
                Permiso(id_p=1, tipo="Especial", id_u=1, id_arch=1, duracion_t=1),
                Permiso(id_p=2, tipo="Especial", id_u=1, duracion_t=1),
                DetallePermiso(
                    id_d=1, id_p=1, id_l=1, fecha=date, hora_inicio=time(10), hora_fin=time(11), duracion=1,
                ),
            ])
            await db.commit()

            result = await service.automatic_review(db, 1, permission_id=1)

            reviewer.assert_awaited_once()
            first = await db.get(Permiso, 1)
            second = await db.get(Permiso, 2)
            assert first is not None and first.estado == expected
            assert second is not None and second.estado == "Pendiente"
            assert (first.id_t_decision, first.fecha_decision is not None) == (
                (None, False) if expected == "Pendiente" else (1, True)
            )
            assert result["resultados"][0]["decision"] == expected
            assert result["pendientes"] == int(expected == "Pendiente")
            assert await db.scalar(select(func.count()).select_from(Notificacion)) == notices
    finally:
        await engine.dispose()
