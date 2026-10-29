"""Browser identity (contracts §6): an unguessable pp_sid cookie; only its sha256 is stored. Never logged."""
import hashlib
import secrets

from fastapi import Request, Response

from backend import db

COOKIE, MAX_AGE = "pp_sid", 30 * 24 * 3600


def _h(v: str) -> str:
    return hashlib.sha256(v.encode()).hexdigest()


def current(request: Request) -> str | None:
    """Session hash for an existing, non-revoked cookie; None if absent."""
    tok = request.cookies.get(COOKIE)
    if not tok:
        return None
    h = _h(tok); c = db.connect()
    row = c.execute("SELECT revoked_at FROM sessions WHERE id_hash=?", (h,)).fetchone()
    if not row or row[0]:
        return None
    c.execute("UPDATE sessions SET last_seen_at=? WHERE id_hash=?", (db.now().isoformat(), h))
    return h


def ensure(request: Request, response: Response) -> str:
    """Existing session hash, or create one and set the cookie."""
    if (h := current(request)):
        return h
    tok = secrets.token_urlsafe(32)   # 256 bits
    h, t = _h(tok), db.now().isoformat()
    ip = _h(f"ip:{request.client.host if request.client else ''}")
    c = db.connect()
    with db.tx(c):
        c.execute("INSERT INTO sessions VALUES(?,?,?,?,NULL)", (h, ip, t, t))
    response.set_cookie(COOKIE, tok, max_age=MAX_AGE, httponly=True, secure=True, samesite="lax", path="/")
    return h
