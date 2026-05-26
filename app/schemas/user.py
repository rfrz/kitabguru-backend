from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field


class UserPublic(BaseModel):
    id: str
    email: str
    username: str
    role: str
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class UserUpdateRequest(BaseModel):
    username: Optional[str] = Field(None, min_length=3, max_length=50, pattern=r"^[a-zA-Z0-9_-]+$")
    email: Optional[EmailStr] = None
    password: Optional[str] = Field(None, min_length=8, max_length=128)


class DeleteAccountRequest(BaseModel):
    """User must confirm with password before soft-delete."""
    password: str


class UserDetailAdmin(BaseModel):
    """Extended user info for admin view."""
    id: str
    email: str
    username: str
    role: str
    is_active: bool
    created_at: datetime
    updated_at: datetime
    deleted_at: Optional[datetime] = None
    session_count: int = 0
    message_count: int = 0

    model_config = {"from_attributes": True}


class UserAdminUpdateRequest(BaseModel):
    """Admin can change role and active status."""
    role: Optional[str] = None
    is_active: Optional[bool] = None


class UserListResponse(BaseModel):
    users: list[UserDetailAdmin]
    total: int
    page: int
    limit: int
