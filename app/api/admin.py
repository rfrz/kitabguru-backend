"""
Admin routes (Admin role required):
  GET    /admin/users              — List all users (paginated, searchable)
  GET    /admin/users/{id}         — Detail user + stats
  PATCH  /admin/users/{id}         — Update user role/status
  DELETE /admin/users/{id}         — Force-delete user
  GET    /admin/sessions           — List all chat sessions
  GET    /admin/sessions/{id}      — View session + messages
  DELETE /admin/sessions/{id}      — Delete session
  GET    /admin/iot/sessions       — List IoT sessions
  GET    /admin/iot/sessions/{id}  — View IoT session + messages
  DELETE /admin/iot/sessions/{id}  — Delete IoT session
"""
# Mengimpor modul uuid untuk validasi dan konversi tipe UUID
import uuid
# Mengimpor Optional untuk menandai nilai parameter yang opsional (boleh None)
from typing import Optional

# Mengimpor modul FastAPI untuk pembuatan router, penanganan HTTP status, parameter query, dan exception
from fastapi import APIRouter, HTTPException, Query, status, Request, UploadFile, File, Form, Body
# Mengimpor modul SQLAlchemy untuk fungsi agregasi (count), operator OR, dan query builder SELECT
from sqlalchemy import func, or_, select
# Mengimpor selectinload untuk memuat relasi data secara efisien (mengurangi query N+1)
from sqlalchemy.orm import selectinload

# Mengimpor dependensi DB (database session) dan AdminUser (verifikasi token & peran admin)
from app.core.dependencies import DB, AdminUser
# Mengimpor helper hash_password untuk mengenkripsi kata sandi pengguna baru
from app.core.security import hash_password
# Mengimpor model IoTSession dan IoTMessage untuk data IoT
from app.models.iot import IoTSession, IoTMessage
# Mengimpor model ChatSession, Message, User, dan UserRole untuk data pengguna dan chat
from app.models.user import ChatSession, Message, User, UserRole
# Mengimpor schema chat untuk format output data pesan dan sesi chat
from app.schemas.chat import MessageOut, SessionDetailResponse, SessionSummary
# Mengimpor schema iot untuk format output sesi dan pesan perangkat IoT
from app.schemas.iot import IoTMessageOut, IoTSessionDetailResponse, IoTSessionListResponse, IoTSessionSummary
# Mengimpor schema user untuk request pembuatan, update, detail, dan list pengguna di admin
from app.schemas.user import UserAdminCreateRequest, UserAdminUpdateRequest, UserDetailAdmin, UserListResponse

# Membuat objek APIRouter baru untuk rute-rute admin
router = APIRouter()


# ─── User Management (Manajemen Pengguna) ───────────────────────────────────

# Menentukan rute GET '/users' untuk mengambil daftar semua pengguna
@router.get(
    "/users",
    # Model skema JSON keluaran rute ini
    response_model=UserListResponse,
    # Penjelasan singkat rute untuk dokumentasi OpenAPI/Swagger
    summary="List all users (admin)",
)
# Fungsi asinkron untuk menampilkan daftar pengguna dengan paging dan pencarian
async def list_users(
    # Memvalidasi token dan role pengguna haruslah admin
    admin: AdminUser,
    # Mendapatkan sesi database aktif
    db: DB,
    # Mengambil parameter nomor halaman, default 1, minimal bernilai 1
    page: int = Query(1, ge=1),
    # Mengambil parameter batas data per halaman, default 20, minimal 1, maksimal 100
    limit: int = Query(20, ge=1, le=100),
    # Parameter pencarian opsional untuk mencocokkan email atau username
    search: Optional[str] = Query(None, description="Search by email or username"),
):
    """Mendapatkan daftar semua user dalam sistem dengan sistem halaman (paginated) termasuk user yang dihapus sementara."""
    # Menghitung offset (data awal yang dilewati) untuk query database SQL
    offset = (page - 1) * limit

    # Menyiapkan kerangka query SQL untuk mengambil model User
    query = select(User)
    # Jika pengguna mengisi input pencarian
    if search:
        # Menyiapkan pola wildcard untuk pencarian teks (seperti: %keyword%)
        pattern = f"%{search}%"
        # Menambahkan klausa WHERE di SQL untuk mencocokkan email atau username secara tidak sensitif huruf besar/kecil (ilike)
        query = query.where(
            or_(User.email.ilike(pattern), User.username.ilike(pattern))
        )

    # Menghitung jumlah total pengguna yang cocok dengan query menggunakan count
    count_result = await db.execute(select(func.count()).select_from(query.subquery()))
    # Mengambil nilai angka total dari hasil query
    total = count_result.scalar_one()

    # Mengeksekusi query untuk mengambil data pengguna dengan urutan pendaftaran terbaru, offset, dan limit paging
    result = await db.execute(
        query.order_by(User.created_at.desc()).offset(offset).limit(limit)
    )
    # Mengubah hasil database mentah menjadi list objek model Python User
    users = result.scalars().all()

    # Membuat daftar ID user dari hasil query untuk mengambil statistik jumlah pesan/sesi mereka
    user_ids = [u.id for u in users]
    # Inisialisasi kamus (dictionary) kosong untuk jumlah sesi per pengguna
    session_counts = {}
    # Inisialisasi kamus kosong untuk jumlah pesan chat per pengguna
    message_counts = {}
    # Jika terdapat user yang ditemukan
    if user_ids:
        # Mengambil jumlah sesi chat per user_id menggunakan fungsi agregasi count
        sc = await db.execute(
            select(ChatSession.user_id, func.count(ChatSession.id))
            .where(ChatSession.user_id.in_(user_ids))
            .group_by(ChatSession.user_id)
        )
        # Mengubah hasil baris database menjadi format kamus {user_id: jumlah_sesi}
        session_counts = {row[0]: row[1] for row in sc.all()}

        # Mengambil jumlah pesan chat per user_id dengan relasi gabungan ke tabel Message
        mc = await db.execute(
            select(ChatSession.user_id, func.count(Message.id))
            .outerjoin(Message, Message.session_id == ChatSession.id)
            .where(ChatSession.user_id.in_(user_ids))
            .group_by(ChatSession.user_id)
        )
        # Mengubah hasil baris database menjadi format kamus {user_id: jumlah_pesan}
        message_counts = {row[0]: row[1] for row in mc.all()}

    # Memetakan daftar objek user dari database ke skema keluaran admin UserDetailAdmin
    user_details = [
        UserDetailAdmin(
            # Konversi objek UUID menjadi string
            id=str(u.id),
            # Alamat email pengguna
            email=u.email,
            # Username pengguna
            username=u.username,
            # Mengambil string peran user ('admin'/'user')
            role=u.role.value,
            # Status keaktifan akun user
            is_active=u.is_active,
            # Waktu pendaftaran akun
            created_at=u.created_at,
            # Waktu terakhir profil diubah
            updated_at=u.updated_at,
            # Waktu ketika akun dihapus sementara (jika ada)
            deleted_at=u.deleted_at,
            # Mengambil jumlah sesi chat dari kamus (default 0 jika tidak ada)
            session_count=session_counts.get(u.id, 0),
            # Mengambil jumlah pesan chat dari kamus (default 0 jika tidak ada)
            message_count=message_counts.get(u.id, 0),
        )
        # Iterasi setiap data pengguna
        for u in users
    ]

    # Mengembalikan skema respons berisi data pengguna terpaginasi beserta info statistik
    return UserListResponse(users=user_details, total=total, page=page, limit=limit)


# Menentukan rute GET '/users/{user_id}' untuk mengambil profil detail user tertentu
@router.get(
    "/users/{user_id}",
    # Model respons schema detail user admin
    response_model=UserDetailAdmin,
    # Ringkasan dokumentasi
    summary="Get user detail + stats (admin)",
)
# Fungsi asinkron untuk mengambil data detail seorang pengguna berdasarkan ID
async def get_user_detail(
    # Parameter ID user dari segmen URL
    user_id: str,
    # Memeriksa otorisasi role admin
    admin: AdminUser,
    # Koneksi sesi database
    db: DB,
):
    # Mengambil objek pengguna dari helper pribadi, lemparkan error 404 jika ID tidak valid/tidak ada
    user = await _get_user_or_404(user_id, db)

    # Menghitung jumlah total sesi chat yang dimiliki oleh user ini
    session_count_result = await db.execute(
        select(func.count(ChatSession.id)).where(ChatSession.user_id == user.id)
    )
    # Mendapatkan nilai angka jumlah sesi
    session_count = session_count_result.scalar_one()

    # Menghitung jumlah total pesan chat yang dikirim oleh user ini di seluruh sesi
    message_count_result = await db.execute(
        select(func.count(Message.id))
        .join(ChatSession, Message.session_id == ChatSession.id)
        .where(ChatSession.user_id == user.id)
    )
    # Mendapatkan nilai angka jumlah pesan
    message_count = message_count_result.scalar_one()

    # Mengembalikan data detail lengkap pengguna beserta total statistiknya
    return UserDetailAdmin(
        id=str(user.id),
        email=user.email,
        username=user.username,
        role=user.role.value,
        is_active=user.is_active,
        created_at=user.created_at,
        updated_at=user.updated_at,
        deleted_at=user.deleted_at,
        session_count=session_count,
        message_count=message_count,
    )


# Menentukan rute PATCH '/users/{user_id}' untuk memperbarui peran atau status aktif pengguna
@router.patch(
    "/users/{user_id}",
    # Model skema JSON respons rute
    response_model=UserDetailAdmin,
    # Ringkasan dokumentasi
    summary="Update user role or active status (admin)",
)
# Fungsi asinkron untuk mengedit data peran/akses user
async def update_user(
    # ID user target dari segmen URL
    user_id: str,
    # Body request berisi field role atau status aktif yang ingin diubah
    body: UserAdminUpdateRequest,
    # Memverifikasi akses admin
    admin: AdminUser,
    # Sesi koneksi database
    db: DB,
):
    # Mengambil objek user dari database, lempar 404 jika tidak ditemukan
    user = await _get_user_or_404(user_id, db)

    # Jika admin mengirimkan nilai pembaruan role (peran)
    if body.role is not None:
        try:
            # Mengubah nilai role menjadi tipe data Enum UserRole yang valid
            user.role = UserRole(body.role)
        # Jika nilai role yang dikirim tidak sesuai dengan isi enum ('user' atau 'admin')
        except ValueError:
            # Lempar HTTP exception 400 Bad Request
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid role: {body.role}. Must be 'user' or 'admin'",
            )

    # Jika admin mengirimkan nilai pembaruan status keaktifan user
    if body.is_active is not None:
        # Mengubah status keaktifan akun user (True/False)
        user.is_active = body.is_active

    # Menyimpan semua perubahan yang terjadi pada model ke database
    await db.commit()
    # Memuat ulang data pengguna dari database agar nilainya tetap tersinkronisasi
    await db.refresh(user)
    # Mengembalikan skema detail user yang terbaru setelah diperbarui
    return UserDetailAdmin(
        id=str(user.id),
        email=user.email,
        username=user.username,
        role=user.role.value,
        is_active=user.is_active,
        created_at=user.created_at,
        updated_at=user.updated_at,
        deleted_at=user.deleted_at,
    )


# Menentukan rute DELETE '/users/{user_id}' untuk menghapus pengguna secara permanen
@router.delete(
    "/users/{user_id}",
    # Mengeset status HTTP respons ke 204 No Content karena tidak mengembalikan teks konten apa pun
    status_code=status.HTTP_204_NO_CONTENT,
    # Ringkasan dokumentasi
    summary="Force-delete user (admin)",
)
# Fungsi asinkron untuk menghapus user secara fisik (hard-delete) langsung
async def delete_user(
    # ID user target yang akan dihapus permanen
    user_id: str,
    # Memverifikasi akses admin yang sedang login
    admin: AdminUser,
    # Koneksi sesi database
    db: DB,
):
    """Menghapus pengguna secara permanen dari database langsung (melewati masa tenggang soft-delete)."""
    # Mengambil objek user dari database, lemparkan error jika tidak terdaftar
    user = await _get_user_or_404(user_id, db)
    # Menolak proses penghapusan jika admin mencoba menghapus akun adminnya sendiri
    if str(user.id) == str(admin.id):
        # Melemparkan HTTP Exception 400 Bad Request
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete your own admin account",
        )
    # Menginstruksikan database session untuk menghapus baris pengguna tersebut secara fisik
    await db.delete(user)
    # Melakukan komit untuk meresmikan penghapusan di database
    await db.commit()


# Menentukan rute POST '/users' untuk membuat pengguna baru secara langsung dari dashboard admin
@router.post(
    "/users",
    # Model skema JSON respons rute
    response_model=UserDetailAdmin,
    # Mengeset status HTTP respons ke 201 Created
    status_code=status.HTTP_201_CREATED,
    # Ringkasan dokumentasi
    summary="Create a new user directly (admin)",
)
# Fungsi asinkron untuk mendaftarkan user baru oleh administrator
async def create_user_admin(
    # Body request berisi data pendaftaran user baru oleh admin
    body: UserAdminCreateRequest,
    # Memverifikasi akses admin
    admin: AdminUser,
    # Koneksi sesi database
    db: DB,
):
    # Memeriksa apakah username yang diajukan sudah terpakai oleh pengguna aktif lainnya
    existing_username = await db.execute(
        select(User).where(User.username == body.username, User.deleted_at.is_(None))
    )
    # Jika ditemukan kecocokan username aktif
    if existing_username.scalar_one_or_none():
        # Melemparkan HTTP Exception 409 Conflict karena username duplikat
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username already in use",
        )

    # Memeriksa apakah alamat email yang diajukan sudah terdaftar oleh pengguna aktif lainnya
    existing_email = await db.execute(
        select(User).where(User.email == body.email, User.deleted_at.is_(None))
    )
    # Jika ditemukan kecocokan email aktif
    if existing_email.scalar_one_or_none():
        # Melemparkan HTTP Exception 409 Conflict karena email duplikat
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already in use",
        )

    try:
        # Memvalidasi nilai peran user yang dikirim apakah sesuai tipe Enum UserRole
        role_enum = UserRole(body.role)
    # Jika nilainya tidak valid
    except ValueError:
        # Melemparkan HTTP Exception 400 Bad Request
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid role: {body.role}. Must be 'user' or 'admin'",
        )

    # Membuat objek model User baru dengan data inputan terenkripsi
    new_user = User(
        # Username baru
        username=body.username,
        # Email baru
        email=body.email,
        # Mengenkripsi password mentah dengan bcrypt sebelum disimpan
        hashed_password=hash_password(body.password),
        # Peran akun user
        role=role_enum,
        # Status akun diset aktif
        is_active=True,
    )
    # Menambahkan objek user baru tersebut ke antrean penyimpanan database session
    db.add(new_user)
    # Menyimpan data user baru ke database
    await db.commit()
    # Memuat ulang data user dari database agar ID otomatis dan timestamp terisi
    await db.refresh(new_user)

    # Mengembalikan skema representasi profil user baru yang berhasil dibuat
    return UserDetailAdmin(
        id=str(new_user.id),
        email=new_user.email,
        username=new_user.username,
        role=new_user.role.value,
        is_active=new_user.is_active,
        created_at=new_user.created_at,
        updated_at=new_user.updated_at,
        deleted_at=new_user.deleted_at,
        session_count=0,
        message_count=0,
    )


# ─── Chat Session Management (Manajemen Sesi Chat) ───────────────────────────

# Menentukan rute GET '/sessions' untuk menampilkan seluruh sesi percakapan chat
@router.get(
    "/sessions",
    # Ringkasan dokumentasi
    summary="List all chat sessions (admin)",
)
# Fungsi asinkron untuk mengambil semua sesi chat dengan sistem paging
async def list_all_sessions(
    # Memverifikasi akses admin
    admin: AdminUser,
    # Sesi koneksi database
    db: DB,
    # Parameter opsional untuk memfilter sesi milik ID user tertentu saja
    user_id: Optional[str] = Query(None, description="Filter by user ID"),
    # Parameter halaman, default halaman ke-1
    page: int = Query(1, ge=1),
    # Batas data per halaman, default 20
    limit: int = Query(20, ge=1, le=100),
):
    """Mendapatkan daftar seluruh sesi chat yang ada di sistem dari semua pengguna."""
    # Menghitung offset data awal yang dilewati dalam paging
    offset = (page - 1) * limit
    # Menyiapkan query dasar untuk mengambil model ChatSession
    query = select(ChatSession)

    # Jika filter user_id disediakan
    if user_id:
        try:
            # Memvalidasi format string menjadi objek tipe UUID
            uid = uuid.UUID(user_id)
            # Menambahkan filter WHERE untuk mencocokkan user_id
            query = query.where(ChatSession.user_id == uid)
        # Jika format UUID salah/tidak valid, abaikan filter tersebut
        except ValueError:
            pass

    # Menghitung jumlah total sesi chat yang cocok dengan kriteria filter
    count_result = await db.execute(select(func.count()).select_from(query.subquery()))
    # Mendapatkan nilai angka jumlah total sesi
    total = count_result.scalar_one()

    # Mengambil list sesi chat terurut dari yang terbaru, menggunakan offset dan limit
    result = await db.execute(
        query.order_by(ChatSession.created_at.desc()).offset(offset).limit(limit)
    )
    # Mengonversi hasil database menjadi list objek model Python ChatSession
    sessions = result.scalars().all()

    # Membuat daftar ID sesi chat untuk mempermudah perhitungan jumlah pesan masing-masing
    session_ids = [s.id for s in sessions]
    # Inisialisasi kamus kosong untuk jumlah pesan
    msg_counts = {}
    # Jika ada sesi yang ditemukan
    if session_ids:
        # Mengambil jumlah pesan (Message) untuk masing-masing session_id
        mc = await db.execute(
            select(Message.session_id, func.count(Message.id))
            .where(Message.session_id.in_(session_ids))
            .group_by(Message.session_id)
        )
        # Mengubah hasil database menjadi kamus dengan bentuk {session_id: jumlah_pesan}
        msg_counts = {row[0]: row[1] for row in mc.all()}

    # Memetakan hasil objek sesi chat ke skema ringkasan sesi SessionSummary
    summaries = [
        SessionSummary(
            id=str(s.id),
            title=s.title,
            created_at=s.created_at,
            updated_at=s.updated_at,
            # Mendapatkan jumlah pesan sesi dari kamus (default 0 jika tidak ada pesan)
            message_count=msg_counts.get(s.id, 0),
        )
        # Iterasi setiap sesi chat
        for s in sessions
    ]
    # Mengembalikan objek dictionary terstruktur berisi list data, total data, dan info halaman saat ini
    return {"sessions": summaries, "total": total, "page": page, "limit": limit}


# Menentukan rute GET '/sessions/{session_id}' untuk melihat pesan dan detail dalam sesi chat tertentu
@router.get(
    "/sessions/{session_id}",
    # Model skema respons yang mengembalikan detail sesi dan daftar pesannya
    response_model=SessionDetailResponse,
    # Ringkasan dokumentasi
    summary="View a specific chat session + messages (admin)",
)
# Fungsi asinkron untuk mengambil data detail satu sesi chat beserta riwayat pesannya
async def get_session_admin(
    # ID sesi chat yang ingin dilihat
    session_id: str,
    # Memverifikasi akses admin
    admin: AdminUser,
    # Sesi database
    db: DB,
):
    # Mengambil objek sesi chat dari database, lemparkan error 404 jika ID salah/tidak terdaftar
    session = await _get_session_or_404(session_id, db)
    # Memetakan daftar pesan aslinya ke skema terstruktur MessageOut untuk output JSON
    messages = [
        MessageOut(
            id=str(m.id),
            role=m.role.value,
            content=m.content,
            metadata=m.meta,
            created_at=m.created_at,
        )
        # Iterasi semua objek pesan di dalam sesi
        for m in session.messages
    ]
    # Membuat objek summary ringkasan sesi chat tersebut
    summary = SessionSummary(
        id=str(session.id),
        title=session.title,
        created_at=session.created_at,
        updated_at=session.updated_at,
        # Jumlah pesan dihitung dari panjang list pesan
        message_count=len(messages),
    )
    # Mengembalikan skema detail respons gabungan dari ringkasan sesi dan daftar pesan
    return SessionDetailResponse(session=summary, messages=messages)


# Menentukan rute DELETE '/sessions/{session_id}' untuk menghapus sesi percakapan chat beserta pesannya
@router.delete(
    "/sessions/{session_id}",
    # Menetapkan status HTTP respons ke 204 No Content
    status_code=status.HTTP_204_NO_CONTENT,
    # Ringkasan dokumentasi
    summary="Delete a chat session (admin)",
)
# Fungsi asinkron untuk menghapus satu sesi chat oleh administrator
async def delete_session_admin(
    # ID sesi chat target yang akan dihapus
    session_id: str,
    # Memverifikasi akses admin
    admin: AdminUser,
    # Sesi database
    db: DB,
):
    # Mengambil objek sesi chat dari database, lempar 404 jika tidak ditemukan
    session = await _get_session_or_404(session_id, db)
    # Menghapus objek sesi chat tersebut (relasi pesan akan otomatis terhapus karena ON DELETE CASCADE)
    await db.delete(session)
    # Melakukan komit untuk menerapkan penghapusan di database
    await db.commit()


# ─── IoT Session Management (Manajemen Sesi Perangkat IoT) ───────────────────

# Menentukan rute GET '/iot/sessions' untuk mengambil semua sesi perangkat IoT
@router.get(
    "/iot/sessions",
    # Model skema JSON respons daftar sesi IoT
    response_model=IoTSessionListResponse,
    # Ringkasan dokumentasi
    summary="List all IoT sessions (admin)",
)
# Fungsi asinkron untuk mencantumkan daftar sesi IoT terpaginasi
async def list_iot_sessions(
    # Memverifikasi akses admin
    admin: AdminUser,
    # Sesi database
    db: DB,
    # Filter opsional berdasarkan ID perangkat keras IoT
    device_id: Optional[str] = Query(None),
    # Halaman keberapa, default 1
    page: int = Query(1, ge=1),
    # Batas data per halaman, default 20
    limit: int = Query(20, ge=1, le=100),
):
    # Menghitung offset data awal yang dilewati dalam paging
    offset = (page - 1) * limit
    # Menyiapkan query dasar untuk mengambil model IoTSession
    query = select(IoTSession)
    # Jika admin memfilter berdasarkan ID perangkat
    if device_id:
        # Menambahkan filter pencocokan device_id di database
        query = query.where(IoTSession.device_id == device_id)

    # Menghitung jumlah total sesi IoT yang cocok dengan filter
    count_result = await db.execute(select(func.count()).select_from(query.subquery()))
    # Mendapatkan nilai angka jumlah total sesi IoT
    total = count_result.scalar_one()

    # Mengambil daftar sesi IoT terurut dari sesi mulai yang paling baru, menggunakan offset dan limit
    result = await db.execute(
        query.order_by(IoTSession.started_at.desc()).offset(offset).limit(limit)
    )
    # Mengubah hasil database menjadi list objek model Python IoTSession
    sessions = result.scalars().all()

    # Membuat daftar ID sesi IoT untuk menghitung jumlah pesan masing-masing sesi
    session_ids = [s.id for s in sessions]
    # Inisialisasi kamus kosong untuk jumlah pesan IoT
    msg_counts = {}
    # Jika ditemukan sesi IoT
    if session_ids:
        # Menghitung jumlah IoTMessage per iot_session_id
        mc = await db.execute(
            select(IoTMessage.iot_session_id, func.count(IoTMessage.id))
            .where(IoTMessage.iot_session_id.in_(session_ids))
            .group_by(IoTMessage.iot_session_id)
        )
        # Mengubah hasil database menjadi bentuk kamus {iot_session_id: jumlah_pesan}
        msg_counts = {row[0]: row[1] for row in mc.all()}

    # Memetakan objek sesi IoT ke skema ringkasan sesi IoT IoTSessionSummary
    summaries = [
        IoTSessionSummary(
            id=str(s.id),
            device_id=s.device_id,
            started_at=s.started_at,
            ended_at=s.ended_at,
            # Mendapatkan jumlah pesan IoT dari kamus (default 0 jika tidak ada)
            message_count=msg_counts.get(s.id, 0),
        )
        # Iterasi setiap sesi IoT
        for s in sessions
    ]
    # Mengembalian respons terstruktur berisi ringkasan list sesi IoT, total data, dan info paging
    return IoTSessionListResponse(sessions=summaries, total=total, page=page, limit=limit)


# Menentukan rute GET '/iot/sessions/{session_id}' untuk melihat pesan suara/teks pada sesi IoT tertentu
@router.get(
    "/iot/sessions/{session_id}",
    # Model skema respons detail sesi IoT
    response_model=IoTSessionDetailResponse,
    # Ringkasan dokumentasi
    summary="View IoT session + messages (admin)",
)
# Fungsi asinkron untuk menampilkan percakapan di dalam satu sesi IoT secara detail
async def get_iot_session_admin(
    # ID sesi IoT yang akan ditampilkan detailnya
    session_id: str,
    # Memverifikasi akses admin
    admin: AdminUser,
    # Sesi database
    db: DB,
):
    # Mengambil objek sesi IoT dari database, lemparkan error 404 jika ID salah/tidak terdaftar
    session = await _get_iot_session_or_404(session_id, db)
    # Memetakan daftar pesan IoT aslinya ke skema terstruktur IoTMessageOut
    messages = [
        IoTMessageOut(
            id=str(m.id),
            role=m.role.value,
            content=m.content,
            audio_path=m.audio_path,
            metadata=m.meta,
            created_at=m.created_at,
        )
        # Iterasi semua pesan di dalam sesi IoT ini
        for m in session.messages
    ]
    # Mengembalikan skema detail respons sesi IoT beserta daftar pesan percakapannya
    return IoTSessionDetailResponse(
        session_id=str(session.id),
        device_id=session.device_id,
        started_at=session.started_at,
        ended_at=session.ended_at,
        messages=messages,
    )


# Menentukan rute DELETE '/iot/sessions/{session_id}' untuk menghapus rekaman sesi IoT
@router.delete(
    "/iot/sessions/{session_id}",
    # Menetapkan status HTTP respons ke 204 No Content
    status_code=status.HTTP_204_NO_CONTENT,
    # Ringkasan dokumentasi
    summary="Delete IoT session (admin)",
)
# Fungsi asinkron untuk menghapus rekaman sesi IoT dari database oleh admin
async def delete_iot_session_admin(
    # ID sesi IoT target yang akan dihapus
    session_id: str,
    # Memverifikasi akses admin
    admin: AdminUser,
    # Sesi database
    db: DB,
):
    # Mengambil objek sesi IoT dari database, lempar 404 jika tidak ditemukan
    session = await _get_iot_session_or_404(session_id, db)
    # Menghapus objek sesi IoT dari database (pesan IoT di dalamnya otomatis ikut terhapus karena ON DELETE CASCADE)
    await db.delete(session)
    # Melakukan komit untuk meresmikan penghapusan di database
    await db.commit()


# ─── Private Helpers (Fungsi Pembantu Pribadi) ────────────────────────────────

# Fungsi pembantu untuk mengambil data user berdasarkan ID atau melemparkan error 404
async def _get_user_or_404(user_id: str, db) -> User:
    try:
        # Mencoba mengubah string user_id menjadi objek UUID yang valid
        uid = uuid.UUID(user_id)
    # Jika gagal (format string salah), segera lemparkan HTTP Exception 404
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    # Membuat kueri SQL untuk memilih pengguna berdasarkan UUID-nya
    result = await db.execute(select(User).where(User.id == uid))
    # Mengambil satu data pengguna atau None jika tidak ditemukan
    user = result.scalar_one_or_none()
    # Jika user tidak ada di database
    if not user:
        # Melemparkan HTTP Exception 404 Not Found
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    # Mengembalikan objek user yang ditemukan
    return user


# Fungsi pembantu untuk mengambil data sesi chat berdasarkan ID atau melemparkan error 404
async def _get_session_or_404(session_id: str, db) -> ChatSession:
    try:
        # Mencoba mengubah string session_id menjadi objek UUID yang valid
        sid = uuid.UUID(session_id)
    # Jika gagal (format string salah), segera lemparkan HTTP Exception 404
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    # Membuat kueri SQL untuk memilih ChatSession dan memuat relasi messages-nya sekalian (eager loading)
    result = await db.execute(
        select(ChatSession)
        .options(selectinload(ChatSession.messages))
        .where(ChatSession.id == sid)
    )
    # Mengambil satu objek sesi chat atau None jika tidak ada
    session = result.scalar_one_or_none()
    # Jika sesi tidak ada di database
    if not session:
        # Melemparkan HTTP Exception 404 Not Found
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    # Mengembalikan objek sesi chat yang ditemukan
    return session


# Fungsi pembantu untuk mengambil data sesi IoT berdasarkan ID atau melemparkan error 404
async def _get_iot_session_or_404(session_id: str, db) -> IoTSession:
    try:
        # Mencoba mengubah string session_id menjadi objek UUID yang valid
        sid = uuid.UUID(session_id)
    # Jika gagal (format string salah), segera lemparkan HTTP Exception 404
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="IoT session not found")
    # Membuat kueri SQL untuk memilih IoTSession dan memuat relasi messages-nya sekalian (eager loading)
    result = await db.execute(
        select(IoTSession)
        .options(selectinload(IoTSession.messages))
        .where(IoTSession.id == sid)
    )
    # Mengambil satu objek sesi IoT atau None jika tidak ada
    session = result.scalar_one_or_none()
    # Jika sesi tidak ada di database
    if not session:
        # Melemparkan HTTP Exception 404 Not Found
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="IoT session not found")
    # Mengembalikan objek sesi IoT yang ditemukan
    return session


# ─── Document Management (Manajemen Dokumen) ───────────────────────────────────

@router.get(
    "/documents",
    summary="List all documents from inference engine",
)
async def list_documents(
    admin: AdminUser,
    request: Request,
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    search: Optional[str] = Query(None, description="Search by title or author"),
):
    client = request.app.state.inference_client
    return await client.get_documents(skip=skip, limit=limit, search=search)


@router.post(
    "/documents/import",
    summary="Import EPUB document to inference engine",
)
async def import_document(
    admin: AdminUser,
    request: Request,
    file: UploadFile = File(...),
    title: Optional[str] = Form(None),
    author: Optional[str] = Form(None),
):
    client = request.app.state.inference_client
    content = await file.read()
    return await client.import_document(file_content=content, filename=file.filename, title=title, author=author)


@router.get(
    "/documents/tasks/{task_id}",
    summary="Check document import task status",
)
async def get_document_task(
    task_id: str,
    admin: AdminUser,
    request: Request,
):
    client = request.app.state.inference_client
    return await client.get_document_task(task_id=task_id)


@router.patch(
    "/documents/{book_id}",
    summary="Update document metadata",
)
async def update_document(
    book_id: str,
    admin: AdminUser,
    request: Request,
    payload: dict = Body(...),
):
    client = request.app.state.inference_client
    title = payload.get("title")
    author = payload.get("author")
    return await client.update_document(book_id=book_id, title=title, author=author)


@router.delete(
    "/documents/{book_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete document",
)
async def delete_document(
    book_id: str,
    admin: AdminUser,
    request: Request,
):
    client = request.app.state.inference_client
    await client.delete_document(book_id=book_id)
