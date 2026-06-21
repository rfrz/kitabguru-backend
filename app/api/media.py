"""
Media generation routes:
  POST /media/generate/image        — Generate image from chat context
  POST /media/generate/video        — Start async video generation
  GET  /media/jobs/{job_id}         — Poll video job status
  GET  /media/{media_id}            — Get media metadata
  GET  /media/user                  — List all user media
"""
# Mengimpor modul uuid untuk keperluan validasi format dan pengolahan bertipe UUID
import uuid

# Mengimpor modul dari FastAPI untuk pembuatan router, tugas latar belakang, penanganan exception, dan status kode HTTP
from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, status
# Mengimpor modul select untuk menyusun kueri SQL SELECT di SQLAlchemy
from sqlalchemy import select
# Mengimpor AsyncSession untuk penulisan tipe data asinkron pada sesi database (opsional)
from sqlalchemy.ext.asyncio import AsyncSession

# Mengimpor dependensi database (DB), konfigurasi (AppSettings), dan info user yang masuk (CurrentUser)
from app.core.dependencies import DB, AppSettings, CurrentUser
# Mengimpor model data media, status pekerjaan, dan tipe media dari database
from app.models.media import GeneratedMedia, JobStatus, MediaJob, MediaStatus, MediaType
# Mengimpor skema data terstruktur untuk input dan output data generator media
from app.schemas.media import (
    ImageGenerateRequest,
    ImageGenerateResponse,
    JobStatusResponse,
    MediaListResponse,
    MediaOut,
    VideoGenerateRequest,
    VideoGenerateResponse,
)
# Mengimpor MediaService untuk mengeksekusi logika pembuatan gambar dan video
from app.services.media_service import MediaService

# Membuat objek APIRouter baru khusus untuk media
router = APIRouter()


# Menentukan rute POST '/generate/image' untuk menghasilkan gambar dari konteks percakapan chat
@router.post(
    "/generate/image",
    # Skema respons berupa detail pembuatan gambar yang sukses
    response_model=ImageGenerateResponse,
    # Menetapkan status HTTP respons ke 201 Created
    status_code=status.HTTP_201_CREATED,
    # Ringkasan dokumentasi
    summary="Generate image from current chat session context",
)
# Fungsi asinkron untuk memproses pembuatan gambar AI
async def generate_image(
    # Body request berisi ID sesi dan ID pesan acuan
    body: ImageGenerateRequest,
    # Objek request untuk mengakses client inference
    request: Request,
    # Memverifikasi user aktif saat ini
    current_user: CurrentUser,
    # Sesi database
    db: DB,
    # Konfigurasi aplikasi
    settings: AppSettings,
):
    """
    Meringkas sesi chat untuk membuat prompt gambar,
    lalu memanggil Cloudflare Workers AI (SDXL) untuk menghasilkan gambar.
    Gambar disimpan ke folder media/ dan rekam data GeneratedMedia dibuat di database.
    """
    # Mengambil objek klien inferensi terbagi dari app.state
    inference_client = request.app.state.inference_client
    # Membuat instans MediaService
    service = MediaService(db, settings, inference_client)
    # Memanggil fungsi generate_image pada service untuk memproses pembuatan gambar secara sinkron-asinkron
    return await service.generate_image(body.session_id, body.message_id, current_user)


# Menentukan rute POST '/generate/video' untuk memulai proses pembuatan video secara asinkronus (tugas latar belakang)
@router.post(
    "/generate/video",
    # Skema respons berisi ID job antrean video
    response_model=VideoGenerateResponse,
    # Menetapkan status HTTP ke 202 Accepted karena request diproses di latar belakang
    status_code=status.HTTP_202_ACCEPTED,
    # Ringkasan dokumentasi
    summary="Start async video generation from chat session",
)
# Fungsi asinkron untuk memulai proses antrean pembuatan video
async def generate_video(
    # Body request berisi ID sesi dan ID pesan acuan
    body: VideoGenerateRequest,
    # Objek BackgroundTasks untuk menambahkan tugas asinkron yang berjalan di luar thread utama FastAPI
    background_tasks: BackgroundTasks,
    # Objek request untuk mengakses state aplikasi
    request: Request,
    # Memverifikasi user aktif saat ini
    current_user: CurrentUser,
    # Sesi database
    db: DB,
    # Konfigurasi aplikasi
    settings: AppSettings,
):
    """
    Memulai pipeline video asinkron:
    chat → skrip narasi → audio Edge-TTS → slide estetika Islami → penggabungan FFmpeg MP4.
    Mengembalikan job_id untuk dipantau status pemrosesannya (polling).
    """
    # Mengambil objek klien inferensi terbagi dari app.state
    inference_client = request.app.state.inference_client
    # Mengambil pembuat sesi database terbagi (session_maker) agar thread latar belakang bisa membuka koneksi db sendiri
    session_maker = request.app.state.session_maker
    # Membuat instans MediaService
    service = MediaService(db, settings, inference_client)
    # Memanggil start_video_job pada service untuk mendaftarkan pekerjaan pembuatan video ke antrean tugas latar belakang
    return await service.start_video_job(body.session_id, body.message_id, current_user, background_tasks, session_maker)


# Menentukan rute GET '/jobs/{job_id}' untuk memantau (polling) status pembuatan video asinkron
@router.get(
    "/jobs/{job_id}",
    # Skema respons berupa status pekerjaan
    response_model=JobStatusResponse,
    # Ringkasan dokumentasi
    summary="Poll video generation job status",
)
# Fungsi asinkron untuk memeriksa status pekerjaan pembuatan video
async def get_job_status(
    # ID pekerjaan (job) dari URL
    job_id: str,
    # Memverifikasi user aktif
    current_user: CurrentUser,
    # Sesi database
    db: DB,
    # Konfigurasi aplikasi
    settings: AppSettings,
):
    """
    Memantau status pekerjaan pembuatan video.
    Ketika status berubah menjadi 'completed', properti video_url akan terisi.
    """
    try:
        # Mencoba memvalidasi string job_id menjadi objek tipe UUID
        jid = uuid.UUID(job_id)
    # Jika format UUID salah
    except ValueError:
        # Melemparkan HTTP Exception 404 Not Found
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    # Mengambil objek pekerjaan MediaJob dari database berdasarkan ID pekerjaan tersebut
    result = await db.execute(
        select(MediaJob).where(MediaJob.id == jid)
    )
    # Mendapatkan objek pekerjaan atau None jika tidak ditemukan
    job = result.scalar_one_or_none()
    # Jika pekerjaan tidak terdaftar
    if not job:
        # Melemparkan HTTP Exception 404 Not Found
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    # Memverifikasi kepemilikan pekerjaan dengan memeriksa apakah media terkait dibuat oleh pengguna yang sedang login
    media_result = await db.execute(
        select(GeneratedMedia).where(
            GeneratedMedia.id == job.media_id,
            GeneratedMedia.user_id == current_user.id,
        )
    )
    # Mendapatkan objek data media terkait atau None jika bukan milik user
    media = media_result.scalar_one_or_none()
    # Jika data media tidak ditemukan (berarti user mencoba mengakses milik orang lain atau ID media salah)
    if not media:
        # Melemparkan HTTP Exception 404 Not Found
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    # Inisialisasi video_url dengan None
    video_url = None
    # Jika status pekerjaan sudah selesai dan file path video di server telah terisi
    if job.status == JobStatus.completed and media.file_path:
        # Menyusun URL lengkap untuk memutar video tersebut di sisi klien
        video_url = f"{settings.media_base_url}/{media.file_path}"

    # Mengembalikan respons status pekerjaan terperinci beserta persentase progresnya
    return JobStatusResponse(
        # ID pekerjaan dalam bentuk string
        job_id=str(job.id),
        # Nilai string status pekerjaan (queued/processing/completed/failed)
        status=job.status.value,
        # Persentase progres saat ini
        progress_pct=job.progress_pct,
        # URL video jika sudah selesai
        video_url=video_url,
        # Keterangan error jika gagal
        error=job.error_detail,
        # Waktu pekerjaan dimulai
        started_at=job.started_at,
        # Waktu pekerjaan selesai
        completed_at=job.completed_at,
    )


# Menentukan rute GET '/user' untuk menampilkan semua daftar media yang pernah dihasilkan oleh pengguna yang aktif
@router.get(
    "/user",
    # Skema respons berupa daftar media
    response_model=MediaListResponse,
    # Ringkasan dokumentasi
    summary="List all media generated by current user",
)
# Fungsi asinkron untuk mengambil riwayat pembuatan media milik user
async def list_user_media(
    # Memverifikasi user aktif saat ini
    current_user: CurrentUser,
    # Sesi database
    db: DB,
):
    """Mengembalikan semua daftar gambar dan video yang dihasilkan oleh pengguna yang sedang aktif."""
    # Mencari seluruh data GeneratedMedia milik pengguna diurutkan dari yang terbaru dibuat
    result = await db.execute(
        select(GeneratedMedia)
        .where(GeneratedMedia.user_id == current_user.id)
        .order_by(GeneratedMedia.created_at.desc())
    )
    # Mendapatkan seluruh baris hasil pencarian dalam bentuk list
    media_list = result.scalars().all()
    # Mengonversi setiap objek media database menjadi format skema JSON keluaran MediaOut
    items = [_media_out(m) for m in media_list]
    # Mengembalikan daftar media beserta total jumlah medianya
    return MediaListResponse(media=items, total=len(items))


# Menentukan rute GET '/{media_id}' untuk mengambil metadata berkas media spesifik berdasarkan ID
@router.get(
    "/{media_id}",
    # Skema respons keluaran media
    response_model=MediaOut,
    # Ringkasan dokumentasi
    summary="Get metadata for a specific media item",
)
# Fungsi asinkron untuk mengambil profil satu item media
async def get_media(
    # ID media dari URL
    media_id: str,
    # Memverifikasi user aktif
    current_user: CurrentUser,
    # Sesi database
    db: DB,
):
    """Mengembalikan metadata untuk item media tertentu yang dihasilkan dan dimiliki oleh user saat ini."""
    try:
        # Mencoba memvalidasi format string media_id menjadi objek tipe UUID
        mid = uuid.UUID(media_id)
    # Jika format UUID salah
    except ValueError:
        # Melemparkan HTTP Exception 404 Not Found
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Media not found")

    # Mencari data media berdasarkan ID media dan ID pengguna di database
    result = await db.execute(
        select(GeneratedMedia).where(
            GeneratedMedia.id == mid,
            GeneratedMedia.user_id == current_user.id,
        )
    )
    # Mendapatkan satu objek media atau None jika tidak ditemukan
    media = result.scalar_one_or_none()
    # Jika media tidak terdaftar atau bukan milik user tersebut
    if not media:
        # Melemparkan HTTP Exception 404 Not Found
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Media not found")
    # Mengembalikan format skema keluaran dari media yang ditemukan
    return _media_out(media)


# ─── Helpers (Fungsi Pembantu) ────────────────────────────────────────────────

# Fungsi pembantu untuk memetakan model database GeneratedMedia ke skema keluaran JSON MediaOut
def _media_out(media: GeneratedMedia) -> MediaOut:
    return MediaOut(
        # Mengonversi UUID media menjadi string
        id=str(media.id),
        # Tipe media (image/video)
        media_type=media.media_type.value,
        # Lokasi path file media di server
        file_path=media.file_path,
        # Prompt deskripsi yang dipakai
        prompt_used=media.prompt_used,
        # Status pemrosesan media
        status=media.status.value,
        # Tanggal data media mulai dibuat
        created_at=media.created_at,
        # Tanggal selesai diproses (bisa bernilai null jika masih diproses/gagal)
        completed_at=media.completed_at,
    )
