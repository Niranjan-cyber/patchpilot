"""B14: compare PatchPilot outcomes with the official tests (pure; results come from scripts/eval.py)."""
from statistics import median

UNABLE = {"CANNOT_REPRODUCE", "ENV_FAILED", "BLOCKED"}


def verdict(c: dict) -> str:
    """official is "pass" | "fail" | anything else = unknown (never treated as a pass)."""
    if not c.get("outcome"):
        return "no_result"
    if c["outcome"] != "VERIFIED_FIX":
        return "no_claim"
    return {"pass": "confirmed", "fail": "false_verified"}.get(c.get("official"), "unconfirmed")


def summarize(results: dict) -> dict:
    rows = [{**c, "official": c.get("official") if c.get("official") in ("pass", "fail") else None, "verdict": verdict(c)}
            for c in results.get("cases", [])]
    rows.sort(key=lambda r: (r["verdict"] != "false_verified", r["verdict"] == "no_result"))   # false claims first, not-run last
    v = [r["verdict"] for r in rows]
    oc = [r.get("outcome") for r in rows]
    secs = [r["seconds"] for r in rows if isinstance(r.get("seconds"), (int, float))]
    counts = {"total": len(rows), "verified": oc.count("VERIFIED_FIX"), "confirmed": v.count("confirmed"),
              "false_verified": v.count("false_verified"), "unconfirmed": v.count("unconfirmed"),
              "needs_attention": oc.count("FIX_NEEDS_ATTENTION"), "triage": oc.count("TRIAGE_ONLY"),
              "unable": sum(o in UNABLE for o in oc), "no_result": v.count("no_result"),
              "median_seconds": median(secs) if secs else None}
    state = ("failed" if counts["no_result"] == len(rows)
             else "partial" if counts["no_result"] or counts["unconfirmed"] else "success")
    return {"generated_at": results.get("generated_at"), "commit": results.get("commit"),
            "state": state, "counts": counts, "rows": rows}


def parse_ra(out: str) -> dict[str, str]:
    """`pytest -rA` summary lines -> {test id: PASSED|FAILED|ERROR|...} (the way SWE-bench grades)."""
    st = {}
    for line in out.splitlines():
        word, _, rest = line.partition(" ")
        if word in ("PASSED", "FAILED", "ERROR", "XFAIL", "XPASS", "SKIPPED") and rest:
            st[rest.split(" - ")[0].strip()] = word
    return st


def case_gradable(fail_to_pass: list[str], pass_to_pass: list[str], before: dict[str, str] | None,
                  after: dict[str, str] | None) -> tuple[bool, str]:
    """Can this SWE-bench case give an honest eval number in our sandbox? before = test patch only, after = + reference fix.
    A case whose reference fix doesn't pass here would grade a correct PatchPilot fix as false_verified."""
    if before is None or after is None:
        return False, "tests_not_run"
    if any(before.get(t) == "PASSED" for t in fail_to_pass) or not any(before.get(t) for t in fail_to_pass):
        return False, "fail_to_pass_not_failing_before"
    res = official_result(fail_to_pass, pass_to_pass, after)
    return (True, "ok") if res == "pass" else (False, "reference_fix_fails" if res == "fail" else "tests_missing_after")


def official_result(fail_to_pass: list[str], pass_to_pass: list[str], st: dict[str, str]) -> str | None:
    """pass only if every official test passed; any failure = fail; a test we never saw = unknown."""
    ids = fail_to_pass + pass_to_pass
    if any(st.get(t) in ("FAILED", "ERROR") for t in ids):
        return "fail"
    return "pass" if ids and all(st.get(t) == "PASSED" for t in ids) else None
