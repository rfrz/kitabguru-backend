# Mengimpor modul pytest untuk anotasi pengujian asinkron
import pytest
# Mengimpor tipe data AsyncClient untuk mensimulasikan request HTTP di unit test
from httpx import AsyncClient

# Penanda dari pytest agar pengujian dijalankan dalam lingkup asinkron (async/await)
@pytest.mark.asyncio
# Fungsi pengujian untuk memverifikasi fungsionalitas registrasi, login, penyegaran token, dan logout
async def test_register_and_login(client: AsyncClient):
    # ── Bagian 1. Registrasi (Pendaftaran Akun Baru) ──────────────────────────
    # Menyusun payload JSON berisi data pendaftaran pengguna baru
    payload = {
        "email": "test@example.com",
        "username": "testuser",
        "password": "Password123!"
    }
    # Mendaftarkan pengguna baru dengan mengirimkan request POST ke rute auth/register
    res = await client.post("/api/v1/auth/register", json=payload)
    # Memverifikasi bahwa akun berhasil dibuat dengan status respons kode HTTP 201 Created
    assert res.status_code == 201
    # Mengambil respons tubuh (body) dalam format kamus JSON Python
    data = res.json()
    # Memastikan kunci 'access_token' dikembalikan dalam respons
    assert "access_token" in data
    # Memastikan kunci 'refresh_token' dikembalikan dalam respons
    assert "refresh_token" in data
    # Memastikan alamat email pengguna terdaftar di respons bernilai sesuai
    assert data["user"]["email"] == "test@example.com"

    # ── Bagian 2. Login (Masuk ke Aplikasi) ──────────────────────────────────
    # Menyusun payload JSON berisi email dan kata sandi yang valid untuk masuk
    login_payload = {
        "email": "test@example.com",
        "password": "Password123!"
    }
    # Mengirimkan request POST ke endpoint masuk auth/login
    res = await client.post("/api/v1/auth/login", json=login_payload)
    # Memverifikasi bahwa login sukses dengan status respons kode HTTP 200 OK
    assert res.status_code == 200
    # Mengambil respons data JSON login terbaru
    data = res.json()
    # Memverifikasi keberadaan token akses JWT baru
    assert "access_token" in data
    # Memverifikasi keberadaan token penyegar JWT baru
    assert "refresh_token" in data

    # ── Bagian 3. Refresh Token (Memperbarui Token) ──────────────────────────
    # Menyusun payload JSON berisi refresh token dari respon login yang aktif
    refresh_payload = {
        "refresh_token": data["refresh_token"]
    }
    # Mengirimkan request POST untuk memperbarui token ke endpoint auth/refresh
    res = await client.post("/api/v1/auth/refresh", json=refresh_payload)
    # Memverifikasi bahwa proses pembaruan sukses dengan status respons kode HTTP 200 OK
    assert res.status_code == 200
    # Mengambil respons pasangan token yang baru diterbitkan
    new_data = res.json()
    # Memastikan access token yang baru diterima
    assert "access_token" in new_data
    # Memastikan refresh token yang baru diterima
    assert "refresh_token" in new_data
    # Memastikan refresh token yang baru berbeda nilainya dari token lama (rotasi token sukses)
    assert new_data["refresh_token"] != data["refresh_token"]

    # ── Bagian 4. Logout (Keluar dari Aplikasi) ──────────────────────────────
    # Menyusun payload JSON berisi token refresh baru yang aktif untuk dicabut
    logout_payload = {
        "refresh_token": new_data["refresh_token"]
    }
    # Mengirimkan request POST ke endpoint auth/logout dengan menyertakan token akses di header Authorization
    res = await client.post(
        "/api/v1/auth/logout",
        json=logout_payload,
        # Memverifikasi bahwa logout membutuhkan autentikasi Bearer token akses yang valid
        headers={"Authorization": f"Bearer {new_data['access_token']}"}
    )
    # Memverifikasi proses keluar akun berhasil dengan status respons kode HTTP 204 No Content
    assert res.status_code == 204
