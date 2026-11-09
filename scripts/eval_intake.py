"""#70 item 11, intake slice: run PatchPilot's intake (G0 checks + assessment + suitability) on real issues and compare the
proceed/stop decision with C's labels in eval/intake_cases.json. Read-only: GitHub reads and one model extraction per
issue; no repository code runs, nothing is posted. Writes eval/intake_results.json.

    python scripts/eval_intake.py            # all cases
    python scripts/eval_intake.py --no-model # keyword-only intake (no tokens; the model fields stay empty)
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.github.reader import GitHubError, check_issue  # noqa: E402

PROCEED = {"READY"}   # everything else stops or asks a human first


def grade(expected: list[str], got: str | None) -> dict:
    """exact: the decision is one C accepted. direction: proceed vs. stop/ask agrees, the decision that matters most."""
    if got is None:
        return {"exact": False, "direction": False}
    return {"exact": got in expected, "direction": (got in PROCEED) == any(e in PROCEED for e in expected)}


def main() -> None:
    model = "--no-model" not in sys.argv
    cases = json.loads((ROOT / "eval" / "intake_cases.json").read_text(encoding="utf-8"))["cases"]
    out = []
    for c in cases:
        row = {"id": c["id"], "kind": c["kind"], "expected": c["expected"]}
        try:
            chk = check_issue(c["url"], extract_model=model)
            a = chk.assessment
            row.update(decision=a.handling_decision if a else None, reasons=a.decision_reasons if a else [],
                       issue_type=a.issue_type if a else None, warnings=chk.warnings, unsupported=chk.unsupported,
                       suitability={d["dimension"]: d["outcome"] for d in (getattr(chk, "suitability", None) or [])} or None)
        except GitHubError as e:
            row.update(decision=None, error=f"{e.code}: {e}")
        except Exception as e:   # one bad case never stops the eval; it counts as wrong
            row.update(decision=None, error=type(e).__name__)
        row.update(grade(c["expected"], row.get("decision")))
        out.append(row)
        print(f"{'ok ' if row['exact'] else 'DIR' if row['direction'] else 'XX '} {c['id']:<16} {str(row.get('decision')):<18} "
              f"expected {'/'.join(c['expected'])}  {', '.join(row.get('reasons') or []) or row.get('error', '')}")
    n = len(out)
    summary = {"cases": n, "exact": sum(r["exact"] for r in out), "direction": sum(r["direction"] for r in out),
               "model": model, "ran_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    (ROOT / "eval" / "intake_results.json").write_text(json.dumps({"summary": summary, "results": out}, indent=1), encoding="utf-8")
    print(f"\nexact {summary['exact']}/{n} · proceed-vs-stop {summary['direction']}/{n} · model {'on' if model else 'off'}")


if __name__ == "__main__":
    main()
