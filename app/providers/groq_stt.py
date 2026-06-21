"""
Client Groq Whisper STT (Speech-to-Text) untuk transkripsi audio ke teks.
Memerlukan kunci API GROQ_API_KEY dan model model GROQ_WHISPER_MODEL dari env.
Akselerasi LPU Groq memproses audio dengan sangat cepat (1-2 detik untuk 30 detik audio).
"""
# Mengimpor modul Path untuk penanganan file lokal
from pathlib import Path
# Mengimpor type BinaryIO untuk validasi tipe data input bytes audio
from typing import BinaryIO

# Mengimpor AsyncGroq dari pustaka resmi groq untuk koneksi API secara asinkron
from groq import AsyncGroq

# Mengimpor skema Settings untuk membaca kunci API dan nama model
from app.config import Settings


# Kelas Exception khusus untuk menangani error transkripsi Groq STT
class GroqSTTError(RuntimeError):
    # Mewarisi RuntimeError bawaan Python
    pass


# Kelas Client untuk berinteraksi dengan API transkripsi suara Groq
class GroqSTTClient:
    # Menginisialisasi kunci API dan memverifikasi ketersediaannya di env
    def __init__(self, settings: Settings):
        # Memastikan GROQ_API_KEY diset, lempar error jika kosong
        if not settings.groq_api_key:
            raise GroqSTTError("GROQ_API_KEY is not set in environment")
        # Inisialisasi client asinkron Groq dengan API key
        self._client = AsyncGroq(api_key=settings.groq_api_key)
        # Menetapkan model Whisper yang akan dipanggil (misalnya whisper-large-v3)
        self.model = settings.groq_whisper_model

    # Mentranskripsikan byte audio mentah menjadi teks tertulis
    async def transcribe(self, audio_bytes: bytes, filename: str = "audio.wav") -> str:
        """
        Menterjemahkan rekaman bytes audio menjadi teks menggunakan API Groq Whisper.
        Mengembalikan teks hasil transkripsi dalam bentuk string.
        """
        # Memanggil endpoint transkripsi asinkron dari API Groq
        transcription = await self._client.audio.transcriptions.create(
            # Mengirim file audio dengan nama file dan bytes datanya
            file=(filename, audio_bytes),
            # Menetapkan model Whisper yang digunakan
            model=self.model,
            # Menetapkan format respon text (menghasilkan string polos, bukan JSON)
            response_format="text",
            # Mengunci deteksi bahasa ke Bahasa Indonesia agar hasil transkripsi akurat
            language="id",
        )
        # Mengonversi respon transkripsi ke tipe string polos dan membuang spasi kosong di ujungnya
        return str(transcription).strip()

    # Mentranskripsikan file audio yang tersimpan di disk server lokal
    async def transcribe_file(self, file_path: str) -> str:
        """Mentranskripsikan file audio dari penyimpanan disk lokal."""
        # Membuat objek Path dari lokasi file audio
        path = Path(file_path)
        # Memastikan file audio tersebut benar-benar ada di penyimpanan disk
        if not path.exists():
            raise GroqSTTError(f"Audio file not found: {file_path}")
        # Membaca seluruh data biner file audio tersebut ke memori bytes
        audio_bytes = path.read_bytes()
        # Memanggil fungsi transcribe asinkron dengan menyertakan nama asli file audio tersebut
        return await self.transcribe(audio_bytes, filename=path.name)
