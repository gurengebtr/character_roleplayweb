import hashlib
import hmac
import secrets

from fastapi import Header, HTTPException

from .config import settings


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.scrypt(password.encode(), salt=salt.encode(), n=16384, r=8, p=1).hex()
    return f"scrypt${salt}${digest}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, salt, expected = stored.split("$")
        actual = hashlib.scrypt(password.encode(), salt=salt.encode(), n=16384, r=8, p=1).hex()
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


async def service_auth(authorization: str = Header(default="")):
    if not settings.service_token or not hmac.compare_digest(
        authorization, "Bearer " + settings.service_token
    ):
        raise HTTPException(401, "Service authentication required")


async def user_auth(authorization: str = Header(default=""), x_user_id: str = Header(default="")) -> str:
    await service_auth(authorization)
    if not x_user_id or len(x_user_id) > 100:
        raise HTTPException(401, "User session required")
    return x_user_id
