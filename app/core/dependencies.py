# Mengimpor modul uuid untuk mengelola identifikasi unik universal (UUID) pengguna
import uuid
# Mengimpor Annotated dari modul typing untuk menyisipkan metadata (Depends) pada type hint
from typing import Annotated

# Mengimpor kelas Depends, Header, HTTPException, dan status dari FastAPI untuk injeksi dependensi dan error HTTP
from fastapi import Depends, Header, HTTPException, status
# Mengimpor skema pengaman HTTPBearer dan kredensialnya untuk menangani autentikasi token Bearer
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
# Mengimpor class exception khusus PyJWTError untuk menangani error saat decoding token JWT
from jwt.exceptions import PyJWTError
# Mengimpor select dari SQLAlchemy untuk membangun query select database
from sqlalchemy import select
# Mengimpor AsyncSession untuk type-hinting sesi transaksi database asinkron
from sqlalchemy.ext.asyncio import AsyncSession

# Mengimpor Settings dan get_settings untuk mendapatkan file konfigurasi sistem
from app.config import Settings, get_settings
# Mengimpor decode_token untuk memverifikasi dan membaca payload dari token JWT
from app.core.security import decode_token
# Mengimpor get_db sebagai fungsi penyuplai sesi database asinkron
from app.database import get_db
# Mengimpor model User dan enum UserRole untuk operasi data pengguna
from app.models.user import User, UserRole

# Menginisialisasi skema HTTPBearer tanpa error otomatis agar kita bisa mengendalikan respon error secara manual
bearer_scheme = HTTPBearer(auto_error=False)


# Fungsi dependensi FastAPI untuk mendapatkan objek user yang saat ini sedang aktif login
async def get_current_user(
    # Kredensial otorisasi JWT Bearer yang diekstrak dari header Authorization
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    # Sesi transaksi database asinkron yang diinjeksikan otomatis
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    """
    Ekstrak dan verifikasi token JWT Bearer, lalu kembalikan objek User yang aktif.
    
    Args:
        credentials: Token JWT Bearer dari HTTP header.
        db: Sesi database asinkron.
        
    Returns:
        User: Objek user yang berhasil diotentikasi.
        
    Raises:
        HTTPException: Jika token tidak valid, kadaluwarsa, atau user tidak aktif.
    """
    # Mendefinisikan template error HTTP 401 Unauthorized secara terpusat
    exc = HTTPException(
        # Kode status 401 menunjukkan ketidakabsahan kredensial otentikasi
        status_code=status.HTTP_401_UNAUTHORIZED,
        # Pesan detail kesalahan otentikasi
        detail="Could not validate credentials",
        # Header HTTP untuk memberitahu tipe otentikasi Bearer yang valid
        headers={"WWW-Authenticate": "Bearer"},
    )
    # Jika tidak ada token Bearer yang dikirimkan dalam request header
    if credentials is None:
        # Lempar pengecualian error 401 Unauthorized
        raise exc

    # Memulai blok try-except untuk mendeteksi error decoding JWT atau konversi UUID
    try:
        # Mendekode dan memverifikasi tanda tangan token JWT
        payload = decode_token(credentials.credentials)
        # Memastikan tipe token yang digunakan adalah token akses (bukan refresh token)
        if payload.get("type") != "access":
            # Jika tipe token bukan access, lempar error
            raise exc
        # Mendapatkan user ID dalam bentuk string dari claim 'sub' di payload token
        user_id_str: str | None = payload.get("sub")
        # Jika claim sub kosong atau tidak ada
        if not user_id_str:
            # Lempar error karena subjek token tidak jelas
            raise exc
        # Mengonversi string ID user menjadi objek UUID Python yang valid
        user_id = uuid.UUID(user_id_str)
    # Menangkap error JWT yang tidak valid atau value error saat parsing UUID
    except (PyJWTError, ValueError):
        # Lempar error 401 jika penanganan token gagal
        raise exc

    # Melakukan query database untuk mencari data user berdasarkan UUID dan memastikan data belum di-softdelete
    result = await db.execute(
        # Query mencari baris User di mana id cocok dan deleted_at bernilai NULL
        select(User).where(User.id == user_id, User.deleted_at.is_(None))
    )
    # Mengambil satu objek User atau None jika tidak ditemukan
    user = result.scalar_one_or_none()
    # Jika user tidak ditemukan di database atau status akunnya tidak aktif (is_active = False)
    if user is None or not user.is_active:
        # Lempar error HTTP 401 Unauthorized dengan keterangan yang lebih spesifik
        raise HTTPException(
            # Status 401 Unauthorized
            status_code=status.HTTP_401_UNAUTHORIZED,
            # Pesan kesalahan
            detail="User not found or deactivated",
        )
    # Mengembalikan objek user yang sukses terotentikasi
    return user


# Fungsi dependensi FastAPI untuk memverifikasi apakah user yang login memiliki peran admin
async def get_admin_user(
    # Mengambil user saat ini lewat dependensi get_current_user
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    """
    Memastikan pengguna saat ini memiliki peran (role) administrator.
    
    Args:
        current_user: Objek user terotentikasi.
        
    Returns:
        User: Objek user admin jika terverifikasi.
        
    Raises:
        HTTPException: Jika peran user bukan admin.
    """
    # Memeriksa apakah role user bukan admin
    if current_user.role != UserRole.admin:
        # Lempar error HTTP 403 Forbidden karena akses ditolak
        raise HTTPException(
            # Status 403 Forbidden
            status_code=status.HTTP_403_FORBIDDEN,
            # Pesan kesalahan akses khusus admin
            detail="Admin access required",
        )
    # Mengembalikan objek user yang sudah terverifikasi sebagai admin
    return current_user


# Fungsi dependensi FastAPI untuk memverifikasi API Key perangkat IoT dari request header
async def verify_iot_api_key(
    # Membaca header HTTP dengan alias 'X-API-Key'
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
    # Mengambil konfigurasi sistem lewat dependensi get_settings
    settings: Settings = Depends(get_settings),
) -> str:
    """
    Verifikasi API Key perangkat IoT dari header request X-API-Key.
    
    Args:
        x_api_key: Kunci API yang diambil dari header request HTTP.
        settings: Konfigurasi aplikasi.
        
    Returns:
        str: API Key yang valid.
        
    Raises:
        HTTPException: Jika API Key salah atau tidak dikirim.
    """
    # Jika header X-API-Key kosong atau isinya tidak sesuai dengan iot_api_key di settings
    if not x_api_key or x_api_key != settings.iot_api_key:
        # Lempar error HTTP 401 Unauthorized
        raise HTTPException(
            # Status 401 Unauthorized
            status_code=status.HTTP_401_UNAUTHORIZED,
            # Pesan kesalahan kunci API tidak valid
            detail="Invalid or missing IoT API key",
        )
    # Mengembalikan string API key yang sudah terverifikasi
    return x_api_key


# ─── Alias Tipe Data (Type Aliases) agar deklarasi rute FastAPI lebih ringkas ─────

# Type alias untuk user biasa terotentikasi
CurrentUser = Annotated[User, Depends(get_current_user)]
# Type alias untuk user admin terotentikasi
AdminUser = Annotated[User, Depends(get_admin_user)]
# Type alias untuk verifikasi API key IoT
IoTAuth = Annotated[str, Depends(verify_iot_api_key)]
# Type alias untuk sesi database asinkron
DB = Annotated[AsyncSession, Depends(get_db)]
# Type alias untuk konfigurasi global Settings
AppSettings = Annotated[Settings, Depends(get_settings)]
