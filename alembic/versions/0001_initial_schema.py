"""Initial schema

Revision ID: 0001
Revises: 
Create Date: 2026-05-26 15:00:00.000000

"""
from typing import Sequence, Union
import os
import uuid
from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from app.core.security import hash_password as get_password_hash
from app.config import get_settings

settings = get_settings()

# revision identifiers, used by Alembic.
revision: str = '0001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Enums
    userrole_enum = postgresql.ENUM('user', 'admin', name='userrole')
    messagerole_enum = postgresql.ENUM('user', 'assistant', 'system', name='messagerole')
    mediatype_enum = postgresql.ENUM('image', 'video', name='mediatype')
    mediastatus_enum = postgresql.ENUM('processing', 'completed', 'failed', name='mediastatus')
    jobstatus_enum = postgresql.ENUM('queued', 'processing', 'completed', 'failed', name='jobstatus')
    iotmessagerole_enum = postgresql.ENUM('user', 'assistant', name='iotmessagerole')

    # 2. Tables
    users_table = op.create_table(
        'users',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('username', sa.String(length=100), nullable=False),
        sa.Column('hashed_password', sa.String(length=255), nullable=False),
        sa.Column('role', userrole_enum, nullable=False, server_default='user'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True)
    )
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=True)
    op.create_index(op.f('ix_users_username'), 'users', ['username'], unique=True)

    op.create_table(
        'refresh_tokens',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('token_hash', sa.String(length=255), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('revoked', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE')
    )
    op.create_index(op.f('ix_refresh_tokens_user_id'), 'refresh_tokens', ['user_id'], unique=False)
    op.create_index(op.f('ix_refresh_tokens_token_hash'), 'refresh_tokens', ['token_hash'], unique=True)

    op.create_table(
        'chat_sessions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('title', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE')
    )
    op.create_index(op.f('ix_chat_sessions_user_id'), 'chat_sessions', ['user_id'], unique=False)

    op.create_table(
        'messages',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('session_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('role', messagerole_enum, nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['session_id'], ['chat_sessions.id'], ondelete='CASCADE')
    )
    op.create_index(op.f('ix_messages_session_id'), 'messages', ['session_id'], unique=False)

    op.create_table(
        'generated_media',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('session_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('media_type', mediatype_enum, nullable=False),
        sa.Column('file_path', sa.String(length=500), nullable=False),
        sa.Column('file_size_bytes', sa.Integer(), nullable=True),
        sa.Column('prompt_used', sa.Text(), nullable=True),
        sa.Column('status', mediastatus_enum, nullable=False, server_default='processing'),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['session_id'], ['chat_sessions.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE')
    )
    op.create_index(op.f('ix_generated_media_session_id'), 'generated_media', ['session_id'], unique=False)
    op.create_index(op.f('ix_generated_media_user_id'), 'generated_media', ['user_id'], unique=False)

    op.create_table(
        'media_jobs',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('media_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('status', jobstatus_enum, nullable=False, server_default='queued'),
        sa.Column('progress_pct', sa.Integer(), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('error_detail', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['media_id'], ['generated_media.id'], ondelete='CASCADE')
    )
    op.create_index(op.f('ix_media_jobs_media_id'), 'media_jobs', ['media_id'], unique=True)

    op.create_table(
        'iot_sessions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('device_id', sa.String(length=100), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('ended_at', sa.DateTime(timezone=True), nullable=True)
    )
    op.create_index(op.f('ix_iot_sessions_device_id'), 'iot_sessions', ['device_id'], unique=False)

    op.create_table(
        'iot_messages',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('iot_session_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('role', iotmessagerole_enum, nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('audio_path', sa.String(length=500), nullable=True),
        sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['iot_session_id'], ['iot_sessions.id'], ondelete='CASCADE')
    )
    op.create_index(op.f('ix_iot_messages_iot_session_id'), 'iot_messages', ['iot_session_id'], unique=False)

    # 3. Admin Seeding
    if settings.admin_email and settings.admin_password:
        op.execute(
            users_table.insert().values(
                id=uuid.uuid4(),
                email=settings.admin_email,
                username="admin",
                hashed_password=get_password_hash(settings.admin_password),
                role='admin',
                is_active=True,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc)
            )
        )


def downgrade() -> None:
    op.drop_table('iot_messages')
    op.drop_table('iot_sessions')
    op.drop_table('media_jobs')
    op.drop_table('generated_media')
    op.drop_table('messages')
    op.drop_table('chat_sessions')
    op.drop_table('refresh_tokens')
    op.drop_table('users')

    postgresql.ENUM(name='iotmessagerole').drop(op.get_bind())
    postgresql.ENUM(name='jobstatus').drop(op.get_bind())
    postgresql.ENUM(name='mediastatus').drop(op.get_bind())
    postgresql.ENUM(name='mediatype').drop(op.get_bind())
    postgresql.ENUM(name='messagerole').drop(op.get_bind())
    postgresql.ENUM(name='userrole').drop(op.get_bind())
