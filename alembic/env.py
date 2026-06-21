# Mengimpor modul asyncio untuk mendukung pemrograman asinkronus (async/await)
import asyncio
# Mengimpor modul fileConfig untuk memuat konfigurasi logging dari file .ini
from logging.config import fileConfig

# Mengimpor modul pool dari SQLAlchemy untuk mengelola koneksi database pool
from sqlalchemy import pool
# Mengimpor tipe Connection dari SQLAlchemy untuk anotasi tipe data koneksi database
from sqlalchemy.engine import Connection
# Mengimpor fungsi pembuat mesin database asinkron berdasarkan konfigurasi
from sqlalchemy.ext.asyncio import async_engine_from_config

# Mengimpor objek context dari Alembic untuk mengontrol jalannya migrasi database
from alembic import context

# Mengimpor fungsi untuk mengambil pengaturan konfigurasi aplikasi
from app.config import get_settings
# Mengimpor kelas Base deklaratif SQLAlchemy untuk mengenali metadata tabel
from app.database import Base
# Memanggil fungsi get_settings untuk mendapatkan objek konfigurasi saat ini
settings = get_settings()
# Mengimpor semua model database agar terdaftar ke metadata SQLAlchemy sebelum migrasi dijalankan
from app.models import User, ChatSession, Message, GeneratedMedia, MediaJob, IoTSession, IoTMessage

# Mengambil objek konfigurasi Alembic yang sedang berjalan dari context
config = context.config

# Jika nama file konfigurasi log tersedia di objek config Alembic
if config.config_file_name is not None:
    # Konfigurasikan logger Python menggunakan file config tersebut
    fileConfig(config.config_file_name)

# Menyimpan metadata tabel dari Base SQLAlchemy untuk dipakai oleh fitur auto-generate migrasi Alembic
target_metadata = Base.metadata

# Mengatur opsi URL database SQLAlchemy pada konfigurasi Alembic menggunakan nilai dari settings aplikasi
config.set_main_option("sqlalchemy.url", settings.database_url)


# Fungsi untuk menjalankan migrasi database tanpa koneksi langsung (offline mode)
def run_migrations_offline() -> None:
    """Menjalankan migrasi dalam mode 'offline'.

    Mode ini mengonfigurasi context hanya dengan menggunakan URL database,
    tanpa membuat objek Engine koneksi database sungguhan.
    """
    # Mengambil URL database yang diset pada opsi sqlalchemy.url
    url = config.get_main_option("sqlalchemy.url")
    # Mengonfigurasi konteks Alembic dengan URL, metadata tabel, dan setelan dialek SQL
    context.configure(
        # Menentukan URL database target
        url=url,
        # Menentukan metadata skema tabel tujuan
        target_metadata=target_metadata,
        # Memastikan nilai parameter langsung di-render ke SQL (literal bind)
        literal_binds=True,
        # Menentukan format parameter SQL bermodel 'named'
        dialect_opts={"paramstyle": "named"},
    )

    # Membuka transaksi migrasi
    with context.begin_transaction():
        # Menjalankan kumpulan skrip migrasi yang belum terpasang
        context.run_migrations()


# Fungsi pembantu untuk mengeksekusi migrasi di dalam koneksi database yang aktif
def do_run_migrations(connection: Connection) -> None:
    # Mengonfigurasi konteks Alembic dengan koneksi aktif dan metadata tabel
    context.configure(connection=connection, target_metadata=target_metadata)

    # Membuka transaksi migrasi baru di database
    with context.begin_transaction():
        # Menjalankan proses migrasi database
        context.run_migrations()


# Fungsi asinkron untuk mengelola pembuatan mesin database asinkron dan koneksinya
async def run_async_migrations() -> None:
    """Dalam skenario ini kita perlu membuat Engine asinkron

    dan mengaitkan sebuah koneksi aktif dengan konteks migrasi Alembic.
    """

    # Membuat engine database asinkron dari konfigurasi Alembic
    connectable = async_engine_from_config(
        # Mengambil konfigurasi database berawalan 'sqlalchemy.' dari bagian .ini
        config.get_section(config.config_ini_section, {}),
        # Menentukan prefix konfigurasi SQLAlchemy
        prefix="sqlalchemy.",
        # Menggunakan NullPool agar koneksi langsung ditutup setelah dipakai
        poolclass=pool.NullPool,
    )

    # Membuka koneksi database asinkron secara aman menggunakan context manager
    async with connectable.connect() as connection:
        # Menjalankan migrasi secara sinkron di dalam koneksi asinkron
        await connection.run_sync(do_run_migrations)

    # Menutup mesin database asinkron dan membersihkan seluruh resources
    await connectable.dispose()


# Fungsi untuk menjalankan migrasi database dengan koneksi online (online mode)
def run_migrations_online() -> None:
    """Menjalankan migrasi dalam mode 'online'."""

    # Menjalankan loop event asinkron untuk memproses migrasi secara asinkronus
    asyncio.run(run_async_migrations())


# Memeriksa apakah Alembic dijalankan dalam mode offline atau online
if context.is_offline_mode():
    # Jika offline, panggil fungsi migrasi offline
    run_migrations_offline()
else:
    # Jika online, panggil fungsi migrasi online
    run_migrations_online()
