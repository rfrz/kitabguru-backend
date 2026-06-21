"""
KitabGuru Backend — FastAPI Application Entry Point.
File utama untuk menjalankan server backend FastAPI, mendaftarkan router API,
mengaktifkan middleware CORS, static media folder, rate limiter, dan lifecycle hook (lifespan).

Lifecycle:
  - startup: memastikan media dir, seeding admin user awal, menjalankan penjadwal hapus asinkron
  - shutdown: menutup koneksi klien inferensi RAG dan menutup engine pool database
"""
# Mengimpor modul logging untuk pencatatan log sistem
import logging
# Mengimpor utilitas context manager asinkron untuk mendefinisikan lifecycle aplikasi
from contextlib import asynccontextmanager

# Mengimpor class utama FastAPI untuk inisiasi web framework
from fastapi import FastAPI
# Mengimpor middleware CORS untuk menangani otorisasi request lintas origin
from fastapi.middleware.cors import CORSMiddleware
# Mengimpor modul StaticFiles untuk mengekspos folder lokal ke internet sebagai file statis
from fastapi.staticfiles import StaticFiles

# Mengimpor helper pengambil konfigurasi aplikasi
from app.config import get_settings
# Mengimpor pembuat sesi database, engine, dan kelas Base dari database.py
from app.database import AsyncSessionLocal, engine, Base

# Menginisialisasi logger sistem khusus untuk file main ini
logger = logging.getLogger(__name__)


# Fungsi internal untuk membuat data admin secara otomatis (seeding) jika belum terdaftar
async def _seed_admin() -> None:
    """Membuat user admin dari variabel env apabila belum ada di database."""
    # Mengimpor select untuk membangun query pencarian data di database
    from sqlalchemy import select
    # Mengimpor model User dan enum UserRole dari models
    from app.models.user import User, UserRole
    # Mengimpor fungsi hashing password dari modul security
    from app.core.security import hash_password

    # Mengambil konfigurasi aplikasi saat ini
    settings = get_settings()
    # Membuka sesi database asinkron secara otomatis
    async with AsyncSessionLocal() as db:
        # Melakukan query pencarian user berdasarkan alamat email admin dari konfigurasi
        result = await db.execute(
            select(User).where(User.email == settings.admin_email)
        )
        # Mengambil satu baris data user hasil query, bernilai None jika tidak ditemukan
        existing = result.scalar_one_or_none()
        # Jika user admin dengan email tersebut sudah terdaftar
        if existing:
            # Mencatat log info bahwa user admin sudah terdaftar sebelumnya
            logger.info("Admin user already exists: %s", settings.admin_email)
            # Keluar dari fungsi seeding karena tidak perlu membuat admin baru
            return

        # Menginisialisasi objek User admin baru dengan data dari settings
        admin = User(
            # Menetapkan email admin dari config
            email=settings.admin_email,
            # Menetapkan username admin dari config
            username=settings.admin_username,
            # Mengenkripsi password admin sebelum disimpan ke database
            hashed_password=hash_password(settings.admin_password),
            # Memberikan peran administrator
            role=UserRole.admin,
            # Menetapkan status akun langsung aktif
            is_active=True,
        )
        # Menambahkan data admin baru ke unit of work database session
        db.add(admin)
        # Menyimpan dan menerapkan perubahan data ke database secara permanen
        await db.commit()
        # Mencatat log sukses melakukan seeding admin default
        logger.info("Admin user seeded: %s", settings.admin_email)


# Fungsi internal untuk menjalankan scheduler pembersihan soft-delete
async def _start_purge_scheduler() -> None:
    """Menjalankan scheduler di background untuk menghapus akun soft-deleted secara berkala."""
    # Blok try-except agar kegagalan scheduler tidak menghentikan startup aplikasi utama
    try:
        # Mengimpor fungsi penjadwal scheduler secara lokal
        from app.services.purge_service import start_purge_scheduler
        # Menjalankan fungsi scheduler pembersihan database
        start_purge_scheduler()
        # Mencatat log info bahwa scheduler berhasil dijalankan
        logger.info("Purge scheduler started")
    # Menangkap semua error yang terjadi saat mencoba menyalakan scheduler
    except Exception as exc:
        # Mencatat log peringatan kegagalan scheduler beserta isi error-nya
        logger.warning("Failed to start purge scheduler: %s", exc)


# Context manager asinkron untuk mengelola lifecycle siklus hidup startup dan shutdown FastAPI
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Mengelola siklus hidup aplikasi: startup dan shutdown hooks."""
    # Mengambil konfigurasi aplikasi saat ini
    settings = get_settings()

    # ── Startup Hooks (Dijalankan saat aplikasi mulai berjalan) ───────────
    # Mencatat log info bahwa backend KitabGuru sedang mulai dijalankan
    logger.info("Starting KitabGuru Backend (port %s)", settings.app_port)

    # Memastikan folder media lokal sudah ada dan siap digunakan
    settings.ensure_media_dir()

    # Menjalankan fungsi seeding database untuk akun administrator default
    await _seed_admin()

    # Menjalankan fungsi scheduler pembersihan database soft delete di background
    await _start_purge_scheduler()

    # Mengimpor client inferensi RAG secara lokal
    from app.providers.inference_client import InferenceClient
    # Menyimpan client inferensi ke dalam state aplikasi FastAPI agar bisa diakses global
    app.state.inference_client = InferenceClient(settings)
    # Menyimpan objek config settings ke dalam state aplikasi agar bisa diakses global
    app.state.settings = settings
    # Menyimpan pembuat sesi database ke dalam state aplikasi agar bisa diakses global
    app.state.session_maker = AsyncSessionLocal

    # Mencatat log info bahwa server backend siap menerima request
    logger.info("KitabGuru Backend ready")
    # Mengalirkan kendali kembali ke FastAPI untuk memproses request web
    yield

    # ── Shutdown Hooks (Dijalankan saat aplikasi dihentikan) ──────────────
    # Menutup koneksi HTTP client asinkron pada engine inferensi model RAG
    await app.state.inference_client.aclose()
    # Memutuskan semua koneksi database yang ada di dalam pool engine SQLAlchemy
    await engine.dispose()
    # Mencatat log bahwa proses shutdown backend telah selesai dengan aman
    logger.info("KitabGuru Backend shutdown complete")


# Fungsi pembangun aplikasi web FastAPI (Application Factory Pattern)
def create_app() -> FastAPI:
    # Mengambil konfigurasi settings aplikasi
    settings = get_settings()

    # Membuat instance aplikasi FastAPI lengkap dengan meta deskripsi dan konfigurasi docs
    app = FastAPI(
        # Judul API aplikasi backend
        title="KitabGuru Backend API",
        # Deskripsi fitur-fitur utama API backend KitabGuru
        description=(
            "Platform edukasi AI — Chat RAG, Image/Video Generation, IoT Voice Interface.\n\n"
            "Auth: Bearer JWT (access token) for user endpoints. X-API-Key header for IoT endpoints."
        ),
        # Versi build aplikasi
        version="1.0.0",
        # Menyeting path dokumentasi Swagger UI ke /docs
        docs_url="/docs",
        # Menyeting path dokumentasi alternatif Redoc ke /redoc
        redoc_url="/redoc",
        # Memasang asinkron lifespan handler yang telah didefinisikan sebelumnya
        lifespan=lifespan,
    )

    # ── Konfigurasi Middleware CORS (Cross-Origin Resource Sharing) ─────────
    # Memasang middleware CORS agar frontend dari port lain bisa mengakses API
    app.add_middleware(
        CORSMiddleware,
        # Membaca daftar domain asal yang diijinkan dari konfigurasi
        allow_origins=settings.cors_origin_list,
        # Mengijinkan pengiriman cookie / kredensial otentikasi
        allow_credentials=True,
        # Mengijinkan seluruh jenis method HTTP (GET, POST, PUT, DELETE, dll)
        allow_methods=["*"],
        # Mengijinkan seluruh tipe header HTTP request
        allow_headers=["*"],
    )

    # ── Penyajian File Statis Media (Static Files Serving) ─────────────────
    # Mengimpor library sistem operasi lokal
    import os
    # Membaca path folder media penyimpanan dari konfigurasi
    media_dir = settings.media_dir
    # Membuat folder penyimpanan media lokal jika belum ada di server disk
    os.makedirs(media_dir, exist_ok=True)
    # Memasang mount static file routing untuk menyajikan media di URL path /media
    app.mount("/media", StaticFiles(directory=media_dir), name="media")

    # ── Pendaftaran Router Endpoint API (Routing Registration) ─────────────
    # Mengimpor modul routing API untuk registrasi otentikasi (auth)
    from app.api.auth import router as auth_router
    # Mengimpor modul routing API untuk manajemen pengguna (users)
    from app.api.users import router as users_router
    # Mengimpor modul routing API untuk percakapan AI (chat)
    from app.api.chat import router as chat_router
    # Mengimpor modul routing API untuk pembuatan gambar/video (media)
    from app.api.media import router as media_router
    # Mengimpor modul routing API untuk integrasi hardware IoT (iot)
    from app.api.iot import router as iot_router
    # Mengimpor modul routing API untuk kontrol admin (admin)
    from app.api.admin import router as admin_router

    # Membaca prefix path utama API dari konfigurasi aplikasi
    prefix = settings.api_prefix
    # Mendaftarkan router auth ke bawah prefix API
    app.include_router(auth_router, prefix=f"{prefix}/auth", tags=["Auth"])
    # Mendaftarkan router manajemen user ke bawah prefix API
    app.include_router(users_router, prefix=f"{prefix}/users", tags=["Users"])
    # Mendaftarkan router chat AI ke bawah prefix API
    app.include_router(chat_router, prefix=f"{prefix}/chat", tags=["Chat"])
    # Mendaftarkan router generator media ke bawah prefix API
    app.include_router(media_router, prefix=f"{prefix}/media", tags=["Media"])
    # Mendaftarkan router IoT ke bawah prefix API
    app.include_router(iot_router, prefix=f"{prefix}/iot", tags=["IoT"])
    # Mendaftarkan router admin ke bawah prefix API
    app.include_router(admin_router, prefix=f"{prefix}/admin", tags=["Admin"])

    # ── Endpoint Cek Kesehatan Layanan (Health Check) ──────────────────────
    @app.get("/health", tags=["Health"])
    # Fungsi handler endpoint GET /health untuk memeriksa keaktifan service backend
    async def health():
        # Mengembalikan status json OK
        return {"status": "ok", "service": "kitabguru-backend"}

    # ── Rate Limiting ─────────────────────────────────────────────────────
    from slowapi import _rate_limit_exceeded_handler
    from slowapi.errors import RateLimitExceeded
    from app.core.rate_limit import limiter
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    # Mengembalikan objek aplikasi FastAPI yang sudah terkonfigurasi lengkap
    return app


# Membuat objek aplikasi global dengan memanggil create_app
app = create_app()


# Menjalankan server lokal secara langsung menggunakan uvicorn jika file dieksekusi langsung
if __name__ == "__main__":
    # Mengimpor modul uvicorn untuk web server ASGI
    import uvicorn
    # Mengambil konfigurasi setting aplikasi
    settings = get_settings()
    # Menjalankan aplikasi FastAPI di IP 0.0.0.0 dengan port dari settings serta fitur reload aktif
    uvicorn.run(
        # Menunjuk instance aplikasi FastAPI di modul app.main
        "app.main:app",
        # Mengikat server ke IP address global agar bisa diakses device lain
        host="0.0.0.0",
        # Menentukan port server web
        port=settings.app_port,
        # Mengaktifkan reload otomatis saat ada perubahan file (cocok untuk development)
        reload=True,
        # Menetapkan level pencatatan log server ke info
        log_level="info",
    )
