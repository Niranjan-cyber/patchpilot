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

// One drawn icon set (16px, 1.5px stroke). Status is always icon + word, never colour alone.
const PATHS: Record<string, string> = {
  check: "M3.5 8.5l3 3 6-7", x: "M4.5 4.5l7 7m0-7l-7 7", alert: "M8 4.5v4m0 2.5v.5", dash: "M4.5 8h7",
  plus: "M8 3.5v9m-4.5-4.5h9", list: "M5.5 4.5h7m-7 3.5h7m-7 3.5h7M3 4.5h.01M3 8h.01M3 11.5h.01",
  search: "M7 11.5a4.5 4.5 0 1 0 0-9 4.5 4.5 0 0 0 0 9zm3.2-1.3L13 13", gauge: "M2.5 11a5.5 5.5 0 0 1 11 0M8 11l2.5-3",
  arrow: "M3.5 8h9m-3.5-3.5L12.5 8 9 11.5", chev: "M6 4l4 4-4 4", menu: "M3 5h10M3 8h10M3 11h10",
  github: "M8 1.8a6.2 6.2 0 0 0-2 12.1c.3 0 .4-.1.4-.3v-1.1c-1.7.4-2.1-.8-2.1-.8-.3-.7-.7-.9-.7-.9-.6-.4 0-.4 0-.4.6 0 .9.7.9.7.6 1 1.5.7 1.9.5 0-.4.2-.7.4-.9-1.4-.2-2.8-.7-2.8-3.1 0-.7.2-1.2.6-1.7-.1-.2-.3-.8.1-1.6 0 0 .5-.2 1.7.6a5.8 5.8 0 0 1 3.1 0c1.2-.8 1.7-.6 1.7-.6.3.8.1 1.4.1 1.6.4.4.6 1 .6 1.7 0 2.4-1.5 2.9-2.8 3.1.2.2.4.6.4 1.1v1.7c0 .2.1.4.4.3A6.2 6.2 0 0 0 8 1.8z",
  file: "M4 2.5h5l3 3v8H4zM9 2.5v3h3", pause: "M6 4v8m4-8v8", clock: "M8 13.5a5.5 5.5 0 1 0 0-11 5.5 5.5 0 0 0 0 11zM8 5v3l2 1.5",
  copy: "M5.5 5.5V3.5h7v7h-2M3.5 5.5h7v7h-7z", activity: "M2 8h2.5l2-4.5 3 9 2-4.5H14",
  flask: "M6.5 2.5v4L3 12.5a1 1 0 0 0 .9 1.5h8.2a1 1 0 0 0 .9-1.5L9.5 6.5v-4M5.5 2.5h5", shield: "M8 2l5 2v4c0 3-2.2 5.2-5 6-2.8-.8-5-3-5-6V4z",
  commit: "M8 10.5a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5zM2 8h3.5m5 0H14", eye: "M1.5 8S4 3.5 8 3.5 14.5 8 14.5 8 12 12.5 8 12.5 1.5 8 1.5 8zM8 10a2 2 0 1 0 0-4 2 2 0 0 0 0 4z",
  terminal: "M2.5 3.5h11v9h-11zM5 6.5l2 1.5-2 1.5M8.5 10h2.5", stop: "M4.5 4.5h7v7h-7z", external: "M9.5 2.5h4v4M13.5 2.5L8 8M12 9v4.5H2.5V4H7",
};
export function Icon({ name, size = 16 }: { name: keyof typeof PATHS | string; size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d={PATHS[name]} />
    </svg>
  );
}
const STATUS_ICON: Record<string, string> = { passed: "check", failed: "x", blocked: "x", inconclusive: "alert", not_run: "dash" };
/** Running is a spinning ring: the only motion that reports work, stopped by reduced-motion. */
export function StatusIcon({ s, size = 14 }: { s: string; size?: number }) {
  if (s === "running") return (
    <svg width={size} height={size} viewBox="0 0 16 16" fill="none" aria-hidden>
      <circle cx="8" cy="8" r="5.5" stroke="currentColor" strokeOpacity=".25" strokeWidth="1.5" />
      <path className="spin" d="M8 2.5a5.5 5.5 0 0 1 5.5 5.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  );
  return <Icon name={STATUS_ICON[s] ?? "dash"} size={size} />;
}

export function Status({ s }: { s?: CheckStatus | "running" | null }) {
  const k = s ?? "not_run";
  return <span className={`status status-${k}`}><StatusIcon s={k} size={12} />{WORD[k]}</span>;
}

/** The product mark: a patch square in the one hue. */
export function Mark({ size = 22 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 22 22" aria-hidden>
      <rect width="22" height="22" rx="5" fill="var(--accent)" />
      <path d="M7 15.5V6.5h4.2a2.8 2.8 0 0 1 0 5.6H7" fill="none" stroke="#fff" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M13.5 15.5h2" stroke="#fff" strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
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
    <div className={`live${run.status === "paused" ? " paused" : ""}`}>
      <p className="live-now"><StatusIcon s={run.status === "paused" ? "inconclusive" : "running"} size={16} />{run.status === "paused" ? "Paused" : label}</p>
      <div className={`meter${run.status === "paused" ? " meter-paused" : ""}`} role="progressbar" aria-label="Steps finished" aria-valuemin={0} aria-valuemax={STEPS.length} aria-valuenow={done}>
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
  if (!run.outcome) return <div className={`badge ${run.status === "paused" ? "status-inconclusive" : "status-running"}`} role="status"><StatusIcon s={run.status === "paused" ? "inconclusive" : "running"} size={12} />{run.status === "paused" ? "Paused" : "Working"}</div>;
  const k = BADGE[run.outcome] ?? "bad";
  return <div className={`badge badge-${k}`}><StatusIcon s={k === "good" ? "passed" : k === "warn" ? "inconclusive" : k === "muted" ? "not_run" : "failed"} size={12} />{run.readiness}</div>;
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
        <h3>On the original code <code title={run.base_sha}>{run.base_sha?.slice(0, 7)}</code></h3>
        <div className="proof-runs">{before.map((s, i) => <span key={i} className={`run run-${s}`}><StatusIcon s={s} />Run {i + 1}: {WORD[s]}</span>)}</div>
      </div>
      <div className="proof-arrow" aria-hidden><Icon name="arrow" size={14} /></div>
      <div className="proof-col">
        <h3>After the fix, in a fresh sandbox</h3>
        <div className="proof-runs">
          {after.length ? after.map((s, i) => <span key={i} className={`run run-${s}`}><StatusIcon s={s} />Run {i + 1}: {WORD[s]}</span>)
            : <span className="run run-not_run"><StatusIcon s="not_run" />Not verified</span>}
        </div>
      </div>
      <p className="proof-test"><span>Regression test</span><code>{run.repro?.test_ids.join(", ")}</code></p>
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
  const [copied, setCopied] = useState<"" | "ok" | "failed">("");
  if (!a) return null;
  const saved = a.decision_reasons?.includes("saved_by_user");   // the user chose "Save the assessment report"
  const d = saved ? { title: "Assessment saved", text: "You saved this assessment without starting a fix attempt, so nothing ran." }
    : DECISION[a.handling_decision];
  // no clipboard API on plain http (or it's blocked): say so instead of throwing
  const copy = () => {
    const p = navigator.clipboard?.writeText(a.draft_comment ?? "");
    if (!p) { setCopied("failed"); return; }
    p.then(() => setCopied("ok"), () => setCopied("failed"));
  };
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
          <button type="button" className="secondary" onClick={copy}>{copied === "ok" ? "Copied" : "Copy comment"}</button>
          {copied === "failed" && <p className="notice warn" role="status">Couldn't copy here. Select the text above and copy it yourself.</p>}
        </div>
      )}
    </div>
  );
}
