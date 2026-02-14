"""Authentication routes for SGE login."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List, Dict, Any

from services.auth_service import AuthService
from config.logging_config import get_logger

router = APIRouter(prefix="/api/auth", tags=["Authentication"])
logger = get_logger()


class RequestCodeRequest(BaseModel):
    """Request body for requesting login code."""
    email: EmailStr = Field(..., description="Email address for SGE login")


class VerifyCodeRequest(BaseModel):
    """Request body for verifying login code."""
    code: str = Field(..., min_length=1, max_length=10, description="Verification code from email")
    email: Optional[EmailStr] = Field(None, description="Email address (optional if continuing from request-code)")


class CookieItem(BaseModel):
    """Single cookie item."""
    name: str
    value: str
    domain: str
    path: str = "/"
    expires: Optional[float] = None
    httpOnly: Optional[bool] = False
    secure: Optional[bool] = False
    sameSite: Optional[str] = "Lax"


class ManualSessionRequest(BaseModel):
    """Request body for manual session input."""
    email: EmailStr = Field(..., description="Email yang digunakan untuk login")
    cookies: List[Dict[str, Any]] = Field(..., description="Cookies dari browser (copy dari DevTools)")

    class Config:
        json_schema_extra = {
            "example": {
                "email": "user@example.com",
                "cookies": [
                    {
                        "name": "session_token",
                        "value": "abc123...",
                        "domain": ".www.socialgrowthengineers.com",
                        "path": "/"
                    }
                ]
            }
        }


class TokenSessionRequest(BaseModel):
    """Request body for token-based session (localStorage)."""
    access_token: str = Field(..., description="JWT access token")
    refresh_token: str = Field(..., description="Refresh token")
    expires_at: int = Field(..., description="Token expiration timestamp")
    email: Optional[EmailStr] = Field(None, description="Email (optional, akan diambil dari token jika tidak diisi)")


class AuthStatusResponse(BaseModel):
    """Response for auth status check."""
    logged_in: bool = Field(..., description="Whether user is logged in")
    email: Optional[str] = Field(None, description="Logged in email if available")
    pending_login: bool = Field(False, description="Whether there's a pending login in progress")
    pending_email: Optional[str] = Field(None, description="Email for pending login")


class AuthResponse(BaseModel):
    """Generic auth operation response."""
    success: bool = Field(..., description="Whether operation was successful")
    message: str = Field(..., description="Status message")


@router.post(
    "/request-code",
    response_model=AuthResponse,
    summary="Request Login Code",
    description="Submit email to request a verification code for SGE login.",
)
async def request_login_code(request: RequestCodeRequest):
    """
    Request a login verification code.

    This will:
    1. Navigate to SGE login page
    2. Submit the email address
    3. Trigger verification code to be sent to email

    After this, use /verify-code endpoint with the code from email.
    """
    auth_service = AuthService()

    try:
        logger.info(f"Requesting login code for {request.email}")
        success, message = await auth_service.request_login_code(request.email)
        logger.info(f"Request login code result: success={success}, message={message}")
        return AuthResponse(success=success, message=message)
    except Exception as e:
        logger.error(f"Error in request_login_code: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/verify-code",
    response_model=AuthResponse,
    summary="Verify Login Code",
    description="Submit verification code to complete login.",
)
async def verify_login_code(request: VerifyCodeRequest):
    """
    Verify the login code and complete authentication.

    This will:
    1. Submit the verification code
    2. If successful, save the session for future scraping
    3. Return success status

    After successful verification, the session will be saved and used
    automatically for all scraping operations.
    """
    auth_service = AuthService()

    try:
        success, message = await auth_service.verify_login_code(request.code, request.email)
        return AuthResponse(success=success, message=message)
    except Exception as e:
        logger.error(f"Error in verify_login_code: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/status",
    response_model=AuthStatusResponse,
    summary="Get Auth Status",
    description="Check current authentication status.",
)
async def get_auth_status():
    """
    Get current authentication status.

    Returns whether there's a valid saved session and the associated email.
    """
    auth_service = AuthService()
    status = auth_service.get_login_status()
    return AuthStatusResponse(**status)


@router.post(
    "/set-token",
    response_model=AuthResponse,
    summary="Set Auth Token",
    description="Input auth token dari localStorage (sge-auth-token).",
)
async def set_auth_token(request: TokenSessionRequest):
    """
    Set session menggunakan token dari localStorage.

    Cara mendapatkan token:
    1. Login ke www.socialgrowthengineers.com di browser
    2. Buka DevTools (F12) -> Application -> Local Storage
    3. Cari key "sge-auth-token"
    4. Copy value-nya (JSON string)
    5. Parse JSON dan kirim access_token, refresh_token, expires_at
    """
    auth_service = AuthService()

    try:
        success = auth_service.save_token_session(
            access_token=request.access_token,
            refresh_token=request.refresh_token,
            expires_at=request.expires_at,
            email=request.email
        )
        if success:
            return AuthResponse(success=True, message="Token session saved successfully")
        else:
            return AuthResponse(success=False, message="Failed to save token session")
    except Exception as e:
        logger.error(f"Error saving token session: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/set-session",
    response_model=AuthResponse,
    summary="Set Session Manual (Cookies)",
    description="Input session/cookies secara manual setelah login di browser.",
)
async def set_manual_session(request: ManualSessionRequest):
    """
    Set session secara manual dengan cookies dari browser.

    Cara mendapatkan cookies:
    1. Login ke www.socialgrowthengineers.com di browser
    2. Buka DevTools (F12) -> Application -> Cookies
    3. Copy semua cookies untuk domain www.socialgrowthengineers.com
    4. Atau gunakan extension seperti "EditThisCookie" untuk export cookies sebagai JSON

    Format cookies minimal:
    ```json
    {
        "email": "your@email.com",
        "cookies": [
            {"name": "cookie_name", "value": "cookie_value", "domain": ".www.socialgrowthengineers.com"}
        ]
    }
    ```
    """
    auth_service = AuthService()

    try:
        success = auth_service.save_manual_session(request.email, request.cookies)
        if success:
            return AuthResponse(success=True, message=f"Session saved successfully for {request.email}")
        else:
            return AuthResponse(success=False, message="Failed to save session")
    except Exception as e:
        logger.error(f"Error saving manual session: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete(
    "/logout",
    response_model=AuthResponse,
    summary="Logout",
    description="Clear saved session and logout.",
)
async def logout():
    """
    Clear the saved session.

    This will remove the saved authentication session,
    requiring a new login for future scraping.
    """
    auth_service = AuthService()
    auth_service.clear_session()
    auth_service._clear_login_state()
    return AuthResponse(success=True, message="Logged out successfully. Session cleared.")
