#!/usr/bin/env python3
"""apply_patch for the sandbox: the '*** Begin Patch' format gpt-oss models reach for whatever the prompt says (runs 8, 10).
Usage: apply_patch <<'PATCH' ... PATCH   (or a file argument). Stdlib only; runs inside the sandbox, never on the host.
Every hunk is checked before any file is written, so a patch that doesn't match changes nothing and says why."""
import pathlib
import sys


class PatchError(Exception):
    pass


def _find(lines: list[str], old: list[str], start: int) -> int:
    for norm in (lambda s: s, str.rstrip, str.strip):        # exact first, then forgive whitespace the model got wrong
        want = [norm(x) for x in old]
        for i in range(start, len(lines) - len(old) + 1):
            if [norm(x) for x in lines[i:i + len(old)]] == want:
                return i
    return -1


def _update(text: str, body: list[str], path: str) -> str:
    lines, cur = text.split("\n"), 0
    hunks: list[tuple[str, list[str]]] = []
    for ln in body:
        if ln.startswith("@@"):
            hunks.append((ln[2:].strip(), []))
        elif ln != "*** End of File":
            if not hunks:
                hunks.append(("", []))
            hunks[-1][1].append(ln)
    for anchor, h in hunks:
        if anchor:
            at = next((i for i in range(cur, len(lines)) if anchor in lines[i]), -1)
            if at < 0:
                raise PatchError(f"{path}: context line not found: {anchor!r}")
            cur = at
        old = [x[1:] if x[:1] in " -" else x for x in h if x[:1] != "+"]
        new = [x[1:] if x[:1] in " +" else x for x in h if x[:1] != "-"]
        while old and new and old[-1] == "" and new[-1] == "":     # a blank line closing the hunk is not context
            old.pop(); new.pop()
        i = _find(lines, old, cur) if old else cur
        if i < 0:
            raise PatchError(f"{path}: these lines were not found (check them with sed -n first):\n" + "\n".join(old))
        lines[i:i + len(old)] = new
        cur = i + len(new)
    return "\n".join(lines)


def apply(patch: str, root: pathlib.Path) -> list[str]:
    rows = patch.strip("\n").split("\n")
    if not rows or rows[0].strip() != "*** Begin Patch":
        raise PatchError("a patch starts with '*** Begin Patch' (or write the file with cat > path <<'EOF')")
    ops, cur = [], None
    for ln in rows[1:]:
        if ln.strip() == "*** End Patch":
            break
        for kind in ("Add", "Update", "Delete"):
            tag = f"*** {kind} File: "
            if ln.startswith(tag):
                cur = [kind, ln[len(tag):].strip(), []]; ops.append(cur); break
        else:
            if ln.startswith("*** Move to: ") and cur:
                cur.append(ln[len("*** Move to: "):].strip())
            elif cur is None:
                raise PatchError(f"unexpected line before any '*** ... File:' header: {ln!r}")
            else:
                cur[2].append(ln)
    out = {}                                     # path -> new text (None = delete); written only if every hunk applied
    for op in ops:
        kind, path, body = op[:3]
        f = root / path
        if kind == "Add":
            out[f] = "\n".join(x[1:] if x.startswith("+") else x for x in body) + "\n"
        elif kind == "Delete":
            if not f.exists():
                raise PatchError(f"{path}: no such file to delete")
            out[f] = None
        else:
            if not f.exists():
                raise PatchError(f"{path}: no such file to update (use '*** Add File:')")
            new = _update(f.read_text(encoding="utf-8"), body, path)
            if len(op) > 3:
                out[f] = None; f = root / op[3]
            out[f] = new
    for f, text in out.items():
        if text is None:
            f.unlink(missing_ok=True)
        else:
            f.parent.mkdir(parents=True, exist_ok=True); f.write_text(text, encoding="utf-8")
    return [str(f.relative_to(root)) for f in out]


if __name__ == "__main__":
    try:
        src = open(sys.argv[1], encoding="utf-8").read() if len(sys.argv) > 1 else sys.stdin.read()
        for p in apply(src, pathlib.Path.cwd()):
            print("patched", p)
    except PatchError as e:
        sys.exit(f"apply_patch: {e}")
