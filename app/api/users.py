"""
User profile routes: GET/PATCH /users/me, DELETE /users/me
"""
from datetime import datetime

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.core.dependencies import DB, AppSettings, CurrentUser
from app.core.security import hash_password, verify_password
from app.models.user import User
from app.schemas.user import DeleteAccountRequest, UserPublic, UserUpdateRequest

router = APIRouter()


@router.get(
    "/me",
    response_model=UserPublic,
    summary="Get current user profile",
)
async def get_my_profile(current_user: CurrentUser):
    """Return the authenticated user's public profile."""
    return _user_out(current_user)


@router.patch(
    "/me",
    response_model=UserPublic,
    summary="Update profile (username, email, or password)",
)
async def update_my_profile(
    body: UserUpdateRequest,
    current_user: CurrentUser,
    db: DB,
):
    """
    Update one or more of: username, email, password.
    Validates uniqueness of new username/email.
    """
    if body.username and body.username != current_user.username:
        existing = await db.execute(
            select(User).where(
                User.username == body.username,
                User.id != current_user.id,
                User.deleted_at.is_(None),
            )
        )
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Username already in use",
            )
        current_user.username = body.username

    if body.email and body.email != current_user.email:
        existing = await db.execute(
            select(User).where(
                User.email == body.email,
                User.id != current_user.id,
                User.deleted_at.is_(None),
            )
        )
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email already in use",
            )
        current_user.email = body.email

    if body.password:
        current_user.hashed_password = hash_password(body.password)

    await db.commit()
    await db.refresh(current_user)
    return _user_out(current_user)


@router.delete(
    "/me",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Soft-delete account (requires password confirmation)",
)
async def delete_my_account(
    body: DeleteAccountRequest,
    current_user: CurrentUser,
    db: DB,
):
    """
    Soft-delete the account by setting deleted_at to now.
    Requires current password for confirmation.
    The account will be hard-deleted after 30 days by the purge scheduler.
    """
    if not verify_password(body.password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect password",
        )

    from datetime import timezone
    current_user.deleted_at = datetime.now(timezone.utc)
    current_user.is_active = False
    await db.commit()


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _user_out(user: User) -> UserPublic:
    return UserPublic(
        id=str(user.id),
        email=user.email,
        username=user.username,
        role=user.role.value,
        is_active=user.is_active,
        created_at=user.created_at,
    )
