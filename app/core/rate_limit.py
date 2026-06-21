# Mengimpor class Limiter dari slowapi untuk membatasi frekuensi request API
from slowapi import Limiter
# Mengimpor fungsi get_remote_address untuk mengambil alamat IP client sebagai kunci rate limit
from slowapi.util import get_remote_address

# Menginisialisasi objek limiter global menggunakan alamat IP client untuk membedakan asal request
limiter = Limiter(key_func=get_remote_address)
