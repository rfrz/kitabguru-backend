# Import all models here so Alembic can discover them via Base.metadata
from app.models.user import User, RefreshToken, ChatSession, Message, UserRole, MessageRole  # noqa: F401
from app.models.media import GeneratedMedia, MediaJob, MediaType, MediaStatus, JobStatus  # noqa: F401
from app.models.iot import IoTSession, IoTMessage, IoTMessageRole  # noqa: F401

__all__ = [
    "User",
    "RefreshToken",
    "ChatSession",
    "Message",
    "UserRole",
    "MessageRole",
    "GeneratedMedia",
    "MediaJob",
    "MediaType",
    "MediaStatus",
    "JobStatus",
    "IoTSession",
    "IoTMessage",
    "IoTMessageRole",
]
