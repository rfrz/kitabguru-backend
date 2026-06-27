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


# Kelas IoTService mengelola siklus hidup suara dari perangkat IoT
class IoTService:
    # Inisialisasi service dengan sesi database, settings, dan client RAG
    def __init__(
        self,
        db: AsyncSession,
        settings: Settings,
        inference_client = None,
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

