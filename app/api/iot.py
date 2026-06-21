"""
IoT routes (API Key auth via X-API-Key header):
  POST /iot/sessions              — Create IoT session
  POST /iot/sessions/{id}/voice   — Process voice: STT → inference → TTS → return audio
  GET  /iot/sessions/{id}         — Get IoT session + messages
"""
# Mengimpor modul uuid untuk pembuatan dan pemrosesan tipe UUID
import uuid

# Mengimpor modul dari fastapi untuk mendefinisikan router, penanganan file, upload, status HTTP, dan exception
from fastapi import APIRouter, File, HTTPException, Request, UploadFile, status
# Mengimpor kelas select dari SQLAlchemy untuk melakukan kueri SELECT ke database
from sqlalchemy import select
# Mengimpor selectinload untuk memuat relasi (eager load) secara efisien pada kueri database
from sqlalchemy.orm import selectinload

# Mengimpor dependensi DB (database), AppSettings (konfigurasi), dan IoTAuth (otentikasi token IoT)
from app.core.dependencies import DB, AppSettings, IoTAuth
# Mengimpor model IoTSession untuk interaksi data dengan database
from app.models.iot import IoTSession
# Mengimpor skema data terstruktur untuk input dan output data IoT
from app.schemas.iot import (
    IoTMessageOut,
    IoTSessionCreateRequest,
    IoTSessionDetailResponse,
    IoTSessionResponse,
    IoTVoiceResponse,
)
# Mengimpor IoTService untuk memproses logika bisnis khusus IoT
from app.services.iot_service import IoTService

# Membuat objek APIRouter baru khusus untuk IoT
router = APIRouter()


# Menentukan rute POST '/sessions' untuk membuat sesi percakapan IoT baru
@router.post(
    "/sessions",
    # Model skema JSON respons pembuatan sesi IoT yang sukses
    response_model=IoTSessionResponse,
    # Menetapkan status HTTP respons ke 201 Created
    status_code=status.HTTP_201_CREATED,
    # Ringkasan dokumentasi
    summary="Create a new IoT device session",
)
# Fungsi asinkron untuk menangani pembuatan sesi IoT baru
async def create_iot_session(
    # Body request berupa device_id perangkat IoT
    body: IoTSessionCreateRequest,
    # Sesi database aktif
    db: DB,
    # Konfigurasi aplikasi
    settings: AppSettings,
    # Ketergantungan otentikasi X-API-Key untuk memverifikasi request perangkat IoT
    _: IoTAuth,
):
    """
    Membuat sesi percakapan IoT baru untuk sebuah perangkat hardware.
    Diotentikasi menggunakan header X-API-Key.
    """
    # Membuat instance IoTService
    service = IoTService(db, settings)
    # Memanggil fungsi create_session untuk mendaftarkan sesi IoT baru berdasarkan device_id ke database
    session = await service.create_session(body.device_id)
    # Mengembalikan skema respons berisi ID sesi, ID perangkat, dan waktu sesi dimulai
    return IoTSessionResponse(
        # Mengonversi UUID sesi menjadi string
        session_id=str(session.id),
        # ID perangkat IoT
        device_id=session.device_id,
        # Waktu dimulainya sesi
        started_at=session.started_at,
    )


# Menentukan rute POST '/sessions/{session_id}/voice' untuk memproses input suara, RAG, dan mengembalikan file audio respons
@router.post(
    "/sessions/{session_id}/voice",
    # Model skema JSON respons suara
    response_model=IoTVoiceResponse,
    # Ringkasan dokumentasi
    summary="Process voice: upload audio → get text + audio response",
)
# Fungsi asinkron untuk memproses alur input-output suara perangkat IoT
async def voice_interact(
    # ID sesi IoT yang bersangkutan
    session_id: str,
    # Objek HTTP request untuk mengambil client inference
    request: Request,
    # Mengambil file audio biner yang diunggah dengan batasan wajib diisi
    audio: UploadFile = File(..., description="Audio file (WAV/MP3/OGG)"),
    # Ketergantungan sesi database (diinisialisasi default None agar kompatibel dengan UploadFile)
    db: DB = None,
    # Ketergantungan konfigurasi aplikasi (diinisialisasi default None)
    settings: AppSettings = None,
    # Ketergantungan otentikasi API Key IoT
    _: IoTAuth = None,
):
    """
    Alur lengkap interaksi suara:
    1. Transkripsi suara via Groq Whisper STT: file audio → teks pertanyaan.
    2. Menyimpan teks pertanyaan pengguna ke tabel iot_messages database.
    3. Memanggil mesin inferensi (RAG) untuk mendapatkan teks jawaban.
    4. Menyimpan teks jawaban AI ke tabel iot_messages database.
    5. Sintesis suara via Edge-TTS: teks jawaban → berkas audio tanggapan.
    6. Mengembalikan teks jawaban serta URL berkas audio ke perangkat IoT.
    """
    # Mengimpor modul dependensi secara lokal untuk menghindari kesalahan inisialisasi UploadFile
    from app.core.dependencies import get_db, get_settings, verify_iot_api_key
    # Jika dependensi database gagal teratasi (bernilai None)
    if db is None:
        # Lempar HTTP exception 500 Internal Server Error
        raise HTTPException(status_code=500, detail="DB dependency not resolved")

    # Mengambil objek klien inferensi terbagi dari app.state
    inference_client = request.app.state.inference_client
    # Membuat instans IoTService dengan menyertakan database, konfigurasi, dan klien inferensi
    service = IoTService(db, settings, inference_client)

    # Membaca data biner file audio yang diunggah dari buffer secara asinkron
    audio_bytes = await audio.read()
    # Memanggil metode process_voice pada IoTService untuk mengeksekusi pipeline suara secara lengkap
    return await service.process_voice(
        # ID sesi IoT tujuan
        session_id=session_id,
        # Data biner suara
        audio_bytes=audio_bytes,
        # Nama file audio asal (default: 'audio.wav' jika kosong)
        audio_filename=audio.filename or "audio.wav",
    )


# Menentukan rute GET '/sessions/{session_id}' untuk mengambil riwayat percakapan sesi IoT tertentu
@router.get(
    "/sessions/{session_id}",
    # Model skema JSON respons detail sesi IoT
    response_model=IoTSessionDetailResponse,
    # Ringkasan dokumentasi
    summary="Get IoT session + all messages",
)
# Fungsi asinkron untuk menampilkan data sesi IoT dan dafar pesannya
async def get_iot_session(
    # ID sesi IoT yang ingin diambil datanya
    session_id: str,
    # Sesi database
    db: DB,
    # Konfigurasi aplikasi
    settings: AppSettings,
    # Ketergantungan verifikasi API Key IoT
    _: IoTAuth,
):
    """Mengembalikan detail sesi IoT beserta semua pesan di dalamnya (untuk replay/logging pada perangkat)."""
    try:
        # Mencoba memvalidasi format string session_id menjadi objek tipe UUID
        sid = uuid.UUID(session_id)
    # Jika format UUID salah
    except ValueError:
        # Melemparkan HTTP Exception 404 Not Found
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    # Melakukan kueri pencarian IoTSession dari database dengan memuat seluruh pesan asinkron secara langsung (eager loading)
    result = await db.execute(
        select(IoTSession)
        .options(selectinload(IoTSession.messages))
        .where(IoTSession.id == sid)
    )
    # Mendapatkan satu objek sesi IoT atau None jika tidak ditemukan
    session = result.scalar_one_or_none()
    # Jika sesi tidak terdaftar
    if not session:
        # Melemparkan HTTP Exception 404 Not Found
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    # Memetakan seluruh pesan percakapan sesi IoT tersebut ke skema keluaran IoTMessageOut
    messages = [
        IoTMessageOut(
            id=str(m.id),
            role=m.role.value,
            content=m.content,
            audio_path=m.audio_path,
            metadata=m.meta,
            created_at=m.created_at,
        )
        # Iterasi setiap pesan di dalam sesi IoT
        for m in session.messages
    ]

    # Mengembalikan objek respons detail sesi IoT beserta pesan di dalamnya
    return IoTSessionDetailResponse(
        session_id=str(session.id),
        device_id=session.device_id,
        started_at=session.started_at,
        ended_at=session.ended_at,
        messages=messages,
    )


# Mengimpor modul WebSocket dan WebSocketDisconnect untuk mendukung komunikasi dua arah real-time
from fastapi import WebSocket, WebSocketDisconnect
# Mengimpor httpx untuk melakukan request HTTP asinkron ke server inferensi RAG
import httpx
# Mengimpor klien asinkron AsyncGroq untuk memanggil model LLM Groq secara asinkron
from groq import AsyncGroq
# Mengimpor AudioManager untuk memproses transkripsi (STT) dan sintesis suara (TTS)
from app.services.audio_manager import AudioManager
# Mengimpor model IoTMessage dan IoTMessageRole untuk pencatatan riwayat pesan
from app.models.iot import IoTMessage, IoTMessageRole

# Mendefinisikan rute WebSocket '/sessions/{session_id}/stream' untuk streaming audio real-time dua arah (PCM mentah)
@router.websocket("/sessions/{session_id}/stream")
# Fungsi asinkron untuk menangani koneksi WebSocket streaming audio perangkat IoT
async def iot_stream(
    # Objek WebSocket yang terhubung
    websocket: WebSocket,
    # ID sesi IoT yang aktif
    session_id: str,
    # Sesi database
    db: DB,
    # Konfigurasi aplikasi
    settings: AppSettings,
    # API Key rahasia yang dikirimkan lewat query string (opsional)
    api_key: str = None,
):
    """
    Rute WebSocket untuk streaming audio real-time (Raw PCM).
    Menerapkan logika fallback Fast Route (FAQ lokal) vs Slow Route (RAG penuh).
    """
    # Memeriksa apakah API Key tidak diisi atau tidak cocok dengan kunci rahasia di konfigurasi
    if not api_key or api_key != settings.iot_api_key:
        # Menutup koneksi WebSocket dengan kode status pelanggaran kebijakan keamanan
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        # Segera menghentikan fungsi
        return

    # Menerima koneksi WebSocket dari klien IoT
    await websocket.accept()
    
    # Mencoba membaca konten file FAQ lokal untuk jalur cepat (Fast Route)
    try:
        import os
        # Membuka berkas faq.txt dengan format karakter utf-8
        with open("faq.txt", "r", encoding="utf-8") as f:
            # Membaca seluruh teks FAQ
            faq_text = f.read()
    # Jika berkas faq.txt tidak ditemukan atau gagal dibaca, set teks FAQ ke kosong
    except Exception:
        faq_text = ""

    try:
        # Mengonversi session_id dari string ke objek UUID
        sid = uuid.UUID(session_id)
        # Loop tanpa batas untuk terus menerima data audio dari klien selama koneksi terbuka
        while True:
            # Menerima data biner (PCM mentah) yang dikirim oleh perangkat IoT
            audio_bytes = await websocket.receive_bytes()
            
            # Melakukan transkripsi suara (Speech-to-Text) dari biner PCM mentah menggunakan AudioManager
            transcription = await AudioManager.transcribe(audio_bytes)
            # Jika hasil transkripsi kosong (tidak ada suara terdeteksi), lewati bagian loop ini
            if not transcription.strip():
                continue

            # Jalur Cepat (Fast Route): Menggunakan model ringan LLM Groq untuk memeriksa pertanyaan berdasarkan FAQ lokal
            client = AsyncGroq(api_key=settings.groq_api_key)
            # Menyusun prompt instruksi agar model hanya menjawab dari FAQ, atau membalas 'Saya tidak tahu' jika tidak ada
            prompt = (
                f"Konteks FAQ: {faq_text}\n\nPertanyaan: {transcription}\n"
                "Jawab berdasarkan FAQ. Jika konteks tidak cukup, jawab persis: 'Saya tidak tahu'."
            )
            
            # Meminta penyelesaian chat ke API Groq menggunakan model Llama-3-8B secara asinkron
            completion = await client.chat.completions.create(
                model="llama3-8b-8192",
                messages=[{"role": "user", "content": prompt}],
                # Mengatur temperatur ke 0 agar respons model sangat konsisten dan tidak berimajinasi
                temperature=0.0
            )
            # Mengambil konten teks respons jawaban dan membuang spasi kosong di ujung string
            answer = completion.choices[0].message.content.strip()
            
            # Menentukan penanda rute awal yang dilewati adalah Fast Route FAQ
            route_taken = "fast_faq"
            # Logika Fallback ke Jalur Lambat (Slow Route): Jika jawaban mengandung kalimat penolakan 'tidak tahu'
            if "tidak tahu" in answer.lower():
                # Mengubah penanda rute yang dilewati ke Slow Route RAG
                route_taken = "slow_rag"
                try:
                    # Menyiapkan header otentikasi request
                    headers = {}
                    # Jika token Hugging Face dikonfigurasi
                    if settings.hf_token:
                        # Menambahkan header Authorization Bearer token
                        headers["Authorization"] = f"Bearer {settings.hf_token}"
                        
                    # Membuat HTTP client asinkron untuk memanggil mesin inferensi RAG internal
                    async with httpx.AsyncClient(headers=headers) as http_client:
                        # Mengirimkan request POST berisi query transkripsi ke endpoint inferensi RAG
                        res = await http_client.post(
                            f"{settings.inference_base_url}/api/v1/chat",
                            json={"query": transcription}
                        )
                        # Jika respons sukses (HTTP 200 OK)
                        if res.status_code == 200:
                            # Membaca data respons JSON
                            data = res.json()
                            # Mengambil string jawaban (default teks galat jika kosong)
                            answer = data.get("answer", "Maaf, sistem AI sedang sibuk.")
                        # Jika respons gagal
                        else:
                            answer = "Maaf, terjadi kesalahan pada AI engine."
                # Jika koneksi ke server inferensi RAG gagal total
                except Exception:
                    answer = "Maaf, mesin inferensi sedang tidak dapat dihubungi."

            # Melakukan sintesis suara (Text-to-Speech) dari teks jawaban akhir menggunakan AudioManager
            audio_response = await AudioManager.synthesize(answer)
            
            # Membuat rekam pesan kiriman user untuk disimpan di database
            user_msg = IoTMessage(
                iot_session_id=sid,
                role=IoTMessageRole.user,
                content=transcription,
                meta={"route": route_taken}
            )
            # Membuat rekam pesan jawaban asisten AI untuk disimpan di database
            assistant_msg = IoTMessage(
                iot_session_id=sid,
                role=IoTMessageRole.assistant,
                content=answer,
                meta={"route": route_taken}
            )
            # Memasukkan kedua rekam pesan tersebut ke dalam antrean database
            db.add_all([user_msg, assistant_msg])
            # Melakukan komit database untuk menyimpan pesan percakapan secara permanen
            await db.commit()
            
            # Mengirimkan kembali berkas audio respons suara (biner) langsung ke klien IoT secara real-time
            await websocket.send_bytes(audio_response)
            
    # Menangkap event jika koneksi WebSocket terputus oleh klien, biarkan selesai dengan aman tanpa error
    except WebSocketDisconnect:
        pass
    # Menangkap error umum lainnya selama proses streaming WebSocket
    except Exception as e:
        # Mencetak pesan error ke terminal untuk kebutuhan debugging
        print(f"WebSocket Error: {e}")
        try:
            # Mencoba menutup koneksi WebSocket agar resource terbebaskan
            await websocket.close()
        except:
            # Abaikan jika penutupan gagal atau sudah tertutup sebelumnya
            pass
