"""
Media service: orchestrate image generation and video job creation.
"""
import uuid
from pathlib import Path

from fastapi import BackgroundTasks, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.models.media import GeneratedMedia, JobStatus, MediaJob, MediaStatus, MediaType
from app.models.user import ChatSession, Message, User
from app.providers.cloudflare_image import CloudflareImageClient, CloudflareImageError
from app.providers.inference_client import InferenceClient
from app.schemas.media import ImageGenerateResponse, VideoGenerateResponse
from app.tasks.video_pipeline import run_video_pipeline


class MediaService:
    def __init__(self, db: AsyncSession, settings: Settings, inference_client: InferenceClient):
        self.db = db
        self.settings = settings
        self.inference_client = inference_client

    # ─── Image Generation ─────────────────────────────────────────────────

    async def generate_image(self, session_id: str, user: User) -> ImageGenerateResponse:
        """
        1. Load session history
        2. Generate image prompt via inference
        3. Call Cloudflare SDXL
        4. Save image to disk + DB
        5. Return image metadata
        """
        session = await self._get_session_or_404(session_id, user)

        # Step 1: Generate image prompt from chat context
        prompt = await self._build_image_prompt(session)

        # Step 2: Generate image via Cloudflare Workers AI
        try:
            cf_client = CloudflareImageClient(self.settings)
            image_bytes = await cf_client.generate(prompt)
        except CloudflareImageError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Image generation failed: {exc}",
            )

        # Step 3: Save to filesystem
        media_id = uuid.uuid4()
        media_dir = Path(self.settings.media_dir)
        img_path = media_dir / f"{media_id}.png"
        img_path.write_bytes(image_bytes)
        relative_path = f"{media_id}.png"

        # Step 4: Create GeneratedMedia record
        media = GeneratedMedia(
            id=media_id,
            session_id=session.id,
            user_id=user.id,
            media_type=MediaType.image,
            file_path=relative_path,
            file_size_bytes=len(image_bytes),
            prompt_used=prompt,
            status=MediaStatus.completed,
        )
        from datetime import datetime, timezone
        media.completed_at = datetime.now(timezone.utc)
        self.db.add(media)
        await self.db.commit()
        await self.db.refresh(media)

        image_url = f"{self.settings.media_base_url}/{relative_path}"
        return ImageGenerateResponse(
            media_id=str(media.id),
            prompt_used=prompt,
            image_url=image_url,
            status=media.status.value,
        )

    # ─── Video Generation ─────────────────────────────────────────────────

    async def start_video_job(
        self,
        session_id: str,
        user: User,
        background_tasks: BackgroundTasks,
        session_maker,
    ) -> VideoGenerateResponse:
        """
        1. Load session + build narration from inference
        2. Create GeneratedMedia + MediaJob records (queued)
        3. Queue background task
        4. Return job_id immediately
        """
        session = await self._get_session_or_404(session_id, user)

        # Build narration script from chat context
        narration = await self._build_narration(session)

        # Create media + job records
        media_id = uuid.uuid4()
        job_id = uuid.uuid4()

        media = GeneratedMedia(
            id=media_id,
            session_id=session.id,
            user_id=user.id,
            media_type=MediaType.video,
            file_path=f"{media_id}/{media_id}.mp4",
            prompt_used=narration,
            status=MediaStatus.processing,
        )
        job = MediaJob(
            id=job_id,
            media_id=media_id,
            status=JobStatus.queued,
            progress_pct=0,
        )
        self.db.add(media)
        self.db.add(job)
        await self.db.commit()

        # Queue background pipeline
        background_tasks.add_task(
            run_video_pipeline,
            job_id=job_id,
            media_id=media_id,
            narration_text=narration,
            session_maker=session_maker,
            settings=self.settings,
        )

        return VideoGenerateResponse(
            job_id=str(job_id),
            media_id=str(media_id),
            status="queued",
        )

    # ─── Private Helpers ──────────────────────────────────────────────────

    async def _get_session_or_404(self, session_id: str, user: User) -> ChatSession:
        try:
            sid = uuid.UUID(session_id)
        except ValueError:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

        from sqlalchemy.orm import selectinload
        result = await self.db.execute(
            select(ChatSession)
            .options(selectinload(ChatSession.messages))
            .where(ChatSession.id == sid, ChatSession.user_id == user.id)
        )
        session = result.scalar_one_or_none()
        if not session:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
        return session

    async def _build_image_prompt(self, session: ChatSession) -> str:
        """Summarize the chat session into an image generation prompt via inference."""
        if not session.messages:
            return "An Islamic educational scene with books and geometric patterns"

        # Take last N messages for context
        window = self.settings.chat_context_window
        messages = session.messages[-window:] if window > 0 else session.messages
        context = "\n".join([f"{m.role.value}: {m.content}" for m in messages])

        prompt_request = (
            f"Based on this educational conversation, create a concise image generation prompt "
            f"(max 150 words) that visually represents the main topic. "
            f"Style: Islamic geometric art, educational, professional, vibrant colors.\n\n"
            f"Conversation:\n{context[:3000]}"
        )

        try:
            response = await self.inference_client.chat(query=prompt_request)
            return response.get("answer", "")[:500] or "Islamic educational geometric art"
        except Exception:
            return "An Islamic educational scene with geometric patterns and books"

    async def _build_narration(self, session: ChatSession) -> str:
        """Summarize chat session into narration script for video TTS."""
        if not session.messages:
            return "Selamat datang di KitabGuru, platform pembelajaran Islam berbasis AI."

        window = self.settings.chat_context_window
        messages = session.messages[-window:] if window > 0 else session.messages
        context = "\n".join([f"{m.role.value}: {m.content}" for m in messages])

        narration_request = (
            f"Buatlah narasi video edukatif dalam Bahasa Indonesia berdasarkan percakapan berikut. "
            f"Narasi harus informatif, mudah dipahami, dan berdurasi sekitar 60-90 detik saat dibaca. "
            f"Mulai dengan 'Bismillah' dan akhiri dengan kalimat penutup yang inspiratif.\n\n"
            f"Percakapan:\n{context[:3000]}"
        )

        try:
            response = await self.inference_client.chat(query=narration_request)
            return response.get("answer", "") or "Bismillahirrahmanirrahim. Selamat belajar bersama KitabGuru."
        except Exception:
            return "Bismillahirrahmanirrahim. Selamat belajar bersama KitabGuru, platform pendidikan Islam berbasis AI."
