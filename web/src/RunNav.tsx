import { Link, NavLink } from "react-router-dom";
import { motion } from "motion/react";
import type { RunView } from "./contracts";
import { Icon, ReadinessBadge, SampleBadge } from "./components";
import { spring } from "./motion";

/** A run's own screens, in workflow order. A screen that isn't available yet is shown but not clickable. */
export function RunTabs({ run, id }: { run: RunView; id: string }) {
  const reviewable = run.status === "awaiting_approval" || !!run.approval || !!run.pr;
  const publishable = !!run.approval || !!run.pr;
  const base = "relative h-10 px-4 grid place-items-center rounded-full whitespace-nowrap text-[14.5px] font-semibold no-underline";
  const tab = (to: string, label: string, ok: boolean, end = false) =>
    ok ? (
      <NavLink to={to} end={end} className={({ isActive }) => `${base} ${isActive ? "text-ink" : "text-muted hover:text-ink"}`}>
        {({ isActive }) => (<>{isActive && <motion.span layoutId="run-tab" className="absolute inset-0 rounded-full bg-white" transition={spring} aria-hidden />}<span className="relative">{label}</span></>)}
      </NavLink>
    ) : <span className={`${base} text-faint opacity-60 cursor-not-allowed`} aria-disabled="true" title="Not available at this stage">{label}</span>;
  return (
    <nav className="tabs self-start inline-flex gap-1 p-1 rounded-full bg-soft max-w-full overflow-x-auto mb-8" aria-label="This run">
      {tab(`/runs/${id}`, "Overview", true, true)}
      {tab(`/runs/${id}/review`, "Change and approval", reviewable)}
      {run.pr ? tab(`/runs/${id}/pr`, "Pull request", true) : tab(`/connect?run=${id}`, "Publish", publishable)}
    </nav>
  );
}

/** Title and tabs. The next action lives in the page body, so the header carries none.
 *  `badge` is off on the run overview, whose decision block shows the readiness instead (one badge per screen). */
export function RunHeader({ run, id, badge = true }: { run: RunView; id: string; badge?: boolean }) {
  const real = /^[0-9a-f-]{36}$/.test(id);
  return (
    <>
      <div className="flex flex-wrap items-start justify-between gap-4 mb-6">
        <div className="min-w-0 flex-[1_1_420px]">
          <p className="crumbs"><Link to="/my-runs">My runs</Link><Icon name="chev" size={12} /><a href={run.issue.html_url}>{run.issue.repo} #{run.issue.number}</a>{!real && <SampleBadge />}</p>
          <h1>{run.issue.title}</h1>
        </div>
        {badge && <ReadinessBadge run={run} />}
      </div>
      <RunTabs run={run} id={id} />
    </>
  );
}
