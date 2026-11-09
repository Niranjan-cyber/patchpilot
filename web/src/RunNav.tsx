import { Link, NavLink, useLocation } from "react-router-dom";
import type { RunView } from "./contracts";
import { Icon, ReadinessBadge, SampleBadge } from "./components";

/** A run's own screens, in workflow order. A screen that isn't available yet is shown but not clickable. */
export function RunTabs({ run, id }: { run: RunView; id: string }) {
  const reviewable = run.status === "awaiting_approval" || !!run.approval || !!run.pr;
  const publishable = !!run.approval || !!run.pr;
  const tab = (to: string, label: string, ok: boolean, end = false) =>
    ok ? <NavLink to={to} end={end}>{label}</NavLink> : <span aria-disabled="true" title="Not available at this stage">{label}</span>;
  return (
    <nav className="tabs" aria-label="This run">
      {tab(`/runs/${id}`, "Overview", true, true)}
      {tab(`/runs/${id}/review`, "Change and approval", reviewable)}
      {run.pr ? tab(`/runs/${id}/pr`, "Pull request", true) : tab(`/connect?run=${id}`, "Publish", publishable)}
    </nav>
  );
}

export function RunHeader({ run, id }: { run: RunView; id: string }) {
  const here = useLocation();
  const onOverview = here.pathname === `/runs/${id}`;
  const real = /^[0-9a-f-]{36}$/.test(id);
  const action = run.pr ? { to: `/runs/${id}/pr`, label: "See the pull request" }
    : run.status === "awaiting_approval" && run.approval ? { to: `/connect?run=${id}`, label: "Publish draft pull request" }
    : run.status === "awaiting_approval" ? { to: `/runs/${id}/review`, label: "Review and approve" } : null;
  return (
    <>
      <div className="page-head">
        <div>
          <p className="crumbs"><Link to="/my-runs">My runs</Link><Icon name="chev" size={12} /><a href={run.issue.html_url}>{run.issue.repo} #{run.issue.number}</a>{!real && <SampleBadge />}</p>
          <h1>{run.issue.title}</h1>
          {onOverview && run.status === "awaiting_approval" && !run.approval && <p className="hint">Ready for you: read the exact change and decide. Nothing is published until you approve.</p>}
        </div>
        <div className="actions"><ReadinessBadge run={run} />{action && here.pathname + here.search !== action.to && <Link className="button" to={action.to}>{action.label}</Link>}</div>
      </div>
      <RunTabs run={run} id={id} />
    </>
  );
}
