"""The repo's own checks on the changed files (#70 item 3; mcstatus #1238: basedpyright failed CI on a VERIFIED_FIX).
Code-decided: one row per tool (PASS / FAIL / NOT_RUN / UNSUPPORTED / BLOCKED) with the command and exit code, stored in
kv repo_checks:<run_id>. A FAIL (new problems the change ADDS) is a medium Reviewer concern, so it can only lower readiness.
A check that didn't run is never reported as passed."""
import base64
import json
import re
import shlex
import uuid
from collections import Counter

from backend import db
from backend.gates.diff_policy import diff_paths
from backend.sandbox import docker
from backend.sandbox.steps import image, snap

SEP, EXIT, MISSING, HOOKS = "@@PP_TOOL ", "@@PP_EXIT ", "@@PP_MISSING ", "@@PP_HOOKS "
# Discovery is deterministic: the tool's own config, or a mention in tox / nox / pre-commit / CI / CONTRIBUTING.
# Each tool runs only if found AND installed in the sandbox (no network). File arguments go after `--`
# (pyright has no `--`, so its paths get a ./ prefix): a path starting with "-" is never read as an option.
TOOLS = r"""
cfg() { grep -qsE "$1" pyproject.toml setup.cfg tox.ini; }
said() { grep -qsiE "$1" tox.ini noxfile.py .pre-commit-config.yaml .github/workflows/*.yml .github/workflows/*.yaml CONTRIBUTING* docs/CONTRIBUTING* 2>/dev/null; }
run() { name="$1"; shift; echo "@@PP_TOOL $name|$*"; "$@" 2>&1; echo "@@PP_EXIT $?"; }
lint() {
  if [ -f ruff.toml ] || [ -f .ruff.toml ] || cfg '^\[tool\.ruff' || said '\bruff\b'; then
    if python -m ruff --version >/dev/null 2>&1; then
      run "ruff check" python -m ruff check --no-cache --output-format concise -- "$@"
      run "ruff format" python -m ruff format --check --no-cache -- "$@"
    else echo "@@PP_MISSING ruff"; fi
  fi
  if cfg '^\[tool\.black' || said '\bblack\b'; then
    if python -m black --version >/dev/null 2>&1; then run "black" python -m black --check -- "$@"; else echo "@@PP_MISSING black"; fi
  fi
  if [ -f .flake8 ] || cfg '^\[flake8' || said '\bflake8\b'; then
    if python -m flake8 --version >/dev/null 2>&1; then run "flake8" python -m flake8 -- "$@"; else echo "@@PP_MISSING flake8"; fi
  fi
  if [ -f mypy.ini ] || [ -f .mypy.ini ] || cfg '^\[(tool\.)?mypy' || said '\bmypy\b'; then
    if python -m mypy --version >/dev/null 2>&1; then run "mypy" python -m mypy --no-incremental --no-error-summary -- "$@"
    else echo "@@PP_MISSING mypy"; fi
  fi
  if [ -f pyrightconfig.json ] || cfg '^\[tool\.(based)?pyright' || said '\b(based)?pyright\b'; then
    t=""; for c in basedpyright pyright; do command -v $c >/dev/null 2>&1 && { t=$c; break; }; done
    if [ -n "$t" ]; then
      for f in "$@"; do shift; set -- "$@" "./$f"; done
      run "$t" "$t" "$@"
    else echo "@@PP_MISSING pyright"; fi
  fi
}
hooks() { [ -f .pre-commit-config.yaml ] && echo "@@PP_HOOKS $(grep -oE '^[[:space:]]*-[[:space:]]+id:[[:space:]]*[A-Za-z0-9_.-]+' .pre-commit-config.yaml | sed 's/.*id:[[:space:]]*//' | sort -u | tr '\n' ' ')"; }
"""
RUN_HOOKS = {"ruff", "ruff-format", "ruff-check", "black", "flake8", "mypy", "pyright", "basedpyright"}
# "path:12:5: msg", "path:12: error: msg", "  /src/path:12:5 - error: msg", "Would reformat: path"
_LOC = re.compile(r"^\s*(?:/src/|\./)?(?P<file>[^\s:]+\.pyi?):\d+(?::\d+)?:?\s*(?:-\s*)?(?P<msg>.+)$")
_FMT = re.compile(r"^(?:Would reformat|would reformat):?\s*(?:/src/|\./)?(?P<file>\S+\.pyi?)$")


def parse(out: str) -> dict[str, dict]:
    """tool -> {command, exit_code, problems: Counter of (file, message) without line numbers, last: the last output line}.
    Line numbers are dropped so a moved line isn't a new problem."""
    res, tool = {}, None
    for line in out.splitlines():
        if line.startswith(SEP):
            name, _, cmd = line[len(SEP):].partition("|")
            tool = name.strip(); res[tool] = {"command": cmd.strip(), "exit_code": None, "problems": Counter(), "last": ""}
        elif line.startswith(EXIT) and tool:
            res[tool]["exit_code"] = int(line[len(EXIT):].strip() or -1); tool = None
        elif tool:
            if (m := _LOC.match(line) or _FMT.match(line)):
                res[tool]["problems"][(m.group("file"), m.groupdict().get("msg") or "would reformat")] += 1
            elif line.strip():
                res[tool]["last"] = line.strip()[:200]
    return res


def problems(out: str) -> dict[str, Counter]:
    return {t: r["problems"] for t, r in parse(out).items()}


def new_problems(before: str, after: str) -> dict[str, list[str]]:
    b, a = problems(before), problems(after)
    return {t: [f"{f}: {m}" for (f, m) in (c - b.get(t, Counter())).elements()] for t, c in a.items() if c - b.get(t, Counter())}


def rows(before: str, after: str) -> list[dict]:
    """One row per tool, decided by code. FAIL = the change adds problems; BLOCKED = the tool exited non-zero with no
    readable problem lines (a crash or config error), so we don't know; PASS = ran and added nothing."""
    b, a, new = parse(before), parse(after), new_problems(before, after)
    out = []
    for tool, r in a.items():
        found, existing = new.get(tool, []), sum((b.get(tool) or {"problems": Counter()})["problems"].values())
        if found:   # problems it printed are real even if the output was cut off before the exit code
            status, note = "FAIL", f"{len(found)} new problem{'s' if len(found) != 1 else ''}"
        elif r["exit_code"] is None:
            status, note = "BLOCKED", "the tool didn't finish (timeout or crash)"
        elif r["exit_code"] != 0 and not r["problems"]:
            status, note = "BLOCKED", f"exited {r['exit_code']} without readable results: {r['last']}"
        else:
            status, note = "PASS", "no new problems" + (f" ({existing} were already there)" if existing else "")
        out.append({"tool": tool, "status": status, "command": r["command"], "exit_code": r["exit_code"],
                    "new": found[:20], "note": note})
    for line in after.splitlines():
        if line.startswith(MISSING):
            out.append({"tool": line[len(MISSING):].strip(), "status": "NOT_RUN", "command": None, "exit_code": None, "new": [],
                        "note": "the repo uses it, but it isn't installed in the sandbox"})
        elif line.startswith(HOOKS):
            for h in sorted(set(line[len(HOOKS):].split()) - RUN_HOOKS):
                out.append({"tool": f"pre-commit: {h}", "status": "UNSUPPORTED", "command": None, "exit_code": None, "new": [],
                            "note": "PatchPilot doesn't run this hook; check it yourself before opening the PR"})
    return out


def run_checks(rid: str, test_diff: str, fix_diff: str) -> dict:
    """Runs the checks once in a fresh no-network container and stores the rows in kv repo_checks:<rid>."""
    files = sorted(p for p in diff_paths(test_diff + "\n" + fix_diff)[0] if p.endswith((".py", ".pyi")))
    if not files:
        res = {"checks": [], "files": [], "reason": "no_python_files"}
    else:
        q = " ".join(shlex.quote(f) for f in files)
        apply = " && ".join(f"echo {base64.b64encode(d.encode()).decode()} | base64 -d > /tmp/d{i}.diff && git apply /tmp/d{i}.diff"
                            for i, d in enumerate((test_diff, fix_diff)) if d.strip())
        # before: files the change creates don't exist yet, so lint only the ones that do (set -- keeps paths with spaces whole)
        script = (f"{TOOLS}\nset --; for f in {q}; do [ -f \"$f\" ] && set -- \"$@\" \"$f\"; done\n"
                  f"[ $# -gt 0 ] && lint \"$@\"\necho '@@PP_AFTER'\n{apply} || {{ echo APPLY_FAILED; exit 3; }}\nlint {q}\nhooks")
        r = docker.run(image(rid), script, name=f"pp-{rid[:8]}-lint-{uuid.uuid4().hex[:6]}", timeout=300, snapshot_volume=snap(rid))
        if r.code == 3 or "@@PP_AFTER" not in r.out:
            res = {"checks": [], "files": files, "reason": "diff_did_not_apply" if r.code == 3 else "sandbox_failed"}
        else:
            before, after = r.out.split("@@PP_AFTER", 1)
            res = {"checks": rows(before, after), "files": files, "reason": None}
    db.put_kv(db.connect(), f"repo_checks:{rid}", json.dumps(res))
    return res


def review_concerns(rid: str, test_diff: str, fix_diff: str) -> list[dict]:
    res = run_checks(rid, test_diff, fix_diff)
    return [{"severity": "medium", "text": f"The repo's {c['tool']} reports {len(c['new'])} new problem{'s' if len(c['new']) != 1 else ''} in "
             f"the changed files, so its CI would likely fail: " + "; ".join(c["new"][:3])[:600]}
            for c in res["checks"] if c["status"] == "FAIL"]
