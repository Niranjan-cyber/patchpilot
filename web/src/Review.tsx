import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { motion } from "motion/react";
import { api, ApiError, useRun } from "./api";
import { Loading } from "./components";
import { DiffView } from "./DiffView";
import { RunHeader } from "./RunNav";

type Ctx = { revision: number; diff: string; diff_hash: string; evidence_hash: string; files: string[];
  publish_blockers: string[]; approved: boolean; pr_title: string; pr_summary: string; revise_blocked?: string | null;
  help?: { cause: string | null; tests: string[]; expected_failure: string | null } };

// contracts v0.5 §2.3: required, 20+ characters each; never judged, never in the pull request
const QUESTIONS = [
  ["what_was_broken", "What was broken?", "e.g. Dividing by zero returned None instead of raising an error."],
  ["why_this_fix", "Why does this change fix it?", "e.g. It now checks for zero first and raises ZeroDivisionError, as the docs say."],
  ["what_the_test_proves", "What does the new test prove?", "e.g. It fails on the old code and passes with the fix, so the bug can't come back unnoticed."],
] as const;
const MIN = 20;

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

export default function Review() {
  const { id = "" } = useParams();
  const nav = useNavigate();
  const { run } = useRun(id);
  const [ctx, setCtx] = useState<Ctx | null>(null);
  const [err, setErr] = useState<ApiError | null>(null);
  const [boxes, setBoxes] = useState<Record<string, boolean>>({});
  const [title, setTitle] = useState("");
  const [summary, setSummary] = useState("");
  const [answers, setAnswers] = useState<Record<string, string>>({});
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

  const hard = ctx.publish_blockers.filter((b) => !["not_approved", "not_signed_in", "issue_changed", "no_maintainer_consent"].includes(b));
  const allTicked = BOXES.every(([k]) => boxes[k]);
  const answered = QUESTIONS.every(([k]) => (answers[k] ?? "").trim().length >= MIN);
  const ready = BOXES.filter(([k]) => boxes[k]).length + QUESTIONS.filter(([k]) => (answers[k] ?? "").trim().length >= MIN).length;
  const total = BOXES.length + QUESTIONS.length;
  const approve = async () => {
    const r = await post(`/api/runs/${id}/approve`, { revision: ctx.revision, diff_hash: ctx.diff_hash, evidence_hash: ctx.evidence_hash,
      checklist: boxes, explanation: null,
      ownership: Object.fromEntries(QUESTIONS.map(([k]) => [k, (answers[k] ?? "").trim()])), pr_title: title, pr_summary: summary }, "Checking nothing changed upstream…");
    if (r) nav(`/connect?run=${id}`);
    else load();
  };

  return (
    <section className="review">
      {run ? <RunHeader run={run} id={id} /> : <p className="crumbs"><Link to={`/runs/${id}`}>Back to the run</Link></p>}
      <div>
        <h2>Review the exact change</h2>
        <p className="hint">Everything that would go into the pull request: {ctx.files.length} file{ctx.files.length === 1 ? "" : "s"}, revision {ctx.revision}. Nothing is published until you approve it and connect GitHub.</p>
      </div>
      {ctx.publish_blockers.filter((b) => BLOCKER[b]).map((b) => <p key={b} className="notice warn">{BLOCKER[b]}</p>)}
      {ctx.publish_blockers.includes("deps_inconclusive") && <div><button className="secondary-btn" onClick={() => post(`/api/runs/${id}/recheck-deps`, undefined, "Re-checking dependencies…").then(load)}>Re-check dependencies</button></div>}
      <div className="review-grid">
      <DiffView text={ctx.diff} />
      <div className="stack">
      <ol className="consequences card" aria-label="What happens when you approve">
        <li><strong>You approve this exact diff.</strong> If anything in it changes later, the approval is cancelled.</li>
        <li><strong>We open a draft pull request</strong> with this change, after checking nothing changed upstream.</li>
        <li><strong>Nothing merges.</strong> Maintainers read the draft and decide.</li>
      </ol>
      <div className="card form">
        <label>Pull request title<input value={title} onChange={(e) => setTitle(e.target.value)} maxLength={120} /></label>
        <label>Cause, in a sentence or two (shown in the pull request)<textarea rows={3} value={summary} onChange={(e) => setSummary(e.target.value)} /></label>
        <fieldset>
          <legend>Before you approve</legend>
          {BOXES.map(([k, label]) => (
            <label key={k} className="tick"><input type="checkbox" checked={!!boxes[k]} onChange={(e) => setBoxes({ ...boxes, [k]: e.target.checked })} /> {label}</label>
          ))}
        </fieldset>
        <fieldset>
          <legend>In your own words (required)</legend>
          <p className="hint">Maintainers may ask you about this change, so make sure you can explain it. A rough answer is fine. These stay in your report, not in the pull request.</p>
          {QUESTIONS.map(([k, q, eg]) => (
            <label key={k}>{q}
              <textarea rows={2} value={answers[k] ?? ""} placeholder={eg} maxLength={1000}
                onChange={(e) => setAnswers({ ...answers, [k]: e.target.value })} />
              {(answers[k] ?? "").trim().length > 0 && (answers[k] ?? "").trim().length < MIN && <span className="hint">At least {MIN} characters ({(answers[k] ?? "").trim().length} so far).</span>}
            </label>
          ))}
          {ctx.help && (ctx.help.cause || ctx.help.tests.length > 0) && (
            <details>
              <summary>Not sure? What PatchPilot found</summary>
              {ctx.help.cause && <p><strong>Likely cause:</strong> {ctx.help.cause}</p>}
              {ctx.help.tests.length > 0 && <p><strong>New test:</strong> {ctx.help.tests.map((t) => <code key={t}>{t}</code>)}
                {ctx.help.expected_failure && <> fails on the original code with: {ctx.help.expected_failure}</>}</p>}
              <p className="hint">Read the change with this in mind, then answer in your own words.</p>
            </details>
          )}
        </fieldset>
        <div className="grid gap-2" aria-live="polite">
          <div className="flex justify-between text-[13.5px]"><span className="font-semibold">{ready === total ? "Ready to approve" : "Before you can approve"}</span><span className="text-muted">{ready} of {total} done</span></div>
          <div className="h-2.5 rounded-full bg-soft overflow-hidden">
            <motion.div className={`h-full rounded-full ${ready === total ? "bg-mint-500" : "bg-peach-300"}`} animate={{ width: `${(ready / total) * 100}%` }} transition={{ type: "spring", stiffness: 200, damping: 24 }} />
          </div>
        </div>
        <div className="row !mt-0">
          <button onClick={approve} disabled={!allTicked || !answered || !!busy || hard.length > 0}>{busy ?? "Approve this change"}</button>
          <button className="secondary-btn" onClick={() => post(`/api/runs/${id}/keep-report`).then(() => nav(`/runs/${id}`))}>Keep the report only</button>
        </div>
        {err && <p className="notice warn">{err.message}</p>}
      </div>

      <div className="card form">
        <label>Want something different? Describe it and we'll run it again.
          <textarea rows={2} value={feedback} onChange={(e) => setFeedback(e.target.value)} placeholder="e.g. keep the function's public name the same" /></label>
        <p className="hint">If the test checks the wrong thing, use Rewrite the test: we write a new test, then fix again. Either way, any earlier approval is cancelled, because the change will be different.</p>
        {ctx.revise_blocked && <p className="notice warn">{ctx.revise_blocked}</p>}
        <div className="row !mt-0">
          {(["fix", "test"] as const).map((target) => (
            <button key={target} className="secondary-btn" disabled={feedback.trim().length < 3 || !!busy || !!ctx.revise_blocked}
              onClick={() => post(`/api/runs/${id}/revise`, { feedback, target }, "Starting the revision…").then((r) => r && nav(`/runs/${id}`))}>
              {target === "fix" ? "Revise the fix" : "Rewrite the test"}</button>))}
        </div>
      </div>
      </div>
      </div>
    </section>
  );
}
