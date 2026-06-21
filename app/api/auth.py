"""
Auth routes: /auth/register, /auth/login, /auth/refresh, /auth/logout
"""
# Mengimpor APIRouter untuk mendefinisikan rute, Request untuk data permintaan HTTP, dan status untuk kode HTTP
from fastapi import APIRouter, Request, status
# Mengimpor kelas Limiter dari slowapi untuk membatasi frekuensi request (rate limiting)
from slowapi import Limiter
# Mengimpor helper get_remote_address dari slowapi untuk mengidentifikasi alamat IP klien
from slowapi.util import get_remote_address

# Mengimpor dependensi database (DB), konfigurasi aplikasi (AppSettings), dan pengguna aktif saat ini (CurrentUser)
from app.core.dependencies import DB, AppSettings, CurrentUser
# Mengimpor skema-skema data autentikasi untuk input dan output API
from app.schemas.auth import AuthResponse, LoginRequest, RefreshRequest, RegisterRequest, TokenResponse
# Mengimpor AuthService untuk memproses logika registrasi, login, logout, dan refresh token
from app.services.auth_service import AuthService

# Membuat objek APIRouter baru khusus untuk autentikasi
router = APIRouter()
# Membuat instans Limiter dengan menggunakan fungsi penentu IP address klien sebagai kunci pembatas
limiter = Limiter(key_func=get_remote_address)


# Menentukan rute POST '/register' untuk mendaftarkan akun pengguna baru
@router.post(
    "/register",
    # Model skema JSON respons registrasi yang sukses
    response_model=AuthResponse,
    # Menetapkan status HTTP respons ke 201 Created
    status_code=status.HTTP_201_CREATED,
    # Ringkasan dokumentasi
    summary="Register a new user",
)
# Membatasi frekuensi akses rute ini maksimal 5 kali permintaan per menit per IP
@limiter.limit("5/minute")
# Fungsi asinkron untuk mendaftarkan pengguna baru
async def register(
    # Menyediakan objek request untuk kebutuhan pembatasan frekuensi (slowapi)
    request: Request,
    # Body request JSON yang divalidasi sesuai skema RegisterRequest
    body: RegisterRequest,
    # Sesi koneksi database
    db: DB,
    # Mengambil konfigurasi aplikasi
    settings: AppSettings,
):
    """
    Mendaftarkan akun pengguna baru.
    Mengembalikan profil pengguna + sepasang JWT access token dan refresh token.
    Dibatasi: Maksimal 5 permintaan per menit untuk setiap IP Address.
    """
    # Membuat instance AuthService dengan memberikan sesi database dan konfigurasi
    service = AuthService(db, settings)
    # Memanggil metode register pada service untuk memproses pembuatan akun dan token JWT
    user, access_token, refresh_token = await service.register(body)
    # Mengembalikan objek AuthResponse berisi data profil publik user, access token, dan refresh token
    return AuthResponse(
        # Mengonversi objek model user menjadi format skema publik
        user=_user_to_schema(user),
        # Token akses JWT berumur pendek
        access_token=access_token,
        # Token penyegar JWT berumur panjang
        refresh_token=refresh_token,
    )


# Menentukan rute POST '/login' untuk masuk ke sistem menggunakan email dan kata sandi
@router.post(
    "/login",
    # Model skema JSON respons login yang sukses
    response_model=AuthResponse,
    # Ringkasan dokumentasi
    summary="Login with email + password",
)
# Membatasi frekuensi akses login maksimal 5 kali permintaan per menit per IP
@limiter.limit("5/minute")
# Fungsi asinkron untuk memproses login pengguna
async def login(
    # Menyediakan objek request untuk kebutuhan rate limiting
    request: Request,
    # Body request JSON divalidasi dengan skema LoginRequest (email & password)
    body: LoginRequest,
    # Sesi koneksi database
    db: DB,
    # Konfigurasi aplikasi
    settings: AppSettings,
):
    """
    Autentikasi menggunakan email dan password.
    Mengembalikan profil pengguna + sepasang JWT access token dan refresh token.
    Dibatasi: Maksimal 5 permintaan per menit untuk setiap IP Address.
    """
    # Membuat instance AuthService
    service = AuthService(db, settings)
    # Memanggil metode login pada service untuk mencocokkan kredensial dan menerbitkan token baru
    user, access_token, refresh_token = await service.login(body)
    # Mengembalikan objek AuthResponse berisi profil publik, token akses, dan token penyegar
    return AuthResponse(
        user=_user_to_schema(user),
        access_token=access_token,
        refresh_token=refresh_token,
    )


# Menentukan rute POST '/refresh' untuk memperbarui access token yang telah kedaluwarsa
@router.post(
    "/refresh",
    # Model skema JSON respons berisi pasangan token baru
    response_model=TokenResponse,
    # Ringkasan dokumentasi
    summary="Refresh access token using refresh token",
)
# Fungsi asinkron untuk menerbitkan access token baru berdasarkan refresh token yang valid
async def refresh_token(
    # Body request berisi string refresh_token
    body: RefreshRequest,
    # Sesi koneksi database
    db: DB,
    # Konfigurasi aplikasi
    settings: AppSettings,
):
    """
    Menukarkan refresh token yang valid dengan pasangan access token + refresh token yang baru.
    Refresh token yang lama akan dinonaktifkan (rotasi token demi keamanan ekstra).
    """
    # Membuat instance AuthService
    service = AuthService(db, settings)
    # Memanggil fungsi refresh untuk memvalidasi token lama dan membuat sepasang token baru
    access_token, new_refresh_token = await service.refresh(body.refresh_token)
    # Mengembalikan respons token baru
    return TokenResponse(
        access_token=access_token,
        refresh_token=new_refresh_token,
    )


# Menentukan rute POST '/logout' untuk keluar dari sistem dan membatalkan refresh token
@router.post(
    "/logout",
    # Mengeset status HTTP respons ke 204 No Content
    status_code=status.HTTP_204_NO_CONTENT,
    # Ringkasan dokumentasi
    summary="Logout — invalidate refresh token",
)
# Fungsi asinkron untuk memproses logout pengguna
async def logout(
    # Body request berisi refresh_token yang ingin dinonaktifkan
    body: RefreshRequest,
    # Sesi koneksi database
    db: DB,
    # Konfigurasi aplikasi
    settings: AppSettings,
    # Memverifikasi bahwa request dikirim oleh user yang sedang masuk (login)
    current_user: CurrentUser,
):
    """
    Mencabut dan menghapus status aktif refresh token yang diberikan dari database.
    Upaya refresh token di masa depan menggunakan token ini akan ditolak (gagal).
    """
    # Membuat instance AuthService
    service = AuthService(db, settings)
    # Memanggil fungsi logout untuk mencabut token dari database
    await service.logout(body.refresh_token)


# ─── Helpers (Fungsi Pembantu) ────────────────────────────────────────────────

# Mengubah data mentah objek user dari model database ke format schema publik (UserPublic)
def _user_to_schema(user) -> dict:
    # Melakukan impor lokal UserPublic untuk menghindari ketergantungan melingkar (circular imports)
    from app.schemas.auth import UserPublic
    # Mengembalikan skema publik yang sudah diisi dengan data user
    return UserPublic(
        # Mengonversi UUID user menjadi tipe string
        id=str(user.id),
        # Mengambil alamat email
        email=user.email,
        # Mengambil nama pengguna
        username=user.username,
        # Mengambil string value dari peran pengguna
        role=user.role.value,
        # Status aktif tidaknya akun
        is_active=user.is_active,
        # Mengonversi tanggal pembuatan menjadi string
        created_at=str(user.created_at),
    )
