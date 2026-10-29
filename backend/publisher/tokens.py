"""OAuth tokens at rest (Fernet). Encrypt anywhere; decrypt ONLY inside backend/publisher (contracts §6)."""
import os

from cryptography.fernet import Fernet, InvalidToken


def _f() -> Fernet | None:
    k = os.getenv("FERNET_KEY")
    return Fernet(k.encode()) if k else None


def configured() -> bool:
    return _f() is not None


def encrypt(token: str) -> str:
    f = _f()
    if not f:
        raise RuntimeError("FERNET_KEY is not set; publishing is disabled")
    return f.encrypt(token.encode()).decode()


def decrypt(token_enc: str) -> str | None:
    f = _f()
    try:
        return f.decrypt(token_enc.encode()).decode() if f else None
    except InvalidToken:
        return None
