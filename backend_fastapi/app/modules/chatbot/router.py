from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app.core.database import DBSession
from app.core.exceptions import AppError
from app.core.rate_limit import limiter
from app.core.security import CurrentUser, require_roles
from app.modules.chatbot import service
from app.modules.chatbot.schemas import ChatRequest

router = APIRouter(prefix="/chatbot", tags=["LosaBot"])
Admin = Annotated[CurrentUser, Depends(require_roles("Administrador"))]


@router.post("/")
async def send_message(payload: ChatRequest, request: Request, db: DBSession) -> dict[str, str]:
    client_ip = request.client.host if request.client else "unknown"
    if not await limiter.hit(f"chatbot:{client_ip}", 20, 60):
        raise AppError(
            "Has enviado demasiados mensajes. Espera un momento antes de continuar.",
            429,
            "CHATBOT_RATE_LIMITED",
        )
    message = payload.message.strip()
    reply, source = await service.chat(db, message, [])
    return service.response_payload(reply, source, message)


@router.post("/consulta-ia")
async def send_ai_message(payload: ChatRequest, db: DBSession, admin: Admin) -> dict[str, str]:
    if not await limiter.hit(f"chatbot-ai:{admin.id}", 4, 120):
        raise AppError(
            "Espera un momento antes de volver a consultar con IA.", 429, "CHATBOT_AI_RATE_LIMITED"
        )
    message = payload.message.strip()
    reply, source = await service.chat(db, message, payload.history[-4:], use_ai=True)
    return service.response_payload(reply, source, message)
