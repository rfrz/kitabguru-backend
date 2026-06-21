# Mengimpor modul pytest untuk penandaan pengetesan asinkron
import pytest
# Mengimpor AsyncClient untuk mensimulasikan request HTTP di unit test
from httpx import AsyncClient

# Penanda dari pytest agar pengujian dijalankan secara asinkron (async/await)
@pytest.mark.asyncio
# Fungsi pengujian untuk memverifikasi rute-rute media (gambar, video, histori media)
async def test_media_endpoints(client: AsyncClient):
    # Menyusun data pendaftaran pengguna uji baru
    payload = {
        "email": "media@example.com",
        "username": "mediauser",
        "password": "Password123!"
    }
    # Mendaftarkan pengguna baru via auth/register
    await client.post("/api/v1/auth/register", json=payload)
    # Masuk (login) menggunakan kredensial pengguna uji tersebut
    login_res = await client.post("/api/v1/auth/login", json=payload)
    # Mengambil token akses JWT dari data respons JSON login
    token = login_res.json()["access_token"]
    # Menyiapkan header HTTP Authorization Bearer menggunakan token aktif
    headers = {"Authorization": f"Bearer {token}"}

    # ── Menguji Pembuatan Gambar ──────────────────────────────────────────────
    # Mengirim request POST pembuatan gambar dengan UUID sesi kosong agar memicu error/not found
    res = await client.post("/api/v1/media/generate/image", json={"session_id": "00000000-0000-0000-0000-000000000000"}, headers=headers)
    # Memverifikasi respons status kode HTTP bernilai 404 (Sesi tidak ditemukan) atau 502 (Gagal terhubung ke RAG)
    assert res.status_code in (404, 502)
    
    # ── Menguji Pembuatan Video ──────────────────────────────────────────────
    # Mengirim request POST pembuatan video dengan UUID sesi kosong
    res = await client.post("/api/v1/media/generate/video", json={"session_id": "00000000-0000-0000-0000-000000000000"}, headers=headers)
    # Memverifikasi respons status kode HTTP bernilai 404 atau 502
    assert res.status_code in (404, 502)

    # ── Menguji Daftar Media Pengguna ────────────────────────────────────────
    # Mengirim request GET ke rute media/user untuk mengambil semua riwayat media milik pengguna
    res = await client.get("/api/v1/media/user", headers=headers)
    # Memverifikasi pemanggilan sukses dengan status kode HTTP 200 OK
    assert res.status_code == 200
    # Memastikan bahwa data respons yang diterima bertipe list (atau sesuai skema yang dikembalikan)
    assert isinstance(res.json(), list)
