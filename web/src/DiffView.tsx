import { useState } from "react";
import hljs from "highlight.js/lib/core";
import python from "highlight.js/lib/languages/python";
import ini from "highlight.js/lib/languages/ini";
import yaml from "highlight.js/lib/languages/yaml";
import json from "highlight.js/lib/languages/json";
import markdown from "highlight.js/lib/languages/markdown";
import { Icon } from "./components";
import { CopyButton } from "./ui";

hljs.registerLanguage("python", python); hljs.registerLanguage("ini", ini); hljs.registerLanguage("yaml", yaml);
hljs.registerLanguage("json", json); hljs.registerLanguage("markdown", markdown);
const LANG: Record<string, string> = { py: "python", pyi: "python", toml: "ini", cfg: "ini", ini: "ini", yml: "yaml", yaml: "yaml", json: "json", md: "markdown" };

type Line = { kind: "add" | "del" | "ctx" | "hunk"; text: string; a?: number; b?: number };
type FileDiff = { path: string; status: "added" | "deleted" | "modified"; lines: Line[]; adds: number; dels: number; raw: string[] };

/** Parse a unified git diff into files with old/new line numbers taken from each hunk header. */
export function parseDiff(text: string): FileDiff[] {
  const files: FileDiff[] = [];
  let f: FileDiff | null = null, a = 0, b = 0;
  for (const l of text.split("\n")) {
    if (l.startsWith("diff --git ")) {
      // the "+++ b/…" path below wins; this is the fallback for binary or rename-only entries
      f = { path: l.replace(/^diff --git a\/.* b\//, ""), status: "modified", lines: [], adds: 0, dels: 0, raw: [l] };
      files.push(f); continue;
    }
    if (!f) continue;
    f.raw.push(l);
    if (l.startsWith("new file mode")) f.status = "added";
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

// Line-by-line highlighting: multi-line strings may lose colour, which is acceptable for a diff (never the content).
const hl = (text: string, lang?: string) => (lang ? hljs.highlight(text, { language: lang, ignoreIllegals: true }).value : null);
const anchor = (p: string) => "f-" + p.replace(/[^a-zA-Z0-9]+/g, "-");
const SIGN = { add: "+", del: "-", ctx: " ", hunk: "" } as const;

function FileBlock({ f }: { f: FileDiff }) {
  const [open, setOpen] = useState(true);
  const lang = LANG[f.path.split(".").pop() ?? ""];
  return (
    <section className={`dfile${open ? " open" : ""}`} id={anchor(f.path)} aria-label={f.path}>
      <div className="dfile-head">
        <button className="icon-btn toggle" aria-expanded={open} onClick={() => setOpen(!open)} aria-label={open ? "Collapse file" : "Expand file"}><Icon name="chev" size={14} /></button>
        <span className="dfile-path" title={f.path}>{f.path}</span>
        {f.status !== "modified" && <span className={`status ${f.status === "added" ? "status-passed" : "status-failed"}`}>{f.status === "added" ? "New file" : "Deleted"}</span>}
        <CopyButton text={f.path} label="Path" />
        <span className="count"><span className="add">+{f.adds}</span><span className="del">−{f.dels}</span></span>
        <CopyButton text={f.raw.join("\n")} label="File diff" />
      </div>
      <div className="reveal" style={{ gridTemplateRows: open ? "1fr" : "0fr" }}><div>
        <div className="dscroll">
          <table className="dtable">
            <tbody>
              {f.lines.map((l, i) => l.kind === "hunk" ? (
                <tr key={i} className="hunk"><td colSpan={4}>{l.text}</td></tr>
              ) : (
                <tr key={i} className={l.kind}>
                  <td className="ln">{l.a ?? ""}</td><td className="ln">{l.b ?? ""}</td>
                  <td className="sign" aria-label={l.kind === "add" ? "added" : l.kind === "del" ? "removed" : undefined}>{SIGN[l.kind]}</td>
                  {(() => { const h = hl(l.text, lang); return h !== null ? <td dangerouslySetInnerHTML={{ __html: h }} /> : <td>{l.text}</td>; })()}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div></div>
    </section>
  );
}

export function DiffView({ text }: { text: string }) {
  const files = parseDiff(text);
  if (!files.length) return <p className="verdict-note">This change is empty: no file differs from the original code.</p>;
  const adds = files.reduce((n, f) => n + f.adds, 0), dels = files.reduce((n, f) => n + f.dels, 0);
  return (
    <div className="diffview" aria-label="Exact change">
      <nav className="diff-files" aria-label="Changed files">
        <span className="hint"><span>{files.length} file{files.length === 1 ? "" : "s"} changed · <span className="add">+{adds}</span> <span className="del">−{dels}</span></span>
          <CopyButton text={text} label="Whole diff" /></span>
        {files.map((f) => <a key={f.path} href={`#${anchor(f.path)}`}><Icon name="file" size={14} />{f.path}<span className="count"><span className="add">+{f.adds}</span><span className="del">−{f.dels}</span></span></a>)}
      </nav>
      {files.map((f) => <FileBlock key={f.path} f={f} />)}
    </div>
  );
}
