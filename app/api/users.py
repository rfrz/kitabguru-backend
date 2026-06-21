"""
User profile routes: GET/PATCH /users/me, DELETE /users/me
"""
# Mengimpor kelas datetime dari modul datetime untuk mencatat waktu penghapusan akun
from datetime import datetime

# Mengimpor modul dari FastAPI untuk pembuatan router, penanganan exception, dan status kode HTTP
from fastapi import APIRouter, HTTPException, status
# Mengimpor kelas select dari SQLAlchemy untuk kueri pencarian user di database
from sqlalchemy import select

# Mengimpor dependensi database (DB), konfigurasi (AppSettings), dan user aktif yang login (CurrentUser)
from app.core.dependencies import DB, AppSettings, CurrentUser
# Mengimpor modul pembantu hash_password dan verify_password untuk keamanan sandi pengguna
from app.core.security import hash_password, verify_password
# Mengimpor model User dari backend
from app.models.user import User
# Mengimpor skema data untuk request hapus akun, profil publik user, dan update profil
from app.schemas.user import DeleteAccountRequest, UserPublic, UserUpdateRequest

# Membuat objek APIRouter baru khusus untuk profil user
router = APIRouter()


# Menentukan rute GET '/me' untuk menampilkan profil pengguna yang sedang login
@router.get(
    "/me",
    # Model skema JSON respons profil publik user yang sukses
    response_model=UserPublic,
    # Ringkasan dokumentasi
    summary="Get current user profile",
)
# Fungsi asinkron untuk mengambil profil diri sendiri
async def get_my_profile(current_user: CurrentUser):
    """Mengembalikan profil publik pengguna yang terautentikasi."""
    # Memetakan data user aktif yang diperoleh dari dependency token ke skema keluaran UserPublic
    return _user_out(current_user)


# Menentukan rute PATCH '/me' untuk mengedit profil pengguna (seperti username, email, atau password)
@router.patch(
    "/me",
    # Model skema JSON respons profil publik user yang terupdate
    response_model=UserPublic,
    # Ringkasan dokumentasi
    summary="Update profile (username, email, or password)",
)
# Fungsi asinkron untuk memperbarui data diri user
async def update_my_profile(
    # Body request berisi data perubahan username, email, atau password baru
    body: UserUpdateRequest,
    # Memeriksa data user aktif yang login
    current_user: CurrentUser,
    # Sesi database
    db: DB,
):
    """
    Memperbarui satu atau lebih field dari: username, email, password.
    Memvalidasi keunikan username atau email baru sebelum memperbarui.
    """
    # Jika pengguna mengisi username baru dan nilainya berbeda dari username yang lama
    if body.username and body.username != current_user.username:
        # Memeriksa keunikan username baru di database untuk pengguna lain yang aktif (tidak terhapus)
        existing = await db.execute(
            select(User).where(
                User.username == body.username,
                User.id != current_user.id,
                User.deleted_at.is_(None),
            )
        )
        # Jika ditemukan ada pengguna lain yang sudah memakai username tersebut
        if existing.scalar_one_or_none():
            # Melemparkan HTTP Exception 409 Conflict
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Username already in use",
            )
        # Mengubah nilai username pengguna dengan username baru
        current_user.username = body.username

    # Jika pengguna mengisi email baru dan nilainya berbeda dari email yang lama
    if body.email and body.email != current_user.email:
        # Memeriksa keunikan email baru di database untuk pengguna lain yang aktif
        existing = await db.execute(
            select(User).where(
                User.email == body.email,
                User.id != current_user.id,
                User.deleted_at.is_(None),
            )
        )
        # Jika ditemukan ada pengguna lain yang sudah memakai email tersebut
        if existing.scalar_one_or_none():
            # Melemparkan HTTP Exception 409 Conflict
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email already in use",
            )
        # Mengubah nilai email pengguna dengan email baru
        current_user.email = body.email

    # Jika pengguna mengirimkan password baru untuk mengganti password lama
    if body.password:
        # Mengenkripsi sandi baru menggunakan bcrypt sebelum disimpan ke database
        current_user.hashed_password = hash_password(body.password)

    # Menyimpan semua perubahan kolom pada model user aktif ke database
    await db.commit()
    # Memuat ulang data pengguna dari database agar nilainya tetap sinkron
    await db.refresh(current_user)
    # Mengembalikan skema keluaran profil publik terupdate
    return _user_out(current_user)


# Menentukan rute DELETE '/me' untuk menghapus akun secara mandiri (soft-delete)
@router.delete(
    "/me",
    # Menetapkan status HTTP respons ke 204 No Content
    status_code=status.HTTP_204_NO_CONTENT,
    # Ringkasan dokumentasi
    summary="Soft-delete account (requires password confirmation)",
)
# Fungsi asinkron untuk melakukan penghapusan akun sendiri sementara (soft-delete)
async def delete_my_account(
    # Body request berisi konfirmasi kata sandi lama
    body: DeleteAccountRequest,
    # Memeriksa user aktif yang sedang login
    current_user: CurrentUser,
    # Sesi database
    db: DB,
):
    """
    Menghapus akun secara halus (soft-delete) dengan mengisi kolom deleted_at ke waktu saat ini.
    Memerlukan konfirmasi kata sandi aktif untuk keamanan.
    Akun akan dihapus secara fisik permanen setelah 30 hari oleh layanan pembersih berkala (purge scheduler).
    """
    # Memverifikasi apakah kata sandi yang dikirimkan cocok dengan hash password yang tersimpan
    if not verify_password(body.password, current_user.hashed_password):
        # Jika salah, lemparkan HTTP Exception 401 Unauthorized
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect password",
        )

    # Mengimpor timezone dari datetime secara lokal untuk menangani zona waktu UTC
    from datetime import timezone
    # Mengisi kolom deleted_at dengan tanggal dan waktu UTC saat ini
    current_user.deleted_at = datetime.now(timezone.utc)
    # Nonaktifkan status aktif akun tersebut
    current_user.is_active = False
    # Melakukan komit database untuk menyimpan status soft-deleted user
    await db.commit()


# ─── Helpers (Fungsi Pembantu) ────────────────────────────────────────────────

# Fungsi pembantu untuk memetakan objek user dari model database ke skema keluaran JSON UserPublic
def _user_out(user: User) -> UserPublic:
    return UserPublic(
        # Mengonversi UUID user menjadi string
        id=str(user.id),
        # Email pengguna
        email=user.email,
        # Username pengguna
        username=user.username,
        # Mengambil nilai string peran user ('user'/'admin')
        role=user.role.value,
        # Status aktif tidaknya akun
        is_active=user.is_active,
        # Tanggal pembuatan akun user
        created_at=user.created_at,
    )
