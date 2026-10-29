import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, ApiError } from "./api";

type Row = { run_id: string; repo: string; number: number; title: string; issue_url: string; created_at: string; has_pr: boolean;
  patchpilot: { status: string; outcome: string | null; readiness: string | null; pr_url: string | null; compare_url: string | null };
  github_pr_status: "open" | "draft" | "closed" | "merged" | null };
type Progress = { signed_in: boolean; state: "empty" | "success" | "partial";
  counts: { started: number; analyzed: number; fix_proposed: number; pr_opened: number; pr_merged: number; pr_status_unknown: number };
  rows: Row[] };

const GH: Record<string, string> = { open: "Open", draft: "Draft", closed: "Closed without merging", merged: "Merged" };

/** S-08 progress: what PatchPilot did vs what happened on GitHub, kept in separate columns. No scores, streaks or ranks. */
export default function ProgressView() {
  const [p, setP] = useState<Progress | null>(null);
  const [err, setErr] = useState<ApiError | null>(null);
  const load = () => { setErr(null); api<Progress>("/api/me/progress").then(setP).catch(setErr); };
  useEffect(load, []);
  if (err) return (
    <div className="panel failed"><h2>Couldn't load your progress</h2><p>{err.message}</p><button onClick={load}>Try again</button></div>
  );
  if (!p) return <div className="panel"><p>Loading your progress…</p></div>;
  if (p.state === "empty") return null;   // the run list below already shows the empty state
  const c = p.counts;
  return (
    <section className="progress" aria-label="Your progress">
      <h2>Your progress</h2>
      <div className="stats">
        <div className="stat"><strong>{c.analyzed}</strong><span>issues analyzed</span></div>
        <div className="stat"><strong>{c.fix_proposed}</strong><span>fixes proposed</span></div>
        <div className="stat"><strong>{c.pr_opened}</strong><span>pull requests opened</span></div>
        <div className="stat"><strong>{c.pr_merged}</strong><span>merged on GitHub</span></div>
      </div>
      {p.state === "partial" && (
        <p className="notice warn">GitHub didn't tell us the status of {c.pr_status_unknown} pull request{c.pr_status_unknown > 1 ? "s" : ""}.
          They show "Status unavailable" and aren't counted as merged. <button className="linklike" onClick={load}>Check again</button></p>
      )}
      <div className="table-wrap">
        <table className="evaltable progresstable">
          <thead><tr><th>Issue</th><th>PatchPilot</th><th>Pull request on GitHub</th></tr></thead>
          <tbody>
            {p.rows.map((r) => (
              <tr key={r.run_id}>
                <td><Link to={`/runs/${r.run_id}`}>{r.title}</Link><br />
                  <span className="hint"><a href={r.issue_url}>{r.repo} #{r.number}</a>, {new Date(r.created_at).toLocaleDateString()}</span></td>
                <td>{r.patchpilot.readiness ?? (r.patchpilot.status === "awaiting_approval" ? "Needs your approval" : "Still working")}
                  {r.patchpilot.pr_url && <><br /><a href={r.patchpilot.pr_url}>Pull request opened</a></>}
                  {!r.patchpilot.pr_url && r.patchpilot.compare_url && <><br /><a href={r.patchpilot.compare_url}>Branch pushed (open the PR yourself)</a></>}</td>
                <td>{!r.has_pr ? <span className="hint">No pull request</span>
                  : r.github_pr_status ? <span className={`gh-${r.github_pr_status}`}>{GH[r.github_pr_status]}</span>
                  : <span className="hint">Status unavailable</span>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
