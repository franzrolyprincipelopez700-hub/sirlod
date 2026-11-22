from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints


class HistoryPart(BaseModel):
    text: str = Field(min_length=1, max_length=1000)


class HistoryEntry(BaseModel):
    role: Literal["user", "model"]
    parts: list[HistoryPart] = Field(min_length=1, max_length=3)


class ChatRequest(BaseModel):
    message: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
    history: list[HistoryEntry] = Field(default_factory=list, max_length=10)
