"""
Tugas latar belakang (background task) pembuatan video: teks narasi → audio TTS → slide bertema Islami → FFmpeg → MP4.
Berjalan menggunakan BackgroundTasks FastAPI agar tidak memblokir respon HTTP client.
"""
# Mengimpor modul asyncio untuk jeda dan pemanggilan thread executor
import asyncio
# Mengimpor modul logging untuk pencatatan logs pengerjaan video
import logging
# Mengimpor modul subprocess untuk menjalankan perintah FFmpeg sistem
import subprocess
# Mengimpor modul uuid untuk pembuatan nama file unik
import uuid
# Mengimpor datetime, timezone untuk penanda waktu pengerjaan job
from datetime import datetime, timezone
# Mengimpor Path untuk pengelolaan folder lokal
from pathlib import Path

# Mengimpor komponen PIL (Pillow) untuk membuat/menggambar slide video presentasi
from PIL import Image, ImageDraw, ImageFont
# Mengimpor AsyncSession untuk penanganan transaksi database asinkron
from sqlalchemy.ext.asyncio import AsyncSession

# Mengimpor skema Settings untuk mengambil palet warna dan resolusi video
from app.config import Settings
# Mengimpor model GeneratedMedia, JobStatus, MediaJob, dan MediaStatus
from app.models.media import GeneratedMedia, JobStatus, MediaJob, MediaStatus
# Mengimpor client EdgeTTS
from app.providers.edge_tts import EdgeTTSClient

# Menginisialisasi logger sistem khusus modul video_pipeline ini
logger = logging.getLogger(__name__)

# Teks bismillah arab untuk dipasang sebagai header slide video
_BISMILLAH = "بِسْمِ Lَّهِ الرَّحْمَنِ الرَّحِيمِ"
# Desain bintang pembatas islami untuk dekorasi slide
_STAR_PATTERN = "✦ ✧ ✦ ✧ ✦ ✧ ✦ ✧ ✦ ✧ ✦ ✧ ✦"


# Fungsi utama pipeline generator video yang dijalankan secara asinkron di background worker
async def run_video_pipeline(
    job_id: uuid.UUID,
    media_id: uuid.UUID,
    narration_text: str,
    language_code: str,
    session_maker,  # AsyncSessionLocal factory
    settings: Settings,
) -> None:
    """
    Alur pipeline pembuatan video asinkron lengkap:
    1. Memecah teks narasi menjadi potongan kalimat pendek (maks 10-15 kata).
    2. Iterasi untuk setiap potongan kalimat:
       a. Mensintesis teks menjadi file suara audio_{i}.wav (EdgeTTS).
       b. Menggambar teks slide menjadi gambar slide_{i}.png bertema Islami (Pillow).
       c. Menggabungkan audio_{i}.wav dan slide_{i}.png menjadi clip_{i}.mp4 (FFmpeg).
    3. Menggabungkan seluruh potongan video clip_*.mp4 menjadi file video final {media_id}.mp4.
    4. Menghapus file-file sementara (audio, gambar, klip kecil).
    5. Menyimpan relative path video jadi ke database dan merubah status job menjadi completed.
    """
    # Mengimpor modul regex
    import re

    # Menentukan path folder penyimpanan media
    media_dir = Path(settings.media_dir)
    # Membuat subfolder baru khusus untuk menampung pengerjaan job ini
    job_dir = media_dir / str(media_id)
    job_dir.mkdir(parents=True, exist_ok=True)

    # Path file video akhir (.mp4)
    video_path = job_dir / f"{media_id}.mp4"
    # Path file teks daftar video yang digunakan FFmpeg concat
    list_path = job_dir / "clips.txt"

    # Membuka sesi database untuk mengubah status job menjadi sedang diproses (processing)
    async with session_maker() as db:
        await _update_job(db, job_id, JobStatus.processing, progress_pct=0)

    # Memisahkan naskah narasi berdasarkan tanda baca titik, tanda seru, tanya, atau baris baru
    raw_sentences = re.split(r'(?<=[.!?。！？])\s*|\n+', narration_text.strip())
    # Membuang spasi kosong di ujung string dan menyaring kalimat kosong
    chunks = [s.strip() for s in raw_sentences if s.strip()]
    # Jika hasil pemisahan kosong, gunakan seluruh teks narasi langsung sebagai satu-satunya slide
    if not chunks:
        chunks = [narration_text.strip()]

    # Membuat list penampung file sementara untuk dibersihkan di akhir program
    temp_files = [list_path]
    # List penampung path video potongan kecil (clips)
    clip_paths = []

    # Memulai blok try-except-finally pemrosesan pipeline
    try:
        # Melakukan perulangan untuk memproses setiap kalimat menjadi satu klip video kecil
        for i, chunk in enumerate(chunks):
            # Mencatat log informasi pengerjaan slide kalimat ke-i
            logger.info("[video:%s] Processing chunk %d/%d: %s", job_id, i + 1, len(chunks), chunk)
            
            # Menentukan path file suara sementara
            chunk_audio_path = job_dir / f"audio_{i}.wav"
            # Menentukan path file gambar slide sementara
            chunk_slide_path = job_dir / f"slide_{i}.png"
            # Menentukan path file klip video sementara
            chunk_clip_path = job_dir / f"clip_{i}.mp4"
            
            # Daftarkan path file sementara ke list pembersihan
            temp_files.extend([chunk_audio_path, chunk_slide_path, chunk_clip_path])
            
            # Langkah 1: Sintesis Suara (TTS)
            # Menentukan tipe pengisi suara berdasarkan bahasa naskah
            voice = get_voice_for_language(language_code)
            tts = EdgeTTSClient(settings)
            # Menjalankan TTS asinkron untuk menyimpan suara kalimat ke file wav
            await tts.synthesize(chunk, str(chunk_audio_path), voice=voice)
            
            # Langkah 2: Menggambar Gambar Slide Presentasi Islami (Pillow)
            # Dijalankan di thread executor (run_in_executor) agar proses manipulasi gambar CPU-heavy tidak memblokir event loop
            await asyncio.get_event_loop().run_in_executor(
                None, _render_islamic_slide, str(chunk_slide_path), chunk, settings, language_code
            )
            
            # Langkah 3: Menggabungkan gambar slide dan file audio suara menjadi satu klip video mp4 pendek menggunakan FFmpeg
            await asyncio.get_event_loop().run_in_executor(
                None, _run_ffmpeg, str(chunk_slide_path), str(chunk_audio_path), str(chunk_clip_path), settings
            )
            
            # Memasukkan path klip jadi ke list
            clip_paths.append(chunk_clip_path)
            
            # Menghitung persentase kemajuan pengerjaan (skala 0 sampai 90%)
            progress = int((i + 1) / len(chunks) * 90)
            # Memperbarui kemajuan persen pengerjaan job di database
            async with session_maker() as db:
                await _update_job(db, job_id, JobStatus.processing, progress_pct=progress)

        # Langkah 4: Menggabungkan seluruh potongan video clip_*.mp4 menjadi video final
        logger.info("[video:%s] Concatenating %d clips into final video", job_id, len(clip_paths))
        
        # Menulis nama-nama file klip kecil ke file teks clips.txt sebagai input demuxer FFmpeg
        with open(list_path, "w", encoding="utf-8") as f:
            for cp in clip_paths:
                # Menulis baris format file 'nama_file'
                f.write(f"file '{cp.name}'\n")
        
        # Mengeksekusi command FFmpeg concat secara sinkron di thread terpisah
        await asyncio.get_event_loop().run_in_executor(
            None, _run_ffmpeg_concat, str(list_path), str(video_path), settings
        )

        # Langkah 5: Menyimpan detail hasil finalisasi video ke database
        # Menghitung path relatif video untuk diakses publik
        relative_path = str(video_path.relative_to(media_dir)).replace("\\", "/")
        # Mendapatkan ukuran file video jadi
        file_size = video_path.stat().st_size if video_path.exists() else None

        # Memperbarui data media generated di database menjadi sukses (completed)
        async with session_maker() as db:
            await _finalize_media(
                db, job_id, media_id,
                file_path=relative_path,
                file_size=file_size,
                success=True,
                settings=settings,
            )
        logger.info("[video:%s] Pipeline complete → %s", job_id, video_path)

    # Menangkap error jika proses pembuatan video gagal di tengah jalan
    except Exception as exc:
        # Mencatat stacktrace logs error kegagalan
        logger.exception("[video:%s] Pipeline failed: %s", job_id, exc)
        # Memperbarui status media di database menjadi gagal (failed)
        async with session_maker() as db:
            await _finalize_media(db, job_id, media_id, error=str(exc), settings=settings)
    # Blok finally untuk menghapus seluruh file-file sementara demi menghemat kapasitas disk server
    finally:
        for tmp_file in temp_files:
            try:
                # Jika file sementara masih ada di disk
                if tmp_file.exists():
                    # Hapus file tersebut
                    tmp_file.unlink()
            # Abaikan jika ada kegagalan penghapusan file sementara
            except Exception as e:
                logger.warning("[video:%s] Failed to delete temp file %s: %s", job_id, tmp_file, e)


# ─── Utilitas Desain & Rendering (Rendering Utilities) ─────────────────────────

# Menyeleksi suara neural EdgeTTS berdasarkan bahasa naskah video
def get_voice_for_language(language_code: str) -> str:
    """Mencocokkan kode bahasa ke pengisi suara standard yang didukung EdgeTTS."""
    # Ubah format string bahasa menjadi huruf kecil dan bersihkan whitespace
    lang = language_code.lower().strip()
    # Jika Bahasa Indonesia
    if lang.startswith("id"):
        return "id-ID-ArdiNeural"
    # Jika Bahasa Inggris
    elif lang.startswith("en"):
        return "en-US-AriaNeural"
    # Jika Bahasa Jepang
    elif lang.startswith("ja"):
        return "ja-JP-NanamiNeural"
    # Jika Bahasa Arab
    elif lang.startswith("ar"):
        return "ar-SA-HamedNeural"
    # Jika Bahasa Melayu
    elif lang.startswith("ms"):
        return "ms-MY-YasminNeural"
    # Jika Bahasa Mandarin
    elif lang.startswith("zh"):
        return "zh-CN-XiaoxiaoNeural"
    # Jika Bahasa Turki
    elif lang.startswith("tr"):
        return "tr-TR-AhmetNeural"
    # Jika Bahasa Prancis
    elif lang.startswith("fr"):
        return "fr-FR-DeniseNeural"
    # Jika Bahasa Spanyol
    elif lang.startswith("es"):
        return "es-ES-AlvaroNeural"
    # Jika Bahasa Jerman
    elif lang.startswith("de"):
        return "de-DE-KillianNeural"
    # Respon default menggunakan Bahasa Indonesia suara Ardi
    return "id-ID-ArdiNeural"


# Menentukan file font dan URL unduhan yang sesuai berdasarkan bahasa agar karakter unicode tampil sempurna
def _get_font_info_for_language(language_code: str) -> tuple[str, str]:
    """Mendapatkan nama file font dan link unduhan berdasarkan jenis bahasa."""
    lang = language_code.lower().strip()
    # Pilihan font Jepang
    if lang.startswith("ja"):
        return ("NotoSansJP-Medium.otf", "https://raw.githubusercontent.com/notofonts/noto-cjk/main/Sans/OTF/Japanese/NotoSansCJKjp-Medium.otf")
    # Pilihan font Mandarin
    elif lang.startswith("zh"):
        return ("NotoSansSC-Medium.otf", "https://raw.githubusercontent.com/notofonts/noto-cjk/main/Sans/OTF/SimplifiedChinese/NotoSansCJKsc-Medium.otf")
    # Pilihan font Korea
    elif lang.startswith("ko"):
        return ("NotoSansKR-Medium.otf", "https://raw.githubusercontent.com/notofonts/noto-cjk/main/Sans/OTF/Korean/NotoSansCJKkr-Medium.otf")
    # Pilihan font Arab
    elif lang.startswith("ar"):
        return ("NotoSansArabic-Medium.ttf", "https://raw.githubusercontent.com/notofonts/arabic/main/fonts/NotoSansArabic/hinted/ttf/NotoSansArabic-Medium.ttf")
    # Font default Roboto untuk bahasa latin
    return ("Roboto-Medium.ttf", "https://cdnjs.cloudflare.com/ajax/libs/pdfmake/0.1.66/fonts/Roboto/Roboto-Medium.ttf")


# Memastikan file font bahasa ada di server lokal, jika tidak ada, sistem akan mengunduhnya otomatis
def _ensure_font_for_language(language_code: str) -> Path:
    """Memastikan font bahasa tersedia di folder app/assets, unduh otomatis jika belum ada."""
    # Mendapatkan info nama font dan URL
    font_filename, url = _get_font_info_for_language(language_code)
    # Menentukan path direktori folder assets
    assets_dir = Path(__file__).parent.parent / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    # Menentukan path file font akhir
    font_path = assets_dir / font_filename
    # Jika file font belum ada
    if not font_path.exists():
        import urllib.request
        # Mencatat logs pengunduhan font
        logger.info("Downloading %s from %s to %s", font_filename, url, font_path)
        try:
            # Mengunduh file font menggunakan HTTP request dengan User-Agent agar tidak terblokir
            req = urllib.request.Request(
                url, 
                headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
            )
            # Menyimpan stream data biner font ke file lokal
            with urllib.request.urlopen(req) as response, open(font_path, 'wb') as out_file:
                out_file.write(response.read())
            logger.info("Successfully downloaded %s", font_filename)
        # Menangkap error kegagalan unduh font
        except Exception as e:
            logger.error("Failed to download %s: %s. Falling back to system fonts.", font_filename, e)
    # Mengembalikan path file font
    return font_path


# Menggambar layout slide presentasi islami bertema navy-gold menggunakan Pillow
def _render_islamic_slide(
    output_path: str,
    text: str,
    settings: Settings,
    language_code: str = "id",
) -> None:
    """
    Menggambar slide presentasi menggunakan Pillow dengan palet warna navy-gold Islami.
    Memakai template background gambar jika tersedia di assets.
    """
    # Membaca dimensi slide video dari settings
    W, H = settings.video_slide_width, settings.video_slide_height
    # Membaca warna aksen emas
    accent = settings.video_slide_accent_color
    # Membaca warna teks putih
    text_color = settings.video_slide_text_color
    # Membaca warna terjemahan teal
    sub_color = settings.video_slide_sub_color

    # Path template background gambar islami
    assets_dir = Path(__file__).parent.parent / "assets"
    bg_template_path = assets_dir / "bg_template.png"

    # Jika file template background gambar ada
    if bg_template_path.exists():
        # Membuka gambar template background
        img = Image.open(bg_template_path).convert("RGB")
        # Jika resolusi template tidak pas, lakukan resize ulang dengan filter Lanczos
        if img.size != (W, H):
            img = img.resize((W, H), Image.Resampling.LANCZOS)
    # Jika template gambar tidak ditemukan, gunakan warna solid navy sebagai background
    else:
        logger.warning("bg_template.png not found at %s. Falling back to solid color bg.", bg_template_path)
        bg_color = settings.video_slide_bg_color
        img = Image.new("RGB", (W, H), color=bg_color)

    # Inisiasi objek draw Pillow
    draw = ImageDraw.Draw(img)

    # Batas margin dalam slide
    inner = 30

    # Memuat file font yang sesuai dengan bahasa naskah
    font_path = _ensure_font_for_language(language_code)
    try:
        # Menentukan ukuran default teks slide ke 54
        text_size = 54
        # Perkecil ukuran font jika naskah kalimat agak panjang agar tidak meluap keluar slide
        if len(text) > 80:
            text_size = 42
        # Jika kalimat sangat panjang, perkecil font ke ukuran 32
        if len(text) > 120:
            text_size = 32

        # Jika file font ada di disk
        if font_path.exists():
            font_title = ImageFont.truetype(str(font_path), 32)
            font_text = ImageFont.truetype(str(font_path), text_size)
            font_small = ImageFont.truetype(str(font_path), 18)
        # Jika font tidak ditemukan, gunakan font arial sistem
        else:
            font_title = ImageFont.truetype("arial.ttf", 32)
            font_text = ImageFont.truetype("arial.ttf", text_size)
            font_small = ImageFont.truetype("arial.ttf", 18)
    # Jika gagal memuat font sistem apa pun, gunakan default font Pillow
    except Exception:
        font_title = ImageFont.load_default()
        font_text = font_title
        font_small = font_title

    # Menggambar tulisan bismillah arab di bagian atas tengah slide
    draw.text((W // 2, H // 6), _BISMILLAH, font=font_small, fill=accent, anchor="mm")

    # Menggambar garis pembatas dekorasi bintang di bawah tulisan bismillah
    draw.text((W // 2, H // 6 + 30), _STAR_PATTERN, font=font_small, fill=sub_color, anchor="mm")

    # Menggambar naskah teks utama dengan fitur word-wrap otomatis di tengah slide
    line_spacing = int(text_size * 1.3)
    _draw_wrapped_text(
        draw, text, 
        font=font_text, 
        fill=text_color, 
        box=(inner + 60, H // 4, W - inner - 60, H - H // 4), 
        line_spacing=line_spacing
    )

    # Menggambar watermark "KitabGuru" di bagian bawah slide
    draw.text((W // 2, H - H // 6), "KitabGuru", font=font_small, fill=sub_color, anchor="mm")
    # Menggambar dekorasi aksen bintang di bagian footer bawah
    draw.text((W // 2, H - H // 6 + 24), _STAR_PATTERN, font=font_small, fill=accent, anchor="mm")

    # Menyimpan hasil slide gambar ke format PNG
    img.save(output_path, "PNG")


# Fungsi pembantu untuk membagi teks kalimat panjang ke beberapa baris agar pas di dalam kotak bounding box
def _draw_wrapped_text(
    draw: ImageDraw.Draw,
    text: str,
    font,
    fill: str,
    box: tuple[int, int, int, int],
    line_spacing: int = 32,
) -> None:
    """Menggambar teks rata tengah dengan membungkus baris kata secara dinamis di dalam kotak pembatas."""
    # Membongkar koordinat kotak pembatas
    x1, y1, x2, y2 = box
    # Menghitung lebar maksimal kotak pembatas
    max_width = x2 - x1
    # Memisahkan teks kalimat menjadi kata-kata tunggal
    words = text.split()
    # List untuk menyimpan baris-baris kata hasil bungkus
    lines: list[str] = []
    # Variabel string untuk menyusun baris saat ini
    current = ""

    # Iterasi melalui setiap kata
    for word in words:
        # Coba gabungkan kata ke baris saat ini
        test = f"{current} {word}".strip()
        # Mengukur lebar pixel teks gabungan tersebut menggunakan font aktif
        w = draw.textlength(test, font=font)
        # Jika lebarnya masih muat di dalam batas kotak
        if w <= max_width:
            # Terima penggabungan kata
            current = test
        # Jika kata baru tersebut menyebabkan teks meluap keluar kotak
        else:
            # Jika baris sebelumnya tidak kosong, simpan baris tersebut ke list lines
            if current:
                lines.append(current)
            # Mulai baris baru dengan kata saat ini
            current = word
    # Menyimpan kata terakhir yang tersisa
    if current:
        lines.append(current)

    # Menghitung tinggi total seluruh baris teks
    total_h = len(lines) * line_spacing
    # Menghitung koordinat y awal agar teks berada tepat di tengah kotak secara vertikal
    y = y1 + ((y2 - y1) - total_h) // 2
    # Menghitung titik koordinat x tengah horizontal
    cx = (x1 + x2) // 2

    # Menggambar setiap baris teks ke slide gambar
    for line in lines:
        # Menggambar teks rata tengah horizontal (anchor="mm")
        draw.text((cx, y), line, font=font, fill=fill, anchor="mm")
        # Bergeser ke baris bawahnya
        y += line_spacing


# ─── Pengeksekusian Perintah FFmpeg (FFmpeg Execution Utilities) ────────────────

# Menjalankan program FFmpeg sistem untuk menggabungkan gambar diam dan suara audio ke video klip
def _run_ffmpeg(
    slide_path: str,
    audio_path: str,
    output_path: str,
    settings: Settings,
) -> None:
    """
    Menjalankan FFmpeg secara sinkron untuk menggabungkan gambar diam slide.png dan audio.wav menjadi video clip.mp4.
    """
    # Menyusun argumen command line FFmpeg
    cmd = [
        # Path file executable FFmpeg
        settings.ffmpeg_path,
        "-y",                       # Selalu timpa (overwrite) file jika sudah ada
        "-loop", "1",               # Loop gambar tunggal secara terus-menerus
        "-i", slide_path,           # Input file gambar slide
        "-i", audio_path,           # Input file audio suara
        "-c:v", "libx264",          # Menggunakan codec video H.264 standar
        "-tune", "stillimage",      # Optimasi codec untuk memproses gambar diam
        "-c:a", "aac",              # Menggunakan codec audio AAC
        "-b:a", "192k",             # Set bitrate audio ke 192kbps
        "-pix_fmt", "yuv420p",      # Format warna yuv420p agar kompatibel dengan pemutar HTML5
        "-shortest",                # Hentikan video segera saat file audio habis
        output_path,                # File output klip jadi
    ]
    # Mengeksekusi command line di sub-proses sistem operasi
    result = subprocess.run(cmd, capture_output=True, text=True)
    # Jika kode keluar program (returncode) bukan 0 (artinya terjadi kegagalan)
    if result.returncode != 0:
        # Lempar error runtime beserta logs kesalahan dari FFmpeg
        raise RuntimeError(f"FFmpeg failed: {result.stderr}")


# Menjalankan program FFmpeg demuxer untuk menggabungkan banyak video klip kecil menjadi satu video final
def _run_ffmpeg_concat(
    list_path: str,
    output_path: str,
    settings: Settings,
) -> None:
    """
    Menjalankan FFmpeg concat demuxer untuk menggabungkan seluruh klip video pendek menjadi satu file video utuh.
    """
    # Menetapkan working directory ke folder tempat file clips.txt berada
    cwd = str(Path(list_path).parent)
    # Menyusun argumen concat FFmpeg
    cmd = [
        settings.ffmpeg_path,
        "-y",                       # Timpa output file
        "-f", "concat",             # Menggunakan format concat demuxer
        "-safe", "0",               # Mengabaikan pengecekan nama file aman (agar bisa membaca absolute path)
        "-i", Path(list_path).name, # File input daftar video (clips.txt)
        "-c", "copy",               # Salin langsung codec video/audio tanpa proses transcoding ulang (sangat cepat)
        Path(output_path).name,     # Nama file video output
    ]
    # Menjalankan sub-proses FFmpeg di folder kerja yang ditentukan
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd)
    # Memeriksa kegagalan proses concat
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg concat failed: {result.stderr}")


# ─── DB Helpers ───────────────────────────────────────────────────────────────

# Memperbarui kemajuan persentase (progress) status pekerjaan job di database
async def _update_job(
    db: AsyncSession,
    job_id: uuid.UUID,
    job_status: JobStatus,
    progress_pct: int = 0,
) -> None:
    """Memperbarui status pengerjaan dan persentase progress job video di database."""
    from sqlalchemy import select
    # Mencari record MediaJob berdasarkan ID job
    result = await db.execute(select(MediaJob).where(MediaJob.id == job_id))
    job = result.scalar_one_or_none()
    # Jika record job ditemukan di database
    if job:
        # Menetapkan status pengerjaan baru
        job.status = job_status
        # Menetapkan persentase kemajuan pengerjaan
        job.progress_pct = progress_pct
        # Jika status berubah menjadi processing dan waktu mulai (started_at) belum diset
        if job_status == JobStatus.processing and not job.started_at:
            # Set tanggal-waktu mulai ke waktu UTC sekarang
            job.started_at = datetime.now(timezone.utc)
        # Commit perubahan ke database
        await db.commit()


# Memfinalisasi status pekerjaan dan media di database setelah pipeline selesai
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
    """Menyelesaikan tugas background job di database, mencatat lokasi video jadi atau menulis logs error jika gagal."""
    from sqlalchemy import select
    # Mendapatkan tanggal UTC saat ini
    now = datetime.now(timezone.utc)

    # 1. Memperbarui status pengerjaan tabel MediaJob
    job_result = await db.execute(select(MediaJob).where(MediaJob.id == job_id))
    job = job_result.scalar_one_or_none()
    if job:
        # Set status completed jika sukses, atau failed jika terjadi error
        job.status = JobStatus.completed if success else JobStatus.failed
        # Jika sukses, set persentase progress ke 100%
        job.progress_pct = 100 if success else job.progress_pct
        # Set tanggal selesai pengerjaan
        job.completed_at = now
        # Menyimpan rincian kesalahan jika pengerjaan gagal
        job.error_detail = error

    # 2. Memperbarui status ketersediaan video di tabel GeneratedMedia
    media_result = await db.execute(select(GeneratedMedia).where(GeneratedMedia.id == media_id))
    media = media_result.scalar_one_or_none()
    if media:
        # Mengubah status media menjadi completed atau failed
        media.status = MediaStatus.completed if success else MediaStatus.failed
        # Jika pengerjaan pembuatan video sukses
        if success:
            # Menyimpan path file video jadi
            media.file_path = file_path
            # Menyimpan ukuran kapasitas file video
            media.file_size_bytes = file_size
            # Menyimpan tanggal selesai
            media.completed_at = now

            # Jika objek settings dikirim (untuk menyisipkan balon chat baru)
            if settings:
                from app.models.user import Message, MessageRole
                # Menyusun URL publik video
                video_url = f"{settings.media_base_url}/{file_path}"
                # Membuat balon pesan chat AI baru yang menampilkan link video
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
                # Menyimpan pesan baru ke database
                db.add(new_msg)
        # Jika pengerjaan gagal
        else:
            # Menyimpan detail pesan kesalahan di kolom error GeneratedMedia
            media.error_message = error

    # Commit seluruh perubahan finalisasi ke database secara permanen
    await db.commit()
