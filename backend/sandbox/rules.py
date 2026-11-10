"""Pure gate rules for G1 (pre-flight) and G2 (setup) and baseline sets. No I/O; tested in tests/test_sandbox_rules.py."""
import xml.etree.ElementTree as ET
import re
import tomllib
from datetime import date

from backend.contracts.models import CheckStatus

# Block (no override, contracts §1.1) on a published malicious advisory, or a HIGH-confidence lookalike unless it is
# an established package itself. #118: SupplyGuard rated retry2 (473k downloads/week since 2021) a high lookalike.
# Established = >= 10k downloads last week AND first published >= 1 year ago: downloads alone can be inflated with a
# download loop, a year on PyPI can't (typosquats get removed). Lower-confidence and established ones are findings.
# shortcut: both numbers are parsed from SupplyGuard's evidence text (its JSON has no structured field), so an unknown
# wording reads as "not established" and blocks (fail closed); switch to structured fields if SupplyGuard adds them.
POPULAR_WEEKLY, ESTABLISHED_DAYS = 10_000, 365


def _established(evidence: str, today: date) -> bool:
    n = re.search(r"(\d[\d,]*) downloads last week", evidence or "")   # digits grouped either way: 473,064 / 4,73,064
    first = re.search(r"first published (\d{4}-\d{2}-\d{2})", evidence or "")
    try:
        return (int(n.group(1).replace(",", "")) >= POPULAR_WEEKLY
                and (today - date.fromisoformat(first.group(1))).days >= ESTABLISHED_DAYS) if n and first else False
    except ValueError:
        return False


def _blocks(sig: dict, today: date) -> bool:
    if sig.get("kind") == "malicious-advisory":
        return True
    return sig.get("kind") == "lookalike" and sig.get("confidence") == "high" and not _established(sig.get("evidence", ""), today)


def release_tag_before(releases: list[dict], commit_date: str) -> str | None:
    """Newest non-draft GitHub release published at or before the base commit (#26): tagging the source with it gives
    setuptools_scm / hatch-vcs projects their real version instead of 0.1.dev1. ISO-8601 'Z' dates compare as strings."""
    # the name is repo-controlled and goes to `git tag` on the host: a tag shape only, never something like an option
    older = [r for r in releases if not r.get("draft") and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._+/-]{0,99}", r.get("tag_name") or "")
             and (r.get("published_at") or "9") <= commit_date]
    return max(older, key=lambda r: r["published_at"])["tag_name"] if older else None


def map_supplyguard(exit_code: int | None, report: dict | None, today: date | None = None) -> tuple[CheckStatus, str, list[dict]]:
    """G1 from a SupplyGuard run. Unknown is inconclusive, never clean."""
    if exit_code == 3:   # SupplyGuard prints plain text, not JSON, when it finds no dependency file it reads
        return CheckStatus.INCONCLUSIVE, "no_supported_dependency_files", []
    if exit_code is None or report is None:
        return CheckStatus.INCONCLUSIVE, "supplyguard_unavailable", []
    projects = report.get("projects") or []
    findings, blocked = [], []
    for p in projects:
        for s in p.get("suspicious", []):
            kinds = {sig.get("kind") for sig in s.get("signals", [])}
            item = {"type": "suspicious", "package": s.get("packageId"), "risk": s.get("risk"),
                    "kinds": sorted(k for k in kinds if k), "note": s.get("note", "")}
            findings.append(item)
            if any(_blocks(sig, today or date.today()) for sig in s.get("signals", [])):
                blocked.append(item)
        for v in p.get("vulnerabilities", []):
            findings.append({"type": "vulnerability", "package": v.get("packageId") or v.get("package"),
                             "id": v.get("advisoryId") or v.get("id"), "severity": v.get("severity")})
    if blocked:
        return CheckStatus.BLOCKED, "malicious_package", findings
    if exit_code == 2 or any(p.get("summary", {}).get("incomplete") for p in projects) or not projects:
        return CheckStatus.INCONCLUSIVE, "supplyguard_incomplete", findings
    return CheckStatus.PASSED, "no_malicious_packages", findings


MAX_UNCOLLECTABLE, MAX_UNCOLLECTABLE_SHARE = 10, 0.2   # #120, contracts v0.9


def uncollectable_files(out: str) -> list[str]:
    """Test files pytest couldn't load (UNCOLLECTABLE= lines from the setup script). Repo-controlled names that later go
    to pytest as --ignore, so only plain relative .py paths are kept."""
    return [p for p in re.findall(r"^UNCOLLECTABLE=(.*)$", out, re.M)
            if re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_./-]*\.py", p) and ".." not in p.split("/")]


def evaluate_setup(install_code: int, install_timed_out: bool, collect_code: int, collected: int,
                   uncollectable: int = 0, test_files: int = 0) -> tuple[CheckStatus, str]:
    """G2: install exit 0 within the time cap AND pytest collection exit 0 with >= 1 test. v0.9 (#120): collection exit 2
    still passes as partial_collection when the named files that failed to load are few (<= 10 and <= 20% of test files);
    those files are skipped in every later full-suite run and the baseline counts as partial."""
    if install_timed_out:
        return CheckStatus.FAILED, "install_timeout"
    if install_code != 0:
        return CheckStatus.FAILED, "install_failed"
    if collect_code == 2 and collected >= 1 and 0 < uncollectable <= MAX_UNCOLLECTABLE \
            and uncollectable <= MAX_UNCOLLECTABLE_SHARE * (test_files + uncollectable):
        return CheckStatus.PASSED, "partial_collection"
    if collect_code not in (0,) or collected < 1:
        return CheckStatus.FAILED, "no_tests_collected" if collect_code in (0, 5) else "collection_error"
    return CheckStatus.PASSED, "installed_and_collected"


def junit_outcomes(xml_text: str) -> dict[str, bool]:
    """test id -> passed? (skipped tests are left out: they never passed or failed)."""
    out: dict[str, bool] = {}
    end = xml_text.rfind("</testsuites>")    # docker output appends stderr (e.g. git apply warnings) after the XML
    try:
        root = ET.fromstring(xml_text[:end + len("</testsuites>")] if end >= 0 else xml_text)
    except ET.ParseError:
        return out
    for tc in root.iter("testcase"):
        cls, name = tc.get("classname", ""), tc.get("name", "")
        tid = f"{cls.replace('.', '/')}.py::{name}" if cls else name
        tags = {c.tag for c in tc}
        if "skipped" in tags:
            continue
        out[tid] = not (tags & {"failure", "error"})
    return out


def baseline_sets(first: dict[str, bool], rerun: dict[str, bool]) -> tuple[list[str], list[str], list[str]]:
    """pass / fail / flaky. A failure that passes on its rerun is flaky (contracts: failures rerun once)."""
    passed = sorted(t for t, ok in first.items() if ok)
    failed = sorted(t for t, ok in first.items() if not ok and not rerun.get(t, False))
    flaky = sorted(t for t, ok in first.items() if not ok and rerun.get(t, False))
    return passed, failed, flaky


TEST_EXTRAS = ("test", "tests", "testing", "dev")


def setup_requirements(setup_py: str | None, setup_cfg: str | None) -> list[str] | None:
    """install_requires + the first test extra from setup.cfg, else from setup.py, read statically: setup.py is parsed
    with ast and never run. Only list literals, names bound to them and `+` count; anything else -> None (G1 stays
    inconclusive, never "no dependencies")."""
    import ast
    import configparser
    out = None
    if setup_cfg:
        cp = configparser.ConfigParser(interpolation=None)
        try:
            cp.read_string(setup_cfg)
        except configparser.Error:
            cp = None
        lines = lambda sec, key: [x.strip() for x in cp.get(sec, key, fallback="").splitlines() if x.strip() and not x.strip().startswith("#")]
        if cp and cp.has_option("options", "install_requires"):
            out = lines("options", "install_requires") + next(
                (lines("options.extras_require", k) for k in TEST_EXTRAS if cp.has_option("options.extras_require", k)), [])
    if out is None and setup_py:
        try:
            tree = ast.parse(setup_py)
        except SyntaxError:
            return None
        names = {t.id: n.value for n in tree.body if isinstance(n, ast.Assign) for t in n.targets if isinstance(t, ast.Name)}

        def val(node, depth=0):
            if depth > 20:
                raise ValueError
            if isinstance(node, (ast.List, ast.Tuple)) and all(isinstance(e, ast.Constant) and isinstance(e.value, str) for e in node.elts):
                return [e.value for e in node.elts]
            if isinstance(node, ast.Name) and node.id in names:
                return val(names[node.id], depth + 1)
            if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
                return val(node.left, depth + 1) + val(node.right, depth + 1)
            raise ValueError
        call = next((n for n in ast.walk(tree) if isinstance(n, ast.Call) and getattr(n.func, "id", getattr(n.func, "attr", "")) == "setup"), None)
        kw = {k.arg: k.value for k in (call.keywords if call else [])}
        if "install_requires" not in kw:
            return None
        try:
            out = val(kw["install_requires"])
            ex = kw.get("extras_require")
            if isinstance(ex, ast.Dict):
                extras = {k.value: v for k, v in zip(ex.keys, ex.values) if isinstance(k, ast.Constant)}
                out += next((val(extras[k]) for k in TEST_EXTRAS if k in extras), [])
        except ValueError:
            return None
    if out is None:
        return None
    return list(dict.fromkeys([*out, *([] if any(r.split("[")[0].strip().lower() == "pytest" for r in out) else ["pytest"])]))


def pyproject_requirements(text: str) -> list[str] | None:
    """What G2 installs from a pyproject-only repo, for G1 (INSTALL in steps.py): [project] dependencies, the first of the
    test/tests/testing/dev extras, the test/tests/dev dependency groups, pytest. Unknown (no [project], dynamic deps,
    bad TOML) -> None, so G1 stays inconclusive."""
    try:
        doc = tomllib.loads(text)
    except tomllib.TOMLDecodeError:
        return None
    proj, groups = doc.get("project"), doc.get("dependency-groups") or {}
    if not isinstance(proj, dict) or "dependencies" in (proj.get("dynamic") or []) or not isinstance(proj.get("dependencies", []), list):
        return None
    extras = proj.get("optional-dependencies") or {}
    out = list(proj.get("dependencies", [])) + next((extras[x] for x in ("test", "tests", "testing", "dev") if x in extras), [])

    def group(name: str, seen: frozenset = frozenset()) -> list[str]:
        if name in seen or not isinstance(groups.get(name), list):
            return []
        return [d for e in groups[name] for d in ([e] if isinstance(e, str) else group(e.get("include-group", ""), seen | {name}))]

    for g in ("test", "tests", "dev"):
        out += [d for d in group(g) if d not in out]
    return [*out, "pytest"]
