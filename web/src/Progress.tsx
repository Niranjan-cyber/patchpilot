import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, ApiError } from "./api";
import { Icon } from "./components";

export const RUNS_CHANGED = "pp:runs-changed";

type PrState = "open" | "draft" | "changes_requested" | "approved" | "closed" | "merged" | "review_unavailable";
type Row = { run_id: string; repo: string; number: number; title: string; issue_url: string; created_at: string; has_pr: boolean;
  patchpilot: { status: string; outcome: string | null; readiness: string | null; pr_url: string | null; compare_url: string | null };
  github_pr_status: PrState | null; ci: "passing" | "failing" | "pending" | null; last_activity_at: string | null;
  new_feedback: number; needs_attention: boolean };
type Progress = { signed_in: boolean; state: "empty" | "success" | "partial";
  counts: { started: number; analyzed: number; fix_proposed: number; pr_opened: number; pr_merged: number; pr_status_unknown: number };
  rows: Row[] };

const GH: Record<PrState, string> = { open: "Open", draft: "Draft", changes_requested: "Changes requested", approved: "Approved",
  closed: "Closed without merging", merged: "Merged", review_unavailable: "Open, review status unavailable" };
const CI = { passing: "CI passing", failing: "CI failing", pending: "CI running" } as const;

export function FeedbackBadge({ runId, n }: { runId: string; n: number }) {
  return n > 0 ? <Link className="badge badge-warn feedback-badge" to={`/runs/${runId}/pr`}>
    <Icon name="message" size={13} /> {n} new on GitHub</Link> : null;
}

/** S-08 progress: what PatchPilot did vs what happened on GitHub, kept in separate columns. No scores, streaks or ranks. */
export default function ProgressView() {
  const [p, setP] = useState<Progress | null>(null);
  const [err, setErr] = useState<ApiError | null>(null);
  const [attention, setAttention] = useState(false);
  // the API re-reads GitHub here, so the nav and run-list badges reload after it
  const load = () => { setErr(null); api<Progress>("/api/me/progress").then((x) => { setP(x); window.dispatchEvent(new Event(RUNS_CHANGED)); }).catch(setErr); };
  useEffect(load, []);
  if (err) return (
    <div className="panel failed"><h2>Couldn't load your progress</h2><p>{err.message}</p><button onClick={load}>Try again</button></div>
  );
  if (!p) return <div className="panel"><p>Loading your progress…</p></div>;
  if (p.state === "empty") return null;   // the run list below already shows the empty state
  const c = p.counts;
  const need = p.rows.filter((r) => r.needs_attention).length;
  const rows = attention ? p.rows.filter((r) => r.needs_attention) : p.rows;
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
      <div className="row history-filter" role="group" aria-label="Show">
        <button className={attention ? "secondary" : ""} aria-pressed={!attention} onClick={() => setAttention(false)}>All runs</button>
        <button className={attention ? "" : "secondary"} aria-pressed={attention} onClick={() => setAttention(true)}>
          Needs your attention ({need})</button>
      </div>
      {attention && !need ? <p className="hint">Nothing needs you right now: no new maintainer feedback, failing CI or approvals waiting.</p> : (
      <div className="table-wrap">
        <table className="evaltable progresstable">
          <thead><tr><th>Issue</th><th>PatchPilot</th><th>Pull request on GitHub</th></tr></thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.run_id}>
                <td><Link to={`/runs/${r.run_id}`}>{r.title}</Link><br />
                  <span className="hint"><a href={r.issue_url}>{r.repo} #{r.number}</a>, {new Date(r.created_at).toLocaleDateString()}</span></td>
                <td>{r.patchpilot.readiness ?? (r.patchpilot.status === "awaiting_approval" ? "Needs your approval" : "Still working")}
                  {r.patchpilot.pr_url && <><br /><a href={r.patchpilot.pr_url}>Pull request opened</a></>}
                  {!r.patchpilot.pr_url && r.patchpilot.compare_url && <><br /><a href={r.patchpilot.compare_url}>Branch pushed (open the PR yourself)</a></>}</td>
                <td>{!r.has_pr ? <span className="hint">No pull request</span> : <>
                  {r.github_pr_status ? <span className={`gh-${r.github_pr_status}`}>{GH[r.github_pr_status]}</span>
                    : <span className="hint">Status unavailable</span>}
                  {r.ci && <span className={`ci ci-${r.ci}`}> · {CI[r.ci]}</span>}
                  {r.last_activity_at && <><br /><span className="hint">Maintainer activity {new Date(r.last_activity_at).toLocaleDateString()}</span></>}
                  {r.new_feedback > 0 && <><br /><FeedbackBadge runId={r.run_id} n={r.new_feedback} /></>}
                </>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>)}
    </section>
  );
}
