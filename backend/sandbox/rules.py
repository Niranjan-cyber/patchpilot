"""Pure gate rules for G1 (pre-flight) and G2 (setup) and baseline sets. No I/O; tested in tests/test_sandbox_rules.py."""
import xml.etree.ElementTree as ET

from backend.contracts.models import CheckStatus

# Provisional DECISION (A, 2026-10-30; C owns SupplyGuard and may override in messages.md): block (no override,
# contracts §1.1) on a published malicious advisory, or a HIGH-confidence lookalike (SupplyGuard already checks
# download volume, so a popular package is never a lookalike). Lower-confidence signals are findings.
def _blocks(sig: dict) -> bool:
    return sig.get("kind") == "malicious-advisory" or (sig.get("kind") == "lookalike" and sig.get("confidence") == "high")


def map_supplyguard(exit_code: int | None, report: dict | None) -> tuple[CheckStatus, str, list[dict]]:
    """G1 from a SupplyGuard run. Unknown is inconclusive, never clean."""
    if exit_code is None or report is None:
        return CheckStatus.INCONCLUSIVE, "supplyguard_unavailable", []
    if exit_code == 3:
        return CheckStatus.INCONCLUSIVE, "no_supported_dependency_files", []
    projects = report.get("projects") or []
    findings, blocked = [], []
    for p in projects:
        for s in p.get("suspicious", []):
            kinds = {sig.get("kind") for sig in s.get("signals", [])}
            item = {"type": "suspicious", "package": s.get("packageId"), "risk": s.get("risk"),
                    "kinds": sorted(k for k in kinds if k), "note": s.get("note", "")}
            findings.append(item)
            if any(_blocks(sig) for sig in s.get("signals", [])):
                blocked.append(item)
        for v in p.get("vulnerabilities", []):
            findings.append({"type": "vulnerability", "package": v.get("packageId") or v.get("package"),
                             "id": v.get("advisoryId") or v.get("id"), "severity": v.get("severity")})
    if blocked:
        return CheckStatus.BLOCKED, "malicious_package", findings
    if exit_code == 2 or any(p.get("summary", {}).get("incomplete") for p in projects) or not projects:
        return CheckStatus.INCONCLUSIVE, "supplyguard_incomplete", findings
    return CheckStatus.PASSED, "no_malicious_packages", findings


def evaluate_setup(install_code: int, install_timed_out: bool, collect_code: int, collected: int) -> tuple[CheckStatus, str]:
    """G2: install exit 0 within the time cap AND pytest collection exit 0 with >= 1 test."""
    if install_timed_out:
        return CheckStatus.FAILED, "install_timeout"
    if install_code != 0:
        return CheckStatus.FAILED, "install_failed"
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
