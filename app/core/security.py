# Mengimpor modul hashlib untuk melakukan enkripsi satu arah SHA-256
import hashlib
# Mengimpor modul uuid untuk menggenerasi identifier unik acak (UUID v4)
import uuid
# Mengimpor datetime, timedelta, dan timezone untuk mengelola waktu kedaluwarsa token
from datetime import datetime, timedelta, timezone

# Mengimpor pustaka bcrypt untuk proses hashing password dengan salt aman
import bcrypt
# Mengimpor pustaka PyJWT (alias jwt) untuk encoding dan decoding JSON Web Token (JWT)
import jwt

# Mengimpor fungsi pembaca konfigurasi aplikasi
from app.config import get_settings

# Menginisialisasi variabel settings dengan memanggil get_settings
settings = get_settings()

# ─── Utilitas Password (Password Utilities) ───────────────────────────────────

# Fungsi untuk mengubah password teks biasa menjadi hash bcrypt yang aman
def hash_password(plain: str) -> str:
    """Mengenkripsi password plain-text menggunakan bcrypt salt."""
    # Menggenerasi salt bcrypt acak untuk menambahkan entropi pada hash
    salt = bcrypt.gensalt()
    # Melakukan hashing password dan mengubah output bytes kembali menjadi format string UTF-8
    return bcrypt.hashpw(plain.encode('utf-8'), salt).decode('utf-8')


# Fungsi untuk memvalidasi kesesuaian password teks biasa dengan hash tersimpan
def verify_password(plain: str, hashed: str) -> bool:
    """Memverifikasi kecocokan password teks mentah dengan hash bcrypt."""
    # Menggunakan blok try-except untuk menangani format hash yang tidak valid
    try:
        # Membandingkan password plain yang di-encode ke byte dengan hash yang di-encode ke byte
        return bcrypt.checkpw(plain.encode('utf-8'), hashed.encode('utf-8'))
    # Menangkap error format string hash jika bukan format bcrypt yang valid
    except ValueError:
        # Mengembalikan False jika terjadi kesalahan format
        return False


# ─── Utilitas JWT (JWT Utilities) ──────────────────────────────────────────────

# Fungsi untuk membuat token akses JWT yang berumur pendek (short-lived)
def create_access_token(subject: str, role: str) -> str:
    """Membuat token akses JWT berdurasi pendek untuk autentikasi."""
    # Menghitung waktu kedaluwarsa token (waktu UTC saat ini ditambah batas menit dari konfigurasi)
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.jwt_access_token_expire_minutes
    )
    # Menyusun payload informasi yang akan disimpan di dalam enkripsi token JWT
    payload = {
        "sub": subject,   # Subjek token, biasanya UUID pengguna dalam format string
        "role": role,     # Peran otorisasi pengguna (misal: user atau admin)
        "exp": expire,     # Waktu kedaluwarsa token
        "type": "access",  # Menandakan bahwa token ini bertipe akses token
        "jti": str(uuid.uuid4()), # Identifier unik token (JWT ID) untuk mencegah replay attack
    }
    # Melakukan encoding payload dengan secret key dan algoritma dari settings
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


# Fungsi untuk membuat token refresh JWT yang berumur panjang (long-lived)
def create_refresh_token(subject: str) -> str:
    """Membuat token refresh JWT berdurasi panjang untuk memperbarui token akses."""
    # Menghitung waktu kedaluwarsa token (waktu UTC saat ini ditambah batas hari dari konfigurasi)
    expire = datetime.now(timezone.utc) + timedelta(
        days=settings.jwt_refresh_token_expire_days
    )
    # Menyusun payload informasi token refresh
    payload = {
        "sub": subject,     # UUID pengguna
        "exp": expire,      # Waktu kedaluwarsa token refresh
        "type": "refresh",  # Menandakan tipe token refresh
        "jti": str(uuid.uuid4()), # Identifier unik token refresh
    }
    # Melakukan encoding payload token refresh ke JWT string
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


# Fungsi untuk mendekode dan memvalidasi token JWT
def decode_token(token: str) -> dict:
    """Mendekode dan memverifikasi tanda tangan token JWT. Melempar PyJWTError jika tidak valid."""
    # Melakukan decode token JWT menggunakan secret key dan algoritma yang disetujui
    return jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])


# Fungsi untuk mengenkripsi token refresh (SHA-256) sebelum disimpan di database demi keamanan data
def hash_token(token: str) -> str:
    """Menghasilkan hash SHA-256 dari string token untuk disimpan dengan aman di database."""
    # Melakukan hash SHA-256 pada byte token dan mengembalikan representasi string heksadesimalnya
    return hashlib.sha256(token.encode()).hexdigest()


# Fungsi helper untuk menghitung tanggal kedaluwarsa secara dinamis
def get_token_expiry(days: int = 0, minutes: int = 0) -> datetime:
    """Mendapatkan waktu kedaluwarsa di masa depan berbasis UTC."""
    # Mengembalikan waktu UTC saat ini ditambah durasi hari dan menit yang diberikan
    return datetime.now(timezone.utc) + timedelta(days=days, minutes=minutes)


# Mendefinisikan objek fungsi keamanan yang diekspor dari modul ini
__all__ = [
    "hash_password",
    "verify_password",
    "create_access_token",
    "create_refresh_token",
    "decode_token",
    "hash_token",
    "get_token_expiry",
]
