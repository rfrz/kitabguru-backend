"""
Auth service: register, login, refresh token, logout.
Refresh tokens are stored as SHA-256 hashes in DB for security.
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.core.security import (
    create_access_token,
    create_refresh_token,
    hash_password,
    hash_token,
    verify_password,
    get_token_expiry,
    decode_token,
)
from app.models.user import RefreshToken, User, UserRole
from app.schemas.auth import RegisterRequest, LoginRequest
from fastapi import HTTPException, status


class AuthService:
    def __init__(self, db: AsyncSession, settings: Settings):
        self.db = db
        self.settings = settings

    async def register(self, data: RegisterRequest) -> tuple[User, str, str]:
        """Register a new user. Returns (user, access_token, refresh_token)."""
        # Check uniqueness
        existing = await self.db.execute(
            select(User).where(
                (User.email == data.email) | (User.username == data.username),
                User.deleted_at.is_(None),
            )
        )
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email or username already in use",
            )

        user = User(
            email=data.email,
            username=data.username,
            hashed_password=hash_password(data.password),
            role=UserRole.user,
        )
        self.db.add(user)
        await self.db.flush()  # get user.id before commit

        access_token, refresh_token = await self._issue_tokens(user)
        await self.db.commit()
        await self.db.refresh(user)
        return user, access_token, refresh_token

    async def login(self, data: LoginRequest) -> tuple[User, str, str]:
        """Authenticate user. Returns (user, access_token, refresh_token)."""
        result = await self.db.execute(
            select(User).where(User.email == data.email, User.deleted_at.is_(None))
        )
        user = result.scalar_one_or_none()

        if not user or not verify_password(data.password, user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password",
            )
        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Account is deactivated",
            )

        access_token, refresh_token = await self._issue_tokens(user)
        await self.db.commit()
        return user, access_token, refresh_token

    async def refresh(self, raw_refresh_token: str) -> tuple[str, str]:
        """
        Validate refresh token, revoke it, and issue a new pair.
        Implements token rotation for security.
        """
        try:
            payload = decode_token(raw_refresh_token)
            if payload.get("type") != "refresh":
                raise ValueError("Not a refresh token")
            user_id = uuid.UUID(payload["sub"])
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired refresh token",
            )

        token_hash = hash_token(raw_refresh_token)
        result = await self.db.execute(
            select(RefreshToken).where(
                RefreshToken.token_hash == token_hash,
                RefreshToken.user_id == user_id,
                RefreshToken.revoked.is_(False),
            )
        )
        stored = result.scalar_one_or_none()
        if not stored or stored.expires_at < datetime.now(timezone.utc):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh token not found, expired, or already used",
            )

        # Revoke old token (rotation)
        stored.revoked = True
        self.db.add(stored)

        # Load user
        user_result = await self.db.execute(
            select(User).where(User.id == user_id, User.deleted_at.is_(None))
        )
        user = user_result.scalar_one_or_none()
        if not user or not user.is_active:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

        access_token, new_refresh = await self._issue_tokens(user)
        await self.db.commit()
        return access_token, new_refresh

    async def logout(self, raw_refresh_token: str) -> None:
        """Revoke the refresh token (logout from current device)."""
        try:
            token_hash = hash_token(raw_refresh_token)
        except Exception:
            return  # Silently ignore malformed tokens on logout

        result = await self.db.execute(
            select(RefreshToken).where(
                RefreshToken.token_hash == token_hash,
                RefreshToken.revoked.is_(False),
            )
        )
        stored = result.scalar_one_or_none()
        if stored:
            stored.revoked = True
            self.db.add(stored)
            await self.db.commit()

    async def _issue_tokens(self, user: User) -> tuple[str, str]:
        """Create and store a new access + refresh token pair."""
        access_token = create_access_token(str(user.id), user.role.value)
        refresh_token = create_refresh_token(str(user.id))

        expires_at = get_token_expiry(days=self.settings.jwt_refresh_token_expire_days)
        stored_token = RefreshToken(
            user_id=user.id,
            token_hash=hash_token(refresh_token),
            expires_at=expires_at,
        )
        self.db.add(stored_token)
        return access_token, refresh_token
