"""Approval hash contract (contracts §5). Pure; the API (approve) and the publisher must use exactly these."""
import hashlib
import json
import re


def canonical_diff(diff: str) -> str:
    """LF line endings; per-file sections sorted by path."""
    text = diff.replace("\r\n", "\n")
    parts = [p for p in re.split(r"(?m)^(?=diff --git )", text) if p.strip()]
    key = lambda p: (m.group(1) if (m := re.match(r"diff --git a/(\S+)", p)) else p)
    return "".join(p if p.endswith("\n") else p + "\n" for p in sorted(parts, key=key))


def diff_hash(diff: str) -> str:
    return "sha256:" + hashlib.sha256(canonical_diff(diff).encode()).hexdigest()


def evidence_manifest(*, run_id: str, revision: int, base_sha: str, diff_hash: str, gates: dict, outcome: str | None,
                      verify_evidence_ids: list[str], baseline_evidence_ids: list[str], repro_evidence_ids: list[str],
                      supplyguard_report_id: str | None, review_id: str | None) -> str:
    return json.dumps(dict(run_id=run_id, revision=revision, base_sha=base_sha, diff_hash=diff_hash, gates=gates,
                           outcome=outcome, verify_evidence_ids=verify_evidence_ids,
                           baseline_evidence_ids=baseline_evidence_ids, repro_evidence_ids=repro_evidence_ids,
                           supplyguard_report_id=supplyguard_report_id, review_id=review_id),
                      sort_keys=True, separators=(",", ":"))


def evidence_hash(manifest: str) -> str:
    return "sha256:" + hashlib.sha256(manifest.encode()).hexdigest()
