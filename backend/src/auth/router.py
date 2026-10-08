from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from src.auth import service
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
from src.core.database import get_db
from src.core.dependencies import get_current_user
from src.users.models import User

router = APIRouter()


@router.post("/signup", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def signup(payload: SignupRequest, db: Session = Depends(get_db)) -> TokenResponse:
    return service.signup(
        db,
        email=payload.email,
        password=payload.password,
        first_name=payload.first_name,
        last_name=payload.last_name,
        nick_name=payload.nick_name,
    )


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    return service.login(db, email=payload.email, password=payload.password)


@router.post("/refresh", response_model=TokenResponse)
def refresh(payload: RefreshRequest, db: Session = Depends(get_db)) -> TokenResponse:
    return service.refresh(db, refresh_token=payload.refresh_token)


@router.post("/logout", response_model=MessageResponse)
def logout(payload: LogoutRequest, db: Session = Depends(get_db)) -> MessageResponse:
    service.logout(db, refresh_token=payload.refresh_token)
    return MessageResponse(message="Logged out")


@router.post("/verify-email", response_model=MessageResponse)
def verify_email(payload: VerifyEmailRequest, db: Session = Depends(get_db)) -> MessageResponse:
    service.verify_email(db, token=payload.token)
    return MessageResponse(message="Email verified")


@router.post("/forgot-password", response_model=MessageResponse)
def forgot_password(
    payload: ForgotPasswordRequest, db: Session = Depends(get_db)
) -> MessageResponse:
    service.forgot_password(db, email=payload.email)
    return MessageResponse(message="If the account exists, a reset email has been sent")


@router.post("/reset-password", response_model=MessageResponse)
def reset_password(payload: ResetPasswordRequest, db: Session = Depends(get_db)) -> MessageResponse:
    service.reset_password(db, token=payload.token, new_password=payload.new_password)
    return MessageResponse(message="Password reset")


@router.post("/change-password", response_model=MessageResponse)
def change_password(
    payload: ChangePasswordRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> MessageResponse:
    service.change_password(
        db,
        user=current_user,
        current_password=payload.current_password,
        new_password=payload.new_password,
    )
    return MessageResponse(message="Password changed")


@router.post("/google", response_model=TokenResponse)
def google(payload: GoogleRequest, db: Session = Depends(get_db)) -> TokenResponse:
    return service.google(db, id_token=payload.id_token)
