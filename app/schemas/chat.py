from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


# ─── Session Schemas ──────────────────────────────────────────────────────────

class SessionCreateRequest(BaseModel):
    title: Optional[str] = Field(None, max_length=255)


class SessionRenameRequest(BaseModel):
    title: str = Field(min_length=1, max_length=255)


class SessionSummary(BaseModel):
    id: str
    title: Optional[str]
    created_at: datetime
    updated_at: datetime
    message_count: int = 0

    model_config = {"from_attributes": True}


class SessionListResponse(BaseModel):
    sessions: list[SessionSummary]
    total: int


# ─── Message Schemas ──────────────────────────────────────────────────────────

class MessageOut(BaseModel):
    id: str
    role: str
    content: str
    metadata: Optional[dict[str, Any]] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class SessionDetailResponse(BaseModel):
    session: SessionSummary
    messages: list[MessageOut]


# ─── Send Message ─────────────────────────────────────────────────────────────

class SendMessageRequest(BaseModel):
    content: str = Field(min_length=1, max_length=4000)
    book_filter: Optional[str] = Field(None, description="Optional book_id to filter RAG sources")


class SendMessageResponse(BaseModel):
    user_message: MessageOut
    ai_message: MessageOut
