"""
Layanan IoT (IoT Service): menangani interaksi suara (Speech-to-Text -> Inference -> Text-to-Speech) untuk perangkat IoT.
"""
# Mengimpor modul uuid untuk menggenerasi ID unik sesi/pesan
import uuid
# Mengimpor Path dari pathlib untuk pengelolaan file suara IoT secara cross-platform
from pathlib import Path

# Mengimpor kelas HTTPException dan status HTTP dari FastAPI
from fastapi import HTTPException, status
# Mengimpor select untuk query seleksi database SQLAlchemy
from sqlalchemy import select
# Mengimpor AsyncSession untuk sesi transaksi database asinkron
from sqlalchemy.ext.asyncio import AsyncSession
# Mengimpor selectinload untuk eager loading relasi asinkron (jika diperlukan)
from sqlalchemy.orm import selectinload

# Mengimpor skema Settings untuk mengambil konfigurasi volume, rate, dan path media
from app.config import Settings
# Mengimpor model ORM database IoTMessage, IoTMessageRole, dan IoTSession
from app.models.iot import IoTMessage, IoTMessageRole, IoTSession
# Mengimpor client EdgeTTS untuk pembuatan suara respon
from app.providers.edge_tts import EdgeTTSClient
# Mengimpor client transkripsi Groq Whisper STT beserta exception errornya
from app.providers.groq_stt import GroqSTTClient, GroqSTTError
# Mengimpor client inferensi RAG asinkron
from app.providers.inference_client import InferenceClient
# Mengimpor skema respon DTO IoT
from app.schemas.iot import IoTSessionResponse, IoTVoiceResponse


# Kelas IoTService mengelola siklus hidup suara dari perangkat IoT
class IoTService:
    # Inisialisasi service dengan sesi database, settings, dan client RAG
    def __init__(
        self,
        db: AsyncSession,
        settings: Settings,
        inference_client: InferenceClient | None = None,
    ):
        self.db = db
        self.settings = settings
        self.inference_client = inference_client

    # ─── Manajemen Sesi IoT (Session Management) ──────────────────────────────

    # Membuat sesi percakapan IoT baru untuk sebuah perangkat
    async def create_session(self, device_id: str) -> IoTSession:
        """Membuat sesi percakapan IoT baru untuk suatu perangkat."""
        # Instansiasi objek IoTSession baru
        session = IoTSession(device_id=device_id)
        # Menambahkan sesi baru ke transaksi database
        self.db.add(session)
        # Melakukan commit transaksi ke database secara permanen
        await self.db.commit()
        # Memperbarui instance sesi untuk memuat ID ter-generate
        await self.db.refresh(session)
        # Mengembalikan objek sesi IoT
        return session

    # ─── Pipeline Interaksi Suara (Voice Interaction Pipeline) ──────────────────

    # Memproses file rekaman suara dari perangkat IoT, men-generate teks respon, dan suara jawabannya
    async def process_voice(
        self,
        session_id: str,
        audio_bytes: bytes,
        audio_filename: str = "audio.wav",
    ) -> IoTVoiceResponse:
        """
        Alur pipeline suara lengkap:
        1. Transkripsi Groq Whisper STT: mengubah rekaman audio suara menjadi teks.
        2. Menyimpan pesan pertanyaan user ke database.
        3. Memanggil mesin inferensi RAG: mendapatkan jawaban teks AI berdasarkan database buku.
        4. Menyimpan pesan jawaban AI ke database.
        5. Mengonversi teks jawaban AI menjadi file audio suara (Edge-TTS).
        6. Mengembalikan teks dan URL audio respon ke perangkat IoT.
        """
        # Mendapatkan objek sesi IoT aktif berdasarkan ID
        session = await self._get_session_or_404(session_id)

        # Langkah 1: Transkripsi rekaman suara (Speech-to-Text) menggunakan Groq Whisper
        try:
            # Membuat instance client Groq Whisper STT
            stt_client = GroqSTTClient(self.settings)
            # Menjalankan transkripsi asinkron
            question_text = await stt_client.transcribe(audio_bytes, audio_filename)
        # Menangkap error layanan API Groq
        except GroqSTTError as exc:
            # Lempar error HTTP 503 Service Unavailable
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"STT service error: {exc}",
            )

        # Memastikan hasil transkripsi suara tidak kosong
        if not question_text.strip():
            # Lempar error HTTP 422 jika suara tidak jelas atau kosong
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Could not transcribe audio — please speak clearly",
            )

        # Langkah 2: Menyimpan balon pesan user ke database
        user_msg = IoTMessage(
            iot_session_id=session.id,
            role=IoTMessageRole.user,
            content=question_text,
            meta={"provider": "groq-whisper", "model": self.settings.groq_whisper_model},
        )
        # Tambahkan pesan ke sesi transaksi database
        self.db.add(user_msg)
        # Flush transaksi agar pesan user mendapatkan ID unik
        await self.db.flush()

        # Langkah 3: Memanggil mesin inferensi RAG untuk menjawab pertanyaan
        if not self.inference_client:
            # Lempar error 503 jika client RAG tidak terhubung
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Inference client not available",
            )
        try:
            # Mengirimkan hasil transkripsi teks ke model RAG
            inference_response = await self.inference_client.chat(query=question_text)
            # Mengambil jawaban teks AI atau respon default jika kosong
            answer_text = inference_response.get("answer", "Maaf, saya tidak dapat menjawab pertanyaan ini.")
        # Menangkap error kegagalan server inferensi RAG
        except Exception as exc:
            # Lempar error HTTP 502 Bad Gateway
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Inference service error: {exc}",
            )

        # Langkah 4: Pembuatan suara (Text-to-Speech) - Mengubah teks jawaban AI menjadi file audio
        tts_client = EdgeTTSClient(self.settings)
        # Menggenerasi UUID acak untuk nama file audio respon
        audio_id = uuid.uuid4()
        # Menentukan path folder penyimpanan audio khusus IoT di folder media
        media_dir = Path(self.settings.media_dir) / "iot_audio"
        # Membuat folder tersebut jika belum ada
        media_dir.mkdir(parents=True, exist_ok=True)
        # Menentukan path file audio MP3 akhir
        audio_path = media_dir / f"{audio_id}.mp3"

        try:
            # Mensintesis teks jawaban AI ke file audio lokal secara asinkron
            await tts_client.synthesize(answer_text, str(audio_path))
        # Menangkap error sintesis audio
        except Exception as exc:
            # Kegagalan audio bersifat non-fatal, kita tetap kirim teksnya ke user
            audio_path = None

        # Menentukan relative path file audio untuk URL eksternal
        relative_audio_path = f"iot_audio/{audio_id}.mp3" if audio_path and audio_path.exists() else None

        # Langkah 5: Menyimpan balon pesan jawaban AI ke database
        assistant_msg = IoTMessage(
            iot_session_id=session.id,
            role=IoTMessageRole.assistant,
            content=answer_text,
            # Menyimpan relative path file audio jawaban
            audio_path=relative_audio_path,
            # Menyimpan metadata sumber dan pengisi suara
            meta={
                "provider_used": inference_response.get("provider_used"),
                "sources": inference_response.get("sources"),
                "tts_voice": self.settings.tts_voice,
            },
        )
        # Tambahkan pesan AI ke transaksi
        self.db.add(assistant_msg)
        # Commit seluruh data transaksi pesan suara ke database secara permanen
        await self.db.commit()
        # Perbarui data objek pesan AI
        await self.db.refresh(assistant_msg)

        # Menyusun URL lengkap file audio untuk diunduh/diputar oleh perangkat IoT
        audio_url = (
            f"{self.settings.media_base_url}/{relative_audio_path}"
            if relative_audio_path
            else ""
        )

        # Mengembalikan DTO respon suara IoT lengkap
        return IoTVoiceResponse(
            iot_message_id=str(assistant_msg.id),
            text_question=question_text,
            text_answer=answer_text,
            audio_url=audio_url,
        )

    # ─── Method Helper Internal ───────────────────────────────────────────

    # Mengambil objek sesi IoT dari database atau melempar error HTTP 404 jika tidak terdaftar
    async def _get_session_or_404(self, session_id: str) -> IoTSession:
        # Memastikan ID sesi bertipe UUID valid
        try:
            sid = uuid.UUID(session_id)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="IoT session not found"
            )

        # Query pencarian sesi berdasarkan ID
        result = await self.db.execute(
            select(IoTSession).where(IoTSession.id == sid)
        )
        session = result.scalar_one_or_none()
        # Jika sesi kosong
        if not session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="IoT session not found"
            )
        # Mengembalikan objek sesi
        return session
