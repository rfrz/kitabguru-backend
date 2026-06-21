"""
Inisialisasi package models untuk mendefinisikan skema tabel database (SQLAlchemy).
Mengimpor semua kelas model di sini agar Alembic dapat melacak metadata skema saat membuat migrasi.
"""

# Mengimpor model yang berkaitan dengan data user, token, sesi obrolan, dan peran pesan
from app.models.user import User, RefreshToken, ChatSession, Message, UserRole, MessageRole  # noqa: F401
# Mengimpor model yang berkaitan dengan manajemen media yang dihasilkan (gambar, video) dan statusnya
from app.models.media import GeneratedMedia, MediaJob, MediaType, MediaStatus, JobStatus  # noqa: F401
# Mengimpor model yang berkaitan dengan riwayat komunikasi dan sesi perangkat IoT
from app.models.iot import IoTSession, IoTMessage, IoTMessageRole  # noqa: F401

# Mendaftarkan semua model ke dalam __all__ agar diimpor saat import * dipanggil
__all__ = [
    "User",             # Tabel data user terdaftar
    "RefreshToken",     # Tabel penyimpanan token refresh JWT aktif
    "ChatSession",      # Tabel sesi percakapan chat AI
    "Message",          # Tabel histori pesan di dalam sesi chat
    "UserRole",         # Enum peran user (USER, ADMIN)
    "MessageRole",      # Enum pengirim pesan (USER, ASSISTANT, SYSTEM)
    "GeneratedMedia",   # Tabel daftar aset media hasil generate AI (gambar/video)
    "MediaJob",         # Tabel antrean pekerjaan background generator media
    "MediaType",        # Enum jenis media (IMAGE, VIDEO)
    "MediaStatus",      # Enum status ketersediaan media (PENDING, COMPLETED, FAILED)
    "JobStatus",        # Enum status pekerjaan background (QUEUED, RUNNING, COMPLETED, FAILED)
    "IoTSession",       # Tabel sesi komunikasi antara IoT dan server
    "IoTMessage",       # Tabel histori pesan percakapan khusus perangkat IoT
    "IoTMessageRole",   # Enum peran pesan IoT (USER, ASSISTANT)
]
