from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel


class IoTSessionCreateRequest(BaseModel):
    device_id: str


class IoTSessionResponse(BaseModel):
    session_id: str
    device_id: str
    started_at: datetime

    model_config = {"from_attributes": True}


class IoTVoiceResponse(BaseModel):
    """Response after processing a voice request: text + audio URL."""
    iot_message_id: str
    text_question: str
    text_answer: str
    audio_url: str


class IoTMessageOut(BaseModel):
    id: str
    role: str
    content: str
    audio_path: Optional[str] = None
    metadata: Optional[dict[str, Any]] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class IoTSessionDetailResponse(BaseModel):
    session_id: str
    device_id: str
    started_at: datetime
    ended_at: Optional[datetime] = None
    messages: list[IoTMessageOut]


class IoTSessionSummary(BaseModel):
    id: str
    device_id: str
    started_at: datetime
    ended_at: Optional[datetime] = None
    message_count: int = 0

    model_config = {"from_attributes": True}


class IoTSessionListResponse(BaseModel):
    sessions: list[IoTSessionSummary]
    total: int
    page: int
    limit: int
