"""
Chat routes:
  POST   /chat/sessions               — Create new session
  GET    /chat/sessions               — List all sessions
  GET    /chat/sessions/{id}          — Get session + messages
  DELETE /chat/sessions/{id}          — Delete session
  PATCH  /chat/sessions/{id}          — Rename session
  POST   /chat/sessions/{id}/messages — Send message + get AI response
"""
from fastapi import APIRouter, Request, status

from app.core.dependencies import DB, AppSettings, CurrentUser
from app.providers.inference_client import InferenceClient
from app.schemas.chat import (
    SendMessageRequest,
    SendMessageResponse,
    SessionCreateRequest,
    SessionDetailResponse,
    SessionListResponse,
    SessionRenameRequest,
    SessionSummary,
)
from app.services.chat_service import ChatService

router = APIRouter()


@router.post(
    "/sessions",
    response_model=SessionSummary,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new chat session",
)
async def create_session(
    body: SessionCreateRequest,
    current_user: CurrentUser,
    db: DB,
    settings: AppSettings,
):
    service = ChatService(db, settings)
    session = await service.create_session(current_user, title=body.title)
    return SessionSummary(
        id=str(session.id),
        title=session.title,
        created_at=session.created_at,
        updated_at=session.updated_at,
        message_count=0,
    )


@router.get(
    "/sessions",
    response_model=SessionListResponse,
    summary="List all chat sessions for current user",
)
async def list_sessions(
    current_user: CurrentUser,
    db: DB,
    settings: AppSettings,
):
    service = ChatService(db, settings)
    return await service.list_sessions(current_user)


@router.get(
    "/sessions/{session_id}",
    response_model=SessionDetailResponse,
    summary="Get session details + all messages",
)
async def get_session(
    session_id: str,
    current_user: CurrentUser,
    db: DB,
    settings: AppSettings,
):
    service = ChatService(db, settings)
    return await service.get_session_detail(session_id, current_user)


@router.delete(
    "/sessions/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a chat session and all its messages",
)
async def delete_session(
    session_id: str,
    current_user: CurrentUser,
    db: DB,
    settings: AppSettings,
):
    service = ChatService(db, settings)
    await service.delete_session(session_id, current_user)


@router.patch(
    "/sessions/{session_id}",
    response_model=SessionSummary,
    summary="Rename a chat session",
)
async def rename_session(
    session_id: str,
    body: SessionRenameRequest,
    current_user: CurrentUser,
    db: DB,
    settings: AppSettings,
):
    service = ChatService(db, settings)
    return await service.rename_session(session_id, current_user, body.title)


@router.post(
    "/sessions/{session_id}/messages",
    response_model=SendMessageResponse,
    summary="Send a message and receive AI response",
)
async def send_message(
    session_id: str,
    body: SendMessageRequest,
    request: Request,
    current_user: CurrentUser,
    db: DB,
    settings: AppSettings,
):
    """
    Full chat pipeline:
    1. Save user message to DB
    2. Load recent history (context window)
    3. Forward to inference engine (RAG)
    4. Save AI response + metadata to DB
    5. Return both message objects
    """
    # Use shared inference client from app state
    inference_client: InferenceClient = request.app.state.inference_client
    service = ChatService(db, settings)
    return await service.send_message(session_id, current_user, body, inference_client)
