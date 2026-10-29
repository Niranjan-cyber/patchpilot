import { useEffect, useState } from "react";
import { Link, NavLink, Route, Routes, useNavigate, useParams } from "react-router-dom";
import { api, useRun } from "./api";
import { ProofPanel, ReadinessBadge, SampleBadge, Stepper } from "./components";
import IssueCheck from "./IssueCheck";

function Shell({ children }: { children: React.ReactNode }) {
  return (
    <>
      <div className="demo-banner">Running on a demo machine. Runs may stop if it goes offline.</div>
      <header className="top">
        <Link to="/" className="brand">PatchPilot</Link>
        <nav>
          <NavLink to="/">New run</NavLink>
          <NavLink to="/my-runs">My runs</NavLink>
          <NavLink to="/connect">Sign in with GitHub</NavLink>
        </nav>
      </header>
      <main>{children}</main>
    </>
  );
}

function Start() {
  const [url, setUrl] = useState("");
  const [fixtures, setFixtures] = useState<string[]>([]);
  const nav = useNavigate();
  useEffect(() => { api<string[]>("/api/fixtures").then(setFixtures).catch(() => setFixtures([])); }, []);
  return (
    <section className="start">
      <h1>Turn a GitHub issue into a tested fix.</h1>
      <p className="lede">We reproduce the bug in a sandbox, test a fix, and show you the proof. You decide whether to open a pull request.</p>
      <form onSubmit={(e) => { e.preventDefault(); nav(`/check?url=${encodeURIComponent(url)}`); }} className="paste">
        <label htmlFor="issue">GitHub issue link</label>
        <div className="paste-row">
          <input id="issue" value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://github.com/owner/repo/issues/123" required />
          <button type="submit">Check issue</button>
        </div>
        <p className="hint">Works today on public Python projects with tests. Other projects get a report, not a fix.</p>
      </form>
      {fixtures.length > 0 && (
        <div className="samples">
          <h2>Sample runs <SampleBadge /></h2>
          <ul>{fixtures.map((f) => <li key={f}><Link to={`/runs/${f}`}>{f.replaceAll("_", " ")}</Link></li>)}</ul>
        </div>
      )}
    </section>
  );
}

function Run() {
  const { id = "" } = useParams();
  const { run, error } = useRun(id);
  if (error) return <section className="panel failed"><h1>Couldn't load this run</h1><p>{error.message}</p><Link to="/">Start a new run</Link></section>;
  if (!run) return <section className="panel"><p>Loading the run…</p></section>;
  const done = !!run.outcome;
  return (
    <section className="run-page">
      <div className="run-head">
        <div>
          <p className="issue-ref"><a href={run.issue.html_url}>{run.issue.repo} #{run.issue.number}</a> {!/^[0-9a-f-]{36}$/.test(id) && <SampleBadge />}</p>
          <h1>{run.issue.title}</h1>
        </div>
        <ReadinessBadge run={run} />
      </div>
      {run.status === "paused" && (
        <p className="notice warn">
          {run.pause?.resume_at ? `Paused: free AI capacity resumes around ${new Date(run.pause.resume_at).toLocaleTimeString()}.`
            : "Paused until free AI capacity is available. We'll stop and keep your report if that takes over 2 hours."}
        </p>
      )}
      {run.supplyguard?.status === "inconclusive" && (
        <p className="notice warn">We couldn't fully check this project's dependencies, so publishing is turned off.</p>
      )}
      {done && <ProofPanel run={run} />}
      <div className="run-grid">
        <Stepper run={run} />
        <aside className="side">
          {run.diagnosis && (
            <div className="card">
              <h2>Likely cause</h2>
              <p>{run.diagnosis.hypothesis}</p>
              <ul className="tour">{run.diagnosis.tour?.map((t) => <li key={t.path}><code>{t.path}</code> {t.why}</li>)}</ul>
            </div>
          )}
          {!done && /^[0-9a-f-]{36}$/.test(id) && (
            <button className="secondary-btn" onClick={() => api(`/api/runs/${id}/stop`, { method: "POST" }).catch(() => null)}>
              Stop run and keep the report so far
            </button>
          )}
          <p className="hint">Runs usually take 4–15 minutes. You can leave this page; the run keeps going.</p>
          {done && <a className="button secondary" href={`/api/runs/${id}/report.md`}>Download report</a>}
          {run.status === "awaiting_approval" && <Link className="button" to={`/runs/${id}/review`}>Review and approve</Link>}
          {run.pr?.url && <a className="button" href={run.pr.url}>Open pull request on GitHub</a>}
          {run.details_expired_at && <p className="notice">This run's details have expired. The outcome and pull request link are kept.</p>}
        </aside>
      </div>
    </section>
  );
}

const Stub = ({ title, children }: { title: string; children?: React.ReactNode }) => (
  <section className="panel"><h1>{title} <SampleBadge /></h1>{children}</section>
);

export default function App() {
  return (
    <Shell>
      <Routes>
        <Route path="/" element={<Start />} />
        <Route path="/check" element={<IssueCheck />} />
        <Route path="/runs/:id" element={<Run />} />
        <Route path="/runs/:id/review" element={<Stub title="Review and approve"><p>The exact diff and checklist arrive in B10.</p></Stub>} />
        <Route path="/connect" element={<Stub title="Connect GitHub"><p>We'll only ask for permission to fork, push one branch and open one draft pull request. Arrives in B11.</p></Stub>} />
        <Route path="/runs/:id/pr" element={<Stub title="Pull request opened"><p>What happens next arrives in B11.</p></Stub>} />
        <Route path="/my-runs" element={<Stub title="My runs"><p>Your runs arrive in B12.</p></Stub>} />
        <Route path="*" element={<Stub title="Page not found"><Link to="/">Start a new run</Link></Stub>} />
      </Routes>
    </Shell>
  );
}
