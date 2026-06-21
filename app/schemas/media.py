# Mengimpor modul datetime untuk penanganan tanggal dan waktu
from datetime import datetime
# Mengimpor Optional untuk menandai tipe data yang boleh kosong (None)
from typing import Optional

# Mengimpor BaseModel untuk deklarasi skema validasi Pydantic
from pydantic import BaseModel


# Skema ImageGenerateRequest memvalidasi request body saat meminta generate gambar
class ImageGenerateRequest(BaseModel):
    # ID sesi obrolan tempat meminta gambar
    session_id: str
    # ID pesan terkait (opsional)
    message_id: Optional[str] = None


# Skema ImageGenerateResponse merespon informasi gambar yang berhasil dibuat
class ImageGenerateResponse(BaseModel):
    # ID media gambar yang berhasil terdaftar di database
    media_id: str
    # Prompt bahasa Inggris final yang dipakai untuk generate gambar
    prompt_used: Optional[str]
    # URL publik gambar hasil generate
    image_url: str
    # Status ketersediaan gambar (misalnya: completed)
    status: str


# Skema VideoGenerateRequest memvalidasi request body saat meminta pembuatan video slide
class VideoGenerateRequest(BaseModel):
    # ID sesi obrolan terkait
    session_id: str
    # ID pesan yang memicu pembuatan video (opsional)
    message_id: Optional[str] = None


# Skema VideoGenerateResponse mengembalikan tanda terima tugas background worker pembuat video
class VideoGenerateResponse(BaseModel):
    # ID pekerjaan background worker (job_id) untuk polling status
    job_id: str
    # ID media video yang dibuat di database
    media_id: str
    # Status awal pengerjaan job, default "queued"
    status: str = "queued"


# Skema JobStatusResponse merespon status pengerjaan pembuatan video slide secara asinkron
class JobStatusResponse(BaseModel):
    # ID pekerjaan background task
    job_id: str
    # Status pengerjaan saat ini (queued, processing, completed, atau failed)
    status: str
    # Kemajuan persentase pemrosesan (0 sampai 100)
    progress_pct: Optional[int] = None
    # URL file video jadi untuk diputar (hanya terisi jika status = completed)
    video_url: Optional[str] = None
    # Keterangan error jika status pengerjaan gagal
    error: Optional[str] = None
    # Waktu dimulainya pemrosesan oleh background worker
    started_at: Optional[datetime] = None
    # Waktu selesainya pemrosesan video slide
    completed_at: Optional[datetime] = None


# Skema MediaOut merepresentasikan representasi detail objek media untuk galeri
class MediaOut(BaseModel):
    # ID unik media
    id: str
    # Tipe media (image atau video)
    media_type: str
    # Path lokasi file media di server lokal
    file_path: str
    # Teks prompt yang digunakan untuk men-generate media ini
    prompt_used: Optional[str]
    # Status ketersediaan media
    status: str
    # Tanggal request media dibuat
    created_at: datetime
    # Tanggal media selesai diproses
    completed_at: Optional[datetime] = None

    # Mengizinkan pemetaan otomatis dari atribut objek model ORM database
    model_config = {"from_attributes": True}


# Skema MediaListResponse merespon daftar galeri media hasil generate milik user
class MediaListResponse(BaseModel):
    # List data detail media hasil generate
    media: list[MediaOut]
    # Total keseluruhan file media milik user di database (untuk paginasi)
    total: int
