"""
Layanan Media (Media Service): Mengelola pembuatan gambar AI instan dan inisiasi antrean job pembuatan video slide presentasi.
"""
# Mengimpor modul uuid untuk menggenerasi ID unik gambar/video
import uuid
# Mengimpor Path untuk pengelolaan folder media lokal
from pathlib import Path

# Mengimpor BackgroundTasks dari FastAPI untuk antrean background task asinkron
from fastapi import BackgroundTasks, HTTPException, status
# Mengimpor select dari SQLAlchemy
from sqlalchemy import select
# Mengimpor AsyncSession untuk sesi transaksi database asinkron
from sqlalchemy.ext.asyncio import AsyncSession

# Mengimpor skema Settings untuk URL dasar media dan palet video
from app.config import Settings
# Mengimpor model database GeneratedMedia, JobStatus, MediaJob, MediaStatus, dan MediaType
from app.models.media import GeneratedMedia, JobStatus, MediaJob, MediaStatus, MediaType
# Mengimpor model database ChatSession, Message, MessageRole, dan User
from app.models.user import ChatSession, Message, MessageRole, User
# Mengimpor client Cloudflare Workers AI beserta Exception-nya
from app.providers.cloudflare_image import CloudflareImageClient, CloudflareImageError
# Mengimpor client inferensi RAG asinkron
from app.providers.inference_client import InferenceClient
# Mengimpor client LLM ringan untuk penterjemahan prompt
from app.providers.light_llm import LightLLMClient
# Mengimpor DTO respon media Pydantic
from app.schemas.media import ImageGenerateResponse, VideoGenerateResponse
# Mengimpor fungsi video pipeline pengeksekusi asinkron FFmpeg
from app.tasks.video_pipeline import run_video_pipeline


# Kelas MediaService mengelola pembuatan gambar/video presentasi AI edukasi
class MediaService:
    # Inisialisasi service dengan sesi database, settings, dan client RAG
    def __init__(self, db: AsyncSession, settings: Settings, inference_client: InferenceClient):
        self.db = db
        self.settings = settings
        self.inference_client = inference_client

    # ─── Pembuatan Gambar AI (Image Generation Flow) ──────────────────────

    # Menggenerasi gambar AI berdasarkan konteks obrolan chat saat ini
    async def generate_image(self, session_id: str, message_id: str | None, user: User) -> ImageGenerateResponse:
        """
        Alur pengerjaan pembuatan gambar:
        1. Mengambil riwayat percakapan sesi obrolan.
        2. Meringkas dan menterjemahkan riwayat chat menjadi prompt gambar bahasa Inggris (Light LLM).
        3. Memanggil API Cloudflare Workers AI (SDXL).
        4. Menyimpan file gambar ke penyimpanan lokal server dan mencatat di database.
        5. Mengirimkan gambar tersebut ke balon chat dan mengembalikan metadata detail.
        """
        # Mendapatkan sesi obrolan chat dan memvalidasi hak miliknya
        session = await self._get_session_or_404(session_id, user)

        # Langkah 1: Membangun prompt gambar bahasa Inggris dari konteks chat
        prompt = await self._build_image_prompt(session, message_id)

        # Langkah 2: Mengirim request generate gambar ke API Cloudflare Workers AI
        try:
            cf_client = CloudflareImageClient(self.settings)
            image_bytes = await cf_client.generate(prompt)
        except CloudflareImageError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Image generation failed: {exc}",
            )

        # Langkah 3: Menyimpan data biner gambar ke sistem penyimpanan server lokal
        media_id = uuid.uuid4()
        media_dir = Path(self.settings.media_dir)
        img_path = media_dir / f"{media_id}.png"
        img_path.write_bytes(image_bytes)
        relative_path = f"{media_id}.png"

        # Langkah 4: Mencatat riwayat file gambar ke database di tabel generated_media
        media = GeneratedMedia(
            id=media_id,
            session_id=session.id,
            user_id=user.id,
            media_type=MediaType.image,
            file_path=relative_path,
            file_size_bytes=len(image_bytes),
            prompt_used=prompt,
            status=MediaStatus.completed,
        )
        from datetime import datetime, timezone
        media.completed_at = datetime.now(timezone.utc)
        self.db.add(media)
        
        # Langkah 5: Memasukkan link gambar hasil generate sebagai balon balon chat AI baru
        new_msg = Message(
            session_id=session.id,
            role=MessageRole.assistant,
            content="Berikut adalah media yang di-generate berdasarkan konteks percakapan kita:",
            meta={
                "media_type": "image",
                "url": f"{self.settings.media_base_url}/{relative_path}",
                "media_id": str(media_id)
            }
        )
        self.db.add(new_msg)

        # Commit seluruh perubahan transaksi database secara permanen
        await self.db.commit()
        # Perbarui instance data media
        await self.db.refresh(media)

        # Menyusun URL publik gambar
        image_url = f"{self.settings.media_base_url}/{relative_path}"
        # Mengembalikan DTO sukses respon gambar
        return ImageGenerateResponse(
            media_id=str(media.id),
            prompt_used=prompt,
            image_url=image_url,
            status=media.status.value,
        )

    # ─── Pembuatan Video Slide (Video Generation Flow) ──────────────────────

    # Memulai pengerjaan pembuatan video slide presentasi secara asinkron di latar belakang
    async def start_video_job(
        self,
        session_id: str,
        message_id: str | None,
        user: User,
        background_tasks: BackgroundTasks,
        session_maker,
    ) -> VideoGenerateResponse:
        """
        Alur inisiasi tugas pembuatan video:
        1. Mengambil sesi chat dan meringkas percakapan menjadi teks narasi video slide (Light LLM).
        2. Membuat record data awal di tabel generated_media dan media_jobs dengan status antrean (queued).
        3. Mendaftarkan fungsi pipeline pengerjaan video ke antrean background task FastAPI.
        4. Mengembalikan ID job secara instan ke client (non-blocking).
        """
        # Mendapatkan sesi obrolan chat dan memvalidasi hak miliknya
        session = await self._get_session_or_404(session_id, user)

        # Menyusun naskah narasi slide dan bahasa video dari riwayat chat
        script_data = await self._build_narration(session, message_id)

        # Membuat ID unik media dan ID unik job
        media_id = uuid.uuid4()
        job_id = uuid.uuid4()

        # Mencatat data awal video di tabel generated_media
        media = GeneratedMedia(
            id=media_id,
            session_id=session.id,
            user_id=user.id,
            media_type=MediaType.video,
            # Menetapkan path target file video jadi
            file_path=f"{media_id}/{media_id}.mp4",
            prompt_used=script_data["script_text"],
            status=MediaStatus.processing,
        )
        # Mencatat status pengerjaan awal antrean di tabel media_jobs
        job = MediaJob(
            id=job_id,
            media_id=media_id,
            status=JobStatus.queued,
            progress_pct=0,
        )
        # Menambahkan data ke transaksi
        self.db.add(media)
        self.db.add(job)
        # Commit awal penyimpanan data record antrean ke database
        await self.db.commit()

        # Mendaftarkan fungsi pipeline generator video (FFmpeg) ke antrean background task asinkron
        background_tasks.add_task(
            run_video_pipeline,
            job_id=job_id,
            media_id=media_id,
            narration_text=script_data["script_text"],
            language_code=script_data["language_code"],
            session_maker=session_maker,
            settings=self.settings,
        )

        # Mengembalikan respon info job_id asinkron
        return VideoGenerateResponse(
            job_id=str(job_id),
            media_id=str(media_id),
            status="queued",
        )

    # ─── Method Helper Internal ───────────────────────────────────────────

    # Mengambil objek sesi chat dari database dan mencocokkan hak akses pengguna
    async def _get_session_or_404(self, session_id: str, user: User) -> ChatSession:
        # Memastikan string ID sesi berformat UUID valid
        try:
            sid = uuid.UUID(session_id)
        except ValueError:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

        # Mengimpor selectinload
        from sqlalchemy.orm import selectinload
        # Query mengambil data sesi chat beserta eager load data riwayat pesan
        result = await self.db.execute(
            select(ChatSession)
            .options(selectinload(ChatSession.messages))
            .where(ChatSession.id == sid, ChatSession.user_id == user.id)
        )
        session = result.scalar_one_or_none()
        # Jika sesi kosong atau user bukan pembuat asli
        if not session:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
        # Mengembalikan objek sesi chat
        return session

    # Meringkas percakapan chat menjadi satu prompt gambar bahasa Inggris final
    async def _build_image_prompt(self, session: ChatSession, message_id: str | None) -> str:
        """Meringkas riwayat obrolan sesi chat menjadi prompt gambar bahasa Inggris menggunakan model LLM ringan."""
        # Jika riwayat pesan kosong, kembalikan prompt cadangan default
        if not session.messages:
            return "An Islamic educational scene with books and geometric patterns"

        # Mengambil seluruh daftar pesan chat
        messages = session.messages
        # Jika diinstruksikan membatasi konteks hanya sampai pesan tertentu (message_id)
        if message_id:
            try:
                msg_uuid = uuid.UUID(message_id)
                # Mencari indeks batas pesan target
                idx = next(i for i, m in enumerate(messages) if m.id == msg_uuid)
                # Memotong list pesan sampai batas indeks pesan target
                messages = messages[:idx + 1]
            except (ValueError, StopIteration):
                pass

        # Membersihkan tag sitasi RAG (seperti [S1], [S2]) dari teks pesan chat sebelum diringkas
        import re
        cleaned_messages = []
        for m in messages:
            clean_content = re.sub(r'\[S\d+\]', '', m.content)
            cleaned_messages.append(f"{m.role.value}: {clean_content}")

        # Menggabungkan seluruh list balon obrolan menjadi satu string percakapan utuh
        context = "\n".join(cleaned_messages)

        # Memanggil client LightLLMClient untuk menterjemahkan chat tersebut menjadi prompt bahasa Inggris
        llm = LightLLMClient(self.settings)
        # Mengirimkan 5000 karakter pertama konteks chat ke model LLM
        return await llm.generate_image_prompt(context[:5000])

    # Meringkas percakapan chat menjadi naskah naskah video slide dan bahasanya
    async def _build_narration(self, session: ChatSession, message_id: str | None) -> dict:
        """Meringkas percakapan chat menjadi teks naskah narasi slide dan mendeteksi bahasa untuk TTS video."""
        # Jika riwayat pesan kosong, kembalikan teks narasi default
        if not session.messages:
            return {
                "language_code": "id-ID",
                "script_text": "Selamat datang di KitabGuru, platform pembelajaran Islam berbasis AI."
            }

        # Mengambil seluruh list pesan chat
        messages = session.messages
        # Memotong list pesan sampai batas indeks pesan target (jika ditentukan)
        if message_id:
            try:
                msg_uuid = uuid.UUID(message_id)
                idx = next(i for i, m in enumerate(messages) if m.id == msg_uuid)
                messages = messages[:idx + 1]
            except (ValueError, StopIteration):
                pass
        
        # Membersihkan tag sitasi RAG dari teks pesan chat
        import re
        cleaned_messages = []
        for m in messages:
            clean_content = re.sub(r'\[S\d+\]', '', m.content)
            cleaned_messages.append(f"{m.role.value}: {clean_content}")

        # Menggabungkan seluruh list balon obrolan
        context = "\n".join(cleaned_messages)

        # Memanggil client LightLLMClient untuk membuat naskah video slide dan mendeteksi bahasanya
        llm = LightLLMClient(self.settings)
        # Mengirimkan 5000 karakter pertama konteks chat ke model LLM
        return await llm.generate_video_script(context[:5000])
