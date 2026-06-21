# Mengimpor kelas BaseModel, EmailStr, Field, dan model_validator dari Pydantic untuk validasi skema data
from pydantic import BaseModel, EmailStr, Field, model_validator


# Skema RegisterRequest memvalidasi request body saat pendaftaran akun baru
class RegisterRequest(BaseModel):
    # Menyatakan kolom email wajib berupa format email yang valid
    email: EmailStr
    # Menyatakan username wajib diisi, min 3 karakter, max 50 karakter, dan mencocokkan pola regex karakter alphanumeric + underscore/dash
    username: str = Field(min_length=3, max_length=50, pattern=r"^[a-zA-Z0-9_-]+$")
    # Menyatakan password wajib diisi dengan panjang antara 8 hingga 128 karakter
    password: str = Field(min_length=8, max_length=128)


# Skema LoginRequest memvalidasi request body saat pengguna melakukan login
class LoginRequest(BaseModel):
    # Menyatakan email wajib berupa format email yang valid
    email: EmailStr
    # Menyatakan password wajib diisi (berupa teks biasa)
    password: str


# Skema RefreshRequest memvalidasi request body saat meminta pembaruan token akses
class RefreshRequest(BaseModel):
    # Menyatakan string token refresh wajib dikirimkan
    refresh_token: str


# Skema TokenResponse merespon data token hasil login atau refresh token sukses
class TokenResponse(BaseModel):
    # Menyatakan access token baru bertipe string
    access_token: str
    # Menyatakan refresh token baru bertipe string
    refresh_token: str
    # Menyatakan tipe token yang digunakan, default bernilai "bearer"
    token_type: str = "bearer"


# Skema UserPublic merepresentasikan data profil pengguna yang aman diekspos ke publik
class UserPublic(BaseModel):
    # ID unik user bertipe string
    id: str
    # Alamat email user
    email: str
    # Username user
    username: str
    # Peran user di aplikasi (misalnya admin atau user)
    role: str
    # Status keaktifan akun user (aktif/nonaktif)
    is_active: bool
    # Tanggal pembuatan akun user dalam format string ISO
    created_at: str

    # Konfigurasi Pydantic untuk mengizinkan pembuatan schema langsung dari objek ORM database
    model_config = {"from_attributes": True}


# Skema AuthResponse menggabungkan data user publik dan token otentikasi setelah login/register sukses
class AuthResponse(BaseModel):
    # Menyertakan data detail profil publik user
    user: UserPublic
    # Menyertakan access token JWT
    access_token: str
    # Menyertakan refresh token JWT
    refresh_token: str
    # Menyatakan tipe token, default "bearer"
    token_type: str = "bearer"
