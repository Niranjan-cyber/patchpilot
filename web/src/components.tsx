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

export function Stepper({ run }: { run: RunView }) {
  const steps = (run.steps ?? {}) as Record<string, { status?: CheckStatus | "running"; headline?: string | null }>;
  return (
    <ol className="stepper">
      {STEPS.map((st) => {
        const s = steps[st.id];
        return (
          <li key={st.id} className={`step step-${s?.status ?? "not_run"}`}>
            <div className="step-head"><span className="step-name">{st.label}</span><Status s={s?.status} /></div>
            {s?.headline && <p className="step-line">{s.headline}</p>}
          </li>
        );
      })}
    </ol>
  );
}

const BADGE: Record<string, string> = {
  VERIFIED_FIX: "good", FIX_NEEDS_ATTENTION: "warn", TRIAGE_ONLY: "warn", STOPPED: "muted",
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
