from src.core.config import settings
from src.core.security import (
    TokenType,
    create_access_token,
    create_email_verification_token,
    create_password_reset_token,
    create_refresh_token,
    decode_token,
    decode_token_of_type,
    hash_password,
    verify_password,
)


def test_hash_and_verify_password_roundtrip():
    hashed = hash_password("s3cret-pass")
    assert hashed != "s3cret-pass"
    assert verify_password("s3cret-pass", hashed) is True
    assert verify_password("wrong", hashed) is False


def test_access_token_decodes_with_correct_type():
    token = create_access_token("42")
    claims = decode_token_of_type(token, TokenType.ACCESS)
    assert claims is not None
    assert claims["sub"] == "42"
    assert claims["type"] == "access"


def test_refresh_token_returns_distinct_jti():
    token, jti = create_refresh_token("7")
    assert len(jti) == 32
    claims = decode_token_of_type(token, TokenType.REFRESH)
    assert claims is not None
    assert claims["sub"] == "7"
    assert claims["jti"] == jti


def test_token_type_discrimination_rejects_wrong_type():
    access = create_access_token("1")
    refresh, _ = create_refresh_token("1")
    assert decode_token_of_type(access, TokenType.REFRESH) is None
    assert decode_token_of_type(refresh, TokenType.ACCESS) is None


def test_verification_and_reset_tokens_have_distinct_types():
    verify = create_email_verification_token("9")
    reset = create_password_reset_token("9")
    assert decode_token_of_type(verify, TokenType.EMAIL_VERIFICATION) is not None
    assert decode_token_of_type(reset, TokenType.PASSWORD_RESET) is not None
    assert decode_token_of_type(verify, TokenType.PASSWORD_RESET) is None


def test_invalid_token_returns_none():
    assert decode_token("not-a-token") is None
    assert decode_token_of_type("not-a-token", TokenType.ACCESS) is None


def test_tampered_token_rejected():
    token = create_access_token("1")
    tampered = token[:-4] + "AAAA"
    assert decode_token(tampered) is None


def test_expired_access_token_rejected(monkeypatch):
    token = create_access_token("1")
    claims = decode_token(token)
    assert claims is not None
    monkeypatch.setattr(settings, "access_token_expire_min", -10)
    expired = create_access_token("1")
    assert decode_token_of_type(expired, TokenType.ACCESS) is None
