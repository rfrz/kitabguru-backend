from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class ImageGenerateRequest(BaseModel):
    session_id: str
    message_id: Optional[str] = None


class ImageGenerateResponse(BaseModel):
    media_id: str
    prompt_used: Optional[str]
    image_url: str
    status: str


class VideoGenerateRequest(BaseModel):
    session_id: str
    message_id: Optional[str] = None


class VideoGenerateResponse(BaseModel):
    job_id: str
    media_id: str
    status: str = "queued"


class JobStatusResponse(BaseModel):
    job_id: str
    status: str
    progress_pct: Optional[int] = None
    video_url: Optional[str] = None
    error: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class MediaOut(BaseModel):
    id: str
    media_type: str
    file_path: str
    prompt_used: Optional[str]
    status: str
    created_at: datetime
    completed_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class MediaListResponse(BaseModel):
    media: list[MediaOut]
    total: int
