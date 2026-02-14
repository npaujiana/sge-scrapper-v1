"""TikTok authentication API routes."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from services.tiktok_auth_service import TikTokAuthService


router = APIRouter(prefix="/tiktok", tags=["tiktok"])


class LoginResponse(BaseModel):
    success: bool
    message: str


class SessionStatus(BaseModel):
    has_session: bool
    expires_at: str | None
    storage_state_exists: bool


@router.get("/session", response_model=SessionStatus)
async def get_tiktok_session():
    """Get TikTok session status."""
    auth_service = TikTokAuthService()
    return auth_service.get_status()


@router.post("/login", response_model=LoginResponse)
async def login_tiktok():
    """
    Start TikTok manual login.
    Opens a browser window for user to login manually.
    """
    auth_service = TikTokAuthService()

    # Check if already has session
    has_session, _ = auth_service.has_valid_session()
    if has_session:
        return LoginResponse(
            success=True,
            message="Already logged in to TikTok. Use /logout to clear session first."
        )

    # Start manual login (blocking - opens browser)
    success, message = auth_service.login_manual()

    return LoginResponse(success=success, message=message)


@router.post("/logout", response_model=LoginResponse)
async def logout_tiktok():
    """Clear TikTok session."""
    auth_service = TikTokAuthService()
    auth_service.clear_session()

    return LoginResponse(success=True, message="TikTok session cleared.")
