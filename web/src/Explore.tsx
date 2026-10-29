import { useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { api, ApiError } from "./api";

type Suggestion = { number: number; title: string; html_url: string; score: number; signals: string[]; reasons: string[];
  effort: "small" | "medium" | "large"; comments: number; linked_pr: boolean | null };
type Result = { repo: string; language: string | null; state: "success" | "partial" | "empty" | "unsupported";
  unsupported: "not_python" | "no_tests" | null; suggestions: Suggestion[];
  repo_signals: { python: boolean | null; tests_found: boolean | null; recipe_known: boolean | null; deps_checkable: boolean | null } };

const SIGNAL: [keyof Result["repo_signals"], string][] = [
  ["python", "Python project"], ["tests_found", "Has tests"], ["recipe_known", "Install recipe found"],
  ["deps_checkable", "Dependencies can be checked"],
];
const mark = (v: boolean | null) => (v === null ? "?" : v ? "✓" : "✗");
const UNSUPPORTED = {
  not_python: "PatchPilot can only run Python projects today, so there's nothing to suggest here.",
  no_tests: "We couldn't find tests in this repository, so we couldn't verify any fix.",
};

export default function Explore() {
  const [params] = useSearchParams();
  const nav = useNavigate();
  const q = params.get("url") ?? "";
  const [url, setUrl] = useState(q);
  const [res, setRes] = useState<Result | null>(null);
  const [err, setErr] = useState<ApiError | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!q) return;
    let live = true;
    setLoading(true); setErr(null); setRes(null);
    api<Result>("/api/repos/explore", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ url: q }) })
      .then((r) => live && setRes(r)).catch((e) => live && setErr(e)).finally(() => live && setLoading(false));
    return () => { live = false; };
  }, [q]);

  return (
    <section className="explore">
      <h1>Find an issue PatchPilot can likely run</h1>
      <p className="lede">Paste a repository. We look at its open issues and pick the ones with a concrete bug we can likely reproduce in a test.</p>
      <form className="paste" onSubmit={(e) => { e.preventDefault(); nav(`/explore?url=${encodeURIComponent(url.trim())}`); }}>
        <label htmlFor="repo">GitHub repository link</label>
        <div className="paste-row">
          <input id="repo" value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://github.com/owner/repo" required />
          <button type="submit">Find issues</button>
        </div>
      </form>

      {loading && <div className="panel"><p>Reading the repository's open issues…</p></div>}
      {err && (
        <div className="panel failed">
          <h2>Couldn't check this repository</h2>
          <p>{err.message}</p>
          {err.retryAfter ? <p className="hint">Try again in about {Math.ceil(err.retryAfter / 60)} min.</p> : null}
        </div>
      )}
      {res && (
        <>
          <div className="repo-signals" aria-label="Repository checks">
            <strong><a href={`https://github.com/${res.repo}`}>{res.repo}</a></strong>
            {SIGNAL.map(([k, label]) => (
              <span key={k} className={`chip chip-${String(res.repo_signals[k])}`}>{mark(res.repo_signals[k])} {label}</span>
            ))}
          </div>
          {res.state === "unsupported" && <div className="panel failed"><p>{UNSUPPORTED[res.unsupported ?? "not_python"]}</p></div>}
          {res.state === "empty" && (
            <div className="panel">
              <h2>No good candidates right now</h2>
              <p>None of the open issues describe a concrete bug we could likely reproduce (most are docs, features, already taken, or
                too vague). You can still paste a specific issue on the <Link to="/">New run</Link> page.</p>
            </div>
          )}
          {res.state === "partial" && (
            <p className="notice warn">Some checks didn't finish (GitHub didn't answer for every issue). Items marked "?" weren't fully checked.</p>
          )}
          {!!res.suggestions.length && (
            <ol className="shortlist">
              {res.suggestions.map((s) => (
                <li key={s.number} className="card">
                  <div className="sl-head">
                    <a href={s.html_url}><strong>#{s.number} {s.title}</strong></a>
                    <span className="sample" title="Our guess from the issue text, not a measurement">Estimate: {s.effort} effort</span>
                  </div>
                  <ul className="why">{s.reasons.map((r) => <li key={r}>{r}</li>)}</ul>
                  <p className="hint">
                    {s.linked_pr === null ? "? Couldn't check whether someone already opened a pull request." : "No open pull request links this issue."}
                    {" "}{s.comments} comment{s.comments === 1 ? "" : "s"}.
                  </p>
                  <Link className="button secondary" to={`/check?url=${encodeURIComponent(s.html_url)}`}>Check this issue</Link>
                </li>
              ))}
            </ol>
          )}
        </>
      )}
    </section>
  );
}
