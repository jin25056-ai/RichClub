import hashlib
import hmac
from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def _pre_hash(plain: str) -> str:
    """bcrypt 72바이트 제한 우회: sha256 hex digest로 변환 후 bcrypt 적용"""
    return hmac.new(
        settings.jwt_secret_key.encode(),
        plain.encode(),
        hashlib.sha256,
    ).hexdigest()


def hash_password(plain: str) -> str:
    return pwd_context.hash(_pre_hash(plain))


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(_pre_hash(plain), hashed)


def create_access_token(subject: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.jwt_access_token_expire_minutes
    )
    payload = {"sub": subject, "exp": expire, "type": "access"}
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def create_refresh_token(subject: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=14)
    payload = {"sub": subject, "exp": expire, "type": "refresh"}
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_token(token: str, token_type: str = "access") -> str:
    try:
        payload = jwt.decode(
            token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm]
        )
        if payload.get("type") != token_type:
            raise ValueError("토큰 타입이 올바르지 않습니다.")
        sub: str = payload.get("sub", "")
        if not sub:
            raise ValueError("유효하지 않은 토큰입니다.")
        return sub
    except JWTError as e:
        raise ValueError("유효하지 않은 토큰입니다.") from e
