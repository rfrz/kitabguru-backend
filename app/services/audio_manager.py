import io
from app.config import get_settings

class AudioManager:
    """
    Lazy loads STT and TTS engines based on config to save RAM when not used.
    """
    _stt_engine = None
    _tts_engine = None

    @classmethod
    def get_stt(cls):
        settings = get_settings()
        if settings.stt_provider == "local":
            if cls._stt_engine is None:
                from faster_whisper import WhisperModel
                # Using int8 to save RAM on low-end servers, but we assume backend has some power.
                cls._stt_engine = WhisperModel("base", device="cpu", compute_type="int8")
            return cls._stt_engine
        else:
            # Use Groq
            if cls._stt_engine is None:
                from groq import AsyncGroq
                cls._stt_engine = AsyncGroq(api_key=settings.groq_api_key)
            return cls._stt_engine

    @classmethod
    async def transcribe(cls, audio_bytes: bytes, filename: str = "audio.wav") -> str:
        settings = get_settings()
        if settings.stt_provider == "local":
            model = cls.get_stt()
            # Faster-whisper needs a file-like object or path
            audio_io = io.BytesIO(audio_bytes)
            segments, info = model.transcribe(audio_io, beam_size=5)
            text = " ".join([segment.text for segment in segments])
            return text
        else:
            # Groq
            client = cls.get_stt()
            transcription = await client.audio.transcriptions.create(
                file=(filename, audio_bytes),
                model=settings.groq_whisper_model,
                language="id",
            )
            return transcription.text

    @classmethod
    def get_tts(cls):
        # We don't necessarily need a persistent engine for edge-tts, but for piper we might.
        settings = get_settings()
        if settings.tts_provider == "local":
            if cls._tts_engine is None:
                # Piper TTS python wrapper
                import os
                import tarfile
                import urllib.request
                from piper.voice import PiperVoice
                
                # Auto-download a model if not exists (dummy logic for production)
                model_path = "en_US-lessac-medium.onnx"
                if not os.path.exists(model_path):
                    # For real use, we'd bundle the model. This is a placeholder.
                    pass
                
                # cls._tts_engine = PiperVoice.load(model_path)
                pass
            return cls._tts_engine
        return None

    @classmethod
    async def synthesize(cls, text: str) -> bytes:
        settings = get_settings()
        if settings.tts_provider == "local":
            # For Piper, we'd run synthesize
            # model = cls.get_tts()
            # wav_io = io.BytesIO()
            # model.synthesize(text, wav_io)
            # return wav_io.getvalue()
            # Placeholder since Piper model loading is complex
            raise NotImplementedError("Piper TTS local synthesis not fully implemented in demo")
        else:
            import edge_tts
            communicate = edge_tts.Communicate(
                text, 
                settings.tts_voice,
                rate=settings.tts_rate,
                volume=settings.tts_volume
            )
            audio_data = bytearray()
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    audio_data.extend(chunk["data"])
            return bytes(audio_data)

