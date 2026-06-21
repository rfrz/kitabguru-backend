# Mengimpor modul enum bawaan Python untuk mendefinisikan tipe enumerasi
import enum
# Mengimpor modul uuid untuk menggenerasi ID unik acak (UUID)
import uuid
# Mengimpor datetime dan timezone untuk penanganan waktu berbasis UTC secara akurat
from datetime import datetime, timezone
# Mengimpor Optional dari typing untuk menandai tipe data yang boleh bernilai None
from typing import Optional

# Mengimpor tipe-tipe kolom database dasar dari SQLAlchemy
from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text
# Mengimpor tipe data UUID PostgreSQL
from sqlalchemy.dialects.postgresql import UUID
# Mengimpor mapper modern SQLAlchemy dan relasi database ORM
from sqlalchemy.orm import Mapped, mapped_column, relationship

# Mengimpor Base class database
from app.database import Base


# Fungsi helper untuk mendapatkan tanggal dan waktu UTC saat ini
def utc_now() -> datetime:
    """Mengembalikan objek datetime saat ini dengan timezone UTC."""
    # Mengambil datetime sekarang dan memberikan informasi zona waktu UTC
    return datetime.now(timezone.utc)


# Kelas MediaType mendefinisikan jenis aset media yang didukung aplikasi
class MediaType(str, enum.Enum):
    # Aset berupa gambar statis
    image = "image"
    # Aset berupa video dinamis
    video = "video"


# Kelas MediaStatus mendefinisikan status ketersediaan file media di server
class MediaStatus(str, enum.Enum):
    # File media sedang dalam antrean atau pemrosesan asinkron
    processing = "processing"
    # File media sukses dibuat dan siap diakses/diunduh
    completed = "completed"
    # Proses pembuatan file media gagal karena error teknis
    failed = "failed"


# Kelas JobStatus mendefinisikan status pekerjaan background worker pembuatan media
class JobStatus(str, enum.Enum):
    # Pekerjaan dimasukkan ke dalam antrean tunggu (queue)
    queued = "queued"
    # Pekerjaan sedang dieksekusi oleh background worker
    processing = "processing"
    # Pekerjaan telah selesai dengan sukses
    completed = "completed"
    # Pekerjaan gagal dijalankan
    failed = "failed"


# Kelas model GeneratedMedia mencatat riwayat media hasil generate AI (gambar/video)
class GeneratedMedia(Base):
    # Menentukan nama tabel fisik database
    __tablename__ = "generated_media"

    # Kolom id primary key bertipe UUID
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # Kolom session_id opsional jika media dibuat di dalam sebuah sesi percakapan chat
    session_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        # Mengatur foreign key ke chat_sessions dan set nilainya ke NULL jika sesi dihapus
        ForeignKey("chat_sessions.id", ondelete="SET NULL"),
        # Membolehkan kolom bernilai null
        nullable=True,
        # Indeks kolom untuk optimasi filter media berdasarkan sesi chat
        index=True,
    )
    # Kolom user_id mencatat pemilik / pembuat media tersebut
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        # Mengatur foreign key ke tabel users dan menghapus media jika user dihapus
        ForeignKey("users.id", ondelete="CASCADE"),
        # Wajib diisi karena media harus punya pembuat
        nullable=False,
        # Indeks kolom
        index=True,
    )
    # Kolom media_type bertipe Enum (image/video)
    media_type: Mapped[MediaType] = mapped_column(
        Enum(MediaType, name="mediatype"), nullable=False
    )
    # Kolom file_path menyimpan lokasi file fisik media di filesystem server
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    # Kolom file_size_bytes menyimpan ukuran file dalam satuan byte (opsional)
    file_size_bytes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # Kolom prompt_used menyimpan teks instruksi yang digunakan untuk men-generate media
    prompt_used: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Kolom status menandai status ketersediaan media
    status: Mapped[MediaStatus] = mapped_column(
        Enum(MediaStatus, name="mediastatus"),
        nullable=False,
        # Default awal saat request dibuat adalah sedang diproses (processing)
        default=MediaStatus.processing,
    )
    # Kolom error_message menyimpan detail pesan kesalahan jika pembuatan media gagal
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Kolom created_at mencatat waktu request pembuatan media dikirim
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    # Kolom completed_at mencatat waktu selesai pemrosesan media (bisa null sebelum selesai)
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # ── Relasi Database ───────────────────────────────────────────────────
    # Relasi balik banyak-ke-satu ke model User
    user: Mapped["app.models.user.User"] = relationship(back_populates="generated_media")  # type: ignore[name-defined]
    # Relasi balik banyak-ke-satu ke model ChatSession (opsional)
    session: Mapped[Optional["app.models.user.ChatSession"]] = relationship(back_populates="generated_media")  # type: ignore[name-defined]
    # Relasi satu-ke-satu ke tabel MediaJob antrean background worker
    job: Mapped[Optional["MediaJob"]] = relationship(
        # Hubungan timbal balik dan hapus data job jika relasi media dihapus
        back_populates="media", uselist=False, cascade="all, delete-orphan"
    )


# Kelas model MediaJob mencatat detail status pekerjaan background task
class MediaJob(Base):
    # Menentukan nama tabel fisik database
    __tablename__ = "media_jobs"

    # Kolom id primary key bertipe UUID
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # Kolom media_id sebagai foreign key satu-ke-satu ke tabel generated_media
    media_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        # Mengatur foreign key dan hapus job jika relasi media dihapus
        ForeignKey("generated_media.id", ondelete="CASCADE"),
        nullable=False,
        # Memastikan relasi bersifat satu-ke-satu dengan properti unique=True
        unique=True,
        index=True,
    )
    # Kolom status menyimpan status terbaru eksekusi pekerjaan background task
    status: Mapped[JobStatus] = mapped_column(
        Enum(JobStatus, name="jobstatus"),
        nullable=False,
        # Default pekerjaan awal dimasukkan ke dalam antrean tunggu (queued)
        default=JobStatus.queued,
    )
    # Kolom progress_pct mencatat kemajuan pemrosesan tugas dalam persentase (0-100)
    progress_pct: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # Kolom started_at mencatat waktu mulai pengerjaan tugas oleh worker
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    # Kolom completed_at mencatat waktu selesai pengerjaan tugas
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    # Kolom error_detail mencatat stack trace / detail error jika job gagal dikerjakan
    error_detail: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # ── Relasi Database ───────────────────────────────────────────────────
    # Menyambungkan hubungan satu-ke-satu ke objek GeneratedMedia induk
    media: Mapped["GeneratedMedia"] = relationship(back_populates="job")
