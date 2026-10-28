"""认证：bcrypt 密码哈希 + JWT 签发/校验"""
import datetime as dt
from typing import Optional

import bcrypt
import jwt

from .config import settings

TOKEN_TTL = dt.timedelta(days=7)
ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


def create_token(user_id: int, is_admin: bool) -> str:
    payload = {
        "sub": str(user_id),
        "admin": is_admin,
        "exp": dt.datetime.now(dt.timezone.utc) + TOKEN_TTL,
    }
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def decode_token(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        return None
