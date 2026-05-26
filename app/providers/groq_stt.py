"""
Groq Whisper STT (Speech-to-Text) client.
Uses GROQ_API_KEY and GROQ_WHISPER_MODEL from env.
Groq's LPU hardware processes audio very fast (1-2s for 30s audio).
"""
from pathlib import Path
from typing import BinaryIO

from groq import AsyncGroq

from app.config import Settings


class GroqSTTError(RuntimeError):
    pass


class GroqSTTClient:
    def __init__(self, settings: Settings):
        if not settings.groq_api_key:
            raise GroqSTTError("GROQ_API_KEY is not set in environment")
        self._client = AsyncGroq(api_key=settings.groq_api_key)
        self.model = settings.groq_whisper_model

    async def transcribe(self, audio_bytes: bytes, filename: str = "audio.wav") -> str:
        """
        Transcribe audio bytes to text using Groq Whisper.
        Returns the transcribed text string.
        """
        transcription = await self._client.audio.transcriptions.create(
            file=(filename, audio_bytes),
            model=self.model,
            response_format="text",
            language="id",  # Indonesian; set to None for auto-detect
        )
        # Groq returns a string when response_format="text"
        return str(transcription).strip()

    async def transcribe_file(self, file_path: str) -> str:
        """Transcribe an audio file from disk."""
        path = Path(file_path)
        if not path.exists():
            raise GroqSTTError(f"Audio file not found: {file_path}")
        audio_bytes = path.read_bytes()
        return await self.transcribe(audio_bytes, filename=path.name)
