"""Initial schema

Revision ID: 0001
Revises: 
Create Date: 2026-05-26 15:00:00.000000

"""
# Mengimpor tipe Sequence dan Union untuk anotasi tipe data
from typing import Sequence, Union
# Mengimpor modul os untuk berinteraksi dengan sistem operasi (opsional)
import os
# Mengimpor modul uuid untuk menghasilkan ID unik acak (UUID v4)
import uuid
# Mengimpor datetime dan timezone untuk penanganan data waktu dengan zona waktu
from datetime import datetime, timezone

# Mengimpor objek op dari Alembic untuk mendefinisikan operasi DDL (Data Definition Language)
from alembic import op
# Mengimpor SQLAlchemy sebagai alias sa untuk pembentukan tipe kolom dan tabel
import sqlalchemy as sa
# Mengimpor dialek postgresql untuk mendukung tipe data khusus PostgreSQL seperti UUID, ENUM, JSONB
from sqlalchemy.dialects import postgresql

# Mengimpor fungsi pembantu hash_password untuk mengenkripsi password admin bawaan
from app.core.security import hash_password as get_password_hash
# Mengimpor fungsi get_settings untuk membaca konfigurasi aplikasi (seperti email/password admin)
from app.config import get_settings

# Mengambil instance dari konfigurasi aplikasi
settings = get_settings()

# Identifier revisi migrasi yang unik untuk berkas ini
revision: str = '0001'
# Menyebutkan revisi sebelumnya (karena ini pertama, nilainya None)
down_revision: Union[str, None] = None
# Label cabang migrasi (opsional)
branch_labels: Union[str, Sequence[str], None] = None
# Revisi migrasi lain yang harus dijalankan lebih dulu (opsional)
depends_on: Union[str, Sequence[str], None] = None


# Fungsi upgrade dipanggil ketika menjalankan migrasi naik (alembic upgrade head)
def upgrade() -> None:
    # 1. ENUMS (Mendefinisikan tipe data Enum kustom di PostgreSQL)
    # Membuat tipe enum 'userrole' untuk membedakan peran user biasa ('user') dan admin ('admin')
    userrole_enum = postgresql.ENUM('user', 'admin', name='userrole')
    # Membuat tipe enum 'messagerole' untuk peran pengirim pesan chat ('user', 'assistant', 'system')
    messagerole_enum = postgresql.ENUM('user', 'assistant', 'system', name='messagerole')
    # Membuat tipe enum 'mediatype' untuk jenis berkas media yang bisa dibuat ('image', 'video')
    mediatype_enum = postgresql.ENUM('image', 'video', name='mediatype')
    # Membuat tipe enum 'mediastatus' untuk melacak status pemrosesan media ('processing', 'completed', 'failed')
    mediastatus_enum = postgresql.ENUM('processing', 'completed', 'failed', name='mediastatus')
    # Membuat tipe enum 'jobstatus' untuk melacak status antrean tugas pemrosesan ('queued', 'processing', 'completed', 'failed')
    jobstatus_enum = postgresql.ENUM('queued', 'processing', 'completed', 'failed', name='jobstatus')
    # Membuat tipe enum 'iotmessagerole' untuk peran pesan perangkat IoT ('user', 'assistant')
    iotmessagerole_enum = postgresql.ENUM('user', 'assistant', name='iotmessagerole')

    # 2. TABLES (Membuat tabel-tabel di database)
    # Membuat tabel 'users' untuk menyimpan data pengguna aplikasi
    users_table = op.create_table(
        # Menentukan nama tabel
        'users',
        # Kolom 'id' sebagai Primary Key bertipe UUID, dihasilkan otomatis menggunakan uuid.uuid4
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        # Kolom 'email' bertipe String maksimal 255 karakter, tidak boleh kosong (nullable=False)
        sa.Column('email', sa.String(length=255), nullable=False),
        # Kolom 'username' bertipe String maksimal 100 karakter, tidak boleh kosong
        sa.Column('username', sa.String(length=100), nullable=False),
        # Kolom 'hashed_password' untuk menyimpan hash sandi rahasia user, tidak boleh kosong
        sa.Column('hashed_password', sa.String(length=255), nullable=False),
        # Kolom 'role' bertipe enum userrole_enum, defaultnya diset ke 'user' di level server database
        sa.Column('role', userrole_enum, nullable=False, server_default='user'),
        # Kolom boolean 'is_active' untuk menandai status keaktifan user, defaultnya bernilai true
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        # Kolom 'created_at' untuk waktu pembuatan data user, diset otomatis waktu saat ini oleh database
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        # Kolom 'updated_at' untuk waktu terakhir perubahan data user, diset otomatis waktu saat ini
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        # Kolom 'deleted_at' bertipe DateTime dengan zona waktu untuk melacak soft delete (boleh kosong)
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True)
    )
    # Membuat indeks unik untuk kolom email pada tabel users agar pencarian lebih cepat dan menjamin keunikan email
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=True)
    # Membuat indeks unik untuk kolom username pada tabel users agar pencarian username unik terjamin
    op.create_index(op.f('ix_users_username'), 'users', ['username'], unique=True)

    # Membuat tabel 'refresh_tokens' untuk sesi token JWT refresh demi keamanan autentikasi
    op.create_table(
        # Menentukan nama tabel
        'refresh_tokens',
        # Kolom primary key 'id' bertipe UUID
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        # Kolom 'user_id' untuk relasi foreign key ke tabel users
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        # Kolom 'token_hash' untuk menyimpan string hash token penyegar
        sa.Column('token_hash', sa.String(length=255), nullable=False),
        # Kolom 'expires_at' batas waktu kedaluwarsa token refresh (wajib diisi)
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        # Kolom boolean 'revoked' untuk menandai token dicabut atau tidak, defaultnya false
        sa.Column('revoked', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        # Kolom 'created_at' untuk melacak waktu token dibuat
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        # Menghubungkan relasi foreign key dari user_id ke users.id (dengan cascade delete jika user dihapus)
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE')
    )
    # Membuat indeks biasa pada user_id agar pencarian token milik user tertentu menjadi cepat
    op.create_index(op.f('ix_refresh_tokens_user_id'), 'refresh_tokens', ['user_id'], unique=False)
    # Membuat indeks unik pada token_hash agar tidak ada token refresh yang kembar di database
    op.create_index(op.f('ix_refresh_tokens_token_hash'), 'refresh_tokens', ['token_hash'], unique=True)

    # Membuat tabel 'chat_sessions' untuk wadah riwayat percakapan pengguna
    op.create_table(
        # Menentukan nama tabel
        'chat_sessions',
        # Kolom primary key 'id' bertipe UUID
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        # Kolom 'user_id' pemilik sesi chat ini
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        # Kolom judul sesi chat 'title' (opsional, bisa kosong)
        sa.Column('title', sa.String(length=255), nullable=True),
        # Waktu sesi chat dibuat
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        # Waktu sesi chat diperbarui terakhir kali
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        # Relasi foreign key ke tabel users.id (cascade delete)
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE')
    )
    # Membuat indeks pencarian pada user_id di tabel chat_sessions
    op.create_index(op.f('ix_chat_sessions_user_id'), 'chat_sessions', ['user_id'], unique=False)

    # Membuat tabel 'messages' untuk menampung tiap pesan dalam suatu sesi chat
    op.create_table(
        # Menentukan nama tabel
        'messages',
        # Kolom primary key 'id' bertipe UUID
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        # Menghubungkan pesan ke suatu sesi chat via 'session_id'
        sa.Column('session_id', postgresql.UUID(as_uuid=True), nullable=False),
        # Kolom peran 'role' bertipe enum messagerole_enum
        sa.Column('role', messagerole_enum, nullable=False),
        # Kolom 'content' bertipe Text panjang untuk teks pesan chat
        sa.Column('content', sa.Text(), nullable=False),
        # Kolom metadata bertipe JSONB untuk data tambahan bebas (seperti referensi sitasi)
        sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        # Waktu pengiriman pesan
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        # Relasi foreign key ke chat_sessions.id (cascade delete)
        sa.ForeignKeyConstraint(['session_id'], ['chat_sessions.id'], ondelete='CASCADE')
    )
    # Membuat indeks pencarian pesan berdasarkan session_id agar loading riwayat chat instan
    op.create_index(op.f('ix_messages_session_id'), 'messages', ['session_id'], unique=False)

    # Membuat tabel 'generated_media' untuk mencatat berkas gambar/video yang dibuat oleh AI
    op.create_table(
        # Menentukan nama tabel
        'generated_media',
        # Kolom primary key 'id' bertipe UUID
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        # Menghubungkan pembuatan media ke suatu sesi chat (opsional, bisa diset NULL jika sesi dihapus)
        sa.Column('session_id', postgresql.UUID(as_uuid=True), nullable=True),
        # Menghubungkan ke pembuat media via 'user_id'
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        # Jenis media bertipe enum mediatype_enum ('image'/'video')
        sa.Column('media_type', mediatype_enum, nullable=False),
        # Path atau lokasi berkas media di sistem penyimpanan lokal/cloud
        sa.Column('file_path', sa.String(length=500), nullable=False),
        # Ukuran berkas media dalam satuan byte (opsional)
        sa.Column('file_size_bytes', sa.Integer(), nullable=True),
        # Deskripsi atau prompt yang digunakan untuk menghasilkan media tersebut
        sa.Column('prompt_used', sa.Text(), nullable=True),
        # Status pemrosesan media bertipe enum mediastatus_enum, defaultnya 'processing'
        sa.Column('status', mediastatus_enum, nullable=False, server_default='processing'),
        # Pesan galat 'error_message' jika pembuatan media gagal
        sa.Column('error_message', sa.Text(), nullable=True),
        # Waktu media mulai dipesan/diproses
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        # Waktu pemrosesan media selesai sepenuhnya
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        # Relasi foreign key ke chat_sessions (jika chat didelete, status diset NULL)
        sa.ForeignKeyConstraint(['session_id'], ['chat_sessions.id'], ondelete='SET NULL'),
        # Relasi foreign key ke users.id (jika user didelete, hapus juga rekam medianya)
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE')
    )
    # Membuat indeks pencarian media berdasarkan session_id
    op.create_index(op.f('ix_generated_media_session_id'), 'generated_media', ['session_id'], unique=False)
    # Membuat indeks pencarian media berdasarkan user_id
    op.create_index(op.f('ix_generated_media_user_id'), 'generated_media', ['user_id'], unique=False)

    # Membuat tabel 'media_jobs' untuk antrean tugas asinkron pembuat media (khususnya pemrosesan video)
    op.create_table(
        # Menentukan nama tabel
        'media_jobs',
        # Kolom primary key 'id' bertipe UUID
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        # Menghubungkan job ke record media via 'media_id'
        sa.Column('media_id', postgresql.UUID(as_uuid=True), nullable=False),
        # Status antrean bertipe enum jobstatus_enum, defaultnya 'queued'
        sa.Column('status', jobstatus_enum, nullable=False, server_default='queued'),
        # Persentase progres pembuatan media (0-100)
        sa.Column('progress_pct', sa.Integer(), nullable=True),
        # Waktu pekerjaan mulai dieksekusi secara riil
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        # Waktu pekerjaan selesai dikerjakan
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        # Pesan detail kegagalan tugas jika statusnya failed
        sa.Column('error_detail', sa.Text(), nullable=True),
        # Relasi foreign key ke generated_media.id (cascade delete)
        sa.ForeignKeyConstraint(['media_id'], ['generated_media.id'], ondelete='CASCADE')
    )
    # Membuat indeks pencarian unik pada media_id karena satu media hanya memiliki maksimal satu pekerjaan antrean
    op.create_index(op.f('ix_media_jobs_media_id'), 'media_jobs', ['media_id'], unique=True)

    # Membuat tabel 'iot_sessions' untuk menyimpan sesi komunikasi dari perangkat fisik IoT
    op.create_table(
        # Menentukan nama tabel
        'iot_sessions',
        # Kolom primary key 'id' bertipe UUID
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        # Kolom identitas alat IoT 'device_id' (wajib diisi)
        sa.Column('device_id', sa.String(length=100), nullable=False),
        # Waktu sesi perangkat IoT dimulai
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        # Waktu sesi perangkat IoT selesai (opsional)
        sa.Column('ended_at', sa.DateTime(timezone=True), nullable=True)
    )
    # Membuat indeks pencarian sesi IoT berdasarkan device_id
    op.create_index(op.f('ix_iot_sessions_device_id'), 'iot_sessions', ['device_id'], unique=False)

    # Membuat tabel 'iot_messages' untuk menampung pertukaran audio/teks percakapan di perangkat IoT
    op.create_table(
        # Menentukan nama tabel
        'iot_messages',
        # Kolom primary key 'id' bertipe UUID
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        # Menghubungkan ke sesi IoT yang aktif via 'iot_session_id'
        sa.Column('iot_session_id', postgresql.UUID(as_uuid=True), nullable=False),
        # Peran pengirim pesan IoT bertipe enum iotmessagerole_enum ('user'/'assistant')
        sa.Column('role', iotmessagerole_enum, nullable=False),
        # Isi teks percakapan IoT
        sa.Column('content', sa.Text(), nullable=False),
        # Path berkas suara (TTS/audio rekaman) di sistem file lokal (opsional)
        sa.Column('audio_path', sa.String(length=500), nullable=True),
        # Metadata JSONB untuk info tambahan lainnya
        sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        # Waktu pesan IoT direkam
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        # Relasi foreign key ke iot_sessions.id (cascade delete jika sesi dihapus)
        sa.ForeignKeyConstraint(['iot_session_id'], ['iot_sessions.id'], ondelete='CASCADE')
    )
    # Membuat indeks pencarian pesan IoT berdasarkan iot_session_id
    op.create_index(op.f('ix_iot_messages_iot_session_id'), 'iot_messages', ['iot_session_id'], unique=False)

    # 3. Admin Seeding (Penyuntikan data awal administrator)
    # Jika email admin dan password admin dikonfigurasi di file env
    if settings.admin_email and settings.admin_password:
        # Menjalankan perintah SQL insert secara langsung untuk membuat user admin
        op.execute(
            users_table.insert().values(
                # Menghasilkan UUID unik acak untuk admin
                id=uuid.uuid4(),
                # Menggunakan email admin dari config
                email=settings.admin_email,
                # Mengeset username default sebagai "admin"
                username="admin",
                # Mengeset password yang sudah di-hash secara aman
                hashed_password=get_password_hash(settings.admin_password),
                # Memberikan peran istimewa 'admin'
                role='admin',
                # Mengeset user ini aktif langsung
                is_active=True,
                # Mencatat waktu pembuatan dalam zona UTC
                created_at=datetime.now(timezone.utc),
                # Mencatat waktu modifikasi terakhir dalam zona UTC
                updated_at=datetime.now(timezone.utc)
            )
        )


# Fungsi downgrade dipanggil jika ingin membatalkan/menurunkan versi migrasi ini (alembic downgrade)
def downgrade() -> None:
    # Menghapus tabel 'iot_messages' dari database
    op.drop_table('iot_messages')
    # Menghapus tabel 'iot_sessions' dari database
    op.drop_table('iot_sessions')
    # Menghapus tabel 'media_jobs' dari database
    op.drop_table('media_jobs')
    # Menghapus tabel 'generated_media' dari database
    op.drop_table('generated_media')
    # Menghapus tabel 'messages' dari database
    op.drop_table('messages')
    # Menghapus tabel 'chat_sessions' dari database
    op.drop_table('chat_sessions')
    # Menghapus tabel 'refresh_tokens' dari database
    op.drop_table('refresh_tokens')
    # Menghapus tabel 'users' dari database
    op.drop_table('users')

    # Menghapus tipe data enum 'iotmessagerole' kustom PostgreSQL
    postgresql.ENUM(name='iotmessagerole').drop(op.get_bind())
    # Menghapus tipe data enum 'jobstatus' kustom PostgreSQL
    postgresql.ENUM(name='jobstatus').drop(op.get_bind())
    # Menghapus tipe data enum 'mediastatus' kustom PostgreSQL
    postgresql.ENUM(name='mediastatus').drop(op.get_bind())
    # Menghapus tipe data enum 'mediatype' kustom PostgreSQL
    postgresql.ENUM(name='mediatype').drop(op.get_bind())
    # Menghapus tipe data enum 'messagerole' kustom PostgreSQL
    postgresql.ENUM(name='messagerole').drop(op.get_bind())
    # Menghapus tipe data enum 'userrole' kustom PostgreSQL
    postgresql.ENUM(name='userrole').drop(op.get_bind())
