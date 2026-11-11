"""Real PREFLIGHT (G1), SETUP (G2) and BASELINE steps (B05). Registers itself into the worker's NODES."""
import io
import json
import os
import re
import shlex
import shutil
import subprocess
import tarfile
import uuid
from pathlib import Path

import httpx

from backend import artifacts, db
from backend.config import ROOT, limits
from backend.contracts.models import CheckStatus, EnvProfile, GateResult, PublishBlocker, SGReport, StepId, TestRun
from backend.sandbox import docker
from backend.sandbox.rules import (baseline_sets, evaluate_setup, junit_outcomes, map_supplyguard, pyproject_requirements,
                                    release_tag_before, setup_requirements, uncollectable_files)
from backend.worker import nodes
from backend.worker.nodes import StepContext

WORK = ROOT / "data" / "work"
GH = "https://api.github.com"
MAX_TARBALL = 200 * 1024 * 1024


def snap(rid: str) -> str: return f"pp-snap-{rid}"
def image(rid: str) -> str: return f"pp-run-{rid}"
def cname(rid: str, step: str) -> str: return f"pp-{rid[:8]}-{step}-{uuid.uuid4().hex[:6]}"


def _gh_headers():
    tok = os.getenv("GITHUB_READ_TOKEN")
    return {"Accept": "application/vnd.github+json", **({"Authorization": f"Bearer {tok}"} if tok else {})}


def fetch_source(repo: str, rid: str, sha: str | None = None) -> tuple[str, str]:
    """Download the tarball at the pinned commit (no git clone: no hooks/submodules), extract safely."""
    with httpx.Client(headers=_gh_headers(), timeout=30, follow_redirects=True) as h:
        if not sha:
            branch = h.get(f"{GH}/repos/{repo}").raise_for_status().json()["default_branch"]
            sha = h.get(f"{GH}/repos/{repo}/commits/{branch}").raise_for_status().json()["sha"]
        data = h.get(f"{GH}/repos/{repo}/tarball/{sha}").raise_for_status().content
        tag = _release_tag(h, repo, sha)
    if len(data) > MAX_TARBALL:
        raise ValueError("repository tarball is larger than 200 MB")
    dest = WORK / rid / "src"
    shutil.rmtree(dest.parent, ignore_errors=True); dest.mkdir(parents=True)
    with tarfile.open(fileobj=io.BytesIO(data)) as tf:
        top = tf.getmembers()[0].name.split("/")[0]
        for m in tf.getmembers():
            m.name = m.name[len(top) + 1:] if m.name.startswith(top + "/") else ""
        tf.extractall(dest, members=[m for m in tf.getmembers() if m.name], filter="data")
    commit_base(dest, sha, tag)
    return sha, str(dest)


def commit_base(dest, sha: str, tag: str | None = None) -> None:
    """The base commit the sandbox diffs against, made by the host's git."""
    # autocrlf=false: a Windows host's autocrlf=true stores CRLF files as LF, so the sandbox sees them all as modified
    git = ["git", "-c", "core.hooksPath=/dev/null", "-c", "core.autocrlf=false", "-c", "user.name=PatchPilot",
           "-c", "user.email=pp@localhost", "-C", str(dest)]
    for args in (["init", "-q"], ["add", "-A"], ["commit", "-qm", f"base {sha}"]):
        subprocess.run(git + args, check=True, capture_output=True)
    if tag:   # a bad tag name just means no version hint, never a failed fetch
        subprocess.run(git + ["tag", tag], capture_output=True)


def _release_tag(h: httpx.Client, repo: str, sha: str) -> str | None:
    """Version hint for setuptools_scm / hatch-vcs repos (the tarball has no tags). Any API failure = no hint."""
    try:
        date = h.get(f"{GH}/repos/{repo}/commits/{sha}").raise_for_status().json()["commit"]["committer"]["date"]
        return release_tag_before(h.get(f"{GH}/repos/{repo}/releases", params={"per_page": 100}).raise_for_status().json(), date)
    except Exception:
        return None


def _pyproject_pins(src: Path) -> str | None:
    """A pyproject-only repo's install set as exact pins (transitive included), or None (has a lock file / unknown / failed).
    --no-build: resolves from published metadata only, so no package or repo code runs on the host."""
    if any((src / f).exists() for f in ("requirements.txt", "Pipfile.lock", "poetry.lock")):
        return None
    read = lambda f: (src / f).read_text(encoding="utf-8", errors="replace") if (src / f).exists() else None
    # smart_open-833: deps only in setup.py/setup.cfg left G1 inconclusive; both are read statically, never run
    pyproject = read("pyproject.toml")
    reqs = (pyproject_requirements(pyproject) if pyproject else None) or setup_requirements(read("setup.py"), read("setup.cfg"))
    uv = shutil.which("uv")
    if reqs is None or uv is None:
        return None
    try:
        p = subprocess.run([uv, "pip", "compile", "-", "--no-build", "--no-config", "--python-version", "3.12", "--no-header",
                            "--no-annotate", "--quiet"], input="\n".join(reqs), capture_output=True, text=True, timeout=120,
                           cwd=src.parent)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return p.stdout if p.returncode == 0 and "==" in p.stdout else None


def run_supplyguard(rid: str) -> SGReport:
    """Static dependency check on the extracted source (never installs). Unknown → inconclusive, never clean."""
    src = WORK / rid / "src"
    code, report, log = None, None, ""
    cmd = os.getenv("SUPPLYGUARD_CMD")   # e.g. "data/tools/supplyguard/backend/node_modules/.bin/tsx …/cli/index.ts"
    target, note = src, ""
    if cmd and src.exists() and (pins := _pyproject_pins(src)) is not None:
        target = WORK / rid / "sg"
        target.mkdir(exist_ok=True)
        (target / "requirements.txt").write_text(pins, encoding="utf-8")
        note = "Scanned pyproject.toml's requirements, resolved to exact versions with uv (no builds):\n" + pins + "\n"
    if cmd and src.exists():
        try:
            argv = shlex.split(cmd, posix=os.name != "nt")
            # absolute: a relative "data/..." .CMD path is read by cmd.exe as command "data" + switch "/tools" (never ran)
            argv[0] = os.path.abspath(found) if (found := shutil.which(argv[0])) else argv[0]
            p = subprocess.run(argv + ["analyze", str(target), "--json"], capture_output=True, text=True,
                               encoding="utf-8", errors="replace", timeout=180)
            code, log = p.returncode, note + p.stdout[-200000:] + p.stderr[-20000:]
            report = json.loads(p.stdout) if p.stdout.strip().startswith("{") else None
        except Exception as e:
            log = f"SupplyGuard failed to run: {e!r}"
    status, reason, findings = map_supplyguard(code, report)
    files = [f for f in ("requirements.txt", "Pipfile.lock", "poetry.lock", "uv.lock", "pyproject.toml") if (src / f).exists()]
    ev = artifacts.put(log or json.dumps({"note": "SupplyGuard not configured (SUPPLYGUARD_CMD unset)", "at": db.now().isoformat()}))
    return SGReport(report_id=ev, status=status, findings=findings, files=files,
                    failures=[] if status != CheckStatus.INCONCLUSIVE else [reason])


def preflight(ctx: StepContext) -> GateResult:
    run = ctx.run
    # A failed download raises: the worker retries (2 resumes), then ends with the honest outcome (contracts §7).
    sha, src = fetch_source(run.issue.repo, ctx.run_id, None if run.base_sha == "pending" else run.base_sha)
    run.base_sha = sha
    ctx.emit("step.progress", "preflight", message=f"Pinned commit {sha[:7]}.")
    run.supplyguard = run_supplyguard(ctx.run_id)
    status, findings = run.supplyguard.status, run.supplyguard.findings
    reason = run.supplyguard.failures[0] if run.supplyguard.failures else ("malicious_package" if status == CheckStatus.BLOCKED else "no_malicious_packages")
    ev = run.supplyguard.report_id
    if status == CheckStatus.INCONCLUSIVE and PublishBlocker.DEPS_INCONCLUSIVE not in run.publish_blockers:
        run.publish_blockers.append(PublishBlocker.DEPS_INCONCLUSIVE)
    ctx.scratch["headline"] = {
        CheckStatus.BLOCKED: f"{next((f['package'] for f in findings if f['type'] == 'suspicious'), 'A dependency')} looks like a "
                             "known-malicious or typosquatted package. Nothing from this repository was installed or run.",
        CheckStatus.INCONCLUSIVE: "We couldn't fully check the dependencies, so publishing will stay off.",
    }.get(status, f"No known-malicious packages. {sum(f['type'] == 'vulnerability' for f in findings)} known vulnerabilities listed as findings.")
    db.save_run(db.connect(), run)
    if status == CheckStatus.BLOCKED:
        return GateResult(gate="G1", status=status, reason=reason, evidence_ids=[ev])
    docker.make_snapshot(snap(ctx.run_id), src)
    return GateResult(gate="G1", status=status, reason=reason, evidence_ids=[ev])


INSTALL = r"""cd /src
( for f in requirements.txt requirements-dev.txt requirements-test.txt requirements-tests.txt test-requirements.txt requirements/test.txt requirements/tests.txt requirements/dev.txt tests/requirements.txt; do
    # jsonpickle: a line pip can't read in a -r file (". --group x") shouldn't end setup when the project file can install it
    [ -f "$f" ] || continue
    if pip install -q -r "$f"; then echo "+ pip install -r $f"   # "+ " only for what took (EnvProfile.install_cmds)
    else [ -f pyproject.toml ] || [ -f setup.py ] || exit 1; echo "~ $f failed; trying the project's own extras instead"; fi; done
  if [ -f pyproject.toml ] || [ -f setup.py ]; then
    # pip only warns (exit 0) on an extra the project doesn't have, so keep going until one really exists (#26)
    # only the install that took is logged as "+ " (EnvProfile.install_cmds); tries go to the log as "~ "
    for x in "[test]" "[tests]" "[testing]" "[dev]" ""; do echo "~ trying pip install -e .$x"; o=$(pip install -q -e ".$x" 2>&1); c=$?; echo "$o"
      [ $c -eq 0 ] && ! echo "$o" | grep -q "does not provide the extra" && { echo "+ pip install -e .$x"; break; }; [ -z "$x" ] && exit 1; done
  fi
  # no -U: pp-base already has pip>=25.1, and -U still asks the index (a 203 s stall on Docker's flaky network)
  pip install -q "pip>=25.1" >/dev/null 2>&1
  if grep -q '^\[dependency-groups\]' pyproject.toml 2>/dev/null; then
    for g in test tests dev; do grep -qE "^$g *=" pyproject.toml && { echo "+ pip install --group $g"; pip install -q --group "$g"; }; done
  fi
  pip install -q pytest
  # pytest refuses to start on an addopts flag whose plugin isn't installed (tablib's --cov, twine's --disable-socket)
  cfg=$(cat pytest.ini tox.ini setup.cfg pyproject.toml 2>/dev/null)
  for p in "--cov:pytest-cov" "--disable-socket:pytest-socket" "--timeout:pytest-timeout" "--reruns:pytest-rerunfailures" \
           "-n auto:pytest-xdist" "--numprocesses:pytest-xdist" "--benchmark-:pytest-benchmark"; do
    case "$cfg" in *"${p%%:*}"*) pip install -q "${p#*:}" && echo "+ pip install ${p#*:}";; esac; done ) > /tmp/install.log 2>&1
echo "INSTALL_EXIT=$?"; tail -c 30000 /tmp/install.log
# #26: /src is tmpfs, so files the install generated (e.g. setuptools_scm's _version.py) would vanish from later steps.
# Keep the git-ignored ones in the committed image; docker.run/start unpack them over the snapshot.
# shortcut: archives over 100 MB are dropped (huge build dirs); upgrade to an allow-list if a real project needs more.
git ls-files -z --others --ignored --exclude-standard 2>/dev/null | grep -zv -e __pycache__ -e '\.pyc$' | tar --null -T - -cf /opt/venv/.pp-gen.tar 2>/dev/null
[ "$(stat -c %s /opt/venv/.pp-gen.tar 2>/dev/null || echo 0)" -gt 104857600 ] && rm -f /opt/venv/.pp-gen.tar
python -m pytest --collect-only -q -p no:cacheprovider > /tmp/collect.log 2>&1; echo "COLLECT_EXIT=$?"
# a repo's addopts changes our -q: "-v" gives a tree + "N tests collected", "-q" gives -qq ("file.py: N" lines only)
n=$(grep -oE '[0-9]+(/[0-9]+)? tests? collected' /tmp/collect.log | tail -1 | cut -d' ' -f1 | cut -d/ -f1)   # "2/3 tests collected (1 deselected)": the selected count
[ -n "$n" ] || n=$(awk '/::/{c++} /^[^ ].*: [0-9]+$/{s+=$NF} END{print (c ? c : s+0)}' /tmp/collect.log)
echo "COLLECTED=$n"
# #120: the files that failed to load (pytest's short summary), and how many test files did load (-q ids or -qq counts)
grep -oE '^ERROR [^ ]+\.py' /tmp/collect.log | cut -d' ' -f2 | sort -u | sed 's/^/UNCOLLECTABLE=/'
echo "TEST_FILES=$(grep -oE '^[^ :]+\.py(::|: [0-9]+$)' /tmp/collect.log | sed -E 's/(::|: [0-9]+)$//' | sort -u | wc -l)"
tail -c 5000 /tmp/collect.log
"""


def setup(ctx: StepContext) -> GateResult:
    docker.ensure_infra()
    name = cname(ctx.run_id, "setup")
    r = docker.run("pp-base:3.12", INSTALL, name=name, network=docker.SETUP_NET, timeout=limits()["setup_seconds"],
                   snapshot_volume=snap(ctx.run_id), read_only=False, keep=True, log_path="/tmp/install.log")
    num = lambda k: int(m.group(1)) if (m := re.search(rf"{k}=(\d+)", r.out)) else -1
    skip = uncollectable_files(r.out)
    named = len(re.findall(r"^UNCOLLECTABLE=", r.out, re.M))   # a name we won't pass to --ignore fails closed
    status, reason = evaluate_setup(num("INSTALL_EXIT"), r.timed_out, num("COLLECT_EXIT"), num("COLLECTED"),
                                    uncollectable=len(skip) if len(skip) == named else 0, test_files=max(num("TEST_FILES"), 0))
    ev = artifacts.put(r.out)
    db.put_kv(db.connect(), f"uncollectable:{ctx.run_id}", json.dumps(skip if reason == "partial_collection" else []))
    if status == CheckStatus.PASSED:
        docker.commit(name, image(ctx.run_id))
        ctx.run.env = EnvProfile(python_version="3.12", install_cmds=re.findall(r"^\+ (.+)$", r.out, re.M),
                                 image_id=image(ctx.run_id))
        db.save_run(db.connect(), ctx.run)
        ctx.scratch["headline"] = f"Installed the project in a fresh sandbox and found {num('COLLECTED')} tests." + (
            f" {len(skip)} test file{'s' if len(skip) > 1 else ''} couldn't load, so {'they are' if len(skip) > 1 else 'it is'} skipped."
            if reason == "partial_collection" else "")
    else:
        ctx.scratch["headline"] = {"install_timeout": "Installing took longer than 8 minutes, so we stopped.",
                                   "install_failed": "We couldn't install this project. The install log shows why.",
                                   "collection_error": "The project installed, but its tests failed to load (often a missing test dependency).",
                                   }.get(reason, "The project installed, but we couldn't find any tests to run.")
    docker.rm(name)
    return GateResult(gate="G2", status=status, reason=reason, evidence_ids=[ev])


def _pytest(rid: str, args: str) -> tuple[dict[str, bool], str]:
    r = docker.run(image(rid), f"python -m pytest -q -p no:cacheprovider --junitxml=/tmp/j.xml {args} > /tmp/o.log 2>&1;"
                   " echo EXIT=$?; tail -c 20000 /tmp/o.log; echo '<<<JUNIT>>>'; cat /tmp/j.xml",
                   name=cname(rid, "test"), timeout=300, snapshot_volume=snap(rid), log_path="/tmp/o.log")
    log, _, xml = r.out.rpartition("<<<JUNIT>>>")   # last one: a test may print the sentinel itself (as in verify.split_junit)
    return junit_outcomes(xml.strip()), log


def skipped_files(rid: str) -> list[str]:
    """#120: test files G2 found couldn't load; every full-suite run skips exactly these."""
    return json.loads(db.get_kv(db.connect(), f"uncollectable:{rid}") or "[]")


def ignore_args(rid: str) -> str:
    return "".join(f" --ignore={shlex.quote(f)}" for f in skipped_files(rid))


def baseline(ctx: StepContext) -> None:
    first, log1 = _pytest(ctx.run_id, ignore_args(ctx.run_id))
    failing = [t for t, ok in first.items() if not ok]
    rerun, log2 = _pytest(ctx.run_id, " ".join(shlex.quote(t) for t in failing[:200])) if failing else ({}, "")
    p, f, fl = baseline_sets(first, rerun)
    ctx.run.baseline = TestRun(pass_set=p, fail_set=f, flaky_set=fl, partial=not first or bool(skipped_files(ctx.run_id)),
                               evidence_ids=[artifacts.put(log1 + log2)])
    db.save_run(db.connect(), ctx.run)
    ctx.scratch["headline"] = (f"{len(p)} existing tests pass. {len(f)} already fail and {len(fl)} are flaky (not caused by us)."
                               if first else "We couldn't read the existing test results, so the baseline is partial.")
    return None


nodes.register(StepId.PREFLIGHT, preflight)
nodes.register(StepId.SETUP, setup)
nodes.register(StepId.BASELINE, baseline)
