"""
Inisialisasi package schemas untuk validasi skema input/output data (Pydantic).
Mengekspos kelas-kelas skema (DTO) yang digunakan untuk request body dan response body pada API.
"""

# Mengimpor skema validasi untuk proses registrasi, login, refresh token, dan respon autentikasi
from app.schemas.auth import (
    RegisterRequest,
    LoginRequest,
    RefreshRequest,
    TokenResponse,
    AuthResponse,
)
# Mengimpor skema validasi untuk data profil publik user, request update, dan data detail admin
from app.schemas.user import (
    UserPublic,
    UserUpdateRequest,
    DeleteAccountRequest,
    UserDetailAdmin,
    UserAdminUpdateRequest,
    UserListResponse,
)
# Mengimpor skema validasi sesi chat, pembuatan sesi, pengiriman pesan, dan respon detail chat
from app.schemas.chat import (
    SessionCreateRequest,
    SessionRenameRequest,
    SessionSummary,
    SessionListResponse,
    MessageOut,
    SessionDetailResponse,
    SendMessageRequest,
    SendMessageResponse,
)
# Mengimpor skema validasi request generate gambar/video AI, status job antrean, dan data output media
from app.schemas.media import (
    ImageGenerateRequest,
    ImageGenerateResponse,
    VideoGenerateRequest,
    VideoGenerateResponse,
    JobStatusResponse,
    MediaOut,
    MediaListResponse,
)
# Mengimpor skema validasi pembuatan sesi perangkat IoT, suara respon IoT, dan histori chat IoT
from app.schemas.iot import (
    IoTMessageOut,
    IoTSessionDetailResponse,
    IoTSessionSummary,
    IoTSessionListResponse,
)

# Mengekspos semua skema validasi Pydantic di atas agar siap diimpor dari app.schemas
__all__ = [
    # Kategori Autentikasi (Auth)
    "RegisterRequest",          # Skema untuk input pendaftaran akun baru
    "LoginRequest",             # Skema untuk input login (email & password)
    "RefreshRequest",           # Skema untuk input penyegaran token JWT
    "TokenResponse",            # Skema respon token akses baru hasil refresh
    "AuthResponse",             # Skema respon sukses login/register lengkap dengan profil
    
    # Kategori Pengguna (User)
    "UserPublic",               # Skema profil user terbatas untuk konsumsi umum
    "UserUpdateRequest",        # Skema data yang boleh diubah sendiri oleh user
    "DeleteAccountRequest",     # Skema verifikasi hapus akun mandiri
    "UserDetailAdmin",          # Skema detail data user yang lengkap khusus admin
    "UserAdminUpdateRequest",   # Skema data modifikasi user yang dilakukan admin
    "UserListResponse",         # Skema daftar user terpaginasi untuk panel admin
    
    # Kategori Sesi Chat AI
    "SessionCreateRequest",     # Skema parameter pembuatan sesi chat baru
    "SessionRenameRequest",     # Skema penggantian nama judul sesi chat
    "SessionSummary",           # Skema ringkasan informasi sesi chat
    "SessionListResponse",      # Skema daftar histori sesi chat milik user
    "MessageOut",               # Skema format output satu baris pesan chat
    "SessionDetailResponse",    # Skema detail sesi lengkap dengan riwayat seluruh pesan
    "SendMessageRequest",       # Skema parameter pengiriman pesan baru ke AI
    "SendMessageResponse",      # Skema respon jawaban AI setelah menerima pesan
    
    # Kategori Media Generatif
    "ImageGenerateRequest",     # Skema parameter perintah generate gambar AI
    "ImageGenerateResponse",    # Skema respon tanda terima tugas generate gambar
    "VideoGenerateRequest",     # Skema parameter perintah generate video AI
    "VideoGenerateResponse",    # Skema respon tanda terima tugas generate video
    "JobStatusResponse",        # Skema pengecekan status antrean pemrosesan media
    "MediaOut",                 # Skema detail informasi media yang berhasil dibuat
    "MediaListResponse",        # Skema daftar galeri media hasil buatan AI milik user
    
    # Kategori Internet of Things (IoT)
    "IoTMessageOut",            # Skema format output pesan percakapan perangkat IoT
    "IoTSessionDetailResponse", # Skema data detail sesi IoT dan transkrip obrolannya
    "IoTSessionSummary",        # Skema ringkasan sesi komunikasi IoT
    "IoTSessionListResponse",   # Skema daftar seluruh sesi perangkat IoT aktif
]
