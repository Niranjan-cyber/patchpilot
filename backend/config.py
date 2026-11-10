import tomllib
import os
from functools import cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


@cache
def limits() -> dict:
    return tomllib.loads((ROOT / "config" / "limits.toml").read_text(encoding="utf-8"))


PUBLISH_LIMITED = ("Publishing from this demo is limited to the demo repository. Everything up to approval works on any repo, "
                   "and you can download the diff and report.")


def may_publish(login: str | None, repo: str) -> bool:
    """#100 (human decision 2026-11-10): a team login publishes anywhere; anyone else only to the demo repos. GitHub logins
    and repo names are case-insensitive. A missing list means nobody (fails closed)."""
    lim = limits()
    team = {x.casefold() for x in lim.get("publish_open_logins", [])}
    return repo.casefold() in {x.casefold() for x in lim.get("publish_allowed_repos", [])} or bool(login and login.casefold() in team)


def llm_budget_set() -> bool:
    return limits()["global_llm_tokens_per_day"] > 0


def load_env(path=ROOT / ".env") -> None:
    """Minimal KEY=VALUE loader (no dependency). Real environment variables win."""
    import os
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            k, sep, v = line.partition("=")
            if sep and k.strip() and not k.lstrip().startswith("#"):
                v = v.split(" #", 1)[0].strip().strip('"')
                if v:
                    os.environ.setdefault(k.strip(), v)


load_env()
if os.getenv("GOOGLE_API_KEY") and not os.getenv("GEMINI_API_KEY"):   # LiteLLM reads GEMINI_API_KEY
    os.environ["GEMINI_API_KEY"] = os.environ["GOOGLE_API_KEY"]
