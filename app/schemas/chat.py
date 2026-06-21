# Mengimpor modul datetime untuk tipe data penanggalan
from datetime import datetime
# Mengimpor Any dan Optional dari typing untuk fleksibilitas nilai kosong dan data bertipe dinamis
from typing import Any, Optional

# Mengimpor BaseModel dan Field dari Pydantic untuk validasi data chat
from pydantic import BaseModel, Field


# ─── Skema Sesi Chat (Session Schemas) ──────────────────────────────────────────

# Skema SessionCreateRequest memvalidasi input pembuatan sesi chat baru
class SessionCreateRequest(BaseModel):
    # Judul sesi chat opsional, jika diisi panjangnya maksimal 255 karakter
    title: Optional[str] = Field(None, max_length=255)


# Skema SessionRenameRequest memvalidasi input penggantian judul sesi chat
class SessionRenameRequest(BaseModel):
    # Judul sesi chat baru wajib diisi dengan panjang antara 1 hingga 255 karakter
    title: str = Field(min_length=1, max_length=255)


# Skema SessionSummary memberikan data ringkasan sesi obrolan
class SessionSummary(BaseModel):
    # ID sesi obrolan dalam bentuk string
    id: str
    # Judul sesi obrolan (bisa kosong)
    title: Optional[str]
    # Waktu pembuatan sesi obrolan
    created_at: datetime
    # Waktu perubahan sesi obrolan
    updated_at: datetime
    # Jumlah total pesan di dalam sesi obrolan, default bernilai 0
    message_count: int = 0

    # Mengizinkan pemetaan otomatis dari atribut objek model ORM database
    model_config = {"from_attributes": True}


# Skema SessionListResponse merespon daftar sesi obrolan milik user
class SessionListResponse(BaseModel):
    # List berisi ringkasan sesi obrolan
    sessions: list[SessionSummary]
    # Total keseluruhan sesi obrolan yang dimiliki user (untuk paginasi)
    total: int


# ─── Skema Pesan Obrolan (Message Schemas) ──────────────────────────────────────

# Skema MessageOut merepresentasikan data satu baris pesan yang dikirim/diterima
class MessageOut(BaseModel):
    # ID unik pesan
    id: str
    # Peran pengirim pesan (user, assistant, atau system)
    role: str
    # Konten / isi teks pesan
    content: str
    # Metadata tambahan dinamis (seperti citation/sumber buku)
    metadata: Optional[dict[str, Any]] = None
    # Waktu pengiriman pesan
    created_at: datetime

    # Mengizinkan pemetaan otomatis dari atribut objek model ORM database
    model_config = {"from_attributes": True}


# Skema SessionDetailResponse merespon detail sesi lengkap beserta riwayat seluruh pesannya
class SessionDetailResponse(BaseModel):
    # Informasi ringkas sesi obrolan
    session: SessionSummary
    # Daftar urutan riwayat balon obrolan dalam sesi tersebut
    messages: list[MessageOut]


# ─── Skema Pengiriman Pesan (Send Message) ──────────────────────────────────────

# Skema SendMessageRequest memvalidasi request body saat user mengirim pesan baru ke AI
class SendMessageRequest(BaseModel):
    # Isi teks pertanyaan wajib diisi, panjang minimal 1 dan maksimal 4000 karakter
    content: str = Field(min_length=1, max_length=4000)
    # Filter ID buku opsional untuk mengarahkan pencarian data RAG secara spesifik
    book_filter: Optional[str] = Field(None, description="Optional book_id to filter RAG sources")


# Skema SendMessageResponse mengembalikan pesan user yang terkirim dan jawaban AI
class SendMessageResponse(BaseModel):
    # Salinan balon pesan yang dikirim oleh user (sudah tersimpan di DB)
    user_message: MessageOut
    # Balon pesan jawaban yang di-generate oleh AI (sudah tersimpan di DB)
    ai_message: MessageOut
