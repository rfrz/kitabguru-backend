"""
Auth routes: /auth/register, /auth/login, /auth/refresh, /auth/logout
"""
from fastapi import APIRouter, Request, status
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.dependencies import DB, AppSettings, CurrentUser
from app.schemas.auth import AuthResponse, LoginRequest, RefreshRequest, RegisterRequest, TokenResponse
from app.services.auth_service import AuthService

router = APIRouter()
limiter = Limiter(key_func=get_remote_address)


@router.post(
    "/register",
    response_model=AuthResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user",
)
@limiter.limit("5/minute")
async def register(
    request: Request,
    body: RegisterRequest,
    db: DB,
    settings: AppSettings,
):
    """
    Register a new user account.
    Returns user profile + JWT access/refresh token pair.
    Rate-limited: 5 requests/minute per IP.
    """
    service = AuthService(db, settings)
    user, access_token, refresh_token = await service.register(body)
    return AuthResponse(
        user=_user_to_schema(user),
        access_token=access_token,
        refresh_token=refresh_token,
    )


@router.post(
    "/login",
    response_model=AuthResponse,
    summary="Login with email + password",
)
@limiter.limit("5/minute")
async def login(
    request: Request,
    body: LoginRequest,
    db: DB,
    settings: AppSettings,
):
    """
    Authenticate with email/password.
    Returns user profile + JWT access/refresh token pair.
    Rate-limited: 5 requests/minute per IP.
    """
    service = AuthService(db, settings)
    user, access_token, refresh_token = await service.login(body)
    return AuthResponse(
        user=_user_to_schema(user),
        access_token=access_token,
        refresh_token=refresh_token,
    )


@router.post(
    "/refresh",
    response_model=TokenResponse,
    summary="Refresh access token using refresh token",
)
async def refresh_token(
    body: RefreshRequest,
    db: DB,
    settings: AppSettings,
):
    """
    Exchange a valid refresh token for a new access + refresh token pair.
    The old refresh token is invalidated (token rotation).
    """
    service = AuthService(db, settings)
    access_token, new_refresh_token = await service.refresh(body.refresh_token)
    return TokenResponse(
        access_token=access_token,
        refresh_token=new_refresh_token,
    )


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Logout — invalidate refresh token",
)
async def logout(
    body: RefreshRequest,
    db: DB,
    settings: AppSettings,
    current_user: CurrentUser,
):
    """
    Revoke the provided refresh token from DB.
    Future refresh attempts with this token will fail.
    """
    service = AuthService(db, settings)
    await service.logout(body.refresh_token)


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _user_to_schema(user) -> dict:
    from app.schemas.auth import UserPublic
    return UserPublic(
        id=str(user.id),
        email=user.email,
        username=user.username,
        role=user.role.value,
        is_active=user.is_active,
        created_at=str(user.created_at),
    )
