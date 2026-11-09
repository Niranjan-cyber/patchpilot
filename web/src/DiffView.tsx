import { Icon } from "./components";

type Line = { kind: "add" | "del" | "ctx" | "hunk"; text: string; a?: number; b?: number };
type FileDiff = { path: string; status: "added" | "deleted" | "modified"; lines: Line[]; adds: number; dels: number };

/** Parse a unified git diff into files with old/new line numbers taken from each hunk header. */
export function parseDiff(text: string): FileDiff[] {
  const files: FileDiff[] = [];
  let f: FileDiff | null = null, a = 0, b = 0;
  for (const l of text.split("\n")) {
    if (l.startsWith("diff --git ")) {
      // the b/ path from "+++ b/…" below wins; this is the fallback for binary or rename-only entries
      f = { path: l.replace(/^diff --git a\/.* b\//, ""), status: "modified", lines: [], adds: 0, dels: 0 };
      files.push(f);
    } else if (!f) continue;
    else if (l.startsWith("new file mode")) f.status = "added";
    else if (l.startsWith("deleted file mode")) f.status = "deleted";
    else if (l.startsWith("+++ ")) { if (l !== "+++ /dev/null") f.path = l.slice(4).replace(/^b\//, "").replace(/\t.*$/, ""); }
    else if (l.startsWith("--- ") || l.startsWith("index ") || l.startsWith("similarity") || l.startsWith("rename ")) continue;
    else if (l.startsWith("@@")) {
      const m = /@@ -(\d+)(?:,\d+)? \+(\d+)/.exec(l);
      a = m ? +m[1] : 0; b = m ? +m[2] : 0;
      f.lines.push({ kind: "hunk", text: l });
    } else if (l.startsWith("+")) { f.lines.push({ kind: "add", text: l.slice(1), b: b++ }); f.adds++; }
    else if (l.startsWith("-")) { f.lines.push({ kind: "del", text: l.slice(1), a: a++ }); f.dels++; }
    else if (l.startsWith("\\")) f.lines.push({ kind: "hunk", text: l });
    else if (f.lines.length) f.lines.push({ kind: "ctx", text: l.slice(1), a: a++, b: b++ });
  }
  return files;
}

const anchor = (p: string) => "f-" + p.replace(/[^a-zA-Z0-9]+/g, "-");
const SIGN = { add: "+", del: "-", ctx: " ", hunk: "" } as const;

export function DiffView({ text }: { text: string }) {
  const files = parseDiff(text);
  if (!files.length) return <p className="verdict-note">This change is empty: no file differs from the original code.</p>;
  return (
    <div className="diffview" aria-label="Exact change">
      <div className="diff-files">
        <span className="hint">{files.length} file{files.length === 1 ? "" : "s"} changed</span>
        {files.map((f) => <a key={f.path} href={`#${anchor(f.path)}`}>{f.path}</a>)}
      </div>
      {files.map((f) => (
        <details key={f.path} className="dfile" id={anchor(f.path)} open>
          <summary>
            <span className="chev"><Icon name="chev" size={12} /></span>
            <span>{f.path}</span>
            {f.status !== "modified" && <span className={`status ${f.status === "added" ? "status-passed" : "status-failed"}`}>{f.status === "added" ? "New file" : "Deleted"}</span>}
            <span className="count"><span className="add">+{f.adds}</span> <span className="del">−{f.dels}</span></span>
          </summary>
          <div className="dscroll">
            <table className="dtable">
              <tbody>
                {f.lines.map((l, i) => l.kind === "hunk" ? (
                  <tr key={i} className="hunk"><td colSpan={4}>{l.text}</td></tr>
                ) : (
                  <tr key={i} className={l.kind}>
                    <td className="ln">{l.a ?? ""}</td><td className="ln">{l.b ?? ""}</td>
                    <td className="sign" aria-label={l.kind === "add" ? "added" : l.kind === "del" ? "removed" : undefined}>{SIGN[l.kind]}</td>
                    <td>{l.text}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      ))}
    </div>
  );
}
