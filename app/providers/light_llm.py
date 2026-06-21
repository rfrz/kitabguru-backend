# Mengimpor modul json untuk encoding dan decoding JSON data
import json
# Mengimpor modul logging untuk pencatatan aktivitas sistem
import logging
# Mengimpor modul re untuk operasi pencocokan teks menggunakan regular expression (regex)
import re
# Mengimpor Optional dari typing untuk type-hinting nilai yang boleh None
from typing import Optional

# Mengimpor skema Settings untuk memuat API Key LLM
from app.config import Settings

# Menginisialisasi logger sistem khusus modul light_llm ini
logger = logging.getLogger(__name__)


# Kelas Exception khusus untuk menangani error kegagalan LLM internal
class LightLLMError(Exception):
    # Mewarisi Exception dasar Python
    pass


# Kelas Client untuk menangani model LLM ringan secara fleksibel dengan sistem fallback
class LightLLMClient:
    """
    Wrapper LLM ringan yang menangani mekanisme fallback (cadangan otomatis)
    antara Google Gemini dan provider API OpenAI-compatible.
    Digunakan untuk tugas-tugas pendukung seperti menyederhanakan chat RAG
    menjadi deskripsi prompt gambar SDXL atau teks narasi slide video.
    """
    # Mengambil konfigurasi setting dan memparsing daftar urutan model fallback
    def __init__(self, settings: Settings):
        # Menyimpan instance konfigurasi global
        self.settings = settings
        # Memecah string urutan fallback berdasarkan tanda koma dan membersihkan whitespace
        self.fallback_order = [
            p.strip().lower() 
            for p in self.settings.llm_fallback_order.split(",") 
            if p.strip()
        ]

    # Menerjemahkan riwayat chat edukasi bahasa Indonesia menjadi prompt gambar bahasa Inggris untuk SDXL
    async def generate_image_prompt(self, conversation_text: str) -> str:
        """
        Menerjemahkan obrolan pendidikan Indonesia yang panjang menjadi prompt bahasa Inggris yang padat
        untuk pembuatan gambar Cloudflare SDXL.
        """
        # System instruction untuk memandu model bahasa agar menghasilkan prompt gambar yang optimal
        system_instruction = (
            "You are an assistant that creates prompts for an image generation model (SDXL). "
            "Read the following Indonesian educational conversation and extract the core factual subject. "
            "Write a highly descriptive, concise English prompt (max 70 words) to create an INFOGRAPHIC or ILLUSTRATED POSTER about the subject. "
            "Focus on visual elements: subject, typography layout, informative aesthetic, and style "
            "(e.g., 'Infographic style, clean layout, Islamic geometric borders, educational poster, high quality'). "
            "Output ONLY the prompt string, no markdown, no quotes, no conversational text."
        )

        # Iterasi melalui daftar urutan provider fallback
        for provider in self.fallback_order:
            # Mencoba memanggil provider LLM satu per satu
            try:
                # Jika provider saat ini adalah google gemini
                if provider == "gemini":
                    # Panggil method internal _call_gemini asinkron
                    result = await self._call_gemini(system_instruction, conversation_text)
                    # Jika berhasil mendapatkan respon teks, langsung kembalikan hasilnya
                    if result: return result
                # Jika provider saat ini kompatibel dengan standar OpenAI
                elif provider == "openai_compatible":
                    # Panggil method internal _call_openai_compatible asinkron
                    result = await self._call_openai_compatible(system_instruction, conversation_text)
                    # Jika berhasil mendapatkan teks respon, langsung kembalikan
                    if result: return result
                # Jika provider tidak dikenali dalam daftar
                else:
                    # Catat log warning
                    logger.warning(f"Unknown LLM provider in fallback: {provider}")
            # Menangkap kegagalan jaringan atau error API dari provider
            except Exception as e:
                # Catat error log dan lanjutkan iterasi ke provider cadangan berikutnya
                logger.error(f"LightLLM provider '{provider}' failed: {e}")
                continue
                
        # Jika semua provider cadangan di atas gagal merespon
        logger.error("All LightLLM providers failed. Using generic fallback prompt.")
        # Mengembalikan prompt default Islami sebagai opsi darurat terakhir
        return "An Islamic educational scene with geometric patterns and books, high quality, vibrant."

    # Membuat narasi teks naskah video slide dan mendeteksi bahasa percakapan
    async def generate_video_script(self, conversation_text: str) -> dict:
        """
        Membuat naskah narasi video dan mendeteksi bahasa dari riwayat percakapan.
        Mengembalikan dictionary dengan struktur key:
            - "language_code": kode bahasa yang terdeteksi (seperti: 'id-ID', 'en-US')
            - "script_text": isi naskah teks narasi dengan kalimat pendek (maks 10-15 kata).
        """
        # Instruksi sistem terperinci untuk menghasilkan format naskah video islami yang terstruktur dalam bentuk JSON
        system_instruction = (
            "You are an expert Islamic educator and scriptwriter. Your task is to write a video narration script based on the provided conversation history.\n"
            "Follow these rules strictly:\n"
            "1. Detect the language of the conversation history (e.g. Indonesian, English, Arabic, Japanese, etc.). The script MUST be written in this exact language.\n"
            "2. The narration must be educational, inspiring, calming, and concise. It should summarize the core educational topics discussed.\n"
            "3. Start the script with a peaceful greeting in the detected language (e.g., 'Bismillahirrahmanirrahim. Assalamualaikum...' or English equivalent like 'In the name of Allah, the Beneficent, the Merciful...').\n"
            "4. End with an inspiring closing sentence.\n"
            "5. The sentences must be very short and readable: maximum of 10-15 words per sentence. This is extremely important because the text will be displayed in large font on slides. Use clear, simple punctuation (periods, question marks, exclamation marks) to separate sentences.\n"
            "6. Output the result ONLY as a valid JSON object with the keys \"language_code\" and \"script_text\".\n"
            "Do not add any conversational responses, formatting or markdown outside the JSON.\n\n"
            "Example output:\n"
            "{\n"
            '  "language_code": "id-ID",\n'
            '  "script_text": "Bismillahirrahmanirrahim. Mari kita pelajari ilmu tajwid bersama. Membaca Al-Qur\'an harus dengan tartil. Semoga Allah memudahkan langkah kita."\n'
            "}"
        )

        # Menyiapkan data respon cadangan jika semua request API LLM gagal total
        fallback_result = {
            "language_code": "id-ID",
            "script_text": "Bismillahirrahmanirrahim. Selamat belajar bersama KitabGuru, platform pendidikan Islam berbasis AI."
        }

        # Iterasi melalui daftar provider cadangan untuk memproses naskah video
        for provider in self.fallback_order:
            # Mencoba memanggil API
            try:
                # Pilihan pemanggilan model Gemini
                if provider == "gemini":
                    # Panggil API Gemini dengan batas output token yang lebih panjang (600 token)
                    result = await self._call_gemini(system_instruction, conversation_text, max_tokens=600)
                # Pilihan pemanggilan model OpenAI Compatible
                elif provider == "openai_compatible":
                    # Panggil API OpenAI Compatible dengan batas 600 token
                    result = await self._call_openai_compatible(system_instruction, conversation_text, max_tokens=600)
                # Kasus jika nama provider salah
                else:
                    logger.warning(f"Unknown LLM provider in fallback: {provider}")
                    continue

                # Jika API sukses mengembalikan respon string teks
                if result:
                    # Bersihkan spasi kosong di ujung string
                    clean_res = result.strip()
                    # Menghilangkan markdown format JSON block (```json ... ```) jika LLM menyertakannya
                    if clean_res.startswith("```"):
                        # Menggunakan regex untuk menghapus tag pembuka code block JSON
                        clean_res = re.sub(r"^```(?:json)?\n", "", clean_res)
                        # Menggunakan regex untuk menghapus tag penutup code block
                        clean_res = re.sub(r"\n```$", "", clean_res)
                    # Bersihkan kembali whitespace
                    clean_res = clean_res.strip()
                    # Mencoba memparsing string bersih tersebut menjadi objek JSON/dict Python
                    try:
                        data = json.loads(clean_res)
                        # Memastikan key wajib 'language_code' dan 'script_text' ada di hasil parse JSON
                        if "language_code" in data and "script_text" in data:
                            # Mengembalikan data dictionary sukses
                            return data
                        # Kasus jika JSON valid namun strukturnya salah
                        else:
                            logger.warning(f"JSON from LightLLM missing keys. Content: {clean_res}")
                    # Menangkap error jika output teks LLM tidak berformat JSON valid
                    except json.JSONDecodeError:
                        logger.warning(f"Failed to parse JSON from LightLLM content: {clean_res}")
            # Menangkap error jaringan/API per provider
            except Exception as e:
                logger.error(f"LightLLM provider '{provider}' failed in generate_video_script: {e}")
                continue

        # Jika semua provider gagal mengembalikan data yang valid, cetak error log
        logger.error("All LightLLM providers failed or returned invalid JSON for video script. Using fallback.")
        # Mengembalikan data cadangan default
        return fallback_result

    # Method internal untuk memanggil Google GenAI SDK secara asinkron
    async def _call_gemini(self, system: str, user_text: str, max_tokens: int = 150) -> Optional[str]:
        # Memastikan kunci API Gemini tersedia
        if not self.settings.gemini_api_key:
            raise ValueError("GEMINI_API_KEY is not set")
            
        # Mencoba mengimpor library genai dari Google SDK terbaru
        try:
            from google import genai
            from google.genai import types
        # Lempar error jika library belum terpasang di sistem virtual environment
        except ImportError:
            raise ImportError("google-genai package not installed")

        # Inisialisasi client GenAI dengan kunci API
        client = genai.Client(api_key=self.settings.gemini_api_key)
        
        # Mengirimkan request generate content asinkron menggunakan client.aio
        response = await client.aio.models.generate_content(
            # Menentukan tipe model Gemini
            model=self.settings.gemini_llm_model,
            # Menyusun instruksi sistem di depan instruksi user
            contents=[system + "\n\nConversation:\n" + user_text],
            # Mengonfigurasi parameter temperatur rendah (konsisten) dan batas token
            config=types.GenerateContentConfig(
                temperature=0.3,
                max_output_tokens=max_tokens,
            )
        )
        # Mengembalikan teks respon bersih, atau None jika respon kosong
        return response.text.strip() if response.text else None

    # Method internal untuk memanggil API provider lain yang kompatibel dengan format OpenAI
    async def _call_openai_compatible(self, system: str, user_text: str, max_tokens: int = 150) -> Optional[str]:
        # Memastikan seluruh parameter konfigurasi OpenAI compatible sudah lengkap
        if not self.settings.openai_compatible_api_key or not self.settings.openai_compatible_base_url or not self.settings.openai_compatible_model:
            raise ValueError("OpenAI compatible config is missing")
            
        # Mencoba mengimpor library openai
        try:
            from openai import AsyncOpenAI
        # Lempar error jika pustaka belum terpasang
        except ImportError:
            raise ImportError("openai package not installed")

        # Inisialisasi client AsyncOpenAI asinkron
        client = AsyncOpenAI(
            api_key=self.settings.openai_compatible_api_key,
            base_url=self.settings.openai_compatible_base_url
        )
        
        # Mengirim request chat completion asinkron ke server model
        response = await client.chat.completions.create(
            # Menentukan model API target
            model=self.settings.openai_compatible_model,
            # Menyusun struktur pesan standard chat (system role dan user role)
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_text}
            ],
            temperature=0.3,
            max_tokens=max_tokens
        )
        # Mengembalikan isi konten teks dari pilihan pilihan respon pertama
        return response.choices[0].message.content.strip()
