# Mengimpor modul asyncio untuk menangani loop event asinkron selama pengujian
import asyncio
# Mengimpor modul os untuk mengatur variabel environment sistem
import os
# Mengimpor pytest untuk mendefinisikan fixture dan mengonfigurasi testing framework
import pytest
# Mengimpor AsyncClient untuk mensimulasikan client HTTP asinkron dan ASGITransport untuk memuat app FastAPI tanpa port
from httpx import AsyncClient, ASGITransport

# Mengimpor objek app FastAPI utama untuk diuji
from app.main import app
# Mengimpor Base (metadata tabel), engine database, dan pembuat sesi lokal asinkron
from app.database import Base, engine, AsyncSessionLocal
# Mengimpor get_settings untuk membaca konfigurasi aplikasi
from app.config import get_settings

# Mengatur variabel environment TESTING ke string "1" untuk membedakan mode testing dan production
os.environ["TESTING"] = "1"

# Fixture pytest tingkat sesi (hanya dibuat satu kali per sesi pengujian) untuk loop event asinkron
@pytest.fixture(scope="session")
def event_loop():
    # Membuat loop event asinkron yang baru menggunakan kebijakan default sistem
    loop = asyncio.get_event_loop_policy().new_event_loop()
    # Mengeset loop event yang baru tersebut sebagai loop event asinkron aktif di thread saat ini
    asyncio.set_event_loop(loop)
    # Menyerahkan loop ke pengujian yang membutuhkannya
    yield loop
    # Menutup loop event asinkron secara bersih setelah seluruh sesi pengujian selesai
    loop.close()

# Fixture pytest tingkat sesi yang otomatis dijalankan (autouse=True) untuk mempersiapkan database test
@pytest.fixture(scope="session", autouse=True)
async def setup_db():
    # Menutup koneksi database engine aktif sebelumnya jika ada untuk menghindari konflik status
    await engine.dispose()
    # Membuka koneksi transaksi awal pada database engine test
    async with engine.begin() as conn:
        # Menghapus seluruh tabel yang terdaftar di Metadata Base untuk memastikan db benar-benar bersih
        await conn.run_sync(Base.metadata.drop_all)
        # Membuat ulang semua struktur tabel segar di database test berdasarkan model SQLAlchemy
        await conn.run_sync(Base.metadata.create_all)
    # Menyerahkan kontrol eksekusi ke kode unit test yang sedang berjalan
    yield
    # Membuka koneksi transaksi baru setelah seluruh rangkaian pengujian selesai
    async with engine.begin() as conn:
        # Menghapus kembali semua tabel database agar tidak menyisakan sampah di database test
        await conn.run_sync(Base.metadata.drop_all)
    # Menutup koneksi database engine secara permanen untuk membebaskan memory/socket
    await engine.dispose()

# Fixture pytest tingkat fungsi untuk menyediakan sesi database baru yang terisolasi di tiap fungsi test
@pytest.fixture
async def db_session():
    # Membuka sesi database asinkron yang bersih menggunakan AsyncSessionLocal
    async with AsyncSessionLocal() as session:
        # Menyerahkan objek sesi database ke fungsi unit test
        yield session

# Fixture pytest tingkat fungsi untuk menyediakan client HTTP simulasi pengujian endpoint
@pytest.fixture
async def client():
    # Menutup koneksi database engine sebelumnya untuk menghindari pembagian status koneksi antar request
    await engine.dispose()
    # Membuat instance AsyncClient HTTPX dengan transport ASGI langsung mengarah ke aplikasi FastAPI kita
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # Menyerahkan objek client ke fungsi pengujian
        yield ac
    # Menutup koneksi database engine setelah request simulasi selesai
    await engine.dispose()

# Fixture placeholder untuk token otentikasi admin di masa depan
@pytest.fixture
def admin_token():
    # Akan diimplementasikan nanti atau disimulasikan menggunakan mock
    pass
