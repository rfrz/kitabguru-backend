# Mengimpor modul enum bawaan Python untuk mendefinisikan tipe data enumerasi (pilihan terstruktur)
import enum
# Mengimpor modul uuid untuk menggenerasi ID unik acak (UUID)
import uuid
# Mengimpor datetime dan timezone untuk penanganan waktu berbasis UTC secara akurat
from datetime import datetime, timezone
# Mengimpor Optional dari typing untuk menandai tipe data yang boleh bernilai None
from typing import Optional

# Mengimpor modul DateTime, Enum, ForeignKey, String, dan Text dari SQLAlchemy untuk kolom database
from sqlalchemy import DateTime, Enum, ForeignKey, String, Text
# Mengimpor tipe data UUID khusus dialek PostgreSQL agar kompatibel dengan database Postgres
from sqlalchemy.dialects.postgresql import UUID
# Mengimpor Mapped, mapped_column, dan relationship untuk relasi model ORM modern SQLAlchemy
from sqlalchemy.orm import Mapped, mapped_column, relationship

# Mengimpor kelas Base utama sebagai induk deklaratif model database
from app.database import Base


# Fungsi helper untuk mendapatkan tanggal dan waktu UTC saat ini
def utc_now() -> datetime:
    """Mengembalikan objek datetime saat ini dengan timezone UTC."""
    # Mengambil datetime sekarang dan memberikan informasi zona waktu UTC
    return datetime.now(timezone.utc)


# Kelas IoTMessageRole mendefinisikan peran pengirim pesan dalam percakapan IoT
class IoTMessageRole(str, enum.Enum):
    # Peran user (pengguna yang berinteraksi langsung dengan perangkat IoT)
    user = "user"
    # Peran assistant (jawaban/respon yang dihasilkan oleh AI)
    assistant = "assistant"


# Kelas model IoTSession mewakili sesi percakapan anonim perangkat IoT
class IoTSession(Base):
    """Sesi percakapan perangkat IoT anonim."""
    # Menentukan nama tabel di database PostgreSQL
    __tablename__ = "iot_sessions"

    # Kolom id sebagai primary key bertipe UUID yang diisi otomatis jika tidak diberikan
    id: Mapped[uuid.UUID] = mapped_column(
        # Menetapkan tipe UUID PostgreSQL dan generator default uuid.uuid4
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # Kolom device_id bertipe string untuk mengidentifikasi perangkat keras unik pembuka sesi
    device_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    # Kolom started_at mencatat tanggal-waktu dimulainya sesi komunikasi (default waktu UTC sekarang)
    started_at: Mapped[datetime] = mapped_column(
        # Menggunakan zona waktu lengkap dan memanggil fungsi helper utc_now sebagai nilai default
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    # Kolom ended_at mencatat tanggal-waktu berakhirnya sesi (bisa bernilai kosong jika masih berjalan)
    ended_at: Mapped[Optional[datetime]] = mapped_column(
        # Menggunakan tipe DateTime asinkron bertimezone dan memperbolehkan nilai null
        DateTime(timezone=True), nullable=True
    )

    # ── Relasi Database ───────────────────────────────────────────────────
    # Mendefinisikan hubungan satu-ke-banyak (one-to-many) ke tabel IoTMessage
    messages: Mapped[list["IoTMessage"]] = relationship(
        # Menyambungkan ke properti session di kelas IoTMessage
        back_populates="session",
        # Jika sesi dihapus, hapus juga semua pesan yang terikat dengan sesi tersebut
        cascade="all, delete-orphan",
        # Mengurutkan histori pesan berdasarkan waktu pembuatan secara kronologis
        order_by="IoTMessage.created_at",
    )


# Kelas model IoTMessage mewakili satu baris obrolan suara di dalam sesi komunikasi IoT
class IoTMessage(Base):
    """Satu pertukaran suara dalam sesi IoT (proses STT → inferensi → TTS)."""
    # Menentukan nama tabel pesan IoT di database
    __tablename__ = "iot_messages"

    # Kolom id sebagai primary key pesan bertipe UUID yang digenerasi acak
    id: Mapped[uuid.UUID] = mapped_column(
        # Menggunakan tipe UUID as uuid dan default generator uuid4
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # Kolom iot_session_id sebagai foreign key yang merujuk ke tabel iot_sessions
    iot_session_id: Mapped[uuid.UUID] = mapped_column(
        # Kolom bertipe UUID
        UUID(as_uuid=True),
        # Mengatur relasi foreign key dan menghapus pesan secara beruntun jika sesi dihapus
        ForeignKey("iot_sessions.id", ondelete="CASCADE"),
        # Kolom ini wajib diisi
        nullable=False,
        # Mengindeks kolom agar pencarian histori pesan per sesi berjalan lebih cepat
        index=True,
    )
    # Kolom role menyimpan peran pengirim pesan (user atau assistant)
    role: Mapped[IoTMessageRole] = mapped_column(
        # Menggunakan tipe data Enum berbasis IoTMessageRole
        Enum(IoTMessageRole, name="iotmessagerole"), nullable=False
    )
    # Kolom content menyimpan transkrip teks percakapan
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # Kolom audio_path menyimpan path file audio suara respon TTS (bisa bernilai None)
    audio_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    # Kolom meta menyimpan metadata dinamis (misal: tingkat akurasi STT, provider) dalam format JSONB
    meta: Mapped[Optional[dict]] = mapped_column(
        # Menetapkan nama kolom fisik di DB sebagai 'metadata'
        "metadata",
        # Mengimpor tipe data JSONB dinamis khusus dialek PostgreSQL agar mendukung query json
        type_=__import__("sqlalchemy").dialects.postgresql.JSONB,
        # Memperbolehkan nilai kosong
        nullable=True,
    )
    # Kolom created_at mencatat waktu pengiriman pesan
    created_at: Mapped[datetime] = mapped_column(
        # Menggunakan DateTime bertimezone dan default waktu UTC sekarang
        DateTime(timezone=True), nullable=False, default=utc_now
    )

    # ── Relasi Database ───────────────────────────────────────────────────
    # Mendefinisikan relasi balik banyak-ke-satu (many-to-one) ke kelas induk IoTSession
    session: Mapped["IoTSession"] = relationship(back_populates="messages")
