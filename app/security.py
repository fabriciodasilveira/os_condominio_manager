import base64
import hashlib
import hmac
import os
from datetime import datetime, timedelta

import bcrypt
from jose import JWTError, jwt

from app.config import settings

PBKDF2_PREFIX = "pbkdf2_sha256"
PBKDF2_ROUNDS = 390_000


def _pbkdf2_hash(password: str, rounds: int = PBKDF2_ROUNDS) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, rounds)
    salt_b64 = base64.urlsafe_b64encode(salt).decode("ascii")
    digest_b64 = base64.urlsafe_b64encode(digest).decode("ascii")
    return f"{PBKDF2_PREFIX}${rounds}${salt_b64}${digest_b64}"


def _pbkdf2_verify(password: str, hashed_password: str) -> bool:
    try:
        _, rounds_str, salt_b64, digest_b64 = hashed_password.split("$", 3)
        rounds = int(rounds_str)
        salt = base64.urlsafe_b64decode(salt_b64.encode("ascii"))
        digest = base64.urlsafe_b64decode(digest_b64.encode("ascii"))
    except Exception:
        return False

    candidate = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, rounds)
    return hmac.compare_digest(candidate, digest)


def _bcrypt_verify_compat(password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed_password.encode("utf-8"))
    except ValueError:
        # Compatibilidade com truncamento histórico de 72 bytes do bcrypt.
        return bcrypt.checkpw(password.encode("utf-8")[:72], hashed_password.encode("utf-8"))
    except Exception:
        return False


def verify_password(plain_password: str, hashed_password: str) -> bool:
    if hashed_password.startswith(f"{PBKDF2_PREFIX}$"):
        return _pbkdf2_verify(plain_password, hashed_password)
    if hashed_password.startswith("$2"):
        return _bcrypt_verify_compat(plain_password, hashed_password)
    return False


def get_password_hash(password: str) -> str:
    return _pbkdf2_hash(password)


def create_access_token(subject: str, expires_delta: timedelta | None = None) -> str:
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=settings.access_token_expire_minutes))
    payload = {"sub": subject, "exp": expire}
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def decode_token(token: str) -> str | None:
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        return payload.get("sub")
    except JWTError:
        return None
