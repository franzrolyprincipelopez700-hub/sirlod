import re
import unicodedata
from datetime import UTC, datetime
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models import ConfiguracionGlobal
from app.modules.chatbot.schemas import HistoryEntry


def _plain(value: str) -> str:
    normalized = unicodedata.normalize("NFD", value.lower())
    return "".join(char for char in normalized if unicodedata.category(char) != "Mn")


def local_topic(message: str) -> str:
    text = _plain(message)
    if re.fullmatch(r"(hola|buen(os dias|as tardes|as noches)|saludos|que tal)[!¡?.\s]*", text.strip("¡! ")):
        return "saludo"
    if re.search(r"\b(pdf|document\w*|sustento|firma\w*|especial\w*|requisito\w*)\b", text):
        return "documentos"
    if re.search(r"\b(estado\w*|aprob\w*|rechaz\w*|pendiente\w*|mis permisos|mi solicitud)\b", text):
        return "permisos"
    if re.search(r"\b(horario\w*|hora\w*|atienden|abren|cierran|disponib\w*)\b", text):
        return "horarios"
    if re.search(r"\b(reserv\w*|permiso\w*|solicitud\w*)\b", text):
        return "reservas"
    if re.search(r"\b(deporte\w*|disciplina\w*|losa\w*|cancha\w*|jugar)\b", text):
        return "losas"
    if re.search(r"\b(pausa activa|calentamiento|activar el cuerpo)\b", text):
        return "pausa"
    return "general"


def local_reply(message: str, opening: str, closing: str) -> str:
    """Responde sin proveedor externo y utiliza el horario vigente de SIRLOD."""
    topic = local_topic(message)
    if topic == "saludo":
        return "¡Hola! Soy LosaBot. ¿Buscamos un horario, una losa o los requisitos de un permiso?"
    if topic == "horarios":
        return (
            f"El horario configurado de las losas es de {opening} a {closing}. "
            "Revisa Horarios de Atención para ver bloques disponibles."
        )
    if topic == "reservas":
        return (
            "Para reservar, entra a Horarios de Atención, elige una losa y un bloque. "
            "Los permisos especiales requieren un PDF de sustento."
        )
    if topic == "documentos":
        return (
            "Un permiso especial requiere un documento PDF válido de hasta 10 MB y horarios "
            "futuros sin conflictos. Incluye tu nombre o código, la actividad, la fecha, "
            "el horario y una firma visible."
        )
    if topic == "permisos":
        return "Puedes consultar el estado y el detalle de tus solicitudes en la sección Mis Permisos."
    if topic == "losas":
        return "Consulta Losas Deportivas para ver los espacios y disciplinas activas disponibles en SIRLOD."
    if topic == "pausa":
        return (
            "Pausa activa breve: camina en tu sitio, mueve los hombros suavemente y abre y cierra las manos. "
            "Hazlo a tu ritmo. Luego toma agua y vuelve a tu actividad."
        )
    return (
        "Lo siento, solo puedo orientarte sobre reservas, requisitos, horarios y permisos "
        "de las losas deportivas de la UNHEVAL."
    )


async def chat(
    db: AsyncSession,
    message: str,
    history: list[HistoryEntry],
    *,
    use_ai: bool = False,
) -> tuple[str, str]:
    config = await db.get(ConfiguracionGlobal, 1)
    opening = config.hora_min_apertura.strftime("%H:%M") if config else "07:00"
    closing = config.hora_max_apertura.strftime("%H:%M") if config else "19:00"
    fallback = local_reply(message, opening, closing)
    if not use_ai:
        return fallback, "local"
    if settings.ai_provider == "openai" and not settings.openai_api_key:
        return fallback, "local"
    if settings.ai_provider == "gemini" and not settings.gemini_api_key:
        return fallback, "local"
    if settings.ai_provider == "deepseek" and not settings.deepseek_api_key:
        return fallback, "local"

    system_prompt = (
        "Eres LosaBot, asistente oficial de SIRLOD de la UNHEVAL. Responde solo sobre reservas, "
        "permisos, requisitos, horarios, disciplinas y uso de losas. Responde en español, de forma "
        f"breve y profesional. El horario configurado actual es {opening} a {closing}. "
        "Los permisos especiales requieren PDF y son evaluados con reglas de disponibilidad. "
        "No inventes estados ni reservas; remite a Mis Permisos cuando corresponda."
    )
    if settings.ai_provider == "openai":
        messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
        messages.extend(
            {
                "role": "assistant" if entry.role == "model" else "user",
                "content": "\n".join(part.text for part in entry.parts),
            }
            for entry in history[-10:]
        )
        messages.append({"role": "user", "content": message.strip()})
        try:
            async with httpx.AsyncClient(timeout=25.0) as client:
                response = await client.post(
                    f"{settings.openai_base_url.rstrip('/')}/chat/completions",
                    json={
                        "model": settings.openai_model,
                        "messages": messages,
                        "temperature": 0.2,
                        "max_tokens": 250,
                    },
                    headers={"Authorization": f"Bearer {settings.openai_api_key}"},
                )
                response.raise_for_status()
                body = response.json()
            reply = str(body["choices"][0]["message"]["content"] or "").strip()
            return (reply or fallback), ("openai" if reply else "local")
        except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError):
            return fallback, "local"

    if settings.ai_provider == "deepseek":
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(
            {
                "role": "assistant" if entry.role == "model" else "user",
                "content": "\n".join(part.text for part in entry.parts),
            }
            for entry in history[-10:]
        )
        messages.append({"role": "user", "content": message.strip()})
        try:
            async with httpx.AsyncClient(timeout=25.0) as client:
                response = await client.post(
                    f"{settings.deepseek_base_url.rstrip('/')}/chat/completions",
                    json={
                        "model": settings.deepseek_model,
                        "messages": messages,
                        "thinking": {"type": "disabled"},
                        "temperature": 0.2,
                        "max_tokens": 250,
                    },
                    headers={"Authorization": f"Bearer {settings.deepseek_api_key}"},
                )
                response.raise_for_status()
                body = response.json()
            reply = str(body["choices"][0]["message"]["content"] or "").strip()
            return (reply or fallback), ("deepseek" if reply else "local")
        except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError):
            return fallback, "local"

    contents: list[dict[str, Any]] = [
        {
            "role": entry.role,
            "parts": [{"text": part.text} for part in entry.parts],
        }
        for entry in history[-10:]
    ]
    contents.append({"role": "user", "parts": [{"text": message.strip()}]})
    payload = {
        "systemInstruction": {"parts": [{"text": system_prompt}]},
        "contents": contents,
        "generationConfig": {"temperature": 0.2, "maxOutputTokens": 250},
    }
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{settings.gemini_model}:generateContent"
    )
    try:
        async with httpx.AsyncClient(timeout=25.0) as client:
            response = await client.post(
                url,
                json=payload,
                headers={"x-goog-api-key": settings.gemini_api_key},
            )
            response.raise_for_status()
            body = response.json()
        parts = body.get("candidates", [{}])[0].get("content", {}).get("parts", [])
        reply = "".join(str(part.get("text", "")) for part in parts).strip()
        return (reply or fallback), ("gemini" if reply else "local")
    except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError):
        return fallback, "local"


def response_payload(reply: str, source: str, message: str) -> dict[str, str]:
    return {
        "reply": reply,
        "source": source,
        "topic": local_topic(message) if source == "local" else "general",
        "timestamp": datetime.now(UTC).isoformat(),
    }
