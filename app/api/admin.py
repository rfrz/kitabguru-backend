"""
Admin routes (Admin role required):
  GET    /admin/users              — List all users (paginated, searchable)
  GET    /admin/users/{id}         — Detail user + stats
  PATCH  /admin/users/{id}         — Update user role/status
  DELETE /admin/users/{id}         — Force-delete user
  GET    /admin/sessions           — List all chat sessions
  GET    /admin/sessions/{id}      — View session + messages
  DELETE /admin/sessions/{id}      — Delete session
  GET    /admin/iot/sessions       — List IoT sessions
  GET    /admin/iot/sessions/{id}  — View IoT session + messages
  DELETE /admin/iot/sessions/{id}  — Delete IoT session
"""
import uuid
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import selectinload

from app.core.dependencies import DB, AdminUser
from app.models.iot import IoTSession, IoTMessage
from app.models.user import ChatSession, Message, User, UserRole
from app.schemas.chat import MessageOut, SessionDetailResponse, SessionSummary
from app.schemas.iot import IoTMessageOut, IoTSessionDetailResponse, IoTSessionListResponse, IoTSessionSummary
from app.schemas.user import UserAdminUpdateRequest, UserDetailAdmin, UserListResponse

router = APIRouter()


# ─── User Management ─────────────────────────────────────────────────────────

@router.get(
    "/users",
    response_model=UserListResponse,
    summary="List all users (admin)",
)
async def list_users(
    admin: AdminUser,
    db: DB,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    search: Optional[str] = Query(None, description="Search by email or username"),
):
    """Paginated list of all users including soft-deleted ones."""
    offset = (page - 1) * limit

    query = select(User)
    if search:
        pattern = f"%{search}%"
        query = query.where(
            or_(User.email.ilike(pattern), User.username.ilike(pattern))
        )

    count_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = count_result.scalar_one()

    result = await db.execute(
        query.order_by(User.created_at.desc()).offset(offset).limit(limit)
    )
    users = result.scalars().all()

    # Get session/message counts per user
    user_ids = [u.id for u in users]
    session_counts = {}
    message_counts = {}
    if user_ids:
        sc = await db.execute(
            select(ChatSession.user_id, func.count(ChatSession.id))
            .where(ChatSession.user_id.in_(user_ids))
            .group_by(ChatSession.user_id)
        )
        session_counts = {row[0]: row[1] for row in sc.all()}

        mc = await db.execute(
            select(ChatSession.user_id, func.count(Message.id))
            .outerjoin(Message, Message.session_id == ChatSession.id)
            .where(ChatSession.user_id.in_(user_ids))
            .group_by(ChatSession.user_id)
        )
        message_counts = {row[0]: row[1] for row in mc.all()}

    user_details = [
        UserDetailAdmin(
            id=str(u.id),
            email=u.email,
            username=u.username,
            role=u.role.value,
            is_active=u.is_active,
            created_at=u.created_at,
            updated_at=u.updated_at,
            deleted_at=u.deleted_at,
            session_count=session_counts.get(u.id, 0),
            message_count=message_counts.get(u.id, 0),
        )
        for u in users
    ]

    return UserListResponse(users=user_details, total=total, page=page, limit=limit)


@router.get(
    "/users/{user_id}",
    response_model=UserDetailAdmin,
    summary="Get user detail + stats (admin)",
)
async def get_user_detail(
    user_id: str,
    admin: AdminUser,
    db: DB,
):
    user = await _get_user_or_404(user_id, db)

    session_count_result = await db.execute(
        select(func.count(ChatSession.id)).where(ChatSession.user_id == user.id)
    )
    session_count = session_count_result.scalar_one()

    message_count_result = await db.execute(
        select(func.count(Message.id))
        .join(ChatSession, Message.session_id == ChatSession.id)
        .where(ChatSession.user_id == user.id)
    )
    message_count = message_count_result.scalar_one()

    return UserDetailAdmin(
        id=str(user.id),
        email=user.email,
        username=user.username,
        role=user.role.value,
        is_active=user.is_active,
        created_at=user.created_at,
        updated_at=user.updated_at,
        deleted_at=user.deleted_at,
        session_count=session_count,
        message_count=message_count,
    )


@router.patch(
    "/users/{user_id}",
    response_model=UserDetailAdmin,
    summary="Update user role or active status (admin)",
)
async def update_user(
    user_id: str,
    body: UserAdminUpdateRequest,
    admin: AdminUser,
    db: DB,
):
    user = await _get_user_or_404(user_id, db)

    if body.role is not None:
        try:
            user.role = UserRole(body.role)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid role: {body.role}. Must be 'user' or 'admin'",
            )

    if body.is_active is not None:
        user.is_active = body.is_active

    await db.commit()
    await db.refresh(user)
    return UserDetailAdmin(
        id=str(user.id),
        email=user.email,
        username=user.username,
        role=user.role.value,
        is_active=user.is_active,
        created_at=user.created_at,
        updated_at=user.updated_at,
        deleted_at=user.deleted_at,
    )


@router.delete(
    "/users/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Force-delete user (admin)",
)
async def delete_user(
    user_id: str,
    admin: AdminUser,
    db: DB,
):
    """Hard-delete a user immediately (bypasses soft-delete grace period)."""
    user = await _get_user_or_404(user_id, db)
    if str(user.id) == str(admin.id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete your own admin account",
        )
    await db.delete(user)
    await db.commit()


# ─── Chat Session Management ─────────────────────────────────────────────────

@router.get(
    "/sessions",
    summary="List all chat sessions (admin)",
)
async def list_all_sessions(
    admin: AdminUser,
    db: DB,
    user_id: Optional[str] = Query(None, description="Filter by user ID"),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
):
    """Paginated list of all chat sessions across all users."""
    offset = (page - 1) * limit
    query = select(ChatSession)

    if user_id:
        try:
            uid = uuid.UUID(user_id)
            query = query.where(ChatSession.user_id == uid)
        except ValueError:
            pass

    count_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = count_result.scalar_one()

    result = await db.execute(
        query.order_by(ChatSession.created_at.desc()).offset(offset).limit(limit)
    )
    sessions = result.scalars().all()

    # Get message counts
    session_ids = [s.id for s in sessions]
    msg_counts = {}
    if session_ids:
        mc = await db.execute(
            select(Message.session_id, func.count(Message.id))
            .where(Message.session_id.in_(session_ids))
            .group_by(Message.session_id)
        )
        msg_counts = {row[0]: row[1] for row in mc.all()}

    summaries = [
        SessionSummary(
            id=str(s.id),
            title=s.title,
            created_at=s.created_at,
            updated_at=s.updated_at,
            message_count=msg_counts.get(s.id, 0),
        )
        for s in sessions
    ]
    return {"sessions": summaries, "total": total, "page": page, "limit": limit}


@router.get(
    "/sessions/{session_id}",
    response_model=SessionDetailResponse,
    summary="View a specific chat session + messages (admin)",
)
async def get_session_admin(
    session_id: str,
    admin: AdminUser,
    db: DB,
):
    session = await _get_session_or_404(session_id, db)
    messages = [
        MessageOut(
            id=str(m.id),
            role=m.role.value,
            content=m.content,
            metadata=m.meta,
            created_at=m.created_at,
        )
        for m in session.messages
    ]
    summary = SessionSummary(
        id=str(session.id),
        title=session.title,
        created_at=session.created_at,
        updated_at=session.updated_at,
        message_count=len(messages),
    )
    return SessionDetailResponse(session=summary, messages=messages)


@router.delete(
    "/sessions/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a chat session (admin)",
)
async def delete_session_admin(
    session_id: str,
    admin: AdminUser,
    db: DB,
):
    session = await _get_session_or_404(session_id, db)
    await db.delete(session)
    await db.commit()


# ─── IoT Session Management ───────────────────────────────────────────────────

@router.get(
    "/iot/sessions",
    response_model=IoTSessionListResponse,
    summary="List all IoT sessions (admin)",
)
async def list_iot_sessions(
    admin: AdminUser,
    db: DB,
    device_id: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
):
    offset = (page - 1) * limit
    query = select(IoTSession)
    if device_id:
        query = query.where(IoTSession.device_id == device_id)

    count_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = count_result.scalar_one()

    result = await db.execute(
        query.order_by(IoTSession.started_at.desc()).offset(offset).limit(limit)
    )
    sessions = result.scalars().all()

    session_ids = [s.id for s in sessions]
    msg_counts = {}
    if session_ids:
        mc = await db.execute(
            select(IoTMessage.iot_session_id, func.count(IoTMessage.id))
            .where(IoTMessage.iot_session_id.in_(session_ids))
            .group_by(IoTMessage.iot_session_id)
        )
        msg_counts = {row[0]: row[1] for row in mc.all()}

    summaries = [
        IoTSessionSummary(
            id=str(s.id),
            device_id=s.device_id,
            started_at=s.started_at,
            ended_at=s.ended_at,
            message_count=msg_counts.get(s.id, 0),
        )
        for s in sessions
    ]
    return IoTSessionListResponse(sessions=summaries, total=total, page=page, limit=limit)


@router.get(
    "/iot/sessions/{session_id}",
    response_model=IoTSessionDetailResponse,
    summary="View IoT session + messages (admin)",
)
async def get_iot_session_admin(
    session_id: str,
    admin: AdminUser,
    db: DB,
):
    session = await _get_iot_session_or_404(session_id, db)
    messages = [
        IoTMessageOut(
            id=str(m.id),
            role=m.role.value,
            content=m.content,
            audio_path=m.audio_path,
            metadata=m.meta,
            created_at=m.created_at,
        )
        for m in session.messages
    ]
    return IoTSessionDetailResponse(
        session_id=str(session.id),
        device_id=session.device_id,
        started_at=session.started_at,
        ended_at=session.ended_at,
        messages=messages,
    )


@router.delete(
    "/iot/sessions/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete IoT session (admin)",
)
async def delete_iot_session_admin(
    session_id: str,
    admin: AdminUser,
    db: DB,
):
    session = await _get_iot_session_or_404(session_id, db)
    await db.delete(session)
    await db.commit()


# ─── Private Helpers ─────────────────────────────────────────────────────────

async def _get_user_or_404(user_id: str, db) -> User:
    try:
        uid = uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    result = await db.execute(select(User).where(User.id == uid))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


async def _get_session_or_404(session_id: str, db) -> ChatSession:
    try:
        sid = uuid.UUID(session_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    result = await db.execute(
        select(ChatSession)
        .options(selectinload(ChatSession.messages))
        .where(ChatSession.id == sid)
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    return session


async def _get_iot_session_or_404(session_id: str, db) -> IoTSession:
    try:
        sid = uuid.UUID(session_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="IoT session not found")
    result = await db.execute(
        select(IoTSession)
        .options(selectinload(IoTSession.messages))
        .where(IoTSession.id == sid)
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="IoT session not found")
    return session
