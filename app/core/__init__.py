"""
Inisialisasi package core untuk logika inti aplikasi.
Package ini mengekspos utilitas keamanan (hashing, jwt token) dan dependencies FastAPI
(koneksi database, user session, rate limit, dsb) agar dapat digunakan di seluruh aplikasi.
"""

# Mengimpor fungsi-fungsi penanganan keamanan password dan pembuatan/validasi token JWT
from app.core.security import (
    hash_password,        # Fungsi untuk melakukan enkripsi satu arah pada password
    verify_password,      # Fungsi untuk membandingkan password mentah dengan password terenkripsi
    create_access_token,  # Fungsi untuk membuat token akses JWT berdurasi pendek
    create_refresh_token, # Fungsi untuk membuat token penyegar JWT berdurasi panjang
    decode_token,         # Fungsi untuk mendekode isi token JWT dan memvalidasi keasliannya
    hash_token,           # Fungsi untuk melakukan hashing token (misalnya untuk disimpan di DB)
    get_token_expiry,     # Fungsi untuk mengambil waktu kedaluwarsa dari token JWT
)
# Mengimpor dependensi-dependensi FastAPI yang digunakan sebagai injeksi parameter endpoint
from app.core.dependencies import (
    get_current_user,     # Dependensi untuk mendapatkan data user yang sedang login aktif
    get_admin_user,       # Dependensi untuk memastikan user yang login memiliki peran admin
    verify_iot_api_key,   # Dependensi untuk memverifikasi API Key yang dikirim oleh perangkat IoT
    CurrentUser,          # Type alias / dependensi untuk mempermudah injeksi user saat ini
    AdminUser,            # Type alias / dependensi untuk mempermudah injeksi admin saat ini
    IoTAuth,              # Type alias / dependensi untuk mempermudah injeksi otentikasi IoT
    DB,                   # Type alias / dependensi untuk mempermudah injeksi session database SQLAlchemy
    AppSettings,          # Type alias / dependensi untuk mempermudah injeksi konfigurasi aplikasi
)

# Mengekspos variabel dan fungsi di atas agar bisa diimpor langsung dari package 'app.core'
__all__ = [
    "hash_password",
    "verify_password",
    "create_access_token",
    "create_refresh_token",
    "decode_token",
    "hash_token",
    "get_token_expiry",
    "get_current_user",
    "get_admin_user",
    "verify_iot_api_key",
    "CurrentUser",
    "AdminUser",
    "IoTAuth",
    "DB",
    "AppSettings",
]
