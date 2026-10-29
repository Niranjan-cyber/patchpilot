"""Content-addressed artifact store: the key is the evidence ID (contracts §2)."""
import hashlib

from backend.config import ROOT

STORE = ROOT / "data" / "artifacts"


def put(data: bytes | str) -> str:
    b = data.encode("utf-8", "replace") if isinstance(data, str) else data
    h = hashlib.sha256(b).hexdigest()
    p = STORE / h[:2] / h
    if not p.exists():
        p.parent.mkdir(parents=True, exist_ok=True); p.write_bytes(b)
    return f"sha256:{h}"


def get(evidence_id: str) -> bytes | None:
    h = evidence_id.removeprefix("sha256:")
    if len(h) != 64 or not all(ch in "0123456789abcdef" for ch in h):
        return None
    p = STORE / h[:2] / h
    return p.read_bytes() if p.exists() else None
