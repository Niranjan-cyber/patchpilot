import tomllib
import os
from functools import cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


@cache
def limits() -> dict:
    return tomllib.loads((ROOT / "config" / "limits.toml").read_text())


def llm_budget_set() -> bool:
    return limits()["global_llm_tokens_per_day"] > 0


def load_env(path=ROOT / ".env") -> None:
    """Minimal KEY=VALUE loader (no dependency). Real environment variables win."""
    import os
    if path.exists():
        for line in path.read_text().splitlines():
            k, sep, v = line.partition("=")
            if sep and k.strip() and not k.lstrip().startswith("#"):
                v = v.split(" #", 1)[0].strip().strip('"')
                if v:
                    os.environ.setdefault(k.strip(), v)


load_env()
if os.getenv("GOOGLE_API_KEY") and not os.getenv("GEMINI_API_KEY"):   # LiteLLM reads GEMINI_API_KEY
    os.environ["GEMINI_API_KEY"] = os.environ["GOOGLE_API_KEY"]
