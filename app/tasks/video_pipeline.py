"""
Video generation background task: narration → TTS audio → Islamic slide → FFmpeg → MP4.
Runs in FastAPI BackgroundTasks so it doesn't block the HTTP response.
"""
import asyncio
import logging
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.models.media import GeneratedMedia, JobStatus, MediaJob, MediaStatus
from app.providers.edge_tts import EdgeTTSClient

logger = logging.getLogger(__name__)

# Islamic geometric decorative characters (Unicode)
_BISMILLAH = "بِسْمِ اللَّهِ الرَّحْمَنِ الرَّحِيمِ"
_STAR_PATTERN = "✦ ✧ ✦ ✧ ✦ ✧ ✦ ✧ ✦ ✧ ✦ ✧ ✦"


async def run_video_pipeline(
    job_id: uuid.UUID,
    media_id: uuid.UUID,
    narration_text: str,
    session_maker,  # async_sessionmaker
    settings: Settings,
) -> None:
    """
    Full async video generation pipeline:
    1. TTS: narration → audio.wav
    2. Render: Islamic-styled slide.png (Pillow)
    3. FFmpeg: slide + audio → output.mp4
    4. Update DB with result
    """
    media_dir = Path(settings.media_dir)
    job_dir = media_dir / str(media_id)
    job_dir.mkdir(parents=True, exist_ok=True)

    audio_path = job_dir / "narration.wav"
    slide_path = job_dir / "slide.png"
    video_path = job_dir / f"{media_id}.mp4"

    async with session_maker() as db:
        await _update_job(db, job_id, JobStatus.processing, progress_pct=0)

    try:
        # ── Step 1: TTS (20%) ──────────────────────────────────────────────
        logger.info("[video:%s] Step 1/3 — TTS synthesis", job_id)
        tts = EdgeTTSClient(settings)
        await tts.synthesize(narration_text, str(audio_path))
        async with session_maker() as db:
            await _update_job(db, job_id, JobStatus.processing, progress_pct=33)

        # ── Step 2: Render Islamic Slide (60%) ─────────────────────────────
        logger.info("[video:%s] Step 2/3 — Slide render", job_id)
        await asyncio.get_event_loop().run_in_executor(
            None, _render_islamic_slide, str(slide_path), narration_text, settings
        )
        async with session_maker() as db:
            await _update_job(db, job_id, JobStatus.processing, progress_pct=66)

        # ── Step 3: FFmpeg combine (100%) ──────────────────────────────────
        logger.info("[video:%s] Step 3/3 — FFmpeg combine", job_id)
        await asyncio.get_event_loop().run_in_executor(
            None, _run_ffmpeg, str(slide_path), str(audio_path), str(video_path), settings
        )

        # ── Save result to DB ──────────────────────────────────────────────
        relative_path = str(video_path.relative_to(media_dir))
        file_size = video_path.stat().st_size if video_path.exists() else None

        async with session_maker() as db:
            await _finalize_media(
                db, job_id, media_id,
                file_path=relative_path,
                file_size=file_size,
                success=True,
            )
        logger.info("[video:%s] Pipeline complete → %s", job_id, video_path)

    except Exception as exc:
        logger.exception("[video:%s] Pipeline failed: %s", job_id, exc)
        async with session_maker() as db:
            await _finalize_media(db, job_id, media_id, error=str(exc))


# ─── Rendering Utilities ──────────────────────────────────────────────────────

def _render_islamic_slide(
    output_path: str,
    text: str,
    settings: Settings,
) -> None:
    """
    Render an Islamic-aesthetic slide using Pillow.
    Palette: deep navy bg, gold accents, warm white text.
    """
    W, H = settings.video_slide_width, settings.video_slide_height
    bg_color = settings.video_slide_bg_color
    accent = settings.video_slide_accent_color
    text_color = settings.video_slide_text_color
    sub_color = settings.video_slide_sub_color

    img = Image.new("RGB", (W, H), color=bg_color)
    draw = ImageDraw.Draw(img)

    # ── Decorative border lines ───────────────────────────────────────────
    border = 18
    draw.rectangle([border, border, W - border, H - border], outline=accent, width=2)
    inner = 30
    draw.rectangle([inner, inner, W - inner, H - inner], outline=accent, width=1)

    # ── Corner geometric diamonds ─────────────────────────────────────────
    d_size = 12
    corners = [
        (inner, inner), (W - inner, inner),
        (inner, H - inner), (W - inner, H - inner),
    ]
    for cx, cy in corners:
        draw.polygon(
            [(cx, cy - d_size), (cx + d_size, cy), (cx, cy + d_size), (cx - d_size, cy)],
            fill=accent,
        )

    # ── Horizontal accent lines ───────────────────────────────────────────
    line_y_top = H // 5
    line_y_bot = H - H // 5
    draw.line([(inner + 20, line_y_top), (W - inner - 20, line_y_top)], fill=accent, width=1)
    draw.line([(inner + 20, line_y_bot), (W - inner - 20, line_y_bot)], fill=accent, width=1)

    # ── Try to load fonts, fallback to default ────────────────────────────
    try:
        font_title = ImageFont.truetype("arial.ttf", 28)
        font_text = ImageFont.truetype("arial.ttf", 22)
        font_small = ImageFont.truetype("arial.ttf", 16)
    except Exception:
        font_title = ImageFont.load_default()
        font_text = font_title
        font_small = font_title

    # ── Bismillah header ──────────────────────────────────────────────────
    draw.text((W // 2, H // 6), _BISMILLAH, font=font_small, fill=accent, anchor="mm")

    # ── Star pattern divider ──────────────────────────────────────────────
    draw.text((W // 2, H // 6 + 30), _STAR_PATTERN, font=font_small, fill=sub_color, anchor="mm")

    # ── Main narration text (word-wrapped) ────────────────────────────────
    _draw_wrapped_text(draw, text, font=font_text, fill=text_color, box=(inner + 60, H // 3, W - inner - 60), line_spacing=36)

    # ── Footer ────────────────────────────────────────────────────────────
    draw.text((W // 2, H - H // 6), "KitabGuru", font=font_small, fill=sub_color, anchor="mm")
    draw.text((W // 2, H - H // 6 + 24), _STAR_PATTERN, font=font_small, fill=accent, anchor="mm")

    img.save(output_path, "PNG")


def _draw_wrapped_text(
    draw: ImageDraw.Draw,
    text: str,
    font,
    fill: str,
    box: tuple[int, int, int, int],
    line_spacing: int = 32,
) -> None:
    """Draw word-wrapped text within a bounding box, centered."""
    x1, y1, x2, y2 = box
    max_width = x2 - x1
    words = text.split()
    lines: list[str] = []
    current = ""

    for word in words:
        test = f"{current} {word}".strip()
        w = draw.textlength(test, font=font)
        if w <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)

    total_h = len(lines) * line_spacing
    y = y1 + ((y2 - y1) - total_h) // 2  # Vertically center in box
    cx = (x1 + x2) // 2

    for line in lines:
        draw.text((cx, y), line, font=font, fill=fill, anchor="mm")
        y += line_spacing


def _run_ffmpeg(
    slide_path: str,
    audio_path: str,
    output_path: str,
    settings: Settings,
) -> None:
    """
    Run FFmpeg synchronously (called in executor thread).
    Combines static image + audio into MP4.
    """
    cmd = [
        settings.ffmpeg_path,
        "-y",                       # Overwrite output
        "-loop", "1",               # Loop image
        "-i", slide_path,           # Input: static slide
        "-i", audio_path,           # Input: audio
        "-c:v", "libx264",
        "-tune", "stillimage",
        "-c:a", "aac",
        "-b:a", "192k",
        "-pix_fmt", "yuv420p",
        "-shortest",                # Stop when audio ends
        output_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg failed: {result.stderr}")


# ─── DB Helpers ───────────────────────────────────────────────────────────────

async def _update_job(
    db: AsyncSession,
    job_id: uuid.UUID,
    job_status: JobStatus,
    progress_pct: int = 0,
) -> None:
    from sqlalchemy import select
    result = await db.execute(select(MediaJob).where(MediaJob.id == job_id))
    job = result.scalar_one_or_none()
    if job:
        job.status = job_status
        job.progress_pct = progress_pct
        if job_status == JobStatus.processing and not job.started_at:
            job.started_at = datetime.now(timezone.utc)
        await db.commit()


async def _finalize_media(
    db: AsyncSession,
    job_id: uuid.UUID,
    media_id: uuid.UUID,
    file_path: str = "",
    file_size: int | None = None,
    success: bool = False,
    error: str | None = None,
) -> None:
    from sqlalchemy import select
    now = datetime.now(timezone.utc)

    job_result = await db.execute(select(MediaJob).where(MediaJob.id == job_id))
    job = job_result.scalar_one_or_none()
    if job:
        job.status = JobStatus.completed if success else JobStatus.failed
        job.progress_pct = 100 if success else job.progress_pct
        job.completed_at = now
        job.error_detail = error

    media_result = await db.execute(select(GeneratedMedia).where(GeneratedMedia.id == media_id))
    media = media_result.scalar_one_or_none()
    if media:
        media.status = MediaStatus.completed if success else MediaStatus.failed
        if success:
            media.file_path = file_path
            media.file_size_bytes = file_size
            media.completed_at = now
        else:
            media.error_message = error

    await db.commit()
