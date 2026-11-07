"""#48 intake assessment: what kind of issue this is and whether PatchPilot may act on it. Code decides, never a model.

Pure functions over what `reader.check_issue` already fetched (labels, title, body, root file names, G0 checks).
Returns contracts v0.4 `IssueAssessment` (docs/handoff/48-contract-proposal.md).
"""
import re

from backend.contracts.models import CheckStatus, IssueAssessment
from backend.github.explore import ERROR, OTHER_OS, STEPS
from backend.github.reader import expected_actual

FIXABLE = {"bug", "regression"}
EXECUTES = {"READY", "NEEDS_INFORMATION", "HUMAN_DECISION", "ALREADY_ADDRESSED"}   # the rest end at G0, nothing runs
# overridable G0 warnings these decisions add (accepted through continue_despite, like assigned/linked_pr)
WARNS = {"unclear_type": "unclear_type", "model_unavailable": "unclear_type", "needs_info": "needs_info", "other_os": "other_os",
         "compatibility_unknown": "lookup_failed", "linked_pr_unknown": "lookup_failed", "test_framework_unknown": "lookup_failed",
         "base_sha_unknown": "base_unknown"}
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
# from #41's unclear_bug (A's phrase rule): the reporter isn't sure it's a bug -> never READY on the model's word alone
UNSURE = re.compile(r"\b(?:not sure (?:if|whether)|is this (?:expected|intended|intentional|a bug)|intentional\?|by design\?|"
                    r"feature request|am i (?:missing|doing) something)", re.I)
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


def keyword_type(title: str, body: str, labels: list[str]) -> tuple[str | None, str]:
    """Labels, then text: the cross-check for the model. (None, "none") = no signal; "unknown" = labels disagree."""
    by_label, by_text = _label_type(labels), _text_type(title, body or "")
    if by_label == "unknown" or (by_label and by_text and (by_label in FIXABLE) != (by_text in FIXABLE)):
        return "unknown", "label"      # e.g. "bug" label on an issue whose text is a feature request
    if by_label:
        return by_label, "label"
    return (by_text, "text") if by_text else (None, "none")


def classify(title: str, body: str, labels: list[str], model_type: str | None = None) -> tuple[str, str]:
    """(issue_type, source). The model's extraction is the classifier (DECISION 2026-11-07); labels/text cross-check it.
    A non-bug type (which hard-blocks at G0) needs the model AND labels/text to agree: neither the model alone nor
    keywords alone may set a gate (AGENTS.md; A's review of #50, bugs 2+3). One-sided -> "unknown" -> HUMAN_DECISION."""
    kw, src = keyword_type(title, body, labels)
    if not model_type or model_type == "unknown":
        return "unknown", "model" if model_type == "unknown" else "none"
    if kw == "unknown" or (kw and (kw in FIXABLE) != (model_type in FIXABLE)):
        return "unknown", "model"      # model and labels/text disagree on bug vs not-bug: the human decides
    if model_type in FIXABLE:
        if UNSURE.search(f"{title}\n{body}"):
            return "unknown", "model"  # the reporter asks whether it's a bug at all
        return model_type, "model"
    return (model_type, "model") if kw else ("unknown", "model")   # non-bug: both must say so


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


def environment(names: list[str], tests: CheckStatus = CheckStatus.PASSED) -> tuple[str, str]:
    """(build_system, test_framework) from the repo's root file names. test_framework is the runner we verify with:
    pytest also collects unittest suites, so "tests found" means pytest; unknown only when the tests lookup failed."""
    low = {n.lower() for n in names}
    build = next((b for f, b in LOCKS if f in low), "pip" if "pyproject.toml" in low else "unknown")
    found = low & {"pytest.ini", "conftest.py", "tox.ini", "noxfile.py"} or tests == CheckStatus.PASSED
    return build, "pytest" if found else "unknown"


def decide_handling(*, unsupported: str | None, python: CheckStatus, issue_type: str, missing: list[str],
                    warnings: list[str], other_os: bool = False, model_ok: bool = True, linked_known: bool = True,
                    test_framework: str = "pytest", base_sha_known: bool = True, forbids_ai: bool = False) -> tuple[str, list[str]]:
    """(handling_decision, every reason that fired). First match wins for the label; reasons list them all.
    Unknown, invalid or ambiguous required field -> HUMAN_DECISION, never READY (#48 §3.3, DECISION 2026-11-07)."""
    reasons: list[str] = []
    if unsupported:
        reasons.append(f"unsupported:{unsupported}")
    if issue_type not in FIXABLE and issue_type != "unknown":
        reasons.append(f"not_a_bug:{issue_type}")
    if not model_ok:
        reasons.append("model_unavailable")
    if issue_type == "unknown":
        reasons.append("unclear_type")
    if python == CheckStatus.INCONCLUSIVE:
        reasons.append("compatibility_unknown")
    if not linked_known:
        reasons.append("linked_pr_unknown")
    if test_framework == "unknown" and not unsupported:
        reasons.append("test_framework_unknown")
    if not base_sha_known:
        reasons.append("base_sha_unknown")
    if other_os and issue_type in FIXABLE:   # our sandbox is Linux; a regex, so the human decides (not a hard UNSUPPORTED)
        reasons.append("other_os")
    if issue_type in FIXABLE and {"no_expected", "no_actual"} <= set(missing) and "no_repro" in missing:
        reasons.append("needs_info")
    reasons += [w for w in ("linked_pr", "closed") if w in warnings]
    if forbids_ai:
        reasons.append("repo_forbids_ai")    # explains the permanent publish blocker; doesn't change the decision
    human = ("unclear_type", "model_unavailable", "compatibility_unknown", "linked_pr_unknown", "test_framework_unknown",
             "base_sha_unknown", "other_os")
    order = [("unsupported:", "UNSUPPORTED"), ("not_a_bug:", "ASSESSMENT_ONLY"), *((h, "HUMAN_DECISION") for h in human),
             ("needs_info", "NEEDS_INFORMATION"), ("linked_pr", "ALREADY_ADDRESSED"), ("closed", "ALREADY_ADDRESSED")]
    for prefix, decision in order:
        if any(r == prefix or (prefix.endswith(":") and r.startswith(prefix)) for r in reasons):
            return decision, reasons
    return "READY", reasons


DECISION_TEXT = {
    "READY": "A bug or regression with enough detail, in a supported Python project: PatchPilot can try a verified fix.",
    "NEEDS_INFORMATION": "Looks like a bug, but the issue doesn't say what should happen or show how to trigger it.",
    "UNSUPPORTED": "PatchPilot can read issues from any public repository, but it can only run Python projects with pip and pytest today.",
    "ALREADY_ADDRESSED": "An open pull request may already address this, or the issue is closed. Lookups can be wrong, so check it; you can still start.",
    "HUMAN_DECISION": "Something we need is unknown or unclear (see why below), so you decide whether to go ahead.",
    "ASSESSMENT_ONLY": "This isn't a bug report, so PatchPilot assesses it but doesn't change any code. Fixes run only for bugs and regressions.",
}
NEXT_STEP = {
    "UNSUPPORTED": "Pick an issue from a Python project with tests, or work on this one by hand.",
    "ASSESSMENT_ONLY": "Work on it by hand, or pick a bug report instead.",
    "NEEDS_INFORMATION": "Ask for the missing details on the issue (draft below), or start anyway.",
    "HUMAN_DECISION": "Start anyway if you've read it and it is a bug PatchPilot can run.",
}


# #41's fixed report caveat, kept for v0.4: on EVERY outcome of a run whose user accepted an unclear/under-specified issue
UNCLEAR_CAVEAT = ("> Verified here means the fix passes the test PatchPilot wrote from the issue. The issue doesn't say what the right "
                  "behaviour is, so check it matches what the maintainers want.")


SAVED_TEXT = "You saved this assessment without starting a fix attempt, so nothing ran."


def decision_text(a: IssueAssessment) -> str:
    return SAVED_TEXT if "saved_by_user" in a.decision_reasons else DECISION_TEXT[a.handling_decision]


def report_lines(a: IssueAssessment) -> list[str]:
    """Report section for any run with an assessment. Written from code, never by a model."""
    caveat = a.handling_decision in ("HUMAN_DECISION", "NEEDS_INFORMATION") and bool({"unclear_type", "needs_info", "model_unavailable"} & set(a.decision_reasons))
    return [*([UNCLEAR_CAVEAT, ""] if caveat else []), "## Assessment", f"- Decision: **{a.handling_decision}**: {decision_text(a)}",
            f"- Issue type: {a.issue_type.replace('_', ' ')} (from {a.issue_type_source})",
            f"- Execution support: {a.compatibility_status} (build: {a.build_system}, tests: {a.test_framework})",
            *([f"- Missing information: {', '.join(MISSING_ASK[m] for m in a.missing_information)}"] if a.missing_information else []),
            *([f"- Open pull requests mentioning it: {', '.join(f'#{n}' for n in a.existing_resolution)}"] if a.existing_resolution else []),
            *([f"- Why: {', '.join(a.decision_reasons)}"] if a.decision_reasons else []),
            *([f"- Suggested next step: {NEXT_STEP[a.handling_decision]}"]
              if a.handling_decision in NEXT_STEP and "saved_by_user" not in a.decision_reasons else []), ""]


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
           unsupported: str | None, warnings: list[str], linked: list[int] | None, extracted: dict | None = None,
           base_sha: str | None = "known", forbids_ai: bool = False) -> IssueAssessment:
    """extracted = the model's fields (see `extract`), or None when the model wasn't available."""
    x = extracted or {}
    issue_type, source = classify(title, body, labels, x.get("issue_type"))
    missing = missing_information(body) if issue_type in FIXABLE else []
    build, tests = environment(names, checks.get("tests_found", CheckStatus.INCONCLUSIVE))
    python = checks.get("python", CheckStatus.INCONCLUSIVE)
    decision, reasons = decide_handling(
        unsupported=unsupported, python=python, issue_type=issue_type, missing=missing, warnings=warnings,
        other_os=bool(OTHER_OS.search(f"{title}\n{body}")), model_ok=extracted is not None or bool(unsupported), linked_known=linked is not None,
        test_framework=tests, base_sha_known=bool(base_sha) and base_sha != "pending", forbids_ai=forbids_ai)
    return IssueAssessment(
        issue_type=issue_type, issue_type_source=source, issue_status="closed" if state == "closed" else "open",
        problem_summary=x.get("problem_summary"), acceptance_conditions=x.get("acceptance_conditions") or [],
        reproduction_information=x.get("reproduction_information"),
        missing_information=missing, existing_resolution=linked, build_system=build, test_framework=tests,
        compatibility_status=("unsupported" if unsupported else "unknown" if python == CheckStatus.INCONCLUSIVE else "supported"),
        handling_decision=decision, decision_reasons=reasons,
        draft_comment=draft_comment(missing) if decision == "NEEDS_INFORMATION" else None)


def new_warnings(a: IssueAssessment) -> list[str]:
    """Warning codes this assessment adds to G0's existing ones (only for issues that may still run)."""
    if a.handling_decision not in EXECUTES:
        return []
    return list(dict.fromkeys(w for r in a.decision_reasons if (w := WARNS.get(r))))


# ---- model extraction (DECISION 2026-11-07: the model is the classifier, code decides) ----
TYPES = ("bug", "regression", "feature", "enhancement", "docs", "refactor", "maintenance", "build_ci", "test_failure",
         "question", "other", "unknown")
EXTRACT_PROMPT = """You read one GitHub issue and extract facts. You do NOT decide whether anyone may work on it.
Reply with ONE JSON object and nothing else:
{"issue_type": one of %s,
 "problem_summary": one sentence or null,
 "expected_behavior": what the reporter says should happen, or null,
 "actual_behavior": what the reporter says happens instead, or null,
 "acceptance_conditions": [short checkable statements a fix must satisfy, only ones the issue states],
 "reproduction_information": the code/steps that trigger it, quoted briefly, or null}
Rules: a bug or regression reports existing behaviour that is wrong; a request for new behaviour is a feature or enhancement.
Use "unknown" when the issue doesn't make it clear. Never invent details the issue doesn't contain; use null instead.""" % (list(TYPES),)
EXTRACT_SECONDS = 20          # the S-01 check waits at most this long; a slower model counts as unavailable
EXTRACT_MAX_OUTPUT = 1800     # reasoning models (gpt-oss) spend part of this thinking; with the issue cut to 4,000 chars
EXTRACT_MAX_CHARS = 4000      # (~1k tokens) + the prompt, one call stays around 3k tokens
_CACHE = "CREATE TABLE IF NOT EXISTS assess_cache(key TEXT PRIMARY KEY, json TEXT, ts TEXT)"


def parse_extraction(text: str) -> dict | None:
    """The model's JSON, validated. Anything malformed -> None (= model unavailable -> HUMAN_DECISION at best)."""
    import json
    text, d, dec = text or "", None, json.JSONDecoder()
    for i in (k for k, ch in enumerate(text) if ch == "{"):   # first decodable object with a valid type; a stray "{" in
        try:                                                  # the model's thinking used to break a greedy \{.*\} grab
            cand, _ = dec.raw_decode(text, i)
        except ValueError:
            continue
        if isinstance(cand, dict) and cand.get("issue_type") in TYPES:
            d = cand
            break
    if d is None:
        return None
    s = lambda k: (d.get(k) or None) if isinstance(d.get(k), (str, type(None))) else None
    acc = d.get("acceptance_conditions") if isinstance(d.get("acceptance_conditions"), list) else []
    return {"issue_type": d["issue_type"], "problem_summary": s("problem_summary"), "expected_behavior": s("expected_behavior"),
            "actual_behavior": s("actual_behavior"), "reproduction_information": s("reproduction_information"),
            "acceptance_conditions": [str(a)[:300] for a in acc if isinstance(a, (str, int, float))][:8]}


def assess_tokens_today() -> int:
    from backend import db
    from backend.llm_gateway import _CALLS
    c = db.connect(); c.execute(_CALLS)
    return c.execute("SELECT COALESCE(SUM(prompt_tokens+completion_tokens),0) FROM llm_calls WHERE role='assessor' "
                     "AND substr(ts,1,10)=?", (db.now().date().isoformat(),)).fetchone()[0]


def extract(*, url: str, updated_at: str | None, title: str, body: str, labels: list[str], _completion=None) -> dict | None:
    """One bounded model call per issue version (cached on updated_at). Counted: logged by llm_gateway under role
    "assessor", inside the global daily budget, plus its own daily cap `assess_llm_tokens_per_day`. Never raises."""
    import json
    from concurrent.futures import ThreadPoolExecutor
    from backend import db
    from backend.config import limits
    from backend import llm_gateway
    key = f"{url}@{updated_at}"
    c = db.connect(); c.execute(_CACHE)
    if updated_at and (hit := c.execute("SELECT json FROM assess_cache WHERE key=?", (key,)).fetchone()):
        return json.loads(hit[0])
    if assess_tokens_today() >= limits().get("assess_llm_tokens_per_day", 0):
        return None                    # own cap reached (0 = model extraction off): unavailable, never unmetered
    if _completion is None:
        import litellm
        _completion = lambda **k: litellm.completion(**k, max_tokens=EXTRACT_MAX_OUTPUT)
    issue = f"Title: {title}\nLabels: {', '.join(labels) or 'none'}\n\n{(body or '')[:EXTRACT_MAX_CHARS]}"
    msgs = [{"role": "system", "content": EXTRACT_PROMPT}, {"role": "user", "content": issue}]
    pool = ThreadPoolExecutor(max_workers=1)
    try:
        fut = pool.submit(llm_gateway.complete, msgs, run_id=f"assess:{url}", role="assessor", kind="short", _completion=_completion)
        out = parse_extraction(fut.result(timeout=EXTRACT_SECONDS))
    except Exception:                  # quota, budget, timeout, network, bad JSON: all "unavailable", never a guess
        out = None
    finally:
        pool.shutdown(wait=False)      # a slow call finishes in the background and is still logged and counted
    if out is not None and updated_at:
        with db.tx(c):
            c.execute("INSERT OR REPLACE INTO assess_cache VALUES(?,?,?)", (key, json.dumps(out), db.now().isoformat()))
    return out
