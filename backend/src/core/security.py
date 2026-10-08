import enum
import secrets
from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt
from passlib.context import CryptContext

from src.core.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class TokenType(str, enum.Enum):
    ACCESS = "access"
    REFRESH = "refresh"
    EMAIL_VERIFICATION = "email_verification"
    PASSWORD_RESET = "password_reset"


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _encode(payload: dict) -> str:
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict | None:
    """Decode a JWT and return its claims, or ``None`` if invalid/expired."""
    try:
        return jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm])
    except JWTError:
        return None


def decode_token_of_type(token: str, expected: TokenType) -> dict | None:
    """Decode a token and enforce its ``type`` claim matches ``expected``."""
    claims = decode_token(token)
    if claims is None or claims.get("type") != expected.value:
        return None
    return claims


def create_access_token(subject: str) -> str:
    exp = _now() + timedelta(minutes=settings.access_token_expire_min)
    return _encode(
        {
            "sub": subject,
            "type": TokenType.ACCESS.value,
            "iat": _now(),
            "exp": exp,
        }
    )


def create_refresh_token(subject: str) -> tuple[str, str]:
    """Return ``(token, jti)`` for a refresh token; ``jti`` is persisted for rotation."""
    jti = secrets.token_hex(16)
    exp = _now() + timedelta(days=settings.refresh_token_expire_days)
    token = _encode(
        {
            "sub": subject,
            "type": TokenType.REFRESH.value,
            "iat": _now(),
            "exp": exp,
            "jti": jti,
        }
    )
    return token, jti


def create_email_verification_token(subject: str) -> str:
    exp = _now() + timedelta(hours=settings.email_verification_expire_hours)
    return _encode(
        {
            "sub": subject,
            "type": TokenType.EMAIL_VERIFICATION.value,
            "iat": _now(),
            "exp": exp,
        }
    )


def create_password_reset_token(subject: str) -> str:
    exp = _now() + timedelta(hours=settings.password_reset_expire_hours)
    return _encode(
        {
            "sub": subject,
            "type": TokenType.PASSWORD_RESET.value,
            "iat": _now(),
            "exp": exp,
        }
    )
