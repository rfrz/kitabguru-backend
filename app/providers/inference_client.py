"""
Client HTTP asinkron untuk berinteraksi dengan service inferensi RAG (kitabguru-inference).
"""
# Mengimpor modul typing untuk type-hinting data dictionary
from typing import Any, Optional

# Mengimpor modul httpx untuk request HTTP asinkron yang efisien
import httpx

# Mengimpor skema Settings untuk mengambil URL service RAG
from app.config import Settings


# Kelas Client untuk bertukar data dengan mesin inferensi RAG
class InferenceClient:
    # Inisialisasi client HTTP dengan base URL RAG dan token otentikasi jika tersedia
    def __init__(self, settings: Settings):
        # Membaca base URL inferensi dan membuang karakter slash di ujung jika ada
        self.base_url = settings.inference_base_url.rstrip("/")
        # Menyiapkan dictionary header HTTP kosong
        headers = {}
        # Jika token Hugging Face diatur, pasang token Bearer di header Authorization
        if settings.hf_token:
            headers["Authorization"] = f"Bearer {settings.hf_token}"
            
        # Menginisialisasi instance AsyncClient HTTPX untuk pemakaian jangka panjang
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            # Menetapkan batas timeout 120 detik karena pemrosesan RAG/LLM memerlukan waktu lebih lama
            timeout=120.0,
            headers=headers,
        )

    # Mengirimkan pertanyaan user ke endpoint chat API inferensi RAG
    async def chat(self, query: str, book_filter: Optional[str] = None) -> dict[str, Any]:
        """
        Mengirim permintaan POST ke API /api/chat pada mesin inferensi RAG.
        Mengembalikan dictionary utuh berisi jawaban dan kutipan RAG.
        """
        # Menyusun payload request body berupa query teks
        payload: dict[str, Any] = {"query": query}
        # Jika filter buku diisi, masukkan filter_book ke payload RAG
        if book_filter:
            payload["book_filter"] = book_filter

        # Mengirim request POST secara asinkron ke URL /api/chat
        response = await self._client.post("/api/chat", json=payload)
        # Memastikan status response sukses (200-299), lempar exception HTTPError jika gagal
        response.raise_for_status()
        # Mengembalikan hasil respon dalam format JSON dictionary
        return response.json()

    # Memeriksa keaktifan / status kesehatan service inferensi RAG
    async def health(self) -> bool:
        """Memeriksa apakah service inferensi RAG sedang berjalan aktif."""
        # Menggunakan blok try-except untuk menangani server mati / offline
        try:
            # Mengirim request GET ke /health dengan timeout singkat 5 detik
            resp = await self._client.get("/health", timeout=5.0)
            # Mengembalikan True jika status HTTP response bernilai 200 OK
            return resp.status_code == 200
        # Menangkap error jaringan atau kegagalan koneksi apa pun
        except Exception:
            # Mengembalikan False jika server tidak merespon
            return False

    # Menutup sesi koneksi HTTP client asinkron secara bersih saat shutdown server
    async def aclose(self) -> None:
        """Menutup koneksi client HTTPX asinkron."""
        await self._client.aclose()

    # Mendukung protokol context manager asinkron (enter hook)
    async def __aenter__(self):
        # Mengembalikan objek client ini sendiri
        return self

    # Mendukung protokol context manager asinkron (exit hook)
    async def __aexit__(self, *args):
        # Menutup koneksi client secara otomatis ketika keluar dari blok context
        await self.aclose()
