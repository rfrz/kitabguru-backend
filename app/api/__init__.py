from app.api.auth import router as auth_router
from app.api.users import router as users_router
from app.api.chat import router as chat_router
from app.api.media import router as media_router
from app.api.iot import router as iot_router
from app.api.admin import router as admin_router

__all__ = [
    "auth_router",
    "users_router",
    "chat_router",
    "media_router",
    "iot_router",
    "admin_router",
]
