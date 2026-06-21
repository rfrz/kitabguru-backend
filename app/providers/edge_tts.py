"""
Wrapper Edge-TTS untuk menghasilkan suara manusia buatan (neural Text-to-Speech).
Menggunakan mesin Microsoft Edge TTS gratis lewat pustaka edge-tts tanpa memerlukan API Key.
Suara default diatur lewat variabel env TTS_VOICE (default: id-ID-ArdiNeural).
"""
# Mengimpor pustaka asyncio untuk menjalankan proses I/O secara asinkron
import asyncio
# Mengimpor modul Path untuk mengelola path penyimpanan file audio secara cross-platform
from pathlib import Path

# Mengimpor pustaka pihak ketiga edge_tts untuk sintesis suara
import edge_tts

# Mengimpor skema Settings untuk konfigurasi parameter TTS
from app.config import Settings


# Kelas Client untuk konfigurasi dan sintesis suara TTS Microsoft Edge
class EdgeTTSClient:
    # Menginisialisasi parameter suara, kecepatan bicara, dan volume suara dari settings
    def __init__(self, settings: Settings):
        # Menetapkan suara default (misalnya suara pria/wanita bahasa Indonesia)
        self.voice = settings.tts_voice
        # Menetapkan tingkat kecepatan bicara (misalnya normal atau dipercepat)
        self.rate = settings.tts_rate
        # Menetapkan tingkat kekerasan volume suara audio
        self.volume = settings.tts_volume

    # Mengubah string teks menjadi file audio audio MP3/WAV secara asinkron
    async def synthesize(self, text: str, output_path: str, voice: str | None = None) -> str:
        """
        Mengonversi teks menjadi file audio di lokasi path output_path.
        Mengembalikan string output_path jika proses sintesis sukses.
        """
        # Membuat objek Communicate dari edge-tts dengan teks dan parameter suara
        communicate = edge_tts.Communicate(
            text=text,
            # Gunakan suara custom yang dikirimkan atau suara default client
            voice=voice or self.voice,
            rate=self.rate,
            volume=self.volume,
        )
        # Menyimpan hasil streaming suara asinkron ke file lokal
        await communicate.save(output_path)
        # Mengembalikan lokasi file audio yang berhasil disimpan
        return output_path

    # Mendapatkan daftar seluruh suara bahasa Indonesia yang didukung (untuk panel admin)
    async def list_voices(self) -> list[dict]:
        """Mengembalikan daftar suara yang tersedia (khusus kode negara Indonesia id-)."""
        # Meminta daftar suara global dari server Microsoft Edge TTS secara asinkron
        voices = await edge_tts.list_voices()
        # Memfilter daftar suara agar hanya mengembalikan suara bahasa Indonesia
        return [v for v in voices if "id-" in v.get("ShortName", "").lower()]


# Fungsi pembantu eksternal untuk langsung memproses TTS ke file audio tanpa instansiasi manual
async def synthesize_to_file(text: str, output_path: str, settings: Settings) -> str:
    """Fungsi pembantu instan: mengonversi teks langsung menjadi file audio."""
    # Instansiasi objek EdgeTTSClient menggunakan settings yang dikirim
    client = EdgeTTSClient(settings)
    # Memanggil method synthesize asinkron dan mengembalikan hasilnya
    return await client.synthesize(text, output_path)
