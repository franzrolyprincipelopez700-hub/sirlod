from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.config import settings
from app.core.security import CurrentUser
from app.modules.chatbot import service
from app.modules.chatbot.service import local_reply


def test_local_chatbot_reports_configured_hours() -> None:
    reply = local_reply("¿Cuáles son los horarios?", "07:00", "19:00")
    assert "07:00" in reply
    assert "19:00" in reply


def test_local_chatbot_rejects_unrelated_topics() -> None:
    reply = local_reply("Explícame cálculo diferencial", "07:00", "19:00")
    assert "solo puedo orientarte" in reply


def test_special_permission_and_status_are_distinguished() -> None:
    assert "10 MB" in local_reply("¿Qué PDF requiere un permiso especial?", "07:00", "19:00")
    assert "Mis Permisos" in local_reply("¿Cómo veo el estado de mis permisos?", "07:00", "19:00")


@pytest.mark.asyncio
async def test_standard_chat_keeps_provider_key_out_of_local_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    database = AsyncMock()
    database.get.return_value = None
    api_client = MagicMock()
    monkeypatch.setattr(settings, "deepseek_api_key", "test-key")
    monkeypatch.setattr(service.httpx, "AsyncClient", api_client)

    user = CurrentUser(id=543, rol="Alumno", tipo="usuario", nombre="Estudiante")
    reply, source = await service.chat(database, "¿Cuáles son los horarios?", [], user=user)

    assert source == "local"
    assert "07:00" in reply
    api_client.assert_not_called()


@pytest.mark.asyncio
async def test_chatbot_uses_selected_deepseek_provider(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    class FakeDatabase:
        async def get(self, model: object, item_id: int) -> None:
            return None

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, Any]:
            return {"choices": [{"message": {"content": "Respuesta de DeepSeek"}}]}

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
            return FakeResponse()

    monkeypatch.setattr(settings, "ai_provider", "deepseek")
    monkeypatch.setattr(settings, "deepseek_api_key", "test-key")
    monkeypatch.setattr(settings, "deepseek_model", "deepseek-flash")
    monkeypatch.setattr(service.httpx, "AsyncClient", FakeClient)

    monkeypatch.setattr(service.limiter, "hit", AsyncMock(return_value=True))
    monkeypatch.setattr(service, "booking_context", AsyncMock(return_value={"losa": "Losa de prueba"}))
    user = CurrentUser(id=544, rol="Alumno", tipo="usuario", nombre="Estudiante")
    reply, source = await service.chat(
        FakeDatabase(), "¿Qué me recomiendas para mañana? dato@example.com", [], user=user  # type: ignore[arg-type]
    )

    assert reply == "Respuesta de DeepSeek"
    assert source == "deepseek"
    assert captured["url"] == "https://api.deepseek.com/chat/completions"
    assert captured["json"]["model"] == "deepseek-flash"
    assert "Losa de prueba" in captured["json"]["messages"][0]["content"]
    assert "dato@example.com" not in captured["json"]["messages"][-1]["content"]


@pytest.mark.asyncio
async def test_chatbot_uses_selected_openai_provider(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    class FakeDatabase:
        async def get(self, model: object, item_id: int) -> None:
            return None

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, Any]:
            return {"choices": [{"message": {"content": "Respuesta de ChatGPT OpenAI"}}]}

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

    monkeypatch.setattr(settings, "ai_provider", "openai")
    monkeypatch.setattr(settings, "openai_api_key", "sk-test-key")
    monkeypatch.setattr(settings, "openai_model", "gpt-4o-mini")
    monkeypatch.setattr(service.httpx, "AsyncClient", FakeClient)

    monkeypatch.setattr(service.limiter, "hit", AsyncMock(return_value=True))
    monkeypatch.setattr(service, "booking_context", AsyncMock(return_value={"losa": "Losa de prueba"}))
    user = CurrentUser(id=544, rol="Alumno", tipo="usuario", nombre="Estudiante")
    reply, source = await service.chat(
        FakeDatabase(), "¿Qué me recomiendas para mañana? dato@example.com", [], user=user  # type: ignore[arg-type]
    )

    assert reply == "Respuesta de ChatGPT OpenAI"
    assert source == "openai"
    assert captured["url"] == "https://api.openai.com/v1/chat/completions"
    assert captured["json"]["model"] == "gpt-4o-mini"
    assert captured["headers"] == {"Authorization": "Bearer sk-test-key"}



@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("¿Qué deportes puedo jugar?", False),
        ("¿Qué PDF requiere el permiso especial?", False),
        ("¿Qué losa me recomiendas para mañana?", True),
        ("¿Qué canchas están libres el 2026-12-07?", True),
        ("¿Quién reservó la cancha mañana?", False),
    ],
)
def test_auto_route_distinguishes_faqs_from_context(question: str, expected: bool) -> None:
    assert service.needs_context(service._plain(question), service.local_topic(question)) is expected


@pytest.mark.asyncio
async def test_provider_failure_keeps_chat_local(monkeypatch: pytest.MonkeyPatch) -> None:
    import httpx

    db = AsyncMock()
    db.get.return_value = None
    user = CurrentUser(id=600, rol="Alumno", tipo="usuario", nombre="Prueba")
    monkeypatch.setattr(settings, "deepseek_api_key", "key")
    monkeypatch.setattr(settings, "ai_provider", "deepseek")
    monkeypatch.setattr(service.limiter, "hit", AsyncMock(return_value=True))
    monkeypatch.setattr(service, "booking_context", AsyncMock(return_value={}))
    monkeypatch.setattr(service, "provider_chat", AsyncMock(side_effect=httpx.ReadTimeout("timeout")))

    reply, source = await service.chat(db, "¿Alguna recomendación para mañana?", [], user=user)

    assert source == "local"
    assert reply


@pytest.mark.asyncio
async def test_chat_context_excludes_blocked_and_occupied_slots(monkeypatch: pytest.MonkeyPatch) -> None:
    from datetime import datetime, time
    from decimal import Decimal

    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.core.clock import LIMA
    from app.models import (
        Base,
        ConfiguracionGlobal,
        DetallePermiso,
        DiaBloqueado,
        Disciplina,
        Losa,
        Permiso,
        User,
    )
    from app.modules.chatbot import context

    now = datetime(2026, 11, 22, 8, 30, tzinfo=LIMA)
    monkeypatch.setattr(context, "campus_now", lambda: now)
    today, tomorrow = context.requested_days("hoy y manana", now.date())
    monkeypatch.setattr(service, "provider_chat", AsyncMock())
    config = ConfiguracionGlobal(
        id=1,
        hora_min_solicitud=time(7),
        hora_max_solicitud=time(19),
        hora_min_apertura=time(8),
        hora_max_apertura=time(12),
        restriccion_hoy=time(9),
        max_horas_semana=Decimal(5),
    )
    user = User(id_u=1, codigo="QA-PRIVADO-1", password="hash", rol="Alumno")
    other = User(id_u=2, codigo="QA-PRIVADO-2", password="hash", rol="Alumno")
    engine = create_async_engine("sqlite+aiosqlite://")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with async_sessionmaker(engine, expire_on_commit=False)() as db:
            db.add_all([
                config, user, other, Disciplina(id_d=1, nombre="Futsal"),
                Losa(id_l=1, numero_l="01", nombre="Cancha azul", id_d=1, ubicacion="Campus"),
                Losa(
                    id_l=2, numero_l="02", nombre="Losa cerrada", id_d=1, ubicacion="Campus",
                    estado="Inactiva",
                ),
                DiaBloqueado(fecha=today, motivo="Razón administrativa privada"),
                Permiso(id_p=1, id_u=1, tipo="Normal", estado="Aceptado", duracion_t=1),
                Permiso(id_p=2, id_u=2, tipo="Normal", estado="Pendiente", duracion_t=1),
                DetallePermiso(
                    id_p=1, id_l=1, fecha=tomorrow, hora_inicio=time(9), hora_fin=time(10), duracion=1,
                ),
                DetallePermiso(
                    id_p=2, id_l=1, fecha=tomorrow, hora_inicio=time(10), hora_fin=time(11), duracion=1,
                ),
            ])
            await db.commit()

            result = await context.booking_context(db, config, "hoy y manana")
            assert result["fechas_bloqueadas"] == [today.isoformat()]
            assert result["losas"] == [{
                "nombre": "Cancha azul",
                "disciplina": "Futsal",
                "inicios_libres": {tomorrow.isoformat(): ["08:00", "11:00"]},
            }]
            assert "QA-PRIVADO" not in str(result) and "Razón administrativa" not in str(result)

            actor = CurrentUser(id=1, rol="Alumno", tipo="usuario", nombre="Prueba")
            summary, source = await service.chat(db, "¿Cómo están mis permisos?", [], user=actor)
            assert source == "local"
            assert "1 aceptada" in summary and "pendientes" not in summary
            service.provider_chat.assert_not_called()
    finally:
        await engine.dispose()
