import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, ApiError } from "./api";
import { Icon } from "./components";

export const RUNS_CHANGED = "pp:runs-changed";

export type PrState = "open" | "draft" | "changes_requested" | "approved" | "closed" | "merged" | "review_unavailable";
export type Row = { run_id: string; repo: string; number: number; title: string; issue_url: string; created_at: string; has_pr: boolean;
  patchpilot: { status: string; outcome: string | null; readiness: string | null; pr_url: string | null; compare_url: string | null };
  github_pr_status: PrState | null; ci: "passing" | "failing" | "pending" | null; last_activity_at: string | null;
  new_feedback: number; needs_attention: boolean };
export type Progress = { signed_in: boolean; state: "empty" | "success" | "partial";
  counts: { started: number; analyzed: number; fix_proposed: number; pr_opened: number; pr_merged: number; pr_status_unknown: number };
  rows: Row[] };

export const GH: Record<PrState, string> = { open: "Open", draft: "Draft", changes_requested: "Changes requested", approved: "Approved",
  closed: "Closed without merging", merged: "Merged", review_unavailable: "Open, review status unavailable" };
export const CI = { passing: "CI passing", failing: "CI failing", pending: "CI running" } as const;
const AWAITING: PrState[] = ["open", "draft", "changes_requested", "approved", "review_unavailable"];

export function FeedbackBadge({ runId, n }: { runId: string; n: number }) {
  return n > 0 ? <Link className="badge badge-warn feedback-badge" to={`/runs/${runId}/pr`}>
    <Icon name="message" size={13} /> {n} new on GitHub</Link> : null;
}

/** S-08 progress: GitHub's live PR status per run. The API re-reads GitHub here, so the run list reloads after it. */
export function useProgress() {
  const [p, setP] = useState<Progress | null>(null);
  const [err, setErr] = useState<ApiError | null>(null);
  const load = () => { setErr(null); api<Progress>("/api/me/progress").then((x) => { setP(x); window.dispatchEvent(new Event(RUNS_CHANGED)); }).catch(setErr); };
  useEffect(load, []);
  return { p, err, load };
}

/** What PatchPilot did, then what happened on GitHub: separate counts in one strip. No scores, streaks or ranks. */
export function ProgressSummary({ p, err, reload }: { p: Progress | null; err: ApiError | null; reload: () => void }) {
  if (err) return (
    <div className="notice warn flex flex-wrap items-center gap-3"><span>Couldn't load your pull request status: {err.message}</span>
      <button className="linklike" onClick={reload}>Try again</button></div>
  );
  const c = p?.counts;
  // client-side splits of the PRs GitHub told us about; an unknown status is in neither
  const gh = p?.rows.filter((r) => r.has_pr).map((r) => r.github_pr_status) ?? [];
  const stats: [number | undefined, string, string?][] = [
    [c?.analyzed, "issues analyzed"], [c?.fix_proposed, "fixes proposed"], [c?.pr_opened, "pull requests opened"],
    [p ? gh.filter((s) => s && AWAITING.includes(s)).length : undefined, "awaiting review"],
    [c?.pr_merged, "merged on GitHub", "text-mint-700"], [p ? gh.filter((s) => s === "closed").length : undefined, "closed, not merged"],
  ];
  return (
    <section className="progress" aria-label="Your progress" aria-busy={!p}>
      <h2 className="sr-only">Your progress</h2>
      <div className="stats">
        {stats.map(([n, label, tint], i) => (
          <div key={label} className={`stat ${i === 3 ? "stat-gh" : ""}`}>
            <span>{label}</span>
            {n === undefined ? <span className="skel-num" aria-hidden /> : <strong className={n ? tint : ""}>{n}</strong>}
          </div>
        ))}
      </div>
      {p?.state === "partial" && (
        <p className="notice warn !mt-3">GitHub didn't tell us the full status of {c!.pr_status_unknown} pull request{c!.pr_status_unknown > 1 ? "s" : ""}.
          {c!.pr_status_unknown > 1 ? " They're" : " It's"} marked unavailable below and not counted as merged. <button className="linklike" onClick={reload}>Check again</button></p>
      )}
    </section>
  );
}
