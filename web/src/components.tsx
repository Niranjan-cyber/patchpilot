import { useState } from "react";
import type { CheckStatus, RunView, StepId } from "./contracts";

export const STEPS: { id: StepId; label: string }[] = [
  { id: "preflight", label: "Safety check" }, { id: "setup", label: "Setup" },
  { id: "baseline", label: "Existing tests" }, { id: "reproduce", label: "Reproduce" },
  { id: "diagnose", label: "Diagnose" }, { id: "fix", label: "Fix" },
  { id: "verify", label: "Verify" }, { id: "review", label: "Review" },
];

const WORD: Record<string, string> = {
  passed: "Passed", failed: "Failed", inconclusive: "Inconclusive", not_run: "Not run",
  blocked: "Blocked", running: "Running",
};

export function Status({ s }: { s?: CheckStatus | "running" | null }) {
  const k = s ?? "not_run";
  return <span className={`status status-${k}`}>{WORD[k]}</span>;
}

export function SampleBadge() {
  return <span className="sample" title="This screen shows sample data, not a real run">Sample data</span>;
}

type StepMap = Record<string, { status?: CheckStatus | "running"; headline?: string | null }>;

export function Stepper({ run }: { run: RunView }) {
  const steps = (run.steps ?? {}) as StepMap;
  return (
    <ol className="stepper" aria-label="What PatchPilot did">
      {STEPS.map((st) => {
        const s = steps[st.id];
        return (
          <li key={st.id} className={`step step-${s?.status ?? "not_run"}`} aria-current={s?.status === "running" ? "step" : undefined}>
            <div className="step-head"><span className="step-name">{st.label}</span><Status s={s?.status} /></div>
            {s?.headline && <p className="step-line">{s.headline}</p>}
          </li>
        );
      })}
    </ol>
  );
}

/** A designed loading state: what we're doing in words, plus a quiet placeholder of the content to come. */
export function Loading({ label }: { label: string }) {
  return (
    <section className="panel loading" aria-busy="true" aria-live="polite">
      <p>{label}</p>
      <div className="skel" aria-hidden><span /><span /><span /></div>
    </section>
  );
}

/** For a run that's still going: which step is on, and how far along it is. Counts only recorded step states. */
export function LiveStatus({ run }: { run: RunView }) {
  const steps = (run.steps ?? {}) as StepMap;
  const done = STEPS.filter((st) => steps[st.id]?.status && steps[st.id]?.status !== "running" && steps[st.id]?.status !== "not_run").length;
  const now = STEPS.find((st) => steps[st.id]?.status === "running") ?? STEPS.find((st) => !steps[st.id]?.status || steps[st.id]?.status === "not_run");
  const label = run.status === "queued" ? "Waiting for a free sandbox" : now ? `Now: ${now.label}` : "Finishing up";
  return (
    <div className="live">
      <p className="live-now">{label}</p>
      <div className="meter" role="progressbar" aria-label="Steps finished" aria-valuemin={0} aria-valuemax={STEPS.length} aria-valuenow={done}>
        <span style={{ width: `${(done / STEPS.length) * 100}%` }} />
      </div>
      <p className="live-count">{done} of {STEPS.length} steps finished. You can leave this page; the run keeps going.</p>
    </div>
  );
}

const VERDICT: Record<string, string> = {
  CANNOT_REPRODUCE: "We couldn't make the bug happen in a test, so there's no fix to prove. The report says what we tried.",
  ENV_FAILED: "We couldn't install this project in the sandbox, so none of its code ran. The report has the install log.",
  BLOCKED: "A dependency looked malicious, so nothing from this repository was installed or run.",
  STOPPED: "This run was stopped. Everything recorded up to that point is kept below.",
  SYSTEM_ERROR: "Something on our side failed. The report has what we know; nothing was published.",
};

/** Runs that end without a proof strip still say plainly why, never an empty space. */
export function VerdictNote({ run }: { run: RunView }) {
  const text = run.outcome && VERDICT[run.outcome];
  return text && !run.repro?.runs_on_base?.length ? <p className="verdict-note">{text}</p> : null;
}

const BADGE: Record<string, string> = {
  VERIFIED_FIX: "good", FIX_NEEDS_ATTENTION: "warn", TRIAGE_ONLY: "warn", STOPPED: "muted", ASSESSMENT_ONLY: "muted",
};

export function ReadinessBadge({ run }: { run: RunView }) {
  if (!run.outcome) return <div className="badge badge-muted">Still working</div>;
  return <div className={`badge badge-${BADGE[run.outcome] ?? "bad"}`}>{run.readiness}</div>;
}

/** The winning feature: same test, red on the original code, green after the fix, in a fresh sandbox. */
export function ProofPanel({ run }: { run: RunView }) {
  const before = run.repro?.runs_on_base ?? [];
  const after = run.verify?.new_test_runs ?? [];
  if (!before.length) return null;
  const base = run.baseline;
  return (
    <section className="proof" aria-label="Proof that the fix works">
      <div className="proof-col">
        <h3>On the original code</h3>
        <div className="proof-runs">{before.map((s, i) => <span key={i} className={`run run-${s}`}>Run {i + 1}: {WORD[s]}</span>)}</div>
      </div>
      <div className="proof-arrow" aria-hidden>➜</div>
      <div className="proof-col">
        <h3>After the fix, in a fresh sandbox</h3>
        <div className="proof-runs">
          {after.length ? after.map((s, i) => <span key={i} className={`run run-${s}`}>Run {i + 1}: {WORD[s]}</span>)
            : <span className="run run-not_run">Not verified</span>}
        </div>
      </div>
      <p className="proof-test"><code>{run.repro?.test_ids.join(", ")}</code></p>
      {base && (
        <p className="proof-base">
          {base.pass_set?.length ?? 0} existing tests passed before{run.verify ? ` and still pass` : ""}.
          {(base.fail_set?.length ?? 0) > 0 && ` ${base.fail_set?.length} ${base.fail_set?.length === 1 ? "was" : "were"} already failing before we started (not caused by this fix).`}
        </p>
      )}
    </section>
  );
}

// #48 intake assessment. Wording mirrors backend/github/assess.py DECISION_TEXT (shortcut: duplicated, move to the API if it drifts).
const DECISION: Record<string, { title: string; text: string; next?: string }> = {
  READY: { title: "Ready for a fix attempt", text: "A bug or regression with enough detail, in a supported Python project." },
  NEEDS_INFORMATION: { title: "Needs more information", text: "It looks like a bug, but the issue doesn't say what should happen or show how to trigger it.",
    next: "Ask for the missing details on the issue (draft below), or start anyway." },
  UNSUPPORTED: { title: "Can't run this project", text: "PatchPilot can read issues from any public repository, but it can only run Python projects with pip and pytest today.",
    next: "Pick an issue from a Python project with tests, or work on this one by hand." },
  ALREADY_ADDRESSED: { title: "May already be handled", text: "An open pull request may already address this, or the issue is closed. Lookups can be wrong, so check it; you can still start." },
  HUMAN_DECISION: { title: "Your call", text: "Something we need is unknown or unclear (the warnings below say what), so you decide whether to go ahead.",
    next: "Start anyway if you've read it and it is a bug PatchPilot can run." },
  ASSESSMENT_ONLY: { title: "Assessment only", text: "This isn't a bug report, so PatchPilot assesses it but doesn't change any code. Fixes run only for bugs and regressions.",
    next: "Work on it by hand, or pick a bug report instead." },
};
const MISSING: Record<string, string> = {
  no_expected: "What should happen instead", no_actual: "What happens now (output, error or traceback)",
  no_repro: "A small code example or steps to trigger it",
};

export function AssessmentCard({ a }: { a?: RunView["assessment"] }) {
  const [copied, setCopied] = useState(false);
  if (!a) return null;
  const d = DECISION[a.handling_decision];
  const copy = () => navigator.clipboard?.writeText(a.draft_comment ?? "").then(() => setCopied(true), () => setCopied(false));
  return (
    <div className={`card assessment assessment-${a.handling_decision.toLowerCase()}`}>
      <h2>{d.title}</h2>
      <p>{d.text}</p>
      {a.problem_summary && <p className="hint">AI summary of the issue (may be wrong; it never decides): {a.problem_summary}</p>}
      <ul className="assessment-facts">
        <li>Issue type: <strong>{a.issue_type.replaceAll("_", " ")}</strong>{a.issue_type_source === "none" ? " (no clear signal)" : ""}</li>
        <li>Can PatchPilot run it: <strong>{a.compatibility_status === "supported" ? "yes" : a.compatibility_status === "unsupported" ? "no" : "unknown"}</strong></li>
        {!!a.existing_resolution?.length && <li>Open pull requests mentioning it: {a.existing_resolution.map((n) => `#${n}`).join(", ")}</li>}
      </ul>
      {!!a.acceptance_conditions?.length && (
        <><h3>What a fix must do, per the issue (AI-extracted)</h3><ul>{a.acceptance_conditions.map((c) => <li key={c}>{c}</li>)}</ul></>
      )}
      {!!a.missing_information?.length && (
        <><h3>Missing from the issue</h3><ul>{a.missing_information.map((m) => <li key={m}>{MISSING[m] ?? m}</li>)}</ul></>
      )}
      {d.next && <p className="hint">Next step: {d.next}</p>}
      {a.draft_comment && (
        <div className="draft">
          <h3>Draft comment for the issue</h3>
          <p className="hint">PatchPilot never posts it. Copy it and post it yourself if it helps.</p>
          <pre>{a.draft_comment}</pre>
          <button type="button" className="secondary" onClick={copy}>{copied ? "Copied" : "Copy comment"}</button>
        </div>
      )}
    </div>
  );
}
