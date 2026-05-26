from app.schemas.auth import (
    RegisterRequest,
    LoginRequest,
    RefreshRequest,
    TokenResponse,
    AuthResponse,
)
from app.schemas.user import (
    UserPublic,
    UserUpdateRequest,
    DeleteAccountRequest,
    UserDetailAdmin,
    UserAdminUpdateRequest,
    UserListResponse,
)
from app.schemas.chat import (
    SessionCreateRequest,
    SessionRenameRequest,
    SessionSummary,
    SessionListResponse,
    MessageOut,
    SessionDetailResponse,
    SendMessageRequest,
    SendMessageResponse,
)
from app.schemas.media import (
    ImageGenerateRequest,
    ImageGenerateResponse,
    VideoGenerateRequest,
    VideoGenerateResponse,
    JobStatusResponse,
    MediaOut,
    MediaListResponse,
)
from app.schemas.iot import (
    IoTSessionCreateRequest,
    IoTSessionResponse,
    IoTVoiceResponse,
    IoTMessageOut,
    IoTSessionDetailResponse,
    IoTSessionSummary,
    IoTSessionListResponse,
)

__all__ = [
    # Auth
    "RegisterRequest", "LoginRequest", "RefreshRequest", "TokenResponse", "AuthResponse",
    # User
    "UserPublic", "UserUpdateRequest", "DeleteAccountRequest",
    "UserDetailAdmin", "UserAdminUpdateRequest", "UserListResponse",
    # Chat
    "SessionCreateRequest", "SessionRenameRequest", "SessionSummary",
    "SessionListResponse", "MessageOut", "SessionDetailResponse",
    "SendMessageRequest", "SendMessageResponse",
    # Media
    "ImageGenerateRequest", "ImageGenerateResponse",
    "VideoGenerateRequest", "VideoGenerateResponse",
    "JobStatusResponse", "MediaOut", "MediaListResponse",
    # IoT
    "IoTSessionCreateRequest", "IoTSessionResponse", "IoTVoiceResponse",
    "IoTMessageOut", "IoTSessionDetailResponse", "IoTSessionSummary", "IoTSessionListResponse",
]
