"""
Edge-TTS wrapper for neural Text-to-Speech.
Uses Microsoft Edge TTS engine via edge-tts library (no API key required).
Voice configured via TTS_VOICE env var (default: id-ID-ArdiNeural).
"""
import asyncio
from pathlib import Path

import edge_tts

from app.config import Settings


class EdgeTTSClient:
    def __init__(self, settings: Settings):
        self.voice = settings.tts_voice
        self.rate = settings.tts_rate
        self.volume = settings.tts_volume

    async def synthesize(self, text: str, output_path: str) -> str:
        """
        Convert text to audio file at output_path.
        Returns the output_path on success.
        """
        communicate = edge_tts.Communicate(
            text=text,
            voice=self.voice,
            rate=self.rate,
            volume=self.volume,
        )
        await communicate.save(output_path)
        return output_path

    async def list_voices(self) -> list[dict]:
        """Return available voices (useful for admin/debug)."""
        voices = await edge_tts.list_voices()
        return [v for v in voices if "id-" in v.get("ShortName", "").lower()]


async def synthesize_to_file(text: str, output_path: str, settings: Settings) -> str:
    """Convenience function: synthesize text to audio file."""
    client = EdgeTTSClient(settings)
    return await client.synthesize(text, output_path)
