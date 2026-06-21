# Mengimpor modul enum bawaan Python untuk mendefinisikan enum peran user dan pesan
import enum
# Mengimpor modul uuid untuk menggenerasi ID unik acak (UUID)
import uuid
# Mengimpor datetime dan timezone untuk penanganan waktu berbasis UTC secara akurat
from datetime import datetime, timezone
# Mengimpor Optional dari typing untuk menandai tipe data yang boleh bernilai None
from typing import Optional

# Mengimpor tipe-tipe kolom database dari SQLAlchemy
from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, String, Text
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


# Kelas UserRole mendefinisikan peran otorisasi pengguna dalam aplikasi
class UserRole(str, enum.Enum):
    # Peran user biasa yang memiliki akses terbatas
    user = "user"
    # Peran admin yang memiliki hak kontrol penuh atas sistem
    admin = "admin"


# Kelas model User mewakili data profil pengguna yang terdaftar di sistem
class User(Base):
    # Menentukan nama tabel fisik database
    __tablename__ = "users"

    # Kolom id primary key bertipe UUID
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # Kolom email unik yang wajib diisi dan memiliki indeks pencarian
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    # Kolom username unik untuk profil pengguna
    username: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    # Kolom hashed_password menyimpan password yang sudah di-hash (bcrypt) secara aman
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    # Kolom role bertipe Enum UserRole (default: user biasa)
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="userrole"), nullable=False, default=UserRole.user
    )
    # Kolom is_active menandai apakah akun pengguna aktif (default: True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # Kolom created_at mencatat waktu pembuatan akun pengguna pertama kali
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    # Kolom updated_at mencatat waktu pembaharuan profil (diperbarui otomatis via onupdate)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )
    # Kolom deleted_at menyimpan waktu soft delete akun (None artinya akun masih ada / aktif)
    deleted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )

    # ── Relasi Database ───────────────────────────────────────────────────
    # Relasi satu-ke-banyak ke token refresh yang valid milik user ini
    refresh_tokens: Mapped[list["RefreshToken"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    # Relasi satu-ke-banyak ke riwayat sesi chat AI milik user
    chat_sessions: Mapped[list["ChatSession"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    # Relasi satu-ke-banyak ke galeri media hasil generate milik user
    generated_media: Mapped[list["GeneratedMedia"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )

    # Property helper untuk memeriksa status penghapusan soft delete akun
    @property
    def is_deleted(self) -> bool:
        # Mengembalikan True jika kolom deleted_at tidak bernilai None
        return self.deleted_at is not None


# Kelas model RefreshToken menyimpan riwayat refresh token JWT aktif milik pengguna
class RefreshToken(Base):
    # Menentukan nama tabel database
    __tablename__ = "refresh_tokens"

    # Kolom id primary key bertipe UUID
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # Kolom user_id sebagai foreign key merujuk ke tabel users
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Kolom token_hash menyimpan hash SHA-256 token penyegar secara unik
    token_hash: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    # Kolom expires_at mencatat batas waktu kadaluwarsa refresh token
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # Kolom revoked untuk mencabut/membatalkan token sebelum masa kedaluwarsa habis (default: False)
    revoked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Kolom created_at mencatat waktu pembuatan token refresh
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )

    # ── Relasi Database ───────────────────────────────────────────────────
    # Menyambungkan kembali relasi banyak-ke-satu ke objek User pemilik token
    user: Mapped["User"] = relationship(back_populates="refresh_tokens")


# Kelas model ChatSession mewakili judul dan tanggal dari sebuah folder percakapan chat AI
class ChatSession(Base):
    # Menentukan nama tabel database
    __tablename__ = "chat_sessions"

    # Kolom id primary key sesi chat bertipe UUID
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # Kolom user_id menghubungkan sesi obrolan dengan akun pengguna pembuatnya
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Kolom title menyimpan judul ringkas sesi obrolan yang dapat diedit (opsional)
    title: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    # Kolom created_at mencatat waktu pembuatan sesi chat
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    # Kolom updated_at mencatat aktivitas pesan chat terakhir (diperbarui otomatis)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )

    # ── Relasi Database ───────────────────────────────────────────────────
    # Relasi balik banyak-ke-satu ke User pemilik sesi
    user: Mapped["User"] = relationship(back_populates="chat_sessions")
    # Relasi satu-ke-banyak ke daftar histori pesan di dalam obrolan, diurutkan kronologis
    messages: Mapped[list["Message"]] = relationship(
        back_populates="session", cascade="all, delete-orphan", order_by="Message.created_at"
    )
    # Relasi satu-ke-banyak ke media yang dihasilkan di dalam percakapan ini
    generated_media: Mapped[list["GeneratedMedia"]] = relationship(
        back_populates="session"
    )


# Kelas MessageRole mendefinisikan peran pengirim pesan di dalam chat AI
class MessageRole(str, enum.Enum):
    # Pesan dikirim oleh pengguna (User)
    user = "user"
    # Respon dikirim oleh model AI (Assistant)
    assistant = "assistant"
    # Instruksi tersembunyi untuk memandu perilaku AI (System)
    system = "system"


# Kelas model Message mewakili satu baris balon percakapan di dalam ChatSession
class Message(Base):
    # Menentukan nama tabel database
    __tablename__ = "messages"

    # Kolom id primary key pesan bertipe UUID
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # Kolom session_id menghubungkan pesan ke folder sesi obrolan terkait
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Kolom role menyimpan peran pengirim pesan (user, assistant, atau system)
    role: Mapped[MessageRole] = mapped_column(
        Enum(MessageRole, name="messagerole"), nullable=False
    )
    # Kolom content berisi teks isi pesan obrolan
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # Kolom meta menyimpan metadata dinamis (misal: citation link, filter pencarian buku, dll)
    meta: Mapped[Optional[dict]] = mapped_column(
        # Menetapkan nama kolom fisik di DB sebagai 'metadata'
        "metadata",
        # Menggunakan format JSONB PostgreSQL agar data JSON terindeks dan cepat dibaca
        type_=__import__("sqlalchemy").dialects.postgresql.JSONB,
        # Memperbolehkan nilai kosong
        nullable=True,
    )
    # Kolom created_at mencatat waktu pengiriman pesan
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )

    # ── Relasi Database ───────────────────────────────────────────────────
    # Relasi balik banyak-ke-satu ke objek ChatSession induk
    session: Mapped["ChatSession"] = relationship(back_populates="messages")
