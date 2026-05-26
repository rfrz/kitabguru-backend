"""
IoT service: handle voice interactions (STT → inference → TTS).
"""
import uuid
from pathlib import Path

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import Settings
from app.models.iot import IoTMessage, IoTMessageRole, IoTSession
from app.providers.edge_tts import EdgeTTSClient
from app.providers.groq_stt import GroqSTTClient, GroqSTTError
from app.providers.inference_client import InferenceClient
from app.schemas.iot import IoTSessionResponse, IoTVoiceResponse


class IoTService:
    def __init__(
        self,
        db: AsyncSession,
        settings: Settings,
        inference_client: InferenceClient | None = None,
    ):
        self.db = db
        self.settings = settings
        self.inference_client = inference_client

    # ─── Session Management ───────────────────────────────────────────────

    async def create_session(self, device_id: str) -> IoTSession:
        """Create a new IoT session for a device."""
        session = IoTSession(device_id=device_id)
        self.db.add(session)
        await self.db.commit()
        await self.db.refresh(session)
        return session

    # ─── Voice Interaction Pipeline ───────────────────────────────────────

    async def process_voice(
        self,
        session_id: str,
        audio_bytes: bytes,
        audio_filename: str = "audio.wav",
    ) -> IoTVoiceResponse:
        """
        Full voice pipeline:
        1. Groq Whisper STT: audio → text
        2. Save user message to DB
        3. Inference engine: text → AI answer
        4. Save assistant message to DB
        5. Edge-TTS: answer → audio file
        6. Return text + audio URL
        """
        session = await self._get_session_or_404(session_id)

        # Step 1: STT
        try:
            stt_client = GroqSTTClient(self.settings)
            question_text = await stt_client.transcribe(audio_bytes, audio_filename)
        except GroqSTTError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"STT service error: {exc}",
            )

        if not question_text.strip():
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Could not transcribe audio — please speak clearly",
            )

        # Step 2: Save user message
        user_msg = IoTMessage(
            iot_session_id=session.id,
            role=IoTMessageRole.user,
            content=question_text,
            meta={"provider": "groq-whisper", "model": self.settings.groq_whisper_model},
        )
        self.db.add(user_msg)
        await self.db.flush()

        # Step 3: Call inference engine
        if not self.inference_client:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Inference client not available",
            )
        try:
            inference_response = await self.inference_client.chat(query=question_text)
            answer_text = inference_response.get("answer", "Maaf, saya tidak dapat menjawab pertanyaan ini.")
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Inference service error: {exc}",
            )

        # Step 4: TTS — convert answer to audio
        tts_client = EdgeTTSClient(self.settings)
        audio_id = uuid.uuid4()
        media_dir = Path(self.settings.media_dir) / "iot_audio"
        media_dir.mkdir(parents=True, exist_ok=True)
        audio_path = media_dir / f"{audio_id}.mp3"

        try:
            await tts_client.synthesize(answer_text, str(audio_path))
        except Exception as exc:
            # Non-fatal: still save the text response
            audio_path = None

        relative_audio_path = f"iot_audio/{audio_id}.mp3" if audio_path and audio_path.exists() else None

        # Step 5: Save assistant message
        assistant_msg = IoTMessage(
            iot_session_id=session.id,
            role=IoTMessageRole.assistant,
            content=answer_text,
            audio_path=relative_audio_path,
            meta={
                "provider_used": inference_response.get("provider_used"),
                "sources": inference_response.get("sources"),
                "tts_voice": self.settings.tts_voice,
            },
        )
        self.db.add(assistant_msg)
        await self.db.commit()
        await self.db.refresh(assistant_msg)

        audio_url = (
            f"{self.settings.media_base_url}/{relative_audio_path}"
            if relative_audio_path
            else ""
        )

        return IoTVoiceResponse(
            iot_message_id=str(assistant_msg.id),
            text_question=question_text,
            text_answer=answer_text,
            audio_url=audio_url,
        )

    # ─── Private Helpers ──────────────────────────────────────────────────

    async def _get_session_or_404(self, session_id: str) -> IoTSession:
        try:
            sid = uuid.UUID(session_id)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="IoT session not found"
            )

        result = await self.db.execute(
            select(IoTSession).where(IoTSession.id == sid)
        )
        session = result.scalar_one_or_none()
        if not session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="IoT session not found"
            )
        return session
