import { Link, NavLink, useLocation } from "react-router-dom";
import type { RunView } from "./contracts";
import { Icon, ReadinessBadge, SampleBadge } from "./components";
import { useIndicator } from "./ui";

/** A run's own screens, in workflow order. A screen that isn't available yet is shown but not clickable. */
export function RunTabs({ run, id }: { run: RunView; id: string }) {
  const here = useLocation();
  const { box, style } = useIndicator<HTMLElement>("a.active", [here.pathname, here.search], "x");
  const reviewable = run.status === "awaiting_approval" || !!run.approval || !!run.pr;
  const publishable = !!run.approval || !!run.pr;
  const tab = (to: string, label: string, ok: boolean, end = false) =>
    ok ? <NavLink to={to} end={end}>{label}</NavLink> : <span aria-disabled="true" title="Not available at this stage">{label}</span>;
  return (
    <nav className="tabs" aria-label="This run" ref={box}>
      <span className="tab-ink" style={style} aria-hidden />
      {tab(`/runs/${id}`, "Overview", true, true)}
      {tab(`/runs/${id}/review`, "Change and approval", reviewable)}
      {run.pr ? tab(`/runs/${id}/pr`, "Pull request", true) : tab(`/connect?run=${id}`, "Publish", publishable)}
    </nav>
  );
}

/** Title and tabs. The next action lives in the page body (one button per screen), so the header carries none.
 *  `badge` is off on the run overview, whose decision block shows the readiness instead (one badge per screen). */
export function RunHeader({ run, id, badge = true }: { run: RunView; id: string; badge?: boolean }) {
  const real = /^[0-9a-f-]{36}$/.test(id);
  return (
    <>
      <div className="page-head">
        <div>
          <p className="crumbs"><Link to="/my-runs">My runs</Link><Icon name="chev" size={12} /><a href={run.issue.html_url}>{run.issue.repo} #{run.issue.number}</a>{!real && <SampleBadge />}</p>
          <h1>{run.issue.title}</h1>
        </div>
        {badge && <div className="actions"><ReadinessBadge run={run} /></div>}
      </div>
      <RunTabs run={run} id={id} />
    </>
  );
}
