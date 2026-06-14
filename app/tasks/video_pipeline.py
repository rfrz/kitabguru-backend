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
    language_code: str,
    session_maker,  # async_sessionmaker
    settings: Settings,
) -> None:
    """
    Full async video generation pipeline:
    1. Parse text into sentence chunks.
    2. For each chunk:
       a. Synthesize audio.wav (EdgeTTS)
       b. Render slide.png with template + text
       c. Create clip.mp4 with FFmpeg
    3. Concat all clip.mp4 files into final output.mp4
    4. Clean up temp files.
    5. Update DB with result.
    """
    import re

    media_dir = Path(settings.media_dir)
    job_dir = media_dir / str(media_id)
    job_dir.mkdir(parents=True, exist_ok=True)

    video_path = job_dir / f"{media_id}.mp4"
    list_path = job_dir / "clips.txt"

    async with session_maker() as db:
        await _update_job(db, job_id, JobStatus.processing, progress_pct=0)

    # Split text into sentence chunks
    # Match sentences ending with . ! or ? or newlines
    raw_sentences = re.split(r'(?<=[.!?。！？])\s*|\n+', narration_text.strip())
    chunks = [s.strip() for s in raw_sentences if s.strip()]
    if not chunks:
        chunks = [narration_text.strip()]

    temp_files = [list_path]
    clip_paths = []

    try:
        # Iterate over chunks to build individual clips
        for i, chunk in enumerate(chunks):
            logger.info("[video:%s] Processing chunk %d/%d: %s", job_id, i + 1, len(chunks), chunk)
            
            chunk_audio_path = job_dir / f"audio_{i}.wav"
            chunk_slide_path = job_dir / f"slide_{i}.png"
            chunk_clip_path = job_dir / f"clip_{i}.mp4"
            
            temp_files.extend([chunk_audio_path, chunk_slide_path, chunk_clip_path])
            
            # Step 1: TTS
            voice = get_voice_for_language(language_code)
            tts = EdgeTTSClient(settings)
            await tts.synthesize(chunk, str(chunk_audio_path), voice=voice)
            
            # Step 2: Render Slide
            await asyncio.get_event_loop().run_in_executor(
                None, _render_islamic_slide, str(chunk_slide_path), chunk, settings, language_code
            )
            
            # Step 3: FFmpeg combine slide & audio into a clip
            await asyncio.get_event_loop().run_in_executor(
                None, _run_ffmpeg, str(chunk_slide_path), str(chunk_audio_path), str(chunk_clip_path), settings
            )
            
            clip_paths.append(chunk_clip_path)
            
            # Update DB progress (scales up to 90%)
            progress = int((i + 1) / len(chunks) * 90)
            async with session_maker() as db:
                await _update_job(db, job_id, JobStatus.processing, progress_pct=progress)

        # Step 4: Concatenate all clips
        logger.info("[video:%s] Concatenating %d clips into final video", job_id, len(clip_paths))
        
        # Write the FFmpeg concat file list.txt
        with open(list_path, "w", encoding="utf-8") as f:
            for cp in clip_paths:
                f.write(f"file '{cp.name}'\n")
        
        await asyncio.get_event_loop().run_in_executor(
            None, _run_ffmpeg_concat, str(list_path), str(video_path), settings
        )

        # ── Save result to DB ──────────────────────────────────────────────
        relative_path = str(video_path.relative_to(media_dir)).replace("\\", "/")
        file_size = video_path.stat().st_size if video_path.exists() else None

        async with session_maker() as db:
            await _finalize_media(
                db, job_id, media_id,
                file_path=relative_path,
                file_size=file_size,
                success=True,
                settings=settings,
            )
        logger.info("[video:%s] Pipeline complete → %s", job_id, video_path)

    except Exception as exc:
        logger.exception("[video:%s] Pipeline failed: %s", job_id, exc)
        async with session_maker() as db:
            await _finalize_media(db, job_id, media_id, error=str(exc), settings=settings)
    finally:
        for tmp_file in temp_files:
            try:
                if tmp_file.exists():
                    tmp_file.unlink()
            except Exception as e:
                logger.warning("[video:%s] Failed to delete temp file %s: %s", job_id, tmp_file, e)


# ─── Rendering Utilities ──────────────────────────────────────────────────────

def get_voice_for_language(language_code: str) -> str:
    """Map language code to standard neural voices supported by EdgeTTS."""
    lang = language_code.lower().strip()
    if lang.startswith("id"):
        return "id-ID-ArdiNeural"
    elif lang.startswith("en"):
        return "en-US-AriaNeural"
    elif lang.startswith("ja"):
        return "ja-JP-NanamiNeural"
    elif lang.startswith("ar"):
        return "ar-SA-HamedNeural"
    elif lang.startswith("ms"):
        return "ms-MY-YasminNeural"
    elif lang.startswith("zh"):
        return "zh-CN-XiaoxiaoNeural"
    elif lang.startswith("tr"):
        return "tr-TR-AhmetNeural"
    elif lang.startswith("fr"):
        return "fr-FR-DeniseNeural"
    elif lang.startswith("es"):
        return "es-ES-AlvaroNeural"
    elif lang.startswith("de"):
        return "de-DE-KillianNeural"
    return "id-ID-ArdiNeural"


def _get_font_info_for_language(language_code: str) -> tuple[str, str]:
    """Return (font_filename, font_download_url) based on language code."""
    lang = language_code.lower().strip()
    if lang.startswith("ja"):
        return ("NotoSansJP-Medium.otf", "https://raw.githubusercontent.com/notofonts/noto-cjk/main/Sans/OTF/Japanese/NotoSansCJKjp-Medium.otf")
    elif lang.startswith("zh"):
        return ("NotoSansSC-Medium.otf", "https://raw.githubusercontent.com/notofonts/noto-cjk/main/Sans/OTF/SimplifiedChinese/NotoSansCJKsc-Medium.otf")
    elif lang.startswith("ko"):
        return ("NotoSansKR-Medium.otf", "https://raw.githubusercontent.com/notofonts/noto-cjk/main/Sans/OTF/Korean/NotoSansCJKkr-Medium.otf")
    elif lang.startswith("ar"):
        return ("NotoSansArabic-Medium.ttf", "https://raw.githubusercontent.com/notofonts/arabic/main/fonts/NotoSansArabic/hinted/ttf/NotoSansArabic-Medium.ttf")
    return ("Roboto-Medium.ttf", "https://cdnjs.cloudflare.com/ajax/libs/pdfmake/0.1.66/fonts/Roboto/Roboto-Medium.ttf")


def _ensure_font_for_language(language_code: str) -> Path:
    """Ensure font for language exists in app/assets, downloading it if necessary."""
    font_filename, url = _get_font_info_for_language(language_code)
    assets_dir = Path(__file__).parent.parent / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    font_path = assets_dir / font_filename
    if not font_path.exists():
        import urllib.request
        logger.info("Downloading %s from %s to %s", font_filename, url, font_path)
        try:
            req = urllib.request.Request(
                url, 
                headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
            )
            with urllib.request.urlopen(req) as response, open(font_path, 'wb') as out_file:
                out_file.write(response.read())
            logger.info("Successfully downloaded %s", font_filename)
        except Exception as e:
            logger.error("Failed to download %s: %s. Falling back to system fonts.", font_filename, e)
    return font_path


def _render_islamic_slide(
    output_path: str,
    text: str,
    settings: Settings,
    language_code: str = "id",
) -> None:
    """
    Render an Islamic-aesthetic slide using Pillow.
    Palette: deep navy bg, gold accents, warm white text.
    Loads a template background image from assets if available.
    """
    W, H = settings.video_slide_width, settings.video_slide_height
    accent = settings.video_slide_accent_color
    text_color = settings.video_slide_text_color
    sub_color = settings.video_slide_sub_color

    # Load background template
    assets_dir = Path(__file__).parent.parent / "assets"
    bg_template_path = assets_dir / "bg_template.png"

    if bg_template_path.exists():
        img = Image.open(bg_template_path).convert("RGB")
        if img.size != (W, H):
            img = img.resize((W, H), Image.Resampling.LANCZOS)
    else:
        logger.warning("bg_template.png not found at %s. Falling back to solid color bg.", bg_template_path)
        bg_color = settings.video_slide_bg_color
        img = Image.new("RGB", (W, H), color=bg_color)

    draw = ImageDraw.Draw(img)

    # ── Text bounding box bounds ──────────────────────────────────────────
    inner = 30

    # ── Try to load fonts, fallback to default ────────────────────────────
    font_path = _ensure_font_for_language(language_code)
    try:
        # Scale font down dynamically if text is long
        text_size = 54
        if len(text) > 80:
            text_size = 42
        if len(text) > 120:
            text_size = 32

        if font_path.exists():
            font_title = ImageFont.truetype(str(font_path), 32)
            font_text = ImageFont.truetype(str(font_path), text_size)
            font_small = ImageFont.truetype(str(font_path), 18)
        else:
            font_title = ImageFont.truetype("arial.ttf", 32)
            font_text = ImageFont.truetype("arial.ttf", text_size)
            font_small = ImageFont.truetype("arial.ttf", 18)
    except Exception:
        font_title = ImageFont.load_default()
        font_text = font_title
        font_small = font_title

    # ── Bismillah header ──────────────────────────────────────────────────
    draw.text((W // 2, H // 6), _BISMILLAH, font=font_small, fill=accent, anchor="mm")

    # ── Star pattern divider ──────────────────────────────────────────────
    draw.text((W // 2, H // 6 + 30), _STAR_PATTERN, font=font_small, fill=sub_color, anchor="mm")

    # ── Main narration text (word-wrapped) ────────────────────────────────
    line_spacing = int(text_size * 1.3)
    _draw_wrapped_text(draw, text, font=font_text, fill=text_color, box=(inner + 60, H // 4, W - inner - 60, H - H // 4), line_spacing=line_spacing)

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


def _run_ffmpeg_concat(
    list_path: str,
    output_path: str,
    settings: Settings,
) -> None:
    """
    Run FFmpeg concat demuxer synchronously to merge clips.
    """
    cwd = str(Path(list_path).parent)
    cmd = [
        settings.ffmpeg_path,
        "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", Path(list_path).name,
        "-c", "copy",
        Path(output_path).name,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg concat failed: {result.stderr}")


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
    settings: Settings = None,
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

            if settings:
                from app.models.user import Message, MessageRole
                video_url = f"{settings.media_base_url}/{file_path}"
                new_msg = Message(
                    session_id=media.session_id,
                    role=MessageRole.assistant,
                    content="Berikut adalah video yang di-generate berdasarkan konteks percakapan kita:",
                    meta={
                        "media_type": "video",
                        "url": video_url,
                        "media_id": str(media_id)
                    }
                )
                db.add(new_msg)
        else:
            media.error_message = error

    await db.commit()
