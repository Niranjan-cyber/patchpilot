import { useEffect, useState } from "react";
import { api, ApiError } from "./api";

type Row = { id: string; kind: "planted" | "swebench"; issue_url: string | null; run_id: string | null;
  outcome: string | null; official: "pass" | "fail" | null; seconds: number | null; note: string | null; verdict: string };
type Summary = { generated_at: string | null; commit: string | null; state: "success" | "partial" | "failed";
  counts: Record<string, number | null>; rows: Row[] };

const OUTCOME: Record<string, string> = {
  VERIFIED_FIX: "Verified fix", FIX_NEEDS_ATTENTION: "Fix needs attention", TRIAGE_ONLY: "Triage only",
  CANNOT_REPRODUCE: "Couldn't reproduce", ENV_FAILED: "Setup failed", BLOCKED: "Blocked", STOPPED: "Stopped",
  SYSTEM_ERROR: "System error",
};
const OFFICIAL = { pass: "Pass", fail: "Fail" } as const;
const mins = (s: number | null) => (s == null ? "—" : `${Math.round(s / 6) / 10} min`);

function Stat({ n, label, bad }: { n: number | null | undefined; label: string; bad?: boolean }) {
  return <div className={`stat${bad ? " stat-bad" : ""}`}><strong>{n ?? "—"}</strong><span>{label}</span></div>;
}

export default function Eval() {
  const [s, setS] = useState<Summary | null>(null);
  const [err, setErr] = useState<ApiError | null>(null);
  useEffect(() => { api<Summary>("/api/eval").then(setS).catch(setErr); }, []);

  if (err) return (
    <section className="panel failed">
      <h1>No eval results yet</h1>
      <p>{err.message}</p>
      <p className="hint">Results appear here after the eval script runs on the server. We show no numbers until then.</p>
    </section>
  );
  if (!s) return <section className="panel"><p>Loading the eval…</p></section>;
  const c = s.counts;
  return (
    <section className="eval">
      <h1>How often is PatchPilot right?</h1>
      <p className="lede">PatchPilot has run on {(c.total ?? 0) - (c.no_result ?? 0)} of {c.total} eval issues. We check every
        fix against the project's own official tests, which PatchPilot never sees. A "verified" claim the official tests
        reject counts against us.</p>
      <div className="stats">
        <Stat n={c.confirmed} label={`of ${c.verified} verified fixes confirmed`} />
        <Stat n={c.false_verified} label="false verified claims (target 0)" bad={!!c.false_verified} />
        <Stat n={c.triage} label="triage only" />
        <Stat n={c.unable} label="couldn't run" />
        <Stat n={c.no_result} label="not run yet" />
      </div>
      {s.state === "partial" && (
        <p className="notice warn">Some cases haven't finished or haven't been checked yet. They show unknown, not pass.</p>
      )}
      {s.state === "failed" && (
        <p className="notice warn">None of the cases have results yet. The table lists what will be run.</p>
      )}
      <div className="table-wrap">
        <table className="evaltable">
          <thead><tr><th>Issue</th><th>Source</th><th>PatchPilot said</th><th>Official tests</th><th>Time</th><th>Notes</th></tr></thead>
          <tbody>
            {s.rows.map((r) => (
              <tr key={r.id} className={r.verdict === "false_verified" ? "row-bad" : undefined}>
                <td>{r.issue_url ? <a href={r.issue_url}>{r.id}</a> : r.id}</td>
                <td>{r.kind === "swebench" ? "SWE-bench Lite" : "Planted bug"}</td>
                <td>{r.outcome ? OUTCOME[r.outcome] ?? r.outcome : <span className="hint">Not run yet</span>}</td>
                <td>{r.official ? <span className={`pill-${r.official}`}>{OFFICIAL[r.official]}</span>
                  : <span className="hint">Unknown</span>}</td>
                <td>{mins(r.seconds)}</td>
                <td>{r.verdict === "false_verified" ? <strong>Claimed verified, official tests fail</strong> : r.note ?? ""}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="hint">
        {s.generated_at ? `Run ${new Date(s.generated_at).toLocaleString()}` : "Not run yet"}
        {s.commit && <> on commit <code>{s.commit}</code></>}. Median time {mins(c.median_seconds)}.
        Planted bugs are graded by PatchPilot's own outcome only; SWE-bench cases by their official tests.
      </p>
    </section>
  );
}
