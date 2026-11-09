import { useEffect, useRef, useState } from "react";
import { Link, NavLink, Route, Routes, useLocation, useNavigate, useParams } from "react-router-dom";
import { api, SHOWCASE, useRun } from "./api";
import { AssessmentCard, Icon, LiveStatus, Loading, Mark, ProofPanel, ReadinessBadge, SampleBadge } from "./components";
import IssueCheck from "./IssueCheck";
import Review from "./Review";
import { Connect, PrOpened } from "./Publish";
import MyRuns, { useMyRuns } from "./MyRuns";
import Eval from "./Eval";
import { AttemptHistory, DiagnosisCard } from "./Diagnosis";
import AskPanel from "./Ask";
import { GuidedPauseNotice, PauseToggles } from "./Pauses";
import ExtraChecks from "./ExtraChecks";
import Explore from "./Explore";
import { RunHeader } from "./RunNav";
import { ActivityButton, Findings, RunDetails, StageNavigator } from "./Workspace";
import { Modal, ToastProvider, useIndicator } from "./ui";

const NAV = [
  { to: "/", label: "Overview", icon: "gauge", end: true },
  { to: "/my-runs", label: "My runs", icon: "list" },
  { to: "/explore", label: "Explore a repo", icon: "search" },
  { to: "/eval", label: "Accuracy", icon: "shield" },
] as const;

function Shell({ children }: { children: React.ReactNode }) {
  const [me, setMe] = useState<{ signed_in: boolean; login: string | null } | null>(null);
  const [open, setOpen] = useState(false);
  const loc = useLocation();
  const mine = useMyRuns();
  const waiting = mine.items?.filter((i) => i.status === "awaiting_approval").length ?? 0;   // a count only on a queue that needs you
  const { box, style } = useIndicator<HTMLUListElement>("a.active", [loc.pathname], "y");
  useEffect(() => { api<{ signed_in: boolean; login: string | null }>("/api/me").then(setMe).catch(() => setMe(null)); }, []);
  useEffect(() => setOpen(false), [loc.pathname]);
  useEffect(() => {   // Escape closes the phone menu
    const k = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    window.addEventListener("keydown", k); return () => window.removeEventListener("keydown", k);
  }, []);
  return (
    <div className={`app${open ? " nav-open" : ""}`}>
      <div className="mobile-bar">
        <Link to="/" className="brand"><Mark size={20} />PatchPilot</Link>
        <button className="secondary" aria-expanded={open} aria-controls="sidebar" onClick={() => setOpen(!open)}>
          <Icon name={open ? "x" : "menu"} />{open ? "Close" : "Menu"}
        </button>
      </div>
      <nav className="sidebar" id="sidebar" aria-label="Main">
        <Link to="/" className="brand"><Mark />PatchPilot</Link>
        <ul className="navlist" ref={box}>
          <span className="nav-pill" style={style} aria-hidden />
          {NAV.map((n) => (
            <li key={n.to}><NavLink to={n.to} end={"end" in n}><Icon name={n.icon} />{n.label}
              {n.to === "/my-runs" && waiting > 0 && <span className="count" aria-label={`${waiting} waiting for your approval`}>{waiting}</span>}</NavLink></li>
          ))}
        </ul>
        <div className="side-foot">
          {me?.signed_in ? (
            <div className="account"><span className="avatar" aria-hidden>{(me.login ?? "?")[0].toUpperCase()}</span>{me.login}</div>
          ) : (
            <ul className="navlist"><li><NavLink to="/connect"><Icon name="github" />Sign in with GitHub</NavLink></li></ul>
          )}
          <p className="host-note">{SHOWCASE ? "Showcase: recorded runs, read-only." : "Live on a demo machine. Runs stop if it goes offline."}</p>
        </div>
      </nav>
      <div className="sheet"><main key={loc.pathname}>{children}</main></div>
    </div>
  );
}

// A real, planted bug in the team's demo repo: one click shows the whole flow on an issue PatchPilot is known to fix.
const TRY = "https://github.com/Niranjan-cyber/tinycalc/issues/1";
const HOW = [
  ["search", "Check the issue", "Is it a clear bug in a Python project with tests, and has nobody fixed it yet?"],
  ["x", "Reproduce it", "A new test fails twice on the original code, in a sandbox with no network."],
  ["check", "Fix and verify", "The same test passes twice in a fresh sandbox, and old tests still pass."],
  ["github", "You decide", "You read the exact change and approve it. Nothing reaches GitHub before that."],
] as const;
const ISSUE_RE = /^https:\/\/github\.com\/[\w.-]+\/[\w.-]+\/issues\/\d+\/?$/;
/** Accepts a full issue URL or owner/repo#123. */
const normalise = (s: string) => {
  const t = s.trim(); const m = /^([\w.-]+)\/([\w.-]+)#(\d+)$/.exec(t);
  return m ? `https://github.com/${m[1]}/${m[2]}/issues/${m[3]}` : t;
};
const runWord = (i: { status: string; readiness?: string | null }) => i.status === "awaiting_approval" ? "Needs your approval"
  : i.readiness ?? (i.status === "queued" ? "Waiting to start" : i.status === "paused" ? "Paused" : "Running");

function Overview() {
  const [url, setUrl] = useState("");
  const [touched, setTouched] = useState(false);
  const [fixtures, setFixtures] = useState<string[]>([]);
  const input = useRef<HTMLInputElement>(null);
  const nav = useNavigate();
  const mine = useMyRuns();
  useEffect(() => { api<string[]>("/api/fixtures").then(setFixtures).catch(() => setFixtures([])); }, []);
  useEffect(() => {   // "/" jumps to the issue field, like most developer tools
    const k = (e: KeyboardEvent) => { if (e.key === "/" && document.activeElement?.tagName !== "INPUT" && document.activeElement?.tagName !== "TEXTAREA") { e.preventDefault(); input.current?.focus(); } };
    window.addEventListener("keydown", k); return () => window.removeEventListener("keydown", k);
  }, []);
  const target = normalise(url);
  const bad = touched && url.trim() !== "" && !ISSUE_RE.test(target);
  const check = (u: string) => nav(`/check?url=${encodeURIComponent(u)}`);
  const items = mine.items ?? [];
  // the runs waiting on you first, then the newest; five at most
  const recent = [...items.filter((i) => i.status === "awaiting_approval"), ...items.filter((i) => i.status !== "awaiting_approval")].slice(0, 5);
  return (
    <section className="start">
      <div className="launch">
        <h1>Turn an issue into a verified fix</h1>
        <p className="lede">PatchPilot reproduces the bug, tests a fix against it, and shows you the proof. Nothing reaches GitHub until you approve it.</p>
        <form noValidate onSubmit={(e) => { e.preventDefault(); setTouched(true); if (ISSUE_RE.test(target)) check(target); }} className="paste">
          <label htmlFor="issue">GitHub issue link</label>
          <div className="paste-row">
            <input id="issue" ref={input} value={url} onChange={(e) => setUrl(e.target.value)} onBlur={() => setTouched(true)} placeholder="https://github.com/owner/repo/issues/123"
              aria-invalid={bad} aria-describedby="issue-hint" autoComplete="off" spellCheck={false} />
            <button type="submit">Check issue<Icon name="arrow" /></button>
          </div>
          {bad ? <p className="field-error" id="issue-hint" role="alert">That isn't a GitHub issue link. It should look like github.com/owner/repo/issues/123.</p>
            : <p className="hint" id="issue-hint">Works on public Python projects with pytest tests. Other issues get an assessment instead of a fix.</p>}
        </form>
        <p className="try">No issue in mind? <button type="button" className="linkbtn" onClick={() => check(TRY)}>Try a sample bug</button></p>
      </div>

      <section aria-labelledby="how-h">
        <h2 id="how-h">How it works</h2>
        <ol className="how">{HOW.map(([i, t, d]) => <li key={t}><Icon name={i} /><strong>{t}</strong><span>{d}</span></li>)}</ol>
      </section>

      {items.length > 0 && (
        <section aria-labelledby="runs-h">
          <div className="section-head"><h2 id="runs-h">Your runs</h2><Link to="/my-runs">View all</Link></div>
          <ul className="runlist">{recent.map((i) => (
            <li key={i.run_id}>
              <Link to={`/runs/${i.run_id}`}><strong>{i.title}</strong></Link>
              <span className="hint">{i.repo}#{i.number} · {new Date(i.created_at).toLocaleString([], { dateStyle: "medium", timeStyle: "short" })}</span>
              <span className={`pill pill-${i.status}`}>{runWord(i)}</span>
            </li>))}</ul>
        </section>
      )}

      {fixtures.length > 0 && (
        <details className="samples">
          <summary>See example outcomes <SampleBadge /></summary>
          <p className="hint">Recorded runs showing every way a run can end, including the ones that don't produce a fix.</p>
          <ul className="sample-grid">{fixtures.map((f) => <li key={f}><Link to={`/runs/${f}`}>{f[0].toUpperCase() + f.slice(1).replaceAll("_", " ")}<Icon name="chev" size={14} /></Link></li>)}</ul>
        </details>
      )}
    </section>
  );
}

const OUTCOME_TEXT: Record<string, string> = {
  CANNOT_REPRODUCE: "We couldn't make the bug happen in a test, so there's no fix to prove. The report says what we tried.",
  ENV_FAILED: "We couldn't install this project in the sandbox, so none of its code ran. The report has the install log.",
  BLOCKED: "A dependency looked malicious, so nothing from this repository was installed or run.",
  STOPPED: "This run was stopped. Everything recorded up to that point is kept.",
  SYSTEM_ERROR: "Something on our side failed. The report has what we know; nothing was published.",
  ASSESSMENT_ONLY: "Nothing ran: this issue got an assessment instead of a fix attempt. Details are below.",
};

function Run() {
  const { id = "" } = useParams();
  const { run, events, error } = useRun(id);
  const [confirmStop, setConfirmStop] = useState(false);
  if (error) return <section className="panel failed"><h1>Couldn't load this run</h1><p>{error.message}</p><Link className="button" to="/">Back to overview</Link></section>;
  if (!run) return <Loading label="Loading the run…" />;
  const done = !!run.outcome;
  const real = /^[0-9a-f-]{36}$/.test(id);
  const assessed = run.outcome === "ASSESSMENT_ONLY";   // nothing ran: the assessment is the whole report
  const next = run.pr ? { to: `/runs/${id}/pr`, t: "A draft pull request is open", d: "See it on GitHub and what happens next.", b: "See the pull request" }
    : run.status === "awaiting_approval" && run.approval ? { to: `/connect?run=${id}`, t: "Approved. Ready to publish", d: "Connect GitHub to open a draft pull request with exactly this change.", b: "Publish draft pull request" }
    : run.status === "awaiting_approval" ? { to: `/runs/${id}/review`, t: "Your turn: review the change", d: "The fix passed in a fresh sandbox. Read the exact change and approve it; nothing is published until you do.", b: "Review and approve" } : null;
  const concerns = (run.review as { concerns?: unknown[] } | null | undefined)?.concerns?.length ?? 0;
  const hv = run.verify?.hidden_variant;
  const extraRan = hv === "passed" || hv === "failed";   // otherwise the extra checks are all "not run" and wait under More details
  return (
    <section className="run-page">
      <RunHeader run={run} id={id} badge={false} />
      <GuidedPauseNotice run={run} />
      {run.status === "paused" && run.pause?.reason !== "guided_pause" && (
        <p className="notice warn">
          {run.pause?.resume_at ? `Paused: free AI capacity resumes around ${new Date(run.pause.resume_at).toLocaleTimeString()}.`
            : "Paused until free AI capacity is available. We'll stop and keep your report if that takes over 2 hours."}
        </p>
      )}
      {run.supplyguard?.status === "inconclusive" && <p className="notice warn">We couldn't fully check this project's dependencies, so publishing is turned off.</p>}
      {run.details_expired_at && <p className="notice">This run's details have expired. The outcome and pull request link are kept.</p>}

      <section className={`decision${next ? " act" : ""}`} aria-label="Where this run stands">
        <ReadinessBadge run={run} />
        {done ? (
          <>
            <h2>{next?.t ?? (OUTCOME_TEXT[run.outcome!] ? "What happened" : "Read the report")}</h2>
            <p>{next?.d ?? OUTCOME_TEXT[run.outcome!] ?? "PatchPilot found something a person needs to look at. The report has everything it recorded."}</p>
            <div className="row">
              {next && <Link className="button" to={next.to}>{next.b}<Icon name="arrow" /></Link>}
              <a className={`button${next ? " secondary" : ""}`} href={`/api/runs/${id}/report.md`}><Icon name="file" />Download report</a>
            </div>
          </>
        ) : (
          <>
            <LiveStatus run={run} />
            {real && <div className="row"><button className="danger-btn" onClick={() => setConfirmStop(true)}><Icon name="stop" />Stop run</button></div>}
          </>
        )}
      </section>

      {done && !!run.repro?.runs_on_base?.length && (
        <section aria-labelledby="proof-h">
          <h2 id="proof-h">Proof</h2>
          <ProofPanel run={run} />
        </section>
      )}
      {assessed && <AssessmentCard a={run.assessment} />}
      <DiagnosisCard run={run} />
      {!assessed && (
        <section aria-labelledby="steps-h">
          <h2 id="steps-h">What PatchPilot did</h2>
          <StageNavigator run={run} />
        </section>
      )}
      {concerns > 0 && <Findings run={run} />}
      <AttemptHistory events={events} />
      {extraRan && <ExtraChecks run={run} />}
      <AskPanel run={run} />
      <PauseToggles run={run} />

      <details className="more">
        <summary>More details</summary>
        <div className="more-body">
          <RunDetails run={run} />
          {!extraRan && <ExtraChecks run={run} />}
          <div><ActivityButton events={events} /></div>
        </div>
      </details>

      <Modal open={confirmStop} onClose={() => setConfirmStop(false)} title="Stop this run?"
        actions={<>
          <button className="secondary" onClick={() => setConfirmStop(false)}>Keep running</button>
          <button className="danger-solid" onClick={() => { setConfirmStop(false); api(`/api/runs/${id}/stop`, { method: "POST" }).catch(() => null); }}>Stop run</button>
        </>}>
        <p>The run ends where it is and keeps its report so far. A stopped run can never be published; you'd start a new run to try again.</p>
      </Modal>
    </section>
  );
}

const Stub = ({ title, children }: { title: string; children?: React.ReactNode }) => (
  <section className="panel empty"><h1>{title}</h1>{children}</section>
);

export default function App() {
  return (
    <ToastProvider>
      <Shell>
        <Routes>
          <Route path="/" element={<Overview />} />
          <Route path="/check" element={<IssueCheck />} />
          <Route path="/runs/:id" element={<Run />} />
          <Route path="/runs/:id/review" element={<Review />} />
          <Route path="/connect" element={<Connect />} />
          <Route path="/runs/:id/pr" element={<PrOpened />} />
          <Route path="/my-runs" element={<MyRuns />} />
          <Route path="/eval" element={<Eval />} />
          <Route path="/explore" element={<Explore />} />
          <Route path="*" element={<Stub title="Page not found"><p>This link doesn't match any page. Runs open from My runs, or start a new one.</p>
            <div className="row"><Link className="button" to="/">Back to overview</Link><Link className="button secondary" to="/my-runs">My runs</Link></div></Stub>} />
        </Routes>
      </Shell>
    </ToastProvider>
  );
}
