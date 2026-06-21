"""
Layanan Pembersihan (Purge Service): Menjalankan background task untuk menghapus akun soft-deleted secara permanen beserta datanya setelah lewat 30 hari.
"""
# Mengimpor modul asyncio untuk menangani loop jeda waktu (sleep)
import asyncio
# Mengimpor modul logging untuk pencatatan log service
import logging
# Mengimpor datetime, timedelta, timezone untuk kalkulasi batas 30 hari
from datetime import datetime, timedelta, timezone

# Mengimpor delete dan select dari SQLAlchemy
from sqlalchemy import delete, select
# Mengimpor AsyncSession untuk transaksi database asinkron
from sqlalchemy.ext.asyncio import AsyncSession

# Mengimpor Settings dan helper get_settings
from app.config import Settings, get_settings
# Mengimpor pembuat sesi database lokal
from app.database import AsyncSessionLocal
# Mengimpor model database User
from app.models.user import User

# Menginisialisasi logger sistem khusus modul purge_service ini
logger = logging.getLogger(__name__)


# Kelas PurgeService mengelola logika penghapusan permanen data user soft-deleted
class PurgeService:
    # Inisialisasi service dengan sesi database dan settings
    def __init__(self, db: AsyncSession, settings: Settings):
        self.db = db
        self.settings = settings

    # Menjalankan pembersihan data user yang telah lewat masa tenggang 30 hari
    async def run_purge(self) -> int:
        """
        Menghapus akun pengguna (dan seluruh data terkait secara cascade) yang status deleted_at
        sudah lebih lama dari 30 hari.
        Mengembalikan jumlah user yang berhasil dibersihkan.
        """
        # Menghitung tanggal batas minimal pembersihan (tanggal hari ini dikurangi 30 hari)
        threshold_date = datetime.now(timezone.utc) - timedelta(days=30)
        
        # Query mencari user yang berstatus dihapus (deleted_at tidak null) dan deleted_at sudah melewati threshold
        query = select(User).where(
            User.deleted_at.is_not(None),
            User.deleted_at < threshold_date
        )
        # Mengeksekusi query pencarian
        result = await self.db.execute(query)
        # Mengambil seluruh baris data user
        users_to_purge = result.scalars().all()
        
        # Jika tidak ada user yang memenuhi syarat untuk dibersihkan
        if not users_to_purge:
            # Mengembalikan angka 0
            return 0
            
        # Mengumpulkan ID user yang akan dihapus permanen
        user_ids = [u.id for u in users_to_purge]
        
        # Mempersiapkan statemen penghapusan permanen (hard delete) user
        delete_stmt = delete(User).where(User.id.in_(user_ids))
        # Mengeksekusi penghapusan di database
        await self.db.execute(delete_stmt)
        # Melakukan commit transaksi penghapusan secara permanen
        await self.db.commit()
        
        # Mengembalikan jumlah user yang terhapus
        return len(user_ids)


# Fungsi loop asinkron tak terbatas untuk memicu pembersihan database berkala setiap 24 jam
async def _purge_loop():
    """Loop tak terbatas yang menjalankan pembersihan database berkala setiap 24 jam."""
    # Loop berjalan terus-menerus selama service menyala
    while True:
        # Memulai blok penanganan error
        try:
            # Memuat konfigurasi settings aplikasi terbaru
            settings = get_settings()
            # Membuka sesi database baru secara aman menggunakan asinkron context manager
            async with AsyncSessionLocal() as db:
                # Membuat instance service pembersihan
                service = PurgeService(db, settings)
                # Menjalankan logika pembersihan dan mengambil jumlah data terhapus
                purged_count = await service.run_purge()
                # Jika ada user yang terhapus permanen
                if purged_count > 0:
                    # Mencatat logs info keberhasilan pembersihan data user
                    logger.info(f"PurgeService: Hard-deleted {purged_count} soft-deleted users.")
        # Menangkap signal pembatalan proses asinkron (misal saat shutdown)
        except asyncio.CancelledError:
            # Keluar dari loop pencarian
            break
        # Menangkap exception error tidak terduga lainnya
        except Exception as e:
            # Mencatat logs error
            logger.error(f"PurgeService error: {e}")
        
        # Menunda pengerjaan asinkron selama 24 jam (86400 detik) sebelum loop berikutnya
        await asyncio.sleep(86400)


# Menyalakan thread background scheduler pembersihan database
def start_purge_scheduler():
    """Menjalankan loop pembersihan database di background task asyncio."""
    # Mendapatkan loop event asyncio yang sedang berjalan saat ini
    loop = asyncio.get_running_loop()
    # Mendaftarkan task loop asinkron asinkron _purge_loop ke background
    loop.create_task(_purge_loop())
