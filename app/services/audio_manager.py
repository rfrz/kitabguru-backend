# Mengimpor modul io untuk mengelola stream data biner dalam memori
import io
# Mengimpor helper get_settings untuk memuat pengaturan audio
from app.config import get_settings

# Kelas AudioManager mengelola pemanggilan mesin STT dan TTS secara asinkron dengan metode lazy loading
class AudioManager:
    """
    Memuat mesin STT dan TTS secara asinkron hanya saat dibutuhkan (lazy load)
    untuk menghemat pemakaian RAM server saat fitur audio sedang tidak digunakan.
    """
    # Menyimpan instance engine Speech-to-Text (STT) secara cache (lazy loading)
    _stt_engine = None
    # Menyimpan instance engine Text-to-Speech (TTS) secara cache
    _tts_engine = None

    @classmethod
    # Metode kelas untuk inisiasi engine STT berdasarkan provider pilihan di konfigurasi
    def get_stt(cls):
        # Mengambil konfigurasi aplikasi saat ini
        settings = get_settings()
        # Memeriksa apakah provider STT diatur menggunakan local model (faster_whisper)
        if settings.stt_provider == "local":
            # Jika engine STT lokal belum pernah diinisiasi sebelumnya
            if cls._stt_engine is None:
                # Mengimpor library model Whisper lokal secara dinamis untuk menghemat memori
                from faster_whisper import WhisperModel
                # Inisiasi model Whisper versi "base" berjalan di CPU menggunakan tipe presisi int8 (ringan)
                cls._stt_engine = WhisperModel("base", device="cpu", compute_type="int8")
            # Mengembalikan engine STT lokal
            return cls._stt_engine
        # Jika provider menggunakan layanan cloud API (Groq)
        else:
            # Jika client Groq belum pernah dibuat sebelumnya
            if cls._stt_engine is None:
                # Mengimpor client asinkron Groq secara dinamis
                from groq import AsyncGroq
                # Membuat instance client Groq dengan menyertakan API key dari config
                cls._stt_engine = AsyncGroq(api_key=settings.groq_api_key)
            # Mengembalikan client Groq yang ter-cache
            return cls._stt_engine

    @classmethod
    # Mentranskripsikan byte data rekaman suara menjadi teks tertulis
    async def transcribe(cls, audio_bytes: bytes, filename: str = "audio.wav") -> str:
        # Mengambil konfigurasi aplikasi
        settings = get_settings()
        # Jika menggunakan STT local
        if settings.stt_provider == "local":
            # Dapatkan model faster_whisper ter-cache
            model = cls.get_stt()
            # Mengubah data biner audio bytes menjadi objek file-like BytesIO yang didukung faster-whisper
            audio_io = io.BytesIO(audio_bytes)
            # Menjalankan proses transkripsi dengan beam size 5 untuk akurasi optimal
            segments, info = model.transcribe(audio_io, beam_size=5)
            # Menggabungkan seluruh teks potongan segmentasi kalimat menjadi satu string utuh
            text = " ".join([segment.text for segment in segments])
            # Mengembalikan string teks transkripsi
            return text
        # Jika menggunakan API Groq
        else:
            # Dapatkan client Groq ter-cache
            client = cls.get_stt()
            # Memanggil API Groq audio transcription asinkron
            transcription = await client.audio.transcriptions.create(
                # Menyertakan nama file dan bytes rekaman suara
                file=(filename, audio_bytes),
                # Menetapkan model Whisper yang akan berjalan di Groq
                model=settings.groq_whisper_model,
                # Mengunci transkripsi ke dalam Bahasa Indonesia
                language="id",
            )
            # Mengembalikan teks transkripsi hasil respon Groq
            return transcription.text

    @classmethod
    # Metode kelas untuk inisiasi engine TTS lokal (Piper)
    def get_tts(cls):
        # Mengambil konfigurasi aplikasi
        settings = get_settings()
        # Memeriksa apakah provider TTS diatur ke local
        if settings.tts_provider == "local":
            # Jika engine TTS lokal belum diinisiasi
            if cls._tts_engine is None:
                # Mengimpor modul sistem operasi untuk penanganan file lokal
                import os
                # Mengimpor tarfile untuk mengekstrak model kompresi
                import tarfile
                # Mengimpor urllib untuk fungsi unduh file otomatis dari internet
                import urllib.request
                # Mengimpor modul pengisi suara Piper
                from piper.voice import PiperVoice
                
                # Path model lokal
                model_path = "en_US-lessac-medium.onnx"
                # Jika file model ONNX belum ada di folder lokal
                if not os.path.exists(model_path):
                    # Placeholder unduh model otomatis (dummy)
                    pass
                
                # Placeholder inisiasi model PiperVoice
                pass
            # Mengembalikan engine TTS lokal
            return cls._tts_engine
        # Mengembalikan None jika menggunakan cloud provider (edge_tts tidak perlu engine persistent)
        return None

    @classmethod
    # Mengonversi teks menjadi data bytes biner suara (TTS)
    async def synthesize(cls, text: str) -> bytes:
        # Mengambil konfigurasi settings
        settings = get_settings()
        # Jika menggunakan model lokal
        if settings.tts_provider == "local":
            # Placeholder pengerjaan TTS lokal menggunakan Piper
            raise NotImplementedError("Piper TTS local synthesis not fully implemented in demo")
        # Jika menggunakan edge-tts
        else:
            # Mengimpor edge_tts secara dinamis
            import edge_tts
            # Membuat objek Communicate dengan parameter teks, tipe suara, rate, dan volume
            communicate = edge_tts.Communicate(
                text, 
                settings.tts_voice,
                rate=settings.tts_rate,
                volume=settings.tts_volume
            )
            # Menginisialisasi objek bytearray kosong untuk menampung stream data audio
            audio_data = bytearray()
            # Iterasi secara asinkron melalui chunk stream audio dari edge-tts
            async for chunk in communicate.stream():
                # Jika jenis chunk yang diterima adalah tipe data audio biner
                if chunk["type"] == "audio":
                    # Gabungkan potongan bytes data audio ke buffer penampung
                    audio_data.extend(chunk["data"])
            # Mengembalikan kumpulan data audio utuh dalam format bytes biner
            return bytes(audio_data)
