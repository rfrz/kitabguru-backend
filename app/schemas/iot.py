# Mengimpor modul datetime untuk tipe data penanggalan
from datetime import datetime
# Mengimpor Any dan Optional dari typing untuk fleksibilitas nilai kosong dan data bertipe dinamis
from typing import Any, Optional

# Mengimpor kelas BaseModel dari Pydantic untuk validasi data IoT
from pydantic import BaseModel



# Skema IoTMessageOut merepresentasikan data balon obrolan dalam database IoT
class IoTMessageOut(BaseModel):
    # ID unik pesan obrolan IoT
    id: str
    # Peran pengirim pesan (user atau assistant)
    role: str
    # Konten transkrip teks pesan obrolan
    content: str
    # Path file audio suara pesan (jika ada)
    audio_path: Optional[str] = None
    # Metadata tambahan terkait pesan (seperti confidence rate STT)
    metadata: Optional[dict[str, Any]] = None
    # Waktu pembuatan pesan obrolan
    created_at: datetime

    # Mengizinkan pemetaan otomatis dari atribut objek model ORM database
    model_config = {"from_attributes": True}


# Skema IoTSessionDetailResponse merespon detail sesi obrolan IoT dan transkrip lengkapnya
class IoTSessionDetailResponse(BaseModel):
    # ID sesi obrolan IoT
    session_id: str
    # ID perangkat IoT
    device_id: str
    # Waktu sesi dimulai
    started_at: datetime
    # Waktu sesi berakhir (bernilai null jika masih aktif berjalan)
    ended_at: Optional[datetime] = None
    # Daftar seluruh riwayat percakapan suara dalam sesi IoT tersebut
    messages: list[IoTMessageOut]


# Skema IoTSessionSummary memberikan ringkasan data sesi obrolan IoT untuk admin
class IoTSessionSummary(BaseModel):
    # ID sesi obrolan IoT
    id: str
    # ID perangkat IoT
    device_id: str
    # Waktu sesi dimulai
    started_at: datetime
    # Waktu sesi berakhir (null jika masih aktif)
    ended_at: Optional[datetime] = None
    # Total akumulasi jumlah pesan suara dalam sesi ini
    message_count: int = 0

    # Mengizinkan pemetaan otomatis dari atribut objek model ORM database
    model_config = {"from_attributes": True}


# Skema IoTSessionListResponse merespon daftar histori sesi IoT secara terpaginasi
class IoTSessionListResponse(BaseModel):
    # List berisi ringkasan data sesi IoT
    sessions: list[IoTSessionSummary]
    # Total keseluruhan sesi IoT di database
    total: int
    # Halaman data yang saat ini diambil
    page: int
    # Batas jumlah baris data per halaman
    limit: int
