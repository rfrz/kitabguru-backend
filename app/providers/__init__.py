"""
Inisialisasi package providers untuk integrasi layanan pihak ketiga dan library eksternal.
Mengekspos klien untuk LLM/RAG inference, penyimpanan gambar Cloudflare, Edge TTS, dan Groq STT.
"""

# Mengimpor client untuk berkomunikasi dengan service inferensi model LLM/RAG
from app.providers.inference_client import InferenceClient
# Mengimpor client dan exception error untuk upload/manajemen gambar di Cloudflare Images
from app.providers.cloudflare_image import CloudflareImageClient, CloudflareImageError
# Mengimpor client dan fungsi sintesis text-to-speech menggunakan pustaka edge-tts
from app.providers.edge_tts import EdgeTTSClient, synthesize_to_file
# Mengimpor client dan exception error untuk transkripsi speech-to-text menggunakan API Groq
from app.providers.groq_stt import GroqSTTClient, GroqSTTError

# Menentukan komponen apa saja yang diekspor dari package providers
__all__ = [
    "InferenceClient",          # Penghubung FastAPI ke API RAG / inferensi model bahasa
    "CloudflareImageClient",    # Penyimpan gambar hasil generate ke cloud CDN Cloudflare
    "CloudflareImageError",     # Kelas penanganan error khusus integrasi Cloudflare Images
    "EdgeTTSClient",            # Pengubah teks menjadi berkas audio suara (TTS) secara asinkron
    "synthesize_to_file",       # Utilitas helper untuk langsung menyimpan TTS ke file audio lokal
    "GroqSTTClient",            # Pengubah berkas suara (audio) menjadi teks (STT) melalui Groq API
    "GroqSTTError",             # Kelas penanganan error khusus integrasi transkripsi Groq
]
