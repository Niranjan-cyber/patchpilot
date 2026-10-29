import tomllib
from functools import cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


@cache
def limits() -> dict:
    return tomllib.loads((ROOT / "config" / "limits.toml").read_text())


def llm_budget_set() -> bool:
    return limits()["global_llm_tokens_per_day"] > 0
