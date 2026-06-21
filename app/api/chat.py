"""
Chat routes:
  POST   /chat/sessions               — Create new session
  GET    /chat/sessions               — List all sessions
  GET    /chat/sessions/{id}          — Get session + messages
  DELETE /chat/sessions/{id}          — Delete session
  PATCH  /chat/sessions/{id}          — Rename session
  POST   /chat/sessions/{id}/messages — Send message + get AI response
"""
# Mengimpor APIRouter untuk mendefinisikan rute chat, Request untuk membaca info app state, dan status untuk kode HTTP
from fastapi import APIRouter, Request, status

# Mengimpor dependensi DB (koneksi database), AppSettings (konfigurasi aplikasi), dan CurrentUser (user yang sedang login)
from app.core.dependencies import DB, AppSettings, CurrentUser
# Mengimpor InferenceClient untuk berkomunikasi dengan server inferensi (RAG)
from app.providers.inference_client import InferenceClient
# Mengimpor skema data untuk request dan response terkait sesi dan pesan chat
from app.schemas.chat import (
    SendMessageRequest,
    SendMessageResponse,
    SessionCreateRequest,
    SessionDetailResponse,
    SessionListResponse,
    SessionRenameRequest,
    SessionSummary,
)
# Mengimpor ChatService yang membungkus seluruh logika bisnis percakapan chat
from app.services.chat_service import ChatService

# Membuat objek APIRouter baru khusus untuk chat
router = APIRouter()


# Menentukan rute POST '/sessions' untuk membuat sesi chat baru
@router.post(
    "/sessions",
    # Skema kembalian berupa ringkasan sesi
    response_model=SessionSummary,
    # Menetapkan status HTTP ke 201 Created jika berhasil
    status_code=status.HTTP_201_CREATED,
    # Ringkasan dokumentasi
    summary="Create a new chat session",
)
# Fungsi asinkron untuk memproses pembuatan sesi chat baru
async def create_session(
    # Body request berupa judul sesi chat yang diinput user
    body: SessionCreateRequest,
    # Mengambil objek user aktif saat ini
    current_user: CurrentUser,
    # Sesi database aktif
    db: DB,
    # Konfigurasi aplikasi
    settings: AppSettings,
):
    # Membuat instance ChatService
    service = ChatService(db, settings)
    # Memanggil metode create_session untuk membuat baris sesi baru di database
    session = await service.create_session(current_user, title=body.title)
    # Mengembalikan skema SessionSummary dengan jumlah pesan awal bernilai 0
    return SessionSummary(
        # Mengonversi UUID sesi chat menjadi string
        id=str(session.id),
        # Judul sesi chat
        title=session.title,
        # Waktu pembuatan sesi
        created_at=session.created_at,
        # Waktu terakhir perubahan sesi
        updated_at=session.updated_at,
        # Sesi baru selalu dimulai dengan 0 pesan
        message_count=0,
    )


# Menentukan rute GET '/sessions' untuk menampilkan daftar semua sesi chat milik user yang sedang login
@router.get(
    "/sessions",
    # Skema respons berupa daftar sesi chat
    response_model=SessionListResponse,
    # Ringkasan dokumentasi
    summary="List all chat sessions for current user",
)
# Fungsi asinkron untuk memproses pemanggilan daftar sesi chat
async def list_sessions(
    # Memeriksa data user aktif yang sedang login
    current_user: CurrentUser,
    # Sesi database
    db: DB,
    # Konfigurasi aplikasi
    settings: AppSettings,
):
    # Membuat instance ChatService
    service = ChatService(db, settings)
    # Memanggil metode list_sessions untuk mendapatkan semua sesi chat milik pengguna
    return await service.list_sessions(current_user)


# Menentukan rute GET '/sessions/{session_id}' untuk mengambil detail suatu sesi beserta semua pesannya
@router.get(
    "/sessions/{session_id}",
    # Skema respons berupa detail sesi lengkap dengan pesan-pesannya
    response_model=SessionDetailResponse,
    # Ringkasan dokumentasi
    summary="Get session details + all messages",
)
# Fungsi asinkron untuk memproses pemanggilan detail sesi percakapan
async def get_session(
    # ID sesi chat target dari URL
    session_id: str,
    # User aktif saat ini
    current_user: CurrentUser,
    # Sesi database
    db: DB,
    # Konfigurasi aplikasi
    settings: AppSettings,
):
    # Membuat instance ChatService
    service = ChatService(db, settings)
    # Memanggil fungsi get_session_detail untuk mengambil info sesi dan histori pesannya
    return await service.get_session_detail(session_id, current_user)


# Menentukan rute DELETE '/sessions/{session_id}' untuk menghapus sesi chat tertentu beserta semua pesan di dalamnya
@router.delete(
    "/sessions/{session_id}",
    # Menetapkan status HTTP respons ke 204 No Content
    status_code=status.HTTP_204_NO_CONTENT,
    # Ringkasan dokumentasi
    summary="Delete a chat session and all its messages",
)
# Fungsi asinkron untuk menghapus sesi chat
async def delete_session(
    # ID sesi chat target dari URL
    session_id: str,
    # User aktif saat ini
    current_user: CurrentUser,
    # Sesi database
    db: DB,
    # Konfigurasi aplikasi
    settings: AppSettings,
):
    # Membuat instance ChatService
    service = ChatService(db, settings)
    # Memanggil fungsi delete_session untuk menghapus baris data sesi dari database
    await service.delete_session(session_id, current_user)


# Menentukan rute PATCH '/sessions/{session_id}' untuk mengubah nama/judul sesi chat
@router.patch(
    "/sessions/{session_id}",
    # Skema respons berupa ringkasan sesi yang telah diubah
    response_model=SessionSummary,
    # Ringkasan dokumentasi
    summary="Rename a chat session",
)
# Fungsi asinkron untuk mengganti judul sesi chat
async def rename_session(
    # ID sesi chat target dari URL
    session_id: str,
    # Body request berisi judul baru yang diinginkan
    body: SessionRenameRequest,
    # User aktif saat ini
    current_user: CurrentUser,
    # Sesi database
    db: DB,
    # Konfigurasi aplikasi
    settings: AppSettings,
):
    # Membuat instance ChatService
    service = ChatService(db, settings)
    # Memanggil fungsi rename_session untuk memperbarui kolom title sesi di database
    return await service.rename_session(session_id, current_user, body.title)


# Menentukan rute POST '/sessions/{session_id}/messages' untuk mengirim pesan user dan mendapatkan balasan AI
@router.post(
    "/sessions/{session_id}/messages",
    # Skema respons yang berisi pesan user yang dikirim dan balasan dari AI
    response_model=SendMessageResponse,
    # Ringkasan dokumentasi
    summary="Send a message and receive AI response",
)
# Fungsi asinkron untuk memproses alur pengiriman pesan dan inferensi RAG
async def send_message(
    # ID sesi chat target
    session_id: str,
    # Body request berisi konten pesan user yang dikirim
    body: SendMessageRequest,
    # Objek request untuk mengambil instans klien inferensi terbagi dari app.state
    request: Request,
    # User aktif saat ini
    current_user: CurrentUser,
    # Sesi database
    db: DB,
    # Konfigurasi aplikasi
    settings: AppSettings,
):
    """
    Alur lengkap pipeline chat:
    1. Menyimpan pesan kiriman pengguna (user) ke database.
    2. Memuat histori percakapan terakhir (berdasarkan ukuran context window) untuk diumpankan sebagai konteks.
    3. Mengirimkan pesan dan histori ke mesin inferensi (RAG) eksternal.
    4. Menyimpan respons dari AI (assistant) beserta metadatanya (referensi sumber dokumen) ke database.
    5. Mengembalikan kedua objek pesan (pesan user dan pesan AI) ke klien.
    """
    # Mengambil instance klien inferensi bersama yang sudah disimpan di FastAPI app state saat startup
    inference_client: InferenceClient = request.app.state.inference_client
    # Membuat instance ChatService
    service = ChatService(db, settings)
    # Menjalankan fungsi send_message pada service untuk mengeksekusi pipeline chat lengkap
    return await service.send_message(session_id, current_user, body, inference_client)
