"""
Layanan Chat (Chat Service): mengelola sesi obrolan (CRUD) dan alur pengiriman pesan ke mesin inferensi RAG.
"""
# Mengimpor modul uuid untuk konversi ID unik UUID
import uuid
# Mengimpor Optional untuk type hinting nilai yang boleh kosong
from typing import Optional

# Mengimpor kelas HTTPException dan status HTTP dari FastAPI
from fastapi import HTTPException, status
# Mengimpor func dan select dari SQLAlchemy untuk query database
from sqlalchemy import func, select
# Mengimpor AsyncSession untuk penanganan transaksi database asinkron
from sqlalchemy.ext.asyncio import AsyncSession
# Mengimpor selectinload untuk pemuatan relasi asinkron (eager loading)
from sqlalchemy.orm import selectinload

# Mengimpor skema Settings untuk membaca konfigurasi aplikasi
from app.config import Settings
# Mengimpor model ORM database ChatSession, Message, MessageRole, dan User
from app.models.user import ChatSession, Message, MessageRole, User
# Mengimpor client inferensi RAG asinkron
from app.providers.inference_client import InferenceClient
# Mengimpor seluruh skema DTO chat Pydantic terkait
from app.schemas.chat import (
    MessageOut,
    SendMessageRequest,
    SendMessageResponse,
    SessionDetailResponse,
    SessionListResponse,
    SessionSummary,
)


# Fungsi pembantu untuk mengonversi objek model database ChatSession ke skema SessionSummary
def _session_to_schema(session: ChatSession, message_count: int = 0) -> SessionSummary:
    """Mengubah instance model ChatSession menjadi skema DTO SessionSummary."""
    # Mengembalikan objek SessionSummary hasil pemetaan
    return SessionSummary(
        id=str(session.id),
        title=session.title,
        created_at=session.created_at,
        updated_at=session.updated_at,
        message_count=message_count,
    )


# Fungsi pembantu untuk mengonversi objek model database Message ke skema MessageOut
def _message_to_schema(msg: Message) -> MessageOut:
    """Mengubah instance model Message menjadi skema DTO MessageOut."""
    # Mengembalikan objek MessageOut hasil pemetaan
    return MessageOut(
        id=str(msg.id),
        role=msg.role.value,
        content=msg.content,
        metadata=msg.meta,
        created_at=msg.created_at,
    )


# Kelas ChatService mengelola logika bisnis sesi obrolan AI
class ChatService:
    # Inisialisasi service dengan sesi database dan pengaturan aplikasi
    def __init__(self, db: AsyncSession, settings: Settings):
        self.db = db
        self.settings = settings

    # ─── Operasi CRUD Sesi Obrolan (Session CRUD) ───────────────────────────────

    # Membuat sesi obrolan chat baru untuk pengguna
    async def create_session(self, user: User, title: Optional[str] = None) -> ChatSession:
        """Membuat sesi percakapan chat baru untuk user."""
        # Instansiasi model ChatSession baru
        session = ChatSession(user_id=user.id, title=title)
        # Tambahkan sesi ke antrean transaksi database
        self.db.add(session)
        # Commit perubahan data secara asinkron
        await self.db.commit()
        # Perbarui instance sesi untuk memuat ID dan tanggal ter-generate dari DB
        await self.db.refresh(session)
        # Mengembalikan objek sesi
        return session

    # Menampilkan seluruh daftar sesi obrolan milik user
    async def list_sessions(self, user: User) -> SessionListResponse:
        """Mendapatkan daftar seluruh sesi obrolan milik user beserta jumlah pesannya."""
        # Melakukan query seleksi sesi chat dengan agregasi count kolom pesan
        result = await self.db.execute(
            select(ChatSession, func.count(Message.id).label("message_count"))
            # Gabungkan dengan tabel messages menggunakan outer join agar sesi kosong tetap terhitung
            .outerjoin(Message, Message.session_id == ChatSession.id)
            # Batasi pencarian hanya untuk user yang sedang mengakses
            .where(ChatSession.user_id == user.id)
            # Kelompokkan baris berdasarkan ID sesi
            .group_by(ChatSession.id)
            # Urutkan sesi berdasarkan tanggal pembaruan terbaru di atas
            .order_by(ChatSession.updated_at.desc())
        )
        # Mengambil seluruh baris hasil query
        rows = result.all()
        # Mengonversi seluruh baris database ke dalam list skema DTO SessionSummary
        sessions = [_session_to_schema(row.ChatSession, row.message_count) for row in rows]
        # Mengembalikan respon pembungkus list sesi dan total datanya
        return SessionListResponse(sessions=sessions, total=len(sessions))

    # Mengambil satu objek data sesi dari database serta memvalidasi hak kepemilikannya
    async def get_session(self, session_id: str, user: User) -> ChatSession:
        """Memuat data sesi dan pesan-pesannya, serta memvalidasi kepemilikan user."""
        # Memvalidasi apakah ID sesi yang dikirim berformat UUID yang benar
        try:
            sid = uuid.UUID(session_id)
        # Tangkap error jika format string UUID salah
        except ValueError:
            # Lempar error HTTP 404 Not Found
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

        # Melakukan query untuk memuat sesi chat secara spesifik
        result = await self.db.execute(
            select(ChatSession)
            # Memuat data relasi messages secara asinkron (eager loading)
            .options(selectinload(ChatSession.messages))
            # Mencari ID sesi yang cocok dan memastikan dimiliki oleh user saat ini
            .where(ChatSession.id == sid, ChatSession.user_id == user.id)
        )
        # Mengambil satu hasil data sesi
        session = result.scalar_one_or_none()
        # Jika sesi tidak ditemukan di database
        if not session:
            # Lempar error 404 Not Found
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
        # Mengembalikan objek model database sesi chat
        return session

    # Mendapatkan detail sesi lengkap beserta daftar histori balon pesannya
    async def get_session_detail(self, session_id: str, user: User) -> SessionDetailResponse:
        """Mengambil detail lengkap sesi chat beserta seluruh riwayat pesannya."""
        # Mendapatkan objek sesi chat
        session = await self.get_session(session_id, user)
        # Mengonversi seluruh list pesan database di sesi tersebut menjadi skema MessageOut
        messages = [_message_to_schema(m) for m in session.messages]
        # Mengonversi detail sesi ke skema ringkasan dengan menyertakan jumlah pesan
        summary = _session_to_schema(session, len(messages))
        # Mengembalikan data detail respon lengkap
        return SessionDetailResponse(session=summary, messages=messages)

    # Mengubah judul judul sesi obrolan chat
    async def rename_session(self, session_id: str, user: User, title: str) -> SessionSummary:
        """Mengubah judul sesi obrolan chat."""
        # Mengambil objek sesi chat dan memverifikasi kepemilikannya
        session = await self.get_session(session_id, user)
        # Menetapkan judul baru
        session.title = title
        # Menyimpan perubahan judul ke database
        await self.db.commit()
        # Memperbarui data objek sesi
        await self.db.refresh(session)
        # Mengembalikan ringkasan sesi terbaru
        return _session_to_schema(session)

    # Menghapus sesi obrolan chat beserta pesan di dalamnya
    async def delete_session(self, session_id: str, user: User) -> None:
        """Menghapus sesi obrolan chat beserta riwayat pesan di dalamnya."""
        # Mengambil sesi chat dan memverifikasi kepemilikannya
        session = await self.get_session(session_id, user)
        # Melakukan penghapusan objek sesi di unit transaksi (tabel cascaded akan terhapus otomatis)
        await self.db.delete(session)
        # Commit transaksi penghapusan di database secara permanen
        await self.db.commit()

    # ─── Alur Pengiriman Pesan Ke AI (Send Message Flow) ──────────────────────

    # Mengirim pesan obrolan baru ke AI dan mendapatkan jawabannya
    async def send_message(
        self,
        session_id: str,
        user: User,
        data: SendMessageRequest,
        inference_client: InferenceClient,
    ) -> SendMessageResponse:
        """
        Alur pengiriman pesan lengkap:
        1. Menyimpan balon pesan user baru ke database.
        2. Menyusun teks konteks dari histori obrolan sesi (sampai batas CHAT_CONTEXT_WINDOW).
        3. Memanggil API inferensi RAG.
        4. Menyimpan balon pesan respon AI ke database.
        5. Mengembalikan sepasang respon pesan.
        """
        # Mengambil objek sesi chat dan memverifikasi kepemilikannya
        session = await self.get_session(session_id, user)

        # 1. Menyimpan balon pesan user baru ke database
        user_msg = Message(
            session_id=session.id,
            role=MessageRole.user,
            content=data.content,
            # Menyimpan info filter buku di metadata jika filter diisi
            meta={"book_filter": data.book_filter} if data.book_filter else None,
        )
        # Tambahkan pesan user ke transaksi database
        self.db.add(user_msg)
        # Flush transaksi agar pesan user mendapatkan ID unik pesan sebelum LLM dipanggil
        await self.db.flush()

        # 2. Menyusun teks konteks: memuat histori obrolan N pesan terakhir (context window)
        window = self.settings.chat_context_window
        # Query mengambil histori pesan di database (kecuali pesan user yang baru saja ditambahkan)
        history_result = await self.db.execute(
            select(Message)
            # Batasi pencarian pada sesi ini saja
            .where(Message.session_id == session.id, Message.id != user_msg.id)
            # Urutkan berdasarkan pesan terbaru di atas
            .order_by(Message.created_at.desc())
            # Batasi jumlah baris histori berdasarkan konfigurasi window
            .limit(window if window > 0 else None)
        )
        # Balikkan urutan list agar urutan percakapan kembali kronologis (pesan lama ke pesan baru)
        recent_messages = list(reversed(history_result.scalars().all()))

        # Menggabungkan baris-baris histori pesan ke dalam bentuk string
        context_lines = [
            f"{m.role.value.upper()}: {m.content}" for m in recent_messages
        ]
        # Jika terdapat histori pesan sebelumnya, susun dengan format dialog terpisah
        if context_lines:
            full_query = "\n".join(context_lines) + f"\nUSER: {data.content}"
        # Jika obrolan pertama kali, langsung kirimkan teks pertanyaan user
        else:
            full_query = data.content

        # 3. Memanggil API inferensi RAG asinkron
        try:
            inference_response = await inference_client.chat(
                query=full_query,
                book_filter=data.book_filter,
            )
        # Menangkap error jaringan atau kegagalan dari API inferensi RAG
        except Exception as exc:
            # Lempar error HTTP 502 Bad Gateway
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Inference service error: {exc}",
            )

        # 4. Menyimpan balon pesan respon AI beserta metadata pendukungnya
        ai_msg = Message(
            session_id=session.id,
            role=MessageRole.assistant,
            content=inference_response.get("answer", ""),
            # Menyimpan metadata sumber referensi dan status jawaban dari mesin RAG
            meta={
                "provider_used": inference_response.get("provider_used"),
                "sources": inference_response.get("sources"),
                "citations": inference_response.get("citations"),
                "answer_status": inference_response.get("answer_status"),
            },
        )
        # Menambahkan pesan AI ke transaksi database
        self.db.add(ai_msg)

        # Mengatur judul sesi chat otomatis dari 80 karakter pertama pesan pertama jika belum ada judul
        if not session.title:
            session.title = data.content[:80]

        # Commit seluruh perubahan data pesan dan judul ke database secara permanen
        await self.db.commit()
        # Perbarui objek pesan user agar memuat tanggal generated database
        await self.db.refresh(user_msg)
        # Perbarui objek pesan AI agar memuat tanggal generated database
        await self.db.refresh(ai_msg)

        # Mengembalikan sepasang DTO respon pesan (pesan user + jawaban AI)
        return SendMessageResponse(
            user_message=_message_to_schema(user_msg),
            ai_message=_message_to_schema(ai_msg),
        )
