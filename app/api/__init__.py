"""
Inisialisasi package API dan registrasi router.
Package ini bertanggung jawab mengekspos semua router API dari submodule
seperti auth, users, chat, media, iot, dan admin agar mudah diimpor secara kolektif.
"""

# Mengimpor router otentikasi (auth) dari modul auth.py dan memberi alias auth_router
from app.api.auth import router as auth_router
# Mengimpor router manajemen user dari modul users.py dan memberi alias users_router
from app.api.users import router as users_router
# Mengimpor router fitur chat AI dari modul chat.py dan memberi alias chat_router
from app.api.chat import router as chat_router
# Mengimpor router fitur pembuatan/manajemen media dari modul media.py dan memberi alias media_router
from app.api.media import router as media_router
# Mengimpor router integrasi IoT dari modul iot.py dan memberi alias iot_router
from app.api.iot import router as iot_router
# Mengimpor router panel admin dari modul admin.py dan memberi alias admin_router
from app.api.admin import router as admin_router

# Mendefinisikan daftar modul/variabel yang diekspor ketika mengimpor modul api ini
__all__ = [
    "auth_router",  # Router untuk proses login, register, dan token refresh
    "users_router",  # Router untuk mengambil dan mengubah data profil user
    "chat_router",   # Router untuk membuat sesi obrolan dan mengirim pesan
    "media_router",  # Router untuk menghasilkan gambar dan video AI
    "iot_router",    # Router untuk menerima data dan voice interaction dari IoT
    "admin_router",  # Router untuk dashboard admin dan manajemen database
]
