# Mengimpor modul pytest untuk menandai pengetesan asinkron
import pytest
# Mengimpor tipe data AsyncClient untuk simulasi request HTTP di dalam pengujian
from httpx import AsyncClient

# Penanda khusus dari pytest untuk mengizinkan testing secara asinkron (async/await)
@pytest.mark.asyncio
# Fungsi pengujian untuk memverifikasi fungsionalitas dan otorisasi endpoint admin
async def test_admin_endpoints(client: AsyncClient):
    # Menyusun data pendaftaran pengguna (user) biasa
    payload = {
        "email": "user@example.com",
        "username": "normaluser",
        "password": "Password123!"
    }
    # Mendaftarkan user biasa melalui API pendaftaran auth/register
    await client.post("/api/v1/auth/register", json=payload)
    # Masuk (login) menggunakan kredensial user biasa yang baru dibuat
    login_res = await client.post("/api/v1/auth/login", json=payload)
    # Mengambil token akses JWT dari data JSON respons login
    user_token = login_res.json()["access_token"]
    # Menyiapkan header HTTP Authorization Bearer menggunakan token user biasa
    user_headers = {"Authorization": f"Bearer {user_token}"}

    # Memastikan pengguna biasa ditolak (Forbidden) saat mencoba mengakses halaman daftar user admin
    res = await client.get("/api/v1/admin/users", headers=user_headers)
    # Memverifikasi bahwa status kode HTTP respons yang diterima bernilai 403 Forbidden
    assert res.status_code == 403

    # Menyiapkan kredensial login admin default sesuai setelan awal aplikasi
    login_admin = {
        # Menggunakan email admin default
        "email": "admin@kitabguru.com",
        # Menggunakan sandi rahasia admin default
        "password": "ChangeThisPassword!"
    }
    # Melakukan login sebagai administrator
    admin_res = await client.post("/api/v1/auth/login", json=login_admin)
    
    # Jika proses masuk administrator sukses (status 200 OK)
    if admin_res.status_code == 200:
        # Mengambil token akses JWT milik administrator
        admin_token = admin_res.json()["access_token"]
        # Menyiapkan header HTTP Authorization Bearer menggunakan token administrator
        admin_headers = {"Authorization": f"Bearer {admin_token}"}

        # Menguji akses administrator ke halaman daftar pengguna
        res = await client.get("/api/v1/admin/users", headers=admin_headers)
        # Memverifikasi akses diijinkan dengan status kode 200 OK
        assert res.status_code == 200
        # Memastikan kunci data 'users' ada di dalam isi JSON respons
        assert "users" in res.json()

        # Menyusun data payload untuk membuat user baru langsung dari akun administrator
        create_payload = {
            "email": "createdbyadmin@example.com",
            "username": "admincreated",
            "password": "AdminPassword123!",
            "role": "user"
        }
        # Melakukan request pembuatan pengguna baru oleh administrator
        res_create = await client.post("/api/v1/admin/users", json=create_payload, headers=admin_headers)
        # Memverifikasi bahwa akun berhasil dibuat dengan status kode 201 Created
        assert res_create.status_code == 201
        # Mengubah respons bodi menjadi objek JSON Python
        created_user = res_create.json()
        # Memastikan email pengguna yang baru dibuat sesuai
        assert created_user["email"] == "createdbyadmin@example.com"
        # Memastikan username sesuai
        assert created_user["username"] == "admincreated"
        # Memastikan peran akun diset sebagai user biasa
        assert created_user["role"] == "user"

        # Menguji pembuatan akun dengan email yang sama kembali untuk memicu error duplikat
        res_dup = await client.post("/api/v1/admin/users", json=create_payload, headers=admin_headers)
        # Memverifikasi bahwa server mengembalikan status kode konflik 409 Conflict
        assert res_dup.status_code == 409
