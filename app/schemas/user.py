# Mengimpor modul datetime untuk tipe data penanggalan
from datetime import datetime
# Mengimpor Optional untuk menandai tipe data yang boleh kosong (None)
from typing import Optional

# Mengimpor BaseModel, EmailStr, dan Field dari Pydantic untuk validasi data user
from pydantic import BaseModel, EmailStr, Field


# Skema UserPublic merepresentasikan data profil pengguna yang aman untuk diekspos ke client
class UserPublic(BaseModel):
    # ID unik user bertipe string
    id: str
    # Alamat email user
    email: str
    # Username user
    username: str
    # Peran user (user atau admin)
    role: str
    # Status aktifasi akun user (aktif/nonaktif)
    is_active: bool
    # Tanggal pembuatan akun user
    created_at: datetime

    # Mengizinkan pemetaan otomatis dari atribut objek model ORM database
    model_config = {"from_attributes": True}


# Skema UserUpdateRequest memvalidasi data profil yang ingin diperbarui sendiri oleh user
class UserUpdateRequest(BaseModel):
    # Mengizinkan edit username opsional dengan regex karakter alphanumeric + underscore/dash
    username: Optional[str] = Field(None, min_length=3, max_length=50, pattern=r"^[a-zA-Z0-9_-]+$")
    # Mengizinkan edit email opsional
    email: Optional[EmailStr] = None
    # Mengizinkan edit password opsional dengan panjang min 8 dan max 128 karakter
    password: Optional[str] = Field(None, min_length=8, max_length=128)


# Skema DeleteAccountRequest memverifikasi password user sebelum proses soft-delete akun dijalankan
class DeleteAccountRequest(BaseModel):
    """User wajib memasukkan password aslinya demi konfirmasi keamanan hapus akun."""
    # Password pengguna untuk konfirmasi hapus akun
    password: str


# Skema UserDetailAdmin merepresentasikan profil data user yang sangat mendalam khusus konsumsi admin
class UserDetailAdmin(BaseModel):
    """Detail informasi profil user lengkap untuk konsumsi admin."""
    # ID user
    id: str
    # Email user
    email: str
    # Username user
    username: str
    # Peran user (user atau admin)
    role: str
    # Status keaktifan akun user
    is_active: bool
    # Tanggal pendaftaran akun
    created_at: datetime
    # Tanggal pembaruan profil akun terakhir
    updated_at: datetime
    # Tanggal soft delete akun (bernilai None jika akun belum dihapus)
    deleted_at: Optional[datetime] = None
    # Akumulasi jumlah sesi chat obrolan yang pernah dibuat oleh user
    session_count: int = 0
    # Akumulasi jumlah balon obrolan yang pernah dikirim oleh user
    message_count: int = 0

    # Mengizinkan pemetaan otomatis dari atribut objek model ORM database
    model_config = {"from_attributes": True}


# Skema UserAdminUpdateRequest memvalidasi data modifikasi status user yang dilakukan admin
class UserAdminUpdateRequest(BaseModel):
    """Admin diperbolehkan untuk mengubah status aktif dan peran (role) user."""
    # Mengubah peran user (misalnya dinaikkan menjadi admin)
    role: Optional[str] = None
    # Mengaktifkan atau menonaktifkan akun user secara sepihak
    is_active: Optional[bool] = None


# Skema UserAdminCreateRequest memvalidasi input pembuatan user baru secara langsung oleh admin
class UserAdminCreateRequest(BaseModel):
    """Admin dapat mendaftarkan user baru secara langsung tanpa registrasi mandiri."""
    # Username wajib diisi dengan regex alphanumeric
    username: str = Field(..., min_length=3, max_length=50, pattern=r"^[a-zA-Z0-9_-]+$")
    # Email wajib diisi dengan email valid
    email: EmailStr
    # Password wajib diisi
    password: str = Field(..., min_length=8, max_length=128)
    # Peran akun baru, default bernilai "user"
    role: str = "user"


# Skema UserListResponse merepresentasikan data respon daftar user untuk tabel admin
class UserListResponse(BaseModel):
    # List berisi detail user
    users: list[UserDetailAdmin]
    # Total baris data user terdaftar di DB (untuk paginasi)
    total: int
    # Halaman data saat ini
    page: int
    # Batas jumlah user per halaman
    limit: int
