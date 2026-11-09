"""#70 item 11, intake slice: run PatchPilot's intake (G0 checks + assessment + suitability) on real issues and compare the
proceed/stop decision with C's labels in eval/intake_cases.json. No repository code runs and nothing is posted, but it
does call GitHub and the assessor model (tokens count toward today's caps; extractions are cached per issue version).

    python scripts/eval_intake.py            # all cases -> eval/intake_results.json
    python scripts/eval_intake.py --no-model # keyword-only intake, no tokens -> eval/intake_results_no_model.json

Unknown is never scored: a case whose lookup failed, or where the model didn't answer, is graded null and counted apart.
"""
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.github.reader import GitHubError, check_issue  # noqa: E402

PROCEED = {"READY"}   # everything else stops or asks a human first
# shortcut: no case expects READY (an open, unclaimed, clear bug doesn't stay that way), so "direction" can't yet catch an
# intake that stops too often; add one when a stable proceed case exists
LIMITATION = "No case expects READY yet, so this can't catch an intake that stops too often."


def grade(expected: list[str], got: str | None) -> dict:
    """exact: the decision is one C accepted. direction: proceed vs. stop/ask agrees. No decision = unknown (null), never wrong."""
    if got is None:
        return {"exact": None, "direction": None}
    return {"exact": got in expected, "direction": (got in PROCEED) == any(e in PROCEED for e in expected)}


def main() -> None:
    model = "--no-model" not in sys.argv
    if not os.getenv("GITHUB_READ_TOKEN"):   # unauthenticated GitHub allows 60 requests/h: about 5 cases, then all errors
        sys.exit("Set GITHUB_READ_TOKEN first (unauthenticated GitHub rate-limits after a few cases).")
    cases = json.loads((ROOT / "eval" / "intake_cases.json").read_text(encoding="utf-8"))["cases"]
    out, stop = [], None
    for c in cases:
        row = {"id": c["id"], "kind": c["kind"], "expected": c["expected"]}
        if stop:
            row.update(decision=None, error=f"not run: {stop}")
        else:
            try:
                chk = check_issue(c["url"], extract_model=model)
                a = chk.assessment
                row.update(decision=a.handling_decision if a else None, reasons=a.decision_reasons if a else [],
                           issue_type=a.issue_type if a else None, warnings=chk.warnings, unsupported=chk.unsupported,
                           suitability={d["dimension"]: d["outcome"] for d in (chk.suitability or [])} or None)
                if model and a and "model_unavailable" in a.decision_reasons:   # a fallback answer isn't the intake's answer
                    row.update(model_answered=False, scored_decision=None)
            except GitHubError as e:
                row.update(decision=None, error=f"{e.code}: {e}")
                if "rate-limit" in str(e):   # the rest would only be errors: stop instead of overwriting results with them
                    stop = "GitHub rate limit reached"
            except Exception as e:   # one bad case never stops the eval; it's unknown, not wrong
                row.update(decision=None, error=f"{type(e).__name__}: {e}"[:300])
        row.update(grade(c["expected"], row["scored_decision"] if "scored_decision" in row else row.get("decision")))
        out.append(row)
        mark = "?? " if row["exact"] is None else "ok " if row["exact"] else "DIR" if row["direction"] else "XX "
        print(f"{mark} {c['id']:<16} {str(row.get('decision')):<18} expected {'/'.join(c['expected'])}  "
              f"{', '.join(row.get('reasons') or []) or row.get('error', '')}")
    graded = [r for r in out if r["exact"] is not None]
    summary = {"cases": len(out), "graded": len(graded), "exact": sum(r["exact"] for r in graded),
               "direction": sum(r["direction"] for r in graded), "errors": sum(1 for r in out if r.get("error")),
               "model_unanswered": sum(1 for r in out if r.get("model_answered") is False), "model": model,
               "limitation": LIMITATION, "ran_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    name = "intake_results.json" if model else "intake_results_no_model.json"   # keyword-only runs never replace model runs
    (ROOT / "eval" / name).write_text(json.dumps({"summary": summary, "results": out}, indent=1), encoding="utf-8")
    g = summary["graded"]
    print(f"\nexact {summary['exact']}/{g} · proceed-vs-stop {summary['direction']}/{g} · graded {g} of {len(out)} "
          f"({summary['errors']} errors, {summary['model_unanswered']} without a model answer) · model {'on' if model else 'off'}\n"
          f"{LIMITATION}")


if __name__ == "__main__":
    main()
