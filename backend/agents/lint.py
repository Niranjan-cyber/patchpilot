"""The repo's own linters / type checker on the changed files (mcstatus #1238: basedpyright failed CI on a VERIFIED_FIX).
Code-decided Reviewer concern: it can only lower readiness. Only problems the change ADDS count; a tool the repo doesn't
configure, or that isn't installed in the sandbox, is skipped (never reported as clean)."""
import base64
import re
import shlex
import uuid
from collections import Counter

from backend.gates.diff_policy import diff_paths
from backend.sandbox import docker
from backend.sandbox.steps import image, snap

SEP = "@@PP_TOOL "
# each tool runs only when the repo configures it and it is installed; "|| true": a failing tool is output, not an error
TOOLS = r"""
cfg() { grep -qsE "$1" pyproject.toml setup.cfg tox.ini; }
lint() {
  if { [ -f ruff.toml ] || [ -f .ruff.toml ] || cfg '^\[tool\.ruff'; } && python -m ruff --version >/dev/null 2>&1; then
    echo "@@PP_TOOL ruff check"; python -m ruff check --no-cache --output-format concise "$@" 2>&1 || true
    echo "@@PP_TOOL ruff format"; python -m ruff format --check --no-cache "$@" 2>&1 || true
  fi
  if { [ -f mypy.ini ] || [ -f .mypy.ini ] || cfg '^\[(tool\.)?mypy'; } && python -m mypy --version >/dev/null 2>&1; then
    echo "@@PP_TOOL mypy"; python -m mypy --no-incremental --no-error-summary "$@" 2>&1 || true
  fi
  if [ -f pyrightconfig.json ] || cfg '^\[tool\.(based)?pyright'; then
    for t in basedpyright pyright; do
      if command -v $t >/dev/null 2>&1; then echo "@@PP_TOOL $t"; $t "$@" 2>&1 || true; break; fi
    done
  fi
}
"""
# "path:12:5: msg", "path:12: error: msg", "  /src/path:12:5 - error: msg", "Would reformat: path"
_LOC = re.compile(r"^\s*(?:/src/)?(?P<file>[^\s:]+\.pyi?):\d+(?::\d+)?:?\s*(?:-\s*)?(?P<msg>.+)$")
_FMT = re.compile(r"^Would reformat:\s*(?:/src/)?(?P<file>\S+)$")


def problems(out: str) -> dict[str, Counter]:
    """tool -> Counter of (file, message) with line numbers dropped, so a moved line isn't a new problem."""
    res, tool = {}, None
    for line in out.splitlines():
        if line.startswith(SEP):
            tool = line[len(SEP):].strip(); res.setdefault(tool, Counter())
        elif tool and (m := _LOC.match(line) or _FMT.match(line)):
            res[tool][(m.group("file"), m.groupdict().get("msg") or "would reformat")] += 1
    return res


def new_problems(before: str, after: str) -> dict[str, list[str]]:
    b, a = problems(before), problems(after)
    return {t: [f"{f}: {m}" for (f, m) in (c - b.get(t, Counter())).elements()] for t, c in a.items() if c - b.get(t, Counter())}


def review_concerns(rid: str, test_diff: str, fix_diff: str) -> list[dict]:
    files = sorted(p for p in diff_paths(test_diff + "\n" + fix_diff)[0] if p.endswith((".py", ".pyi")))
    if not files:
        return []
    q = " ".join(shlex.quote(f) for f in files)
    apply = " && ".join(f"echo {base64.b64encode(d.encode()).decode()} | base64 -d > /tmp/d{i}.diff && git apply /tmp/d{i}.diff"
                        for i, d in enumerate((test_diff, fix_diff)) if d.strip())
    # before: files the change creates don't exist yet, so lint only the ones that do
    script = (f"{TOOLS}\nex=''; for f in {q}; do [ -f \"$f\" ] && ex=\"$ex $f\"; done\n"
              f"[ -n \"$ex\" ] && lint $ex\necho '@@PP_AFTER'\n{apply} || {{ echo APPLY_FAILED; exit 3; }}\nlint {q}")
    r = docker.run(image(rid), script, name=f"pp-{rid[:8]}-lint-{uuid.uuid4().hex[:6]}", timeout=300, snapshot_volume=snap(rid))
    if r.code == 3 or "@@PP_AFTER" not in r.out:
        return []   # shortcut: an unrun lint adds no concern (as with no linter configured); upgrade when the UI shows a lint row
    before, after = r.out.split("@@PP_AFTER", 1)
    return [{"severity": "medium", "text": f"The repo's {tool} reports {len(found)} new problem{'s' if len(found) != 1 else ''} in the "
             f"changed files, so its CI would likely fail: " + "; ".join(found[:3])[:600]}
            for tool, found in new_problems(before, after).items()]
