import { useEffect, useState } from "react";
import { api } from "./api";
import type { RunView } from "./contracts";
import { Status, StatusIcon } from "./components";

// #70 item 3: the repo's own checks, one row per tool. A check that didn't run is never shown as passed.
type Check = { tool: string; status: "PASS" | "FAIL" | "NOT_RUN" | "UNSUPPORTED" | "BLOCKED"; command: string | null;
  exit_code: number | null; new: string[]; note: string };
type RepoChecks = { checks: Check[] | null; files: string[]; reason: string | null };
// BLOCKED means we don't know (amber), not a failure; the row's note says which kind of "not run"
const CHECK = { PASS: "passed", FAIL: "failed", BLOCKED: "inconclusive", NOT_RUN: "not_run", UNSUPPORTED: "not_run" } as const;
// #70 item 8: the regression test's quality, decided by code; amber for "check this", never green for unknown
type TQ = { checks: { check: string; status: "PASS" | "FAIL" | "REVIEW_REQUIRED" | "NOT_COVERED" | "NOT_CHECKED"; note: string }[] | null; reason: string | null };
const TQ_PILL = { PASS: ["passed", "Passed"], FAIL: ["failed", "Failed"], REVIEW_REQUIRED: ["inconclusive", "Check this"],
  NOT_COVERED: ["inconclusive", "Not covered"], NOT_CHECKED: ["not_run", "Not checked"] } as const;
const TQ_LABEL: Record<string, string> = { fails_on_base: "Fails on the original code", passes_with_fix: "Passes with the fix",
  assertions: "Real assertions", mocks: "Mocks", existing_tests: "Existing tests untouched", test_location: "Follows the repo's test layout",
  new_imports: "No new dependencies", covers_issue: "Covers what the issue expects", hidden_variant: "Hidden variant" };
export const NOCHECK: Record<string, string> = {
  not_run_yet: "Not run yet.", sample_run: "Not run: sample run.", no_python_files: "Not run: no Python files changed.",
  diff_did_not_apply: "Not run: the change didn't apply in the check sandbox.", sandbox_failed: "Not run: the check sandbox failed.",
  only_deleted_files: "Not run: the change only deletes Python files.",
  unreadable: "The check ran, but its result couldn't be read.",
};

type Bisect = { status: "found" | "not_run" | "inconclusive" | "pending"; reason: string; first_bad?: string | null;
  last_good?: string | null; url?: string; probes?: { sha: string; result: "pass" | "fail" | null }[]; window?: number;
  variant?: { status: string; reason: string } | null };

export const VREASON: Record<string, string> = {
  no_sandbox: "the sandbox for writing the variant didn't start", ai_unavailable: "the AI was unavailable or over budget",
  no_variant_written: "no variant test was written", edits_non_test_files: "the variant changed non-test files",
  variant_not_failing_on_base: "the variant didn't fail on the original code, so it would prove nothing",
  no_verified_fix: "there was no verified fix to check",
};
export const HV: Record<string, [string, string]> = {
  passed: ["pass", "The fix also passes a hidden variant of the test that the fixer never saw."],
  failed: ["fail", "The fix passes the visible test but FAILS a hidden variant. It may only handle the exact case in the test."],
  not_run: ["muted", "Not run."],
  inconclusive: ["muted", "Unclear: the hidden variant's run didn't give a clean pass or fail."],
};
const WHY: Record<string, string> = {
  step_cap: "the search needed more test runs than our limit (6)", no_passing_commit_in_range: "the bug is older than the commits we checked",
  probe_unclear: "the test couldn't run cleanly on an older commit", history_unavailable: "GitHub didn't give us the commit history",
  no_history: "there's no earlier history to search", stopped: "the run was stopped",
  non_linear_history: "the passing and failing commits aren't parent and child (merges), so we can't name one commit", time_budget: "the run was close to its time limit", not_run_yet: "still running", sample_run: "sample run",
};

/** S-04 extra rows: hidden test variant (S4) and the commit that introduced the bug (S6). Unknown is shown as unknown. */
export default function ExtraChecks({ run }: { run: RunView }) {
  const [b, setB] = useState<Bisect | null>(null);
  const [failed, setFailed] = useState(false);
  const [rc, setRc] = useState<RepoChecks | null>(null);
  const [tq, setTq] = useState<TQ | null>(null);
  useEffect(() => {
    if (!run.repro) return;
    api<Bisect>(`/api/runs/${run.run_id}/bisect`).then(setB).catch(() => setFailed(true));
    api<RepoChecks>(`/api/runs/${run.run_id}/repo-checks`).then(setRc).catch(() => setRc({ checks: null, files: [], reason: "unavailable" }));
    api<TQ>(`/api/runs/${run.run_id}/test-quality`).then(setTq).catch(() => setTq({ checks: null, reason: "unavailable" }));
  }, [run.run_id, run.repro, run.updated_at]);
  if (!run.repro || !run.outcome) return null;
  const hv = run.verify?.hidden_variant;
  const why = b?.variant?.reason;
  const [cls, base] = hv ? HV[hv] ?? ["muted", hv] : ["muted", "Not run."];
  const text = hv === "passed" || hv === "failed" ? base
    : `${base.replace(/\.$/, "")}${why ? `: ${VREASON[why] ?? why}` : hv ? "" : ": there was no verified fix to check"}.`;
  const sha = (s?: string | null) => (s ? s.slice(0, 7) : "");
  return (
    <section className="card extra" aria-label="Extra checks">
      <h2>Extra checks</h2>
      <div className="extra-row">
        <span className={`dot dot-${cls}`} aria-hidden="true" />
        <div><strong>Hidden test variant</strong><p>{text}</p></div>
      </div>
      <div className="extra-row">
        <span className={`dot dot-${rc?.checks?.some((c) => c.status === "FAIL") ? "fail" : rc?.checks?.length ? "info" : "muted"}`} aria-hidden="true" />
        <div>
          <strong>The repository's own checks</strong>
          {!rc && <p>Loading…</p>}
          {/* a stored reason (sandbox failed, diff didn't apply) wins over "none configured": a failure is never shown as empty */}
          {rc && !rc.checks?.length && <p>{rc.reason ? NOCHECK[rc.reason] ?? `Not run: ${rc.reason}.`
            : rc.checks ? "None we can run: the repo configures no linter or type checker we support." : "Status unavailable."}</p>}
          {!!rc?.checks?.length && (
            <ul className="repo-checks">
              {rc.checks.map((c) => {
                return (
                  <li key={c.tool}>
                    <Status s={CHECK[c.status]} /> <strong>{c.tool}</strong>: {c.note}
                    {(c.command || c.new.length > 0) && (
                      <details><summary>Details</summary>
                        {c.command && <p><code>{c.command}</code> exited {c.exit_code ?? "without a code"}</p>}
                        {c.new.length > 0 && <ul>{c.new.slice(0, 10).map((n, i) => <li key={i}><code>{n}</code></li>)}</ul>}
                      </details>
                    )}
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      </div>
      <div className="extra-row">
        <span className={`dot dot-${tq?.checks?.some((c) => c.status === "FAIL") ? "fail" : tq?.checks?.length ? "info" : "muted"}`} aria-hidden="true" />
        <div>
          <strong>Regression test quality</strong>
          {!tq && <p>Loading…</p>}
          {tq && !tq.checks?.length && <p>{tq.reason === "no_test_yet" ? "Not checked: no regression test yet." : "Status unavailable."}</p>}
          {!!tq?.checks?.length && (
            <ul className="repo-checks">
              {tq.checks.map((c) => {
                const [cls, word] = TQ_PILL[c.status];
                return <li key={c.check}><span className={`status status-${cls}`}><StatusIcon s={cls} size={12} />{word}</span>{" "}
                  <strong>{TQ_LABEL[c.check] ?? c.check}</strong>: {c.note}</li>;
              })}
            </ul>
          )}
        </div>
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
