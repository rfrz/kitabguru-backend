"""
Inisialisasi package tasks untuk proses background worker (tugas asinkron).
Mengekspos fungsi video pipeline yang memproses penggabungan gambar & audio di latar belakang.
"""

# Mengimpor fungsi eksekusi pipeline pembuatan video secara asinkron
from app.tasks.video_pipeline import run_video_pipeline

# Mengekspos fungsi video pipeline agar mudah diimpor dari sub-package tasks
__all__ = ["run_video_pipeline"]
