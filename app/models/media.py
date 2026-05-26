import enum
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class MediaType(str, enum.Enum):
    image = "image"
    video = "video"


class MediaStatus(str, enum.Enum):
    processing = "processing"
    completed = "completed"
    failed = "failed"


class JobStatus(str, enum.Enum):
    queued = "queued"
    processing = "processing"
    completed = "completed"
    failed = "failed"


class GeneratedMedia(Base):
    __tablename__ = "generated_media"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("chat_sessions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    media_type: Mapped[MediaType] = mapped_column(
        Enum(MediaType, name="mediatype"), nullable=False
    )
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    file_size_bytes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    prompt_used: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[MediaStatus] = mapped_column(
        Enum(MediaStatus, name="mediastatus"),
        nullable=False,
        default=MediaStatus.processing,
    )
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    user: Mapped["app.models.user.User"] = relationship(back_populates="generated_media")  # type: ignore[name-defined]
    session: Mapped[Optional["app.models.user.ChatSession"]] = relationship(back_populates="generated_media")  # type: ignore[name-defined]
    job: Mapped[Optional["MediaJob"]] = relationship(
        back_populates="media", uselist=False, cascade="all, delete-orphan"
    )


class MediaJob(Base):
    __tablename__ = "media_jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    media_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("generated_media.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    status: Mapped[JobStatus] = mapped_column(
        Enum(JobStatus, name="jobstatus"),
        nullable=False,
        default=JobStatus.queued,
    )
    progress_pct: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    error_detail: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationships
    media: Mapped["GeneratedMedia"] = relationship(back_populates="job")
