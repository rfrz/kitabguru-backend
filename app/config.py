from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        extra="ignore",
    )

    # App
    app_name: str = "KitabGuru Backend"
    app_port: int = 8001
    api_prefix: str = "/api/v1"
    cors_origins: str = "http://localhost:5173,http://localhost:3000"

    # Database
    database_url: str = "postgresql+asyncpg://kitabguru:secret@localhost:5432/kitabguru_db"

    # JWT
    jwt_secret_key: str = "change-this-in-production"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 30
    jwt_refresh_token_expire_days: int = 30

    # Admin Seed
    admin_email: str = "admin@kitabguru.com"
    admin_username: str = "admin"
    admin_password: str = "ChangeThisPassword!"

    # Inference Service
    inference_base_url: str = "http://localhost:8000"
    hf_token: Optional[str] = None

    # IoT
    iot_api_key: str = "change-this-iot-key"

    # Light LLM Pipeline (for image prompt translation)
    llm_fallback_order: str = "gemini,openai_compatible"
    gemini_api_key: Optional[str] = None
    gemini_llm_model: str = "gemini-3.1-flash-lite"
    openai_compatible_api_key: Optional[str] = None
    openai_compatible_base_url: Optional[str] = None
    openai_compatible_model: Optional[str] = None

    # Cloudflare Workers AI (Image Generation)
    cf_account_id: Optional[str] = None
    cf_api_token: Optional[str] = None
    cf_image_model: str = "@cf/stabilityai/stable-diffusion-xl-base-1.0"

    # Groq STT
    groq_api_key: Optional[str] = None
    groq_whisper_model: str = "whisper-large-v3"

    # Provider Toggles ("groq" / "local" for STT, "edge_tts" / "local" for TTS)
    stt_provider: str = "groq"
    tts_provider: str = "edge_tts"

    # Edge-TTS
    tts_voice: str = "id-ID-ArdiNeural"
    tts_rate: str = "+0%"
    tts_volume: str = "+0%"

    # Media Storage
    media_dir: str = "./media"
    media_base_url: str = "http://localhost:8001/media"

    # Video Pipeline — Islamic aesthetic design
    ffmpeg_path: str = "ffmpeg"
    # Islamic geometric pattern palette
    video_slide_bg_color: str = "#0d1b2a"       # Deep navy
    video_slide_accent_color: str = "#c9a84c"   # Islamic gold
    video_slide_text_color: str = "#f0ece2"     # Warm white
    video_slide_sub_color: str = "#8ab4b8"      # Soft teal
    video_slide_width: int = 1280
    video_slide_height: int = 720

    # Purge Scheduler (Soft Delete Cleanup)
    # Hard delete accounts soft-deleted more than this many days ago
    purge_soft_delete_after_days: int = 30

    # Chat Context Window
    # How many recent messages to send as context to Inference (0 = entire session)
    chat_context_window: int = 20

    # Rate Limiting (best-practice defaults)
    # Auth endpoints: max requests per minute per IP
    rate_limit_auth_per_minute: int = 5
    # Media generation: max requests per hour per user
    rate_limit_media_per_hour: int = 10
    # General API: max requests per minute per user
    rate_limit_api_per_minute: int = 60

    @property
    def cors_origin_list(self) -> list[str]:
        if self.cors_origins.strip() == "*":
            return ["*"]
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    def ensure_media_dir(self) -> None:
        Path(self.media_dir).mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_media_dir()
    return settings
