# Mengimpor pytest untuk penandaan pengetesan asinkron
import pytest
# Mengimpor AsyncClient untuk simulasi request HTTP di unit test
from httpx import AsyncClient

# Penanda khusus dari pytest untuk mengizinkan testing secara asinkron (async/await)
@pytest.mark.asyncio
# Fungsi pengujian untuk memverifikasi alur percakapan chat (membuat sesi, kirim pesan, lihat detail, hapus sesi)
async def test_chat_flow(client: AsyncClient):
    # Pendaftaran dan login akun uji baru untuk mendapatkan token otentikasi
    payload = {
        "email": "chat@example.com",
        "username": "chatuser",
        "password": "Password123!"
    }
    # Mengirim request registrasi akun uji
    await client.post("/api/v1/auth/register", json=payload)
    # Mengirim request login menggunakan kredensial akun uji tersebut
    login_res = await client.post("/api/v1/auth/login", json=payload)
    # Mengambil token akses JWT dari data respons JSON login
    token = login_res.json()["access_token"]
    # Menyiapkan header HTTP Authorization Bearer menggunakan token aktif
    headers = {"Authorization": f"Bearer {token}"}

    # ── Bagian 1. Membuat Sesi Chat Baru ──────────────────────────────────────
    # Mengirimkan request POST ke rute chat/sessions untuk membuat sesi chat bernama "Test Chat"
    res = await client.post("/api/v1/chat/sessions", json={"title": "Test Chat"}, headers=headers)
    # Memverifikasi pembuatan sesi chat sukses dengan status kode HTTP 201 Created
    assert res.status_code == 201
    # Menyimpan ID sesi chat yang baru dibuat dari data JSON respons
    session_id = res.json()["id"]

    # ── Bagian 2. Mengirim Pesan Chat ─────────────────────────────────────────
    # Menyusun payload berisi teks pesan percakapan yang dikirim oleh pengguna
    msg_payload = {"content": "Halo apa kabar?"}
    # Mengirimkan request POST berisi pesan ke sesi chat yang bersangkutan
    res = await client.post(f"/api/v1/chat/sessions/{session_id}/messages", json=msg_payload, headers=headers)
    # Memastikan status respons bernilai 200 OK (jika server inferensi aktif) atau 502 Bad Gateway (jika server inferensi mati)
    assert res.status_code in (200, 502)

    # ── Bagian 3. Mengambil Detail Sesi Chat ──────────────────────────────────
    # Mengirim request GET untuk mengambil detail data sesi chat spesifik berdasarkan ID
    res = await client.get(f"/api/v1/chat/sessions/{session_id}", headers=headers)
    # Memverifikasi pengambilan sukses dengan status kode HTTP 200 OK
    assert res.status_code == 200
    # Memverifikasi judul sesi chat yang tersimpan sesuai dengan judul semula
    assert res.json()["session"]["title"] == "Test Chat"

    # ── Bagian 4. Menampilkan Daftar Sesi Chat ────────────────────────────────
    # Mengirim request GET ke rute chat/sessions untuk menampilkan semua daftar sesi milik user
    res = await client.get("/api/v1/chat/sessions", headers=headers)
    # Memverifikasi pemanggilan sukses dengan status kode HTTP 200 OK
    assert res.status_code == 200
    # Memastikan jumlah daftar sesi chat milik user bernilai lebih dari 0
    assert len(res.json()["sessions"]) > 0

    # ── Bagian 5. Menghapus Sesi Chat ─────────────────────────────────────────
    # Mengirim request DELETE ke endpoint sesi chat target untuk menghapus sesi dan riwayatnya
    res = await client.delete(f"/api/v1/chat/sessions/{session_id}", headers=headers)
    # Memverifikasi penghapusan sesi berhasil dengan status kode HTTP 204 No Content
    assert res.status_code == 204
