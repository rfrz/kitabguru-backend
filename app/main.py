"""
KitabGuru Backend — FastAPI Application Entry Point.

Lifecycle:
  - startup: ensure media dir, seed admin user, start purge scheduler
  - shutdown: close inference client
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.database import AsyncSessionLocal, engine, Base

logger = logging.getLogger(__name__)


async def _seed_admin() -> None:
    """Create admin user from env vars if not already present."""
    from sqlalchemy import select
    from app.models.user import User, UserRole
    from app.core.security import hash_password

    settings = get_settings()
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(User).where(User.email == settings.admin_email)
        )
        existing = result.scalar_one_or_none()
        if existing:
            logger.info("Admin user already exists: %s", settings.admin_email)
            return

        admin = User(
            email=settings.admin_email,
            username=settings.admin_username,
            hashed_password=hash_password(settings.admin_password),
            role=UserRole.admin,
            is_active=True,
        )
        db.add(admin)
        await db.commit()
        logger.info("Admin user seeded: %s", settings.admin_email)


async def _start_purge_scheduler() -> None:
    """Start the background soft-delete purge scheduler."""
    try:
        from app.services.purge_service import start_purge_scheduler
        start_purge_scheduler()
        logger.info("Purge scheduler started")
    except Exception as exc:
        logger.warning("Failed to start purge scheduler: %s", exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: startup + shutdown hooks."""
    settings = get_settings()

    # ── Startup ───────────────────────────────────────────────────────────
    logger.info("Starting KitabGuru Backend (port %s)", settings.app_port)

    # Ensure media directory exists
    settings.ensure_media_dir()

    # Seed admin user
    await _seed_admin()

    # Start purge scheduler
    await _start_purge_scheduler()

    # Store inference client in app state for reuse
    from app.providers.inference_client import InferenceClient
    app.state.inference_client = InferenceClient(settings)
    app.state.settings = settings
    app.state.session_maker = AsyncSessionLocal

    logger.info("KitabGuru Backend ready")
    yield

    # ── Shutdown ──────────────────────────────────────────────────────────
    await app.state.inference_client.aclose()
    await engine.dispose()
    logger.info("KitabGuru Backend shutdown complete")


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="KitabGuru Backend API",
        description=(
            "Platform edukasi AI — Chat RAG, Image/Video Generation, IoT Voice Interface.\n\n"
            "Auth: Bearer JWT (access token) for user endpoints. X-API-Key header for IoT endpoints."
        ),
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    # ── CORS ──────────────────────────────────────────────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Static Media ──────────────────────────────────────────────────────
    import os
    media_dir = settings.media_dir
    os.makedirs(media_dir, exist_ok=True)
    app.mount("/media", StaticFiles(directory=media_dir), name="media")

    # ── Routers ───────────────────────────────────────────────────────────
    from app.api.auth import router as auth_router
    from app.api.users import router as users_router
    from app.api.chat import router as chat_router
    from app.api.media import router as media_router
    from app.api.iot import router as iot_router
    from app.api.admin import router as admin_router

    prefix = settings.api_prefix
    app.include_router(auth_router, prefix=f"{prefix}/auth", tags=["Auth"])
    app.include_router(users_router, prefix=f"{prefix}/users", tags=["Users"])
    app.include_router(chat_router, prefix=f"{prefix}/chat", tags=["Chat"])
    app.include_router(media_router, prefix=f"{prefix}/media", tags=["Media"])
    app.include_router(iot_router, prefix=f"{prefix}/iot", tags=["IoT"])
    app.include_router(admin_router, prefix=f"{prefix}/admin", tags=["Admin"])

    # ── Health check ──────────────────────────────────────────────────────
    @app.get("/health", tags=["Health"])
    async def health():
        return {"status": "ok", "service": "kitabguru-backend"}

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn
    settings = get_settings()
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=settings.app_port,
        reload=True,
        log_level="info",
    )
