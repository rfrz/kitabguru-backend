import enum
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class IoTMessageRole(str, enum.Enum):
    user = "user"
    assistant = "assistant"


class IoTSession(Base):
    """Anonymous IoT device conversation session."""
    __tablename__ = "iot_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    device_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    ended_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    messages: Mapped[list["IoTMessage"]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="IoTMessage.created_at",
    )


class IoTMessage(Base):
    """Single voice exchange in an IoT session (STT → inference → TTS)."""
    __tablename__ = "iot_messages"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    iot_session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("iot_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[IoTMessageRole] = mapped_column(
        Enum(IoTMessageRole, name="iotmessagerole"), nullable=False
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    audio_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    # Stores: provider_used, stt_confidence, etc.
    meta: Mapped[Optional[dict]] = mapped_column(
        "metadata",
        type_=__import__("sqlalchemy").dialects.postgresql.JSONB,
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )

    # Relationships
    session: Mapped["IoTSession"] = relationship(back_populates="messages")
