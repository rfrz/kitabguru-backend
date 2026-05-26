"""
Chat service: manage sessions and orchestrate message flow to inference.
"""
import uuid
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import Settings
from app.models.user import ChatSession, Message, MessageRole, User
from app.providers.inference_client import InferenceClient
from app.schemas.chat import (
    MessageOut,
    SendMessageRequest,
    SendMessageResponse,
    SessionDetailResponse,
    SessionListResponse,
    SessionSummary,
)


def _session_to_schema(session: ChatSession, message_count: int = 0) -> SessionSummary:
    return SessionSummary(
        id=str(session.id),
        title=session.title,
        created_at=session.created_at,
        updated_at=session.updated_at,
        message_count=message_count,
    )


def _message_to_schema(msg: Message) -> MessageOut:
    return MessageOut(
        id=str(msg.id),
        role=msg.role.value,
        content=msg.content,
        metadata=msg.meta,
        created_at=msg.created_at,
    )


class ChatService:
    def __init__(self, db: AsyncSession, settings: Settings):
        self.db = db
        self.settings = settings

    # ─── Session CRUD ─────────────────────────────────────────────────────────

    async def create_session(self, user: User, title: Optional[str] = None) -> ChatSession:
        session = ChatSession(user_id=user.id, title=title)
        self.db.add(session)
        await self.db.commit()
        await self.db.refresh(session)
        return session

    async def list_sessions(self, user: User) -> SessionListResponse:
        result = await self.db.execute(
            select(ChatSession, func.count(Message.id).label("message_count"))
            .outerjoin(Message, Message.session_id == ChatSession.id)
            .where(ChatSession.user_id == user.id)
            .group_by(ChatSession.id)
            .order_by(ChatSession.updated_at.desc())
        )
        rows = result.all()
        sessions = [_session_to_schema(row.ChatSession, row.message_count) for row in rows]
        return SessionListResponse(sessions=sessions, total=len(sessions))

    async def get_session(self, session_id: str, user: User) -> ChatSession:
        """Load session + messages, verifying ownership."""
        try:
            sid = uuid.UUID(session_id)
        except ValueError:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

        result = await self.db.execute(
            select(ChatSession)
            .options(selectinload(ChatSession.messages))
            .where(ChatSession.id == sid, ChatSession.user_id == user.id)
        )
        session = result.scalar_one_or_none()
        if not session:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
        return session

    async def get_session_detail(self, session_id: str, user: User) -> SessionDetailResponse:
        session = await self.get_session(session_id, user)
        messages = [_message_to_schema(m) for m in session.messages]
        summary = _session_to_schema(session, len(messages))
        return SessionDetailResponse(session=summary, messages=messages)

    async def rename_session(self, session_id: str, user: User, title: str) -> SessionSummary:
        session = await self.get_session(session_id, user)
        session.title = title
        await self.db.commit()
        await self.db.refresh(session)
        return _session_to_schema(session)

    async def delete_session(self, session_id: str, user: User) -> None:
        session = await self.get_session(session_id, user)
        await self.db.delete(session)
        await self.db.commit()

    # ─── Send Message ─────────────────────────────────────────────────────────

    async def send_message(
        self,
        session_id: str,
        user: User,
        data: SendMessageRequest,
        inference_client: InferenceClient,
    ) -> SendMessageResponse:
        """
        1. Save user message
        2. Build context from session history (up to CHAT_CONTEXT_WINDOW messages)
        3. Call inference engine
        4. Save AI response
        5. Return both messages
        """
        session = await self.get_session(session_id, user)

        # Save user message
        user_msg = Message(
            session_id=session.id,
            role=MessageRole.user,
            content=data.content,
            meta={"book_filter": data.book_filter} if data.book_filter else None,
        )
        self.db.add(user_msg)
        await self.db.flush()

        # Build context: last N messages (configurable window)
        window = self.settings.chat_context_window
        history_result = await self.db.execute(
            select(Message)
            .where(Message.session_id == session.id, Message.id != user_msg.id)
            .order_by(Message.created_at.desc())
            .limit(window if window > 0 else None)
        )
        recent_messages = list(reversed(history_result.scalars().all()))

        # Build the full query with context (simplified: prepend history as context)
        context_lines = [
            f"{m.role.value.upper()}: {m.content}" for m in recent_messages
        ]
        if context_lines:
            full_query = "\n".join(context_lines) + f"\nUSER: {data.content}"
        else:
            full_query = data.content

        # Call inference
        try:
            inference_response = await inference_client.chat(
                query=full_query,
                book_filter=data.book_filter,
            )
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Inference service error: {exc}",
            )

        # Save AI message with metadata from inference
        ai_msg = Message(
            session_id=session.id,
            role=MessageRole.assistant,
            content=inference_response.get("answer", ""),
            meta={
                "provider_used": inference_response.get("provider_used"),
                "sources": inference_response.get("sources"),
                "citations": inference_response.get("citations"),
                "answer_status": inference_response.get("answer_status"),
            },
        )
        self.db.add(ai_msg)

        # Auto-title session from first message if untitled
        if not session.title:
            session.title = data.content[:80]

        await self.db.commit()
        await self.db.refresh(user_msg)
        await self.db.refresh(ai_msg)

        return SendMessageResponse(
            user_message=_message_to_schema(user_msg),
            ai_message=_message_to_schema(ai_msg),
        )
