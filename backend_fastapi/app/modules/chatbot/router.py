from fastapi import APIRouter, Request

from app.core.database import DBSession
from app.core.exceptions import AppError
from app.core.rate_limit import limiter
from app.core.security import AuthenticatedUser
from app.modules.chatbot import service
from app.modules.chatbot.schemas import ChatRequest

router = APIRouter(prefix="/chatbot", tags=["LosaBot"])


async def check_message_limit(key: str) -> None:
    if not await limiter.hit(key, 20, 60):
        raise AppError(
            "Has enviado demasiados mensajes. Espera un momento antes de continuar.",
            429,
            "CHATBOT_RATE_LIMITED",
        )


@router.post("/")
async def send_message(payload: ChatRequest, request: Request, db: DBSession) -> dict[str, str]:
    client_ip = request.client.host if request.client else "unknown"
    await check_message_limit(f"chatbot:{client_ip}")
    reply, source = await service.chat(db, payload.message, [])
    return service.response_payload(reply, source, payload.message)


@router.post("/conversacion")
async def send_chat_message(payload: ChatRequest, db: DBSession, user: AuthenticatedUser) -> dict[str, str]:
    await check_message_limit(f"chatbot:{user.tipo}:{user.id}")
    reply, source = await service.chat(db, payload.message, payload.history, user=user)
    return service.response_payload(reply, source, payload.message)
