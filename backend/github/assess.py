"""#48 intake assessment: what kind of issue this is and whether PatchPilot may act on it. Code decides, never a model.

Pure functions over what `reader.check_issue` already fetched (labels, title, body, root file names, G0 checks).
The result is the `IssueAssessment` shape proposed in docs/handoff/48-contract-proposal.md; it is a plain dict until
that contract change is agreed (shortcut: move to a pydantic model in backend/contracts once v0.4 lands).
"""
import re

from backend.contracts.models import CheckStatus
from backend.github.explore import ERROR, STEPS
from backend.github.reader import expected_actual

SCHEMA_VERSION = 1
FIXABLE = {"bug", "regression"}
# label (lowercased, "type:"/"kind:" style prefixes stripped) -> issue_type
LABELS = {
    "bug": "bug", "bug report": "bug", "defect": "bug", "crash": "bug", "confirmed bug": "bug",
    "regression": "regression",
    "feature": "feature", "feature request": "feature", "new feature": "feature",
    "enhancement": "enhancement", "improvement": "enhancement",
    "documentation": "docs", "docs": "docs", "doc": "docs",
    "refactor": "refactor", "refactoring": "refactor", "cleanup": "refactor", "tech debt": "refactor",
    "maintenance": "maintenance", "chore": "maintenance", "dependencies": "maintenance",
    "ci": "build_ci", "build": "build_ci", "infrastructure": "build_ci", "packaging": "build_ci",
    "tests": "test_failure", "flaky test": "test_failure", "test failure": "test_failure",
    "question": "question", "support": "question", "discussion": "question",
}
PREFIX = re.compile(r"^(?:type|kind|t|category|issue)\s*[:/\-]\s*", re.I)
TITLE_TAG = re.compile(r"^\W*(bug|regression|feature(?: request)?|enhancement|docs?|documentation|question|refactor)\b", re.I)
REGRESSION = re.compile(r"\b(?:regression|used to work|worked (?:in|before|with)|no longer works?|since (?:version|v?\d+\.\d+)|"
                        r"after (?:upgrading|updating) to)\b", re.I)
NOT_BUG_KIND = [(re.compile(r"\b(?:document(?:ation)?|docs?|typo|docstring|readme)\b", re.I), "docs"),
                (re.compile(r"\b(?:feature request|add support|would be nice|proposal|rfc|it would be (?:great|nice))\b", re.I), "feature"),
                (re.compile(r"\b(?:question|how (?:do|can|to) i|discussion)\b", re.I), "question"),
                (re.compile(r"\b(?:refactor\w*|clean ?up)\b", re.I), "refactor")]
SHOULD = re.compile(r"\b(?:should|expected|expect(?:ing)?|supposed to|instead of)\b", re.I)
LOCKS = [("poetry.lock", "poetry"), ("uv.lock", "uv"), ("pdm.lock", "pdm"), ("setup.py", "setuptools"),
         ("setup.cfg", "setuptools"), ("requirements.txt", "pip")]


def _label_type(labels: list[str]) -> str | None:
    """None = no label says; "unknown" = labels disagree (e.g. bug + enhancement)."""
    kinds = {LABELS[k] for l in labels if (k := PREFIX.sub("", l.strip().lower())) in LABELS}
    if kinds == {"bug", "regression"}:
        return "regression"
    return kinds.pop() if len(kinds) == 1 else ("unknown" if kinds else None)


def _text_type(title: str, body: str) -> str | None:
    if m := TITLE_TAG.match(title):
        t = m.group(1).lower()
        return {"feature request": "feature", "doc": "docs", "documentation": "docs"}.get(t, t)
    text = f"{title}\n{body}"
    has_error = bool(ERROR.search(text))
    if REGRESSION.search(text):
        return "regression"
    for rx, kind in NOT_BUG_KIND:   # a title that says "docs"/"feature" wins; in the body only when no error is shown
        if rx.search(title) or (rx.search(body) and not has_error):
            return kind
    return "bug" if has_error else None


def classify(title: str, body: str, labels: list[str]) -> tuple[str, str]:
    """(issue_type, source). Labels first, then text. Disagreement or no signal -> ("unknown", ...)."""
    by_label, by_text = _label_type(labels), _text_type(title, body or "")
    if by_label == "unknown":
        return "unknown", "label"
    if by_label and by_text and (by_label in FIXABLE) != (by_text in FIXABLE):
        return "unknown", "label"      # e.g. "bug" label on an issue whose text is a feature request
    if by_label:
        return by_label, "label"
    if by_text:
        return by_text, "text"
    return "unknown", "none"


def missing_information(body: str) -> list[str]:
    """What a fix needs but the issue doesn't say. Codes, worded by the UI."""
    body = body or ""
    exp, act = expected_actual(body)
    out = []
    if not exp and not SHOULD.search(body):
        out.append("no_expected")
    if not act and not ERROR.search(body):
        out.append("no_actual")
    if not STEPS.search(body) and "```" not in body and not re.search(r"(?m)^ {4}\S", body) and not ERROR.search(body):
        out.append("no_repro")
    return out


def environment(names: list[str]) -> tuple[str, str]:
    """(build_system, test_framework) from the repo's root file names."""
    low = {n.lower() for n in names}
    build = next((b for f, b in LOCKS if f in low), "pip" if "pyproject.toml" in low else "unknown")
    tests = "pytest" if low & {"pytest.ini", "conftest.py", "tox.ini", "noxfile.py"} else "unknown"
    return build, tests


def decide_handling(*, unsupported: str | None, python: CheckStatus, issue_type: str, missing: list[str],
                    warnings: list[str]) -> tuple[str, list[str]]:
    """(handling_decision, every reason that fired). First match wins for the label; reasons list them all.
    Unknown is never READY (#48 §3.3)."""
    reasons: list[str] = []
    if unsupported:
        reasons.append(f"unsupported:{unsupported}")
    if issue_type not in FIXABLE and issue_type != "unknown":
        reasons.append(f"not_a_bug:{issue_type}")
    if issue_type == "unknown":
        reasons.append("unclear_type")
    if python == CheckStatus.INCONCLUSIVE:
        reasons.append("compatibility_unknown")
    if issue_type in FIXABLE and {"no_expected", "no_actual"} <= set(missing) and "no_repro" in missing:
        reasons.append("needs_info")
    reasons += [w for w in ("linked_pr", "closed") if w in warnings]
    order = [("unsupported:", "UNSUPPORTED"), ("not_a_bug:", "ASSESSMENT_ONLY"), ("unclear_type", "HUMAN_DECISION"),
             ("compatibility_unknown", "HUMAN_DECISION"), ("needs_info", "NEEDS_INFORMATION"),
             ("linked_pr", "ALREADY_ADDRESSED"), ("closed", "ALREADY_ADDRESSED")]
    for prefix, decision in order:
        if any(r.startswith(prefix) for r in reasons):
            return decision, reasons
    return "READY", reasons


MISSING_ASK = {
    "no_expected": "What should happen instead? (the expected result or behaviour)",
    "no_actual": "What happens now? (the actual output, error message or traceback)",
    "no_repro": "A minimal code snippet or steps that show the problem, with the package version",
}


def draft_comment(missing: list[str]) -> str | None:
    """A comment the contributor may post on the issue themselves. PatchPilot never posts it (#48 §3.5)."""
    asks = [MISSING_ASK[m] for m in missing if m in MISSING_ASK]
    if not asks:
        return None
    return ("Hi! I'd like to work on a fix for this. To write a test that reproduces it, could you add:\n\n"
            + "\n".join(f"- {a}" for a in asks) + "\n\nThanks!")


def assess(*, title: str, body: str, labels: list[str], names: list[str], state: str, checks: dict[str, CheckStatus],
           unsupported: str | None, warnings: list[str], linked: list[int] | None) -> dict:
    issue_type, source = classify(title, body, labels)
    missing = missing_information(body) if issue_type in FIXABLE else []
    build, tests = environment(names)
    python = checks.get("python", CheckStatus.INCONCLUSIVE)
    decision, reasons = decide_handling(unsupported=unsupported, python=python, issue_type=issue_type,
                                        missing=missing, warnings=warnings)
    return {
        "schema_version": SCHEMA_VERSION, "issue_type": issue_type, "issue_type_source": source,
        "issue_status": "closed" if state == "closed" else "open",
        "problem_summary": None, "acceptance_conditions": [], "missing_information": missing,
        "reproduction_information": None, "existing_resolution": linked,
        "build_system": build, "test_framework": tests, "environment_requirements": [],
        "compatibility_status": ("unsupported" if unsupported else "unknown" if python == CheckStatus.INCONCLUSIVE else "supported"),
        "handling_decision": decision, "decision_reasons": reasons,
        "draft_comment": draft_comment(missing) if decision == "NEEDS_INFORMATION" else None,
    }
