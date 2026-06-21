"""
Layanan Otentikasi (Auth Service): menangani pendaftaran, login, refresh token, dan logout.
Menyimpan hash SHA-256 dari refresh token di database demi melindungi integritas sesi.
"""
# Mengimpor modul uuid untuk penanganan ID user unik
import uuid
# Mengimpor datetime, timezone untuk manipulasi tanggal dan waktu UTC
from datetime import datetime, timezone

# Mengimpor select untuk membangun query seleksi database SQLAlchemy
from sqlalchemy import select
# Mengimpor AsyncSession untuk penanganan sesi transaksi database asinkron
from sqlalchemy.ext.asyncio import AsyncSession

# Mengimpor skema Settings untuk konfigurasi parameter JWT
from app.config import Settings
# Mengimpor utilitas keamanan JWT dan password dari core.security
from app.core.security import (
    create_access_token,   # Membuat token akses berumur pendek
    create_refresh_token,  # Membuat token refresh berumur panjang
    hash_password,         # Hashing password dengan bcrypt
    hash_token,            # Hashing token refresh dengan SHA-256
    verify_password,       # Verifikasi kecocokan password teks polos dan hash
    get_token_expiry,      # Mendapatkan waktu kadaluwarsa token
    decode_token,          # Mendekode dan memvalidasi payload token JWT
)
# Mengimpor model tabel database terkait
from app.models.user import RefreshToken, User, UserRole
# Mengimpor skema request DTO registrasi dan login
from app.schemas.auth import RegisterRequest, LoginRequest
# Mengimpor HTTPException dan status HTTP FastAPI
from fastapi import HTTPException, status


# Kelas AuthService menyediakan logika bisnis lengkap untuk alur autentikasi user
class AuthService:
    # Inisialisasi service dengan sesi database dan pengaturan aplikasi
    def __init__(self, db: AsyncSession, settings: Settings):
        # Menyimpan referensi session database asinkron
        self.db = db
        # Menyimpan referensi konfigurasi settings
        self.settings = settings

    # Menangani proses pendaftaran akun pengguna baru
    async def register(self, data: RegisterRequest) -> tuple[User, str, str]:
        """Mendaftarkan user baru. Mengembalikan tuple (user, access_token, refresh_token)."""
        # Melakukan query untuk memeriksa apakah email atau username yang diinput sudah terdaftar sebelumnya
        existing = await self.db.execute(
            select(User).where(
                # Mencocokkan email atau username
                (User.email == data.email) | (User.username == data.username),
                # Memastikan akun tersebut bukan akun yang di-softdelete
                User.deleted_at.is_(None),
            )
        )
        # Jika hasil query mengembalikan data user (artinya email/username sudah terpakai)
        if existing.scalar_one_or_none():
            # Lempar error HTTP 409 Conflict karena data bertabrakan
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email or username already in use",
            )

        # Membuat objek User baru dengan data dari request register
        user = User(
            email=data.email,
            username=data.username,
            # Melakukan hashing password dengan bcrypt sebelum disimpan ke database
            hashed_password=hash_password(data.password),
            # Memberikan peran pengguna biasa secara default
            role=UserRole.user,
        )
        # Menambahkan data user ke antrean transaksi database
        self.db.add(user)
        # Melakukan flush transaksi agar database men-generate ID user otomatis sebelum commit dijalankan
        await self.db.flush()

        # Membuat token akses dan token refresh baru untuk user yang sukses terdaftar
        access_token, refresh_token = await self._issue_tokens(user)
        # Menyimpan seluruh data user dan token refresh baru ke database secara permanen
        await self.db.commit()
        # Memperbarui data objek user agar memuat nilai-nilai database terbaru
        await self.db.refresh(user)
        # Mengembalikan objek user beserta sepasang token akses & refresh
        return user, access_token, refresh_token

    # Menangani verifikasi kredensial login pengguna
    async def login(self, data: LoginRequest) -> tuple[User, str, str]:
        """Memverifikasi data login user. Mengembalikan tuple (user, access_token, refresh_token)."""
        # Melakukan pencarian user di database berdasarkan alamat email yang dikirim
        result = await self.db.execute(
            select(User).where(User.email == data.email, User.deleted_at.is_(None))
        )
        # Mengambil objek user hasil query (bernilai None jika email tidak terdaftar)
        user = result.scalar_one_or_none()

        # Memastikan user terdaftar dan password teks mentah cocok dengan hash password yang disimpan
        if not user or not verify_password(data.password, user.hashed_password):
            # Lempar error HTTP 401 Unauthorized jika email tidak terdaftar atau password salah
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password",
            )
        # Memastikan akun user tersebut berstatus aktif (tidak diblokir)
        if not user.is_active:
            # Lempar error HTTP 403 Forbidden karena akun dinonaktifkan
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Account is deactivated",
            )

        # Menghasikan sepasang token akses dan token refresh baru bagi user
        access_token, refresh_token = await self._issue_tokens(user)
        # Melakukan commit transaksi penyimpanan token refresh baru ke database
        await self.db.commit()
        # Mengembalikan data user login berserta tokennya
        return user, access_token, refresh_token

    # Menangani proses refresh token (Token Rotation) demi keamanan sesi
    async def refresh(self, raw_refresh_token: str) -> tuple[str, str]:
        """
        Validasi refresh token, mencabut status keaktifannya, dan mengeluarkan sepasang token baru.
        Menerapkan rotasi token (Token Rotation) untuk mencegah penyalahgunaan token lama.
        """
        # Memulai blok pemeriksaan keaslian token refresh
        try:
            # Mendekode token refresh mentah
            payload = decode_token(raw_refresh_token)
            # Memastikan tipe token di payload bernilai "refresh"
            if payload.get("type") != "refresh":
                # Lempar ValueError jika tipe token salah
                raise ValueError("Not a refresh token")
            # Mengonversi string ID subjek (user ID) menjadi objek UUID
            user_id = uuid.UUID(payload["sub"])
        # Menangkap error jika token kadaluwarsa, tidak valid, atau bermasalah
        except Exception:
            # Lempar error HTTP 401 Unauthorized
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired refresh token",
            )

        # Menghasilkan hash SHA-256 dari refresh token mentah yang dikirim client
        token_hash = hash_token(raw_refresh_token)
        # Mencari record token refresh tersebut di database
        result = await self.db.execute(
            select(RefreshToken).where(
                # Mencocokkan hash token
                RefreshToken.token_hash == token_hash,
                # Mencocokkan ID user
                RefreshToken.user_id == user_id,
                # Memastikan token tersebut belum dicabut/digunakan sebelumnya
                RefreshToken.revoked.is_(False),
            )
        )
        # Mengambil record token tersimpan
        stored = result.scalar_one_or_none()
        # Memastikan token ada dan belum melewati batas waktu kadaluwarsa
        if not stored or stored.expires_at < datetime.now(timezone.utc):
            # Lempar error 401 Unauthorized jika token tidak ditemukan, kadaluwarsa, atau sudah terpakai
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh token not found, expired, or already used",
            )

        # Mencabut token refresh lama (rotasi token) dengan mengubah properti revoked menjadi True
        stored.revoked = True
        # Memperbarui status token lama di database
        self.db.add(stored)

        # Mengambil data objek user dari database untuk memverifikasi keaktifan akun terbarunya
        user_result = await self.db.execute(
            select(User).where(User.id == user_id, User.deleted_at.is_(None))
        )
        # Mengambil objek user
        user = user_result.scalar_one_or_none()
        # Memastikan user ada dan status akunnya masih aktif
        if not user or not user.is_active:
            # Lempar error HTTP 401 Unauthorized
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

        # Menggenerasi token akses dan token refresh yang baru (rotasi lengkap)
        access_token, new_refresh = await self._issue_tokens(user)
        # Melakukan commit transaksi pencabutan token lama dan penyimpanan token baru ke database
        await self.db.commit()
        # Mengembalikan sepasang token baru
        return access_token, new_refresh

    # Menangani proses logout (pencabutan token aktif)
    async def logout(self, raw_refresh_token: str) -> None:
        """Mencabut refresh token aktif (logout dari perangkat saat ini)."""
        # Mencoba menghasilkan hash SHA-256 dari token refresh
        try:
            token_hash = hash_token(raw_refresh_token)
        # Menangkap error jika token cacat
        except Exception:
            # Abaikan secara diam-diam karena proses logout tidak boleh menghentikan UI client
            return

        # Mencari record token refresh aktif di database
        result = await self.db.execute(
            select(RefreshToken).where(
                RefreshToken.token_hash == token_hash,
                RefreshToken.revoked.is_(False),
            )
        )
        # Mengambil record token tersimpan
        stored = result.scalar_one_or_none()
        # Jika token ditemukan aktif di database
        if stored:
            # Ubah status token menjadi dicabut (revoked = True)
            stored.revoked = True
            # Update data ke database
            self.db.add(stored)
            # Terapkan perubahan database secara permanen
            await self.db.commit()

    # Membuat sepasang token akses + refresh dan menyimpannya di database
    async def _issue_tokens(self, user: User) -> tuple[str, str]:
        """Membuat dan menyimpan sepasang token akses + refresh baru ke database."""
        # Membuat token akses JWT berdurasi pendek
        access_token = create_access_token(str(user.id), user.role.value)
        # Membuat token refresh JWT berdurasi panjang
        refresh_token = create_refresh_token(str(user.id))

        # Menghitung tanggal kadaluwarsa token refresh berdasarkan konfigurasi settings
        expires_at = get_token_expiry(days=self.settings.jwt_refresh_token_expire_days)
        # Membuat objek model RefreshToken baru untuk disimpan di database
        stored_token = RefreshToken(
            # Menghubungkan ID user
            user_id=user.id,
            # Menyimpan hash SHA-256 token refresh (bukan token mentah) demi keamanan
            token_hash=hash_token(refresh_token),
            expires_at=expires_at,
        )
        # Menyimpan data token refresh ke sesi database
        self.db.add(stored_token)
        # Mengembalikan sepasang token akses dan refresh polos (mentah) ke pemanggil
        return access_token, refresh_token
