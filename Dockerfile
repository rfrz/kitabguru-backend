FROM python:3.14-slim

# Mencegah Python membuat file .pyc dan memastikan log terminal langsung muncul
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install system dependencies (FFmpeg for video generation)
RUN apt-get update && apt-get install -y ffmpeg build-essential && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy dependency definition
COPY pyproject.toml .

# Install dependencies (tanpa -e untuk production)
RUN pip install --no-cache-dir .

# Copy seluruh source code
COPY . .

# Buat direktori media untuk upload/storage
RUN mkdir -p /app/media

# Setup non-root user (Wajib untuk Hugging Face Spaces karena masalah permission)
RUN useradd -m -u 1000 user
RUN chown -R user:user /app

USER user

# Hugging Face Spaces mewajibkan aplikasi berjalan di port 7860
EXPOSE 7860

# Command: Jalankan migrasi database terlebih dahulu, lalu jalankan FastAPI
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 7860"]
