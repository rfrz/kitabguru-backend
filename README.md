---
title: KitabGuru Backend
emoji: 🗄️
colorFrom: blue
colorTo: indigo
sdk: docker
pinned: false
app_port: 7860
---

# KitabGuru Backend

FastAPI backend — pusat orkestrasi antara Frontend, Inference Engine, dan perangkat IoT.

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
Copy-Item .env.example .env
# Edit .env sesuai konfigurasi lokal
alembic upgrade head
uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8001/docs` untuk API docs.

## Fitur Utama

- **Auth**: JWT access + refresh token (simpan di DB), register/login/logout
- **Chat**: Manajemen sesi + messages, proxy ke `kitabguru-inference` (RAG)
- **Media**: Generate gambar via Cloudflare Workers AI, video via Edge-TTS + FFmpeg (async)
- **Admin**: Kelola user, monitor chat sessions, lihat IoT logs
- **IoT**: Endpoint voice (STT → Inference → TTS), anonymous session logging

## Struktur

```
app/
├── main.py           # FastAPI app + lifespan
├── config.py         # Pydantic Settings (semua dari .env)
├── database.py       # Async SQLAlchemy engine + session
├── models/           # SQLAlchemy ORM models
├── schemas/          # Pydantic request/response schemas
├── api/              # Route handlers
├── services/         # Business logic
├── providers/        # External service clients
├── core/             # Security utils + DI dependencies
└── tasks/            # Background tasks (video pipeline)
```

## Environment Variables

Lihat `.env.example` untuk daftar lengkap konfigurasi.

## API Docs

Setelah server berjalan, buka:
- Swagger UI: `http://localhost:8001/docs`
- ReDoc: `http://localhost:8001/redoc`

## Deployment to Hugging Face Spaces

Aplikasi ini sudah dikonfigurasi untuk berjalan di Hugging Face Spaces menggunakan Docker SDK. Konfigurasi HF Spaces telah disertakan pada YAML frontmatter di bagian atas file ini (`sdk: docker`, `app_port: 7860`).

Untuk deploy:
1. Buat Space baru di Hugging Face dengan memilih **Docker** sebagai Blank template.
2. Push repositori ini ke Space tersebut.
3. Buka pengaturan Space (Settings > Variables and secrets).
4. Tambahkan seluruh environment variable yang dibutuhkan (seperti `DATABASE_URL`, kredensial JWT, API Keys untuk Groq/OpenAI/Gemini) sebagai **Secrets**.
5. Hugging Face akan secara otomatis melakukan build Docker image berdasarkan `Dockerfile` di root folder backend ini dan menjalankannya di port `7860`.
