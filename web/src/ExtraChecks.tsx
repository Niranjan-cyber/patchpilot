import { useEffect, useState } from "react";
import { api } from "./api";
import type { RunView } from "./contracts";

type Bisect = { status: "found" | "not_run" | "inconclusive" | "pending"; reason: string; first_bad?: string | null;
  last_good?: string | null; url?: string; probes?: { sha: string; result: "pass" | "fail" | null }[]; window?: number };

const HV: Record<string, [string, string]> = {
  passed: ["pass", "The fix also passes a hidden variant of the test that the fixer never saw."],
  failed: ["fail", "The fix passes the visible test but FAILS a hidden variant. It may only handle the exact case in the test."],
  not_run: ["muted", "Not run: we couldn't write a variant that fails on the original code, so it would prove nothing."],
  inconclusive: ["muted", "Unclear: the hidden variant's run didn't give a clean pass or fail."],
};
const WHY: Record<string, string> = {
  step_cap: "the search needed more test runs than our limit (6)", no_passing_commit_in_range: "the bug is older than the commits we checked",
  probe_unclear: "the test couldn't run cleanly on an older commit", history_unavailable: "GitHub didn't give us the commit history",
  no_history: "there's no earlier history to search", time_budget: "the run was close to its time limit", not_run_yet: "still running", sample_run: "sample run",
};

/** S-04 extra rows: hidden test variant (S4) and the commit that introduced the bug (S6). Unknown is shown as unknown. */
export default function ExtraChecks({ run }: { run: RunView }) {
  const [b, setB] = useState<Bisect | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    if (!run.repro) return;
    api<Bisect>(`/api/runs/${run.run_id}/bisect`).then(setB).catch(() => setFailed(true));
  }, [run.run_id, run.repro, run.updated_at]);
  if (!run.repro || !run.outcome) return null;
  const hv = run.verify?.hidden_variant;
  const [cls, text] = hv ? HV[hv] ?? ["muted", hv] : ["muted", "Not run: there was no verified fix to check."];
  const sha = (s?: string | null) => (s ? s.slice(0, 7) : "");
  return (
    <section className="card extra" aria-label="Extra checks">
      <h2>Extra checks</h2>
      <div className="extra-row">
        <span className={`dot dot-${cls}`} aria-hidden="true" />
        <div><strong>Hidden test variant</strong><p>{text}</p></div>
      </div>
      <div className="extra-row">
        <span className={`dot dot-${b?.status === "found" ? "info" : "muted"}`} aria-hidden="true" />
        <div>
          <strong>Commit that introduced the bug</strong>
          {failed && <p>Status unavailable: we couldn't load the commit search.</p>}
          {!failed && !b && <p>Loading…</p>}
          {b?.status === "found" && (
            <p>The test passes at <code>{sha(b.last_good)}</code> and fails from <a href={b.url}><code>{sha(b.first_bad)}</code></a> on,
              so that commit likely introduced the bug ({b.probes?.length} test runs over the last {b.window} commits).</p>
          )}
          {b && b.status !== "found" && (
            <p>{b.status === "pending" ? "Not run yet" : b.status === "inconclusive" ? "Unclear" : "Not run"}: {WHY[b.reason] ?? b.reason}. We don't guess a commit.</p>
          )}
          {!!b?.probes?.length && (
            <details><summary>Show the {b.probes.length} test runs</summary>
              <ul>{b.probes.map((p) => <li key={p.sha}><code>{sha(p.sha)}</code>: {p.result === "pass" ? "passes" : p.result === "fail" ? "fails" : "couldn't tell"}</li>)}</ul>
            </details>
          )}
        </div>
      </div>
    </section>
  );
}
