"""
Client Cloudflare Workers AI untuk pemrosesan pembuatan gambar AI (Text-to-Image).
Kredensial akses (CF_ACCOUNT_ID, CF_API_TOKEN, CF_IMAGE_MODEL) dimuat secara dinamis 
dari file env dan tidak pernah ditulis keras (hardcoded) demi keamanan data.
"""
# Mengimpor modul httpx untuk melakukan request HTTP asinkron
import httpx

# Mengimpor skema Settings untuk membaca konfigurasi aplikasi
from app.config import Settings


# Kelas Exception khusus untuk menangani error saat berkomunikasi dengan Cloudflare Images
class CloudflareImageError(RuntimeError):
    # Mewarisi RuntimeError bawaan Python
    pass


# Kelas Client untuk berinteraksi dengan API pembuat gambar Cloudflare Workers AI
class CloudflareImageClient:
    """
    Menghubungi endpoint text-to-image milik Cloudflare Workers AI.
    Dokumentasi API: https://developers.cloudflare.com/workers-ai/models/stable-diffusion-xl-base-1.0/
    """

    # Inisialisasi client dan verifikasi kredensial Cloudflare
    def __init__(self, settings: Settings):
        # Memastikan CF_ACCOUNT_ID diset di environment, lempar error jika tidak ada
        if not settings.cf_account_id:
            raise CloudflareImageError("CF_ACCOUNT_ID is not set in environment")
        # Memastikan CF_API_TOKEN diset di environment, lempar error jika tidak ada
        if not settings.cf_api_token:
            raise CloudflareImageError("CF_API_TOKEN is not set in environment")

        # Menyusun URL endpoint API Cloudflare Workers AI berdasarkan account ID dan model yang dipilih
        self._url = (
            f"https://api.cloudflare.com/client/v4/accounts/"
            f"{settings.cf_account_id}/ai/run/{settings.cf_image_model}"
        )
        # Menyiapkan header HTTP berupa token Bearer untuk otentikasi API Cloudflare
        self._headers = {
            "Authorization": f"Bearer {settings.cf_api_token}",
            "Content-Type": "application/json",
        }

    # Mengirim prompt teks ke Cloudflare untuk diubah menjadi gambar
    async def generate(self, prompt: str) -> bytes:
        """
        Menghasilkan gambar dari teks deskripsi (prompt).
        Mengembalikan byte data mentah dari gambar berformat PNG/JPEG.
        """
        # Membuka koneksi HTTP client asinkron dengan batas timeout 60 detik
        async with httpx.AsyncClient(timeout=60.0) as client:
            # Mengirimkan request POST ke API Cloudflare dengan payload JSON prompt
            response = await client.post(
                self._url,
                headers=self._headers,
                json={"prompt": prompt},
            )
            # Jika status respon API bukan 200 OK, lempar error
            if response.status_code != 200:
                raise CloudflareImageError(
                    f"Cloudflare AI returned {response.status_code}: {response.text}"
                )
            # Mengembalikan byte konten gambar yang diterima
            return response.content
