from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from src.auth.schemas import (
    ChangePasswordRequest,
    ForgotPasswordRequest,
    GoogleRequest,
    LoginRequest,
    LogoutRequest,
    MessageResponse,
    RefreshRequest,
    ResetPasswordRequest,
    SignupRequest,
    TokenResponse,
    VerifyEmailRequest,
)
from src.auth.service import AuthService
from src.core.database import get_db
from src.core.dependencies import get_current_user
from src.core.rate_limit import rate_limit
from src.users.models import User

router = APIRouter()


@router.post("/signup", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def signup(
    payload: SignupRequest,
    db: Session = Depends(get_db),
    _rl: None = Depends(rate_limit("auth_signup", limit_setting="rate_limit_auth_per_minute")),
) -> TokenResponse:
    return AuthService(db).signup(payload)


@router.post("/login", response_model=TokenResponse)
def login(
    payload: LoginRequest,
    db: Session = Depends(get_db),
    _rl: None = Depends(rate_limit("auth_login", limit_setting="rate_limit_auth_per_minute")),
) -> TokenResponse:
    return AuthService(db).login(payload)


@router.post("/refresh", response_model=TokenResponse)
def refresh(payload: RefreshRequest, db: Session = Depends(get_db)) -> TokenResponse:
    return AuthService(db).refresh(payload.refresh_token)


@router.post("/logout", response_model=MessageResponse)
def logout(payload: LogoutRequest, db: Session = Depends(get_db)) -> MessageResponse:
    AuthService(db).logout(payload.refresh_token)
    return MessageResponse(message="Logged out")


@router.post("/verify-email", response_model=MessageResponse)
def verify_email(payload: VerifyEmailRequest, db: Session = Depends(get_db)) -> MessageResponse:
    AuthService(db).verify_email(payload.token)
    return MessageResponse(message="Email verified")


@router.post("/forgot-password", response_model=MessageResponse)
def forgot_password(
    payload: ForgotPasswordRequest,
    db: Session = Depends(get_db),
    _rl: None = Depends(
        rate_limit("auth_forgot_password", limit_setting="rate_limit_auth_per_minute")
    ),
) -> MessageResponse:
    AuthService(db).forgot_password(payload.email)
    return MessageResponse(message="If the account exists, a reset email has been sent")


@router.post("/reset-password", response_model=MessageResponse)
def reset_password(payload: ResetPasswordRequest, db: Session = Depends(get_db)) -> MessageResponse:
    AuthService(db).reset_password(payload.token, payload.new_password)
    return MessageResponse(message="Password reset")


@router.post("/change-password", response_model=MessageResponse)
def change_password(
    payload: ChangePasswordRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> MessageResponse:
    AuthService(db).change_password(
        current_user,
        current_password=payload.current_password,
        new_password=payload.new_password,
    )
    return MessageResponse(message="Password changed")


@router.post("/google", response_model=TokenResponse)
def google(payload: GoogleRequest, db: Session = Depends(get_db)) -> TokenResponse:
    return AuthService(db).google_sign_in(payload.id_token)
