# Mengimpor lru_cache untuk menyimpan hasil pemanggilan fungsi agar tidak diulang (caching)
from functools import lru_cache
# Mengimpor Path untuk mempermudah operasi path folder dan file di sistem operasi
from pathlib import Path
# Mengimpor Optional untuk menandai tipe data yang boleh bernilai None (kosong)
from typing import Optional

# Mengimpor validator lapangan (field_validator) dari Pydantic untuk memvalidasi nilai field
from pydantic import field_validator
# Mengimpor BaseSettings dan SettingsConfigDict untuk mengelola konfigurasi aplikasi lewat env variables
from pydantic_settings import BaseSettings, SettingsConfigDict


# Kelas Settings mewarisi BaseSettings untuk menampung seluruh konfigurasi aplikasi
class Settings(BaseSettings):
    # Mengatur konfigurasi Pydantic Settings untuk membaca file .env dengan encoding utf-8
    model_config = SettingsConfigDict(
        # Menentukan nama file konfigurasi environment
        env_file=".env",
        # Menentukan format karakter file env menggunakan utf-8
        env_file_encoding="utf-8",
        # Mengabaikan nilai kosong di file env agar digantikan nilai default
        env_ignore_empty=True,
        # Mengabaikan variabel tambahan di file env yang tidak didefinisikan di sini
        extra="ignore",
    )

    # ── Bagian App (Aplikasi) ─────────────────────────────────────────────
    # Nama aplikasi, defaultnya "KitabGuru Backend"
    app_name: str = "KitabGuru Backend"
    # Port tempat aplikasi backend FastAPI akan berjalan
    app_port: int = 8001
    # Prefix atau awalan URL untuk seluruh endpoint API
    api_prefix: str = "/api/v1"
    # Daftar origin (domain frontend) yang diperbolehkan mengakses API (CORS)
    cors_origins: str = "http://localhost:5173,http://localhost:3000"

    # ── Bagian Database ───────────────────────────────────────────────────
    # URL koneksi database PostgreSQL async menggunakan pustaka asyncpg
    database_url: str = "postgresql+asyncpg://kitabguru:secret@localhost:5432/kitabguru_db"

    # Validator untuk membersihkan dan menyeimbangkan format database_url setelah diisi
    @field_validator("database_url", mode="after")
    @classmethod
    # Metode kelas untuk memformat ulang database_url jika formatnya kurang sesuai
    def clean_database_url(cls, v: str) -> str:
        # Jika URL dimulai dengan postgres:// (bawaan heroku/paas), ubah menjadi postgresql+asyncpg://
        if v.startswith("postgres://"):
            # Mengganti string postgres:// menjadi skema asyncpg secara tepat 1 kali
            v = v.replace("postgres://", "postgresql+asyncpg://", 1)
        # asyncpg tidak mendukung parameter sslmode=require di string koneksi, mari kita bersihkan
        if "?sslmode=require" in v:
            # Menghapus parameter ?sslmode=require dari URL
            v = v.replace("?sslmode=require", "")
        # Jika sslmode berada di bagian akhir parameter query dengan separator &
        elif "&sslmode=require" in v:
            # Menghapus parameter &sslmode=require dari URL
            v = v.replace("&sslmode=require", "")
        # Mengembalikan string URL database yang sudah bersih dan kompatibel dengan asyncpg
        return v

    # ── Bagian JWT (Keamanan Token) ───────────────────────────────────────
    # Kunci rahasia untuk enkripsi token JWT (harus diganti di server production)
    jwt_secret_key: str = "change-this-in-production"
    # Algoritma enkripsi yang digunakan untuk menandatangani JWT
    jwt_algorithm: str = "HS256"
    # Waktu kedaluwarsa token akses JWT (dalam menit), default 30 menit
    jwt_access_token_expire_minutes: int = 30
    # Waktu kedaluwarsa token penyegar / refresh token (dalam hari), default 30 hari
    jwt_refresh_token_expire_days: int = 30

    # ── Bagian Admin Seed (Data Awal Admin) ───────────────────────────────
    # Alamat email untuk akun administrator default
    admin_email: str = "admin@kitabguru.com"
    # Username untuk akun administrator default
    admin_username: str = "admin"
    # Password default akun administrator (harus diganti setelah dideploy)
    admin_password: str = "ChangeThisPassword!"

    # ── Bagian Layanan Inferensi (Inference Service) ──────────────────────
    # URL dasar layanan model bahasa / RAG (mengarah ke service inference)
    inference_base_url: str = "http://localhost:8000"
    # Token akses API Hugging Face (opsional)
    hf_token: Optional[str] = None

    # ── Bagian Internet of Things (IoT) ───────────────────────────────────
    # Kunci API rahasia untuk memverifikasi request dari perangkat keras IoT
    iot_api_key: str = "change-this-iot-key"

    # ── Pipeline LLM Ringan (Menterjemahkan prompt gambar ke bahasa Inggris) ──
    # Urutan alternatif penyedia LLM (gemini dulu, jika gagal coba openai_compatible)
    llm_fallback_order: str = "gemini,openai_compatible"
    # Kunci API Google Gemini (opsional, jika ingin memakai model Gemini)
    gemini_api_key: Optional[str] = None
    # Nama model Gemini yang digunakan, default menggunakan model ringan
    gemini_llm_model: str = "gemini-3.1-flash-lite"
    # Kunci API untuk provider alternatif yang kompatibel dengan format OpenAI
    openai_compatible_api_key: Optional[str] = None
    # URL endpoint dasar untuk provider alternatif yang kompatibel dengan OpenAI
    openai_compatible_base_url: Optional[str] = None
    # Nama model untuk provider alternatif yang kompatibel dengan OpenAI
    openai_compatible_model: Optional[str] = None

    # ── Cloudflare Workers AI (Untuk Pembuatan Gambar Generatif) ──────────
    # ID akun Cloudflare Workers (opsional)
    cf_account_id: Optional[str] = None
    # Token API Cloudflare Workers (opsional)
    cf_api_token: Optional[str] = None
    # Nama model AI pembuat gambar yang akan dipanggil di Cloudflare
    cf_image_model: str = "@cf/stabilityai/stable-diffusion-xl-base-1.0"

    # ── Groq Speech-to-Text (STT) ─────────────────────────────────────────
    # Kunci API Groq untuk layanan transkripsi suara
    groq_api_key: Optional[str] = None
    # Model Whisper yang dijalankan di Groq, default versi large v3
    groq_whisper_model: str = "whisper-large-v3"

    # ── Pengaturan Provider Pihak Ketiga ──────────────────────────────────
    # Pilihan provider transkripsi suara (default: "groq")
    stt_provider: str = "groq"
    # Pilihan provider suara buatan / Text-to-Speech (default: "edge_tts")
    tts_provider: str = "edge_tts"

    # ── Edge Text-to-Speech (TTS) ─────────────────────────────────────────
    # Suara yang digunakan untuk TTS Bahasa Indonesia, default suara Ardi
    tts_voice: str = "id-ID-ArdiNeural"
    # Mengatur kecepatan bicara audio TTS, default kecepatan normal (+0%)
    tts_rate: str = "+0%"
    # Mengatur tingkat volume audio TTS, default volume normal (+0%)
    tts_volume: str = "+0%"

    # ── Media Penyimpanan ─────────────────────────────────────────────────
    # Path folder penyimpanan lokal untuk file media hasil generate / upload
    media_dir: str = "./media"
    # URL publik untuk mengakses media yang tersimpan di server
    media_base_url: str = "http://localhost:8001/media"

    # ── Pipeline Video - Palet Warna Bertema Estetika Islami ──────────────
    # Path/perintah untuk mengeksekusi FFmpeg di sistem operasi
    ffmpeg_path: str = "ffmpeg"
    # Warna latar belakang slide video: biru dongker gelap (#0d1b2a)
    video_slide_bg_color: str = "#0d1b2a"
    # Warna aksen pembatas/bingkai: emas Islami (#c9a84c)
    video_slide_accent_color: str = "#c9a84c"
    # Warna teks utama dalam slide: putih hangat (#f0ece2)
    video_slide_text_color: str = "#f0ece2"
    # Warna teks sub-elemen / terjemahan: teal lembut (#8ab4b8)
    video_slide_sub_color: str = "#8ab4b8"
    # Lebar resolusi video slide (1280 piksel / HD)
    video_slide_width: int = 1280
    # Tinggi resolusi video slide (720 piksel / HD)
    video_slide_height: int = 720

    # ── Penjadwal Penghapusan Data (Soft Delete Cleanup) ──────────────────
    # Batas jumlah hari sebelum akun yang di-soft-delete dihapus permanen
    purge_soft_delete_after_days: int = 30

    # ── Ukuran Jendela Konteks Chat (Chat Context Window) ──────────────────
    # Jumlah histori pesan terakhir yang dikirim ke model RAG (0 artinya kirim semua)
    chat_context_window: int = 20

    # ── Batas Frekuensi Akses (Rate Limiting) ──────────────────────────────
    # Batas frekuensi akses endpoint auth per menit per IP address
    rate_limit_auth_per_minute: int = 5
    # Batas frekuensi request generate media per jam per user terdaftar
    rate_limit_media_per_hour: int = 10
    # Batas frekuensi request umum API per menit per user terdaftar
    rate_limit_api_per_minute: int = 60

    # Mengembalikan daftar asal domain CORS dalam bentuk list Python
    @property
    def cors_origin_list(self) -> list[str]:
        # Jika cors_origins diset ke '*', maka ijinkan semua domain
        if self.cors_origins.strip() == "*":
            # Mengembalikan list berisi '*'
            return ["*"]
        # Memisahkan string CORS dengan koma dan membuang spasi kosong di ujung string
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    # Memastikan direktori folder media telah dibuat di filesystem lokal
    def ensure_media_dir(self) -> None:
        # Membuat folder media dan folder induknya jika belum ada, tanpa error jika sudah ada
        Path(self.media_dir).mkdir(parents=True, exist_ok=True)


# Menyimpan instance konfigurasi dalam cache agar tidak membaca file env berulang kali
@lru_cache
def get_settings() -> Settings:
    # Membuat satu objek Settings baru
    settings = Settings()
    # Memastikan folder media penyimpanan lokal sudah siap digunakan
    settings.ensure_media_dir()
    # Mengembalikan objek konfigurasi ter-cache
    return settings
