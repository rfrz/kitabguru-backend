"""
IoT routes (API Key auth via X-API-Key header):
  POST /iot/sessions              — Create IoT session
  POST /iot/sessions/{id}/voice   — Process voice: STT → inference → TTS → return audio
  GET  /iot/sessions/{id}         — Get IoT session + messages
"""
import uuid

from fastapi import APIRouter, File, HTTPException, Request, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.dependencies import DB, AppSettings, IoTAuth
from app.models.iot import IoTSession
from app.schemas.iot import (
    IoTMessageOut,
    IoTSessionCreateRequest,
    IoTSessionDetailResponse,
    IoTSessionResponse,
    IoTVoiceResponse,
)
from app.services.iot_service import IoTService

router = APIRouter()


@router.post(
    "/sessions",
    response_model=IoTSessionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new IoT device session",
)
async def create_iot_session(
    body: IoTSessionCreateRequest,
    db: DB,
    settings: AppSettings,
    _: IoTAuth,
):
    """
    Create a new IoT conversation session for a device.
    Authenticated via X-API-Key header.
    """
    service = IoTService(db, settings)
    session = await service.create_session(body.device_id)
    return IoTSessionResponse(
        session_id=str(session.id),
        device_id=session.device_id,
        started_at=session.started_at,
    )


@router.post(
    "/sessions/{session_id}/voice",
    response_model=IoTVoiceResponse,
    summary="Process voice: upload audio → get text + audio response",
)
async def voice_interact(
    session_id: str,
    request: Request,
    audio: UploadFile = File(..., description="Audio file (WAV/MP3/OGG)"),
    db: DB = None,
    settings: AppSettings = None,
    _: IoTAuth = None,
):
    """
    Full voice interaction pipeline:
    1. Groq Whisper STT: audio → transcription text
    2. Save user message (iot_messages)
    3. Call inference engine (RAG)
    4. Save assistant message
    5. Edge-TTS: answer text → audio file
    6. Return text + audio URL
    """
    from app.core.dependencies import get_db, get_settings, verify_iot_api_key
    # Resolve dependencies manually for UploadFile compatibility
    if db is None:
        raise HTTPException(status_code=500, detail="DB dependency not resolved")

    inference_client = request.app.state.inference_client
    service = IoTService(db, settings, inference_client)

    audio_bytes = await audio.read()
    return await service.process_voice(
        session_id=session_id,
        audio_bytes=audio_bytes,
        audio_filename=audio.filename or "audio.wav",
    )


@router.get(
    "/sessions/{session_id}",
    response_model=IoTSessionDetailResponse,
    summary="Get IoT session + all messages",
)
async def get_iot_session(
    session_id: str,
    db: DB,
    settings: AppSettings,
    _: IoTAuth,
):
    """Return IoT session details + all messages (for device replay/logging)."""
    try:
        sid = uuid.UUID(session_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    result = await db.execute(
        select(IoTSession)
        .options(selectinload(IoTSession.messages))
        .where(IoTSession.id == sid)
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    messages = [
        IoTMessageOut(
            id=str(m.id),
            role=m.role.value,
            content=m.content,
            audio_path=m.audio_path,
            metadata=m.meta,
            created_at=m.created_at,
        )
        for m in session.messages
    ]

    return IoTSessionDetailResponse(
        session_id=str(session.id),
        device_id=session.device_id,
        started_at=session.started_at,
        ended_at=session.ended_at,
        messages=messages,
    )
