# Menggunakan base image python:3.14-slim yang ringan untuk menjalankan aplikasi Python
FROM python:3.14-slim

# Mencegah Python membuat file .pyc (compiled bytecode) agar direktori tetap bersih
ENV PYTHONDONTWRITEBYTECODE=1
# Memastikan log keluaran terminal langsung muncul secara realtime tanpa dibuffer
ENV PYTHONUNBUFFERED=1

# Memperbarui package repository dan menginstal library FFmpeg untuk pemrosesan video serta build-essential untuk kompilasi C
RUN apt-get update && apt-get install -y ffmpeg build-essential && rm -rf /var/lib/apt/lists/*

# Menetapkan direktori kerja di dalam container ke folder /app
WORKDIR /app

# Menyalin file spesifikasi dependency (pyproject.toml) ke direktori kerja saat ini
COPY pyproject.toml .

# Menginstal dependensi yang didefinisikan dalam pyproject.toml tanpa cache untuk memperkecil ukuran image
RUN pip install --no-cache-dir .

# Menyalin seluruh kode sumber (source code) proyek ke dalam direktori kerja container
COPY . .

# Membuat direktori media baru untuk menyimpan file upload atau media yang diunduh/dihasilkan
RUN mkdir -p /app/media

# Membuat user non-root bernama 'user' dengan User ID 1000 demi keamanan (dan kompatibilitas Hugging Face Spaces)
RUN useradd -m -u 1000 user
# Mengubah hak kepemilikan direktori /app sepenuhnya menjadi milik user non-root tersebut
RUN chown -R user:user /app

# Menjalankan container menggunakan user non-root yang telah dibuat demi membatasi akses root
USER user

# Membuka port 7860 untuk akses jaringan luar (port default Hugging Face Spaces)
EXPOSE 7860

# CMD menjalankan perintah migrasi database alembic terlebih dahulu, baru kemudian menjalankan aplikasi FastAPI via Uvicorn
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 7860"]
