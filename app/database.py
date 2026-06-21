# Mengimpor Generator Asinkron untuk mendefinisikan type hinting fungsi generator database
from collections.abc import AsyncGenerator

# Mengimpor komponen sesi asinkron, pembuat sesi, dan engine asinkron dari SQLAlchemy
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
# Mengimpor kelas Base deklaratif dari SQLAlchemy ORM sebagai class induk model tabel
from sqlalchemy.orm import DeclarativeBase

# Mengimpor fungsi helper untuk mengambil konfigurasi aplikasi
from app.config import get_settings

# Menginisialisasi variabel settings dengan memanggil get_settings
settings = get_settings()

# Membuat instance engine koneksi database asinkron dengan konfigurasi dari database_url
engine = create_async_engine(
    # Membaca URL database dari pengaturan aplikasi
    settings.database_url,
    # Menyembunyikan log query SQL ke terminal agar logs bersih
    echo=False,
    # Mengaktifkan ping berkala ke database sebelum query untuk memastikan koneksi tidak mati
    pool_pre_ping=True,
)

# Membuat pabrik pembuat sesi asinkron (sessionmaker) untuk digunakan dalam transaksi database
AsyncSessionLocal = async_sessionmaker(
    # Mengikat pembuat sesi ke engine database asinkron yang telah dibuat
    bind=engine,
    # Menetapkan tipe kelas sesi yang dihasilkan ke AsyncSession
    class_=AsyncSession,
    # Mencegah penutupan otomatis status objek setelah commit transaksi
    expire_on_commit=False,
)


# Mendefinisikan kelas Base utama yang akan diwarisi oleh seluruh model database ORM
class Base(DeclarativeBase):
    """Kelas dasar (Base Class) untuk semua model ORM SQLAlchemy di aplikasi."""
    # Tidak melakukan apa-apa karena hanya berfungsi sebagai deklarasi dasar class
    pass


# Fungsi dependensi FastAPI untuk menyediakan sesi database asinkron per request
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency: menghasilkan sesi database asinkron secara asinkron.
    Menghasilkan sesi database untuk setiap request, melakukan rollback jika error,
    dan memastikan sesi ditutup setelah request selesai.
    """
    # Membuka sesi asinkron baru secara otomatis menggunakan AsyncSessionLocal
    async with AsyncSessionLocal() as session:
        # Blok try untuk mendeteksi apabila terjadi error selama pemrosesan request
        try:
            # Memberikan instance session database ke endpoint yang memanggil dependensi ini
            yield session
        # Menangkap semua jenis exception/error yang terjadi selama transaksi
        except Exception:
            # Melakukan rollback database untuk membatalkan semua perubahan jika transaksi gagal
            await session.rollback()
            # Meneruskan kembali error yang tertangkap agar ditangani FastAPI
            raise
        # Blok finally yang akan selalu dieksekusi di akhir, baik sukses maupun error
        finally:
            # Menutup sesi koneksi database asinkron untuk membebaskan resource pool
            await session.close()
