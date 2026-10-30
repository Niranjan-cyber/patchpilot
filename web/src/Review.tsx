import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, ApiError } from "./api";
import { Loading } from "./components";

type Ctx = { revision: number; diff: string; diff_hash: string; evidence_hash: string; files: string[];
  publish_blockers: string[]; approved: boolean; pr_title: string; pr_summary: string };

const BOXES = [
  ["read_diff", "I read every change below"],
  ["understands_change", "I understand what it changes and why"],
  ["ai_note_ok", "The pull request may say that AI helped write it"],
] as const;

const BLOCKER: Record<string, string> = {
  deps_inconclusive: "We couldn't fully check this project's dependencies, so publishing is turned off. You can re-check them.",
  repo_forbids_ai: "This repository doesn't accept AI-assisted pull requests. You can keep the report and diff.",
  issue_changed: "Since your run started, the issue was closed or someone linked a pull request to it.",
  upstream_changed: "Files in this change were edited upstream after we tested, so we won't publish a change that was never tested against that code.",
};

function Diff({ text }: { text: string }) {
  return (
    <pre className="diff" aria-label="Exact change">
      {text.split("\n").map((l, i) => (
        <span key={i} className={l.startsWith("diff --git") ? "d-file" : l.startsWith("+") && !l.startsWith("+++") ? "d-add"
          : l.startsWith("-") && !l.startsWith("---") ? "d-del" : l.startsWith("@@") ? "d-hunk" : ""}>{l}{"\n"}</span>
      ))}
    </pre>
  );
}

export default function Review() {
  const { id = "" } = useParams();
  const nav = useNavigate();
  const [ctx, setCtx] = useState<Ctx | null>(null);
  const [err, setErr] = useState<ApiError | null>(null);
  const [boxes, setBoxes] = useState<Record<string, boolean>>({});
  const [title, setTitle] = useState("");
  const [summary, setSummary] = useState("");
  const [explain, setExplain] = useState("");
  const [feedback, setFeedback] = useState("");
  const [busy, setBusy] = useState<string | null>(null);

  const load = () => api<Ctx>(`/api/runs/${id}/approval`).then((c) => {
    // a reload never overwrites what the user already typed
    setCtx(c); setTitle((t) => t || c.pr_title); setSummary((s) => s || c.pr_summary);
  }).catch(setErr);
  useEffect(() => { load(); }, [id]);

  const post = async (path: string, body?: unknown, label = "Working…") => {
    setBusy(label); setErr(null);
    try { return await api(path, { method: "POST", headers: { "content-type": "application/json" }, body: body ? JSON.stringify(body) : undefined }); }
    catch (e) { setErr(e as ApiError); return null; } finally { setBusy(null); }
  };

  if (!ctx) return err ? <section className="panel failed"><h1>Couldn't open the change</h1><p>{err.message}</p><Link className="button secondary" to={`/runs/${id}`}>Back to the run</Link></section>
    : <Loading label="Loading the exact change…" />;

  const hard = ctx.publish_blockers.filter((b) => !["not_approved", "not_signed_in", "issue_changed"].includes(b));
  const allTicked = BOXES.every(([k]) => boxes[k]);
  const approve = async () => {
    const r = await post(`/api/runs/${id}/approve`, { revision: ctx.revision, diff_hash: ctx.diff_hash, evidence_hash: ctx.evidence_hash,
      checklist: boxes, explanation: explain || null, pr_title: title, pr_summary: summary }, "Checking nothing changed upstream…");
    if (r) nav(`/connect?run=${id}`);
    else load();
  };

  return (
    <section className="review">
      <div className="chapter">
        <p className="issue-ref"><Link to={`/runs/${id}`}>Back to the run</Link></p>
        <h1>Review the exact change</h1>
        <p className="lede">This is everything that would go into the pull request: {ctx.files.length} file{ctx.files.length === 1 ? "" : "s"}. Nothing is published until you approve it and connect GitHub.</p>
      </div>
      <ol className="consequences" aria-label="What happens when you approve">
        <li><strong>You approve this exact diff.</strong> If anything in it changes later, the approval is cancelled.</li>
        <li><strong>We open a draft pull request</strong> with this change, after checking nothing changed upstream.</li>
        <li><strong>Nothing merges.</strong> Maintainers read the draft and decide.</li>
      </ol>
      {ctx.publish_blockers.filter((b) => BLOCKER[b]).map((b) => <p key={b} className="notice warn">{BLOCKER[b]}</p>)}
      {ctx.publish_blockers.includes("deps_inconclusive") && <button className="secondary-btn" onClick={() => post(`/api/runs/${id}/recheck-deps`, undefined, "Re-checking dependencies…").then(load)}>Re-check dependencies</button>}
      <Diff text={ctx.diff} />

      <div className="card form">
        <label>Pull request title<input value={title} onChange={(e) => setTitle(e.target.value)} maxLength={120} /></label>
        <label>Summary for maintainers<textarea rows={3} value={summary} onChange={(e) => setSummary(e.target.value)} /></label>
        <fieldset>
          <legend>Before you approve</legend>
          {BOXES.map(([k, label]) => (
            <label key={k} className="tick"><input type="checkbox" checked={!!boxes[k]} onChange={(e) => setBoxes({ ...boxes, [k]: e.target.checked })} /> {label}</label>
          ))}
        </fieldset>
        <label>In your own words, what does this change do? (optional)<textarea rows={2} value={explain} onChange={(e) => setExplain(e.target.value)} maxLength={2000} /></label>
        <div className="row">
          <button onClick={approve} disabled={!allTicked || !!busy || hard.length > 0}>{busy ?? "Approve this change"}</button>
          <button className="secondary-btn" onClick={() => post(`/api/runs/${id}/keep-report`).then(() => nav(`/runs/${id}`))}>Keep the report only</button>
        </div>
        {err && <p className="notice warn">{err.message}</p>}
      </div>

      <div className="card form">
        <label>Want something different? Describe it and we'll re-run the fix and verification.
          <textarea rows={2} value={feedback} onChange={(e) => setFeedback(e.target.value)} placeholder="e.g. keep the function's public name the same" /></label>
        <p className="hint">Revising cancels any earlier approval, because the change will be different.</p>
        <button className="secondary-btn" disabled={feedback.trim().length < 3 || !!busy}
          onClick={() => post(`/api/runs/${id}/revise`, { feedback }, "Starting the revision…").then((r) => r && nav(`/runs/${id}`))}>Revise the fix</button>
      </div>
    </section>
  );
}
