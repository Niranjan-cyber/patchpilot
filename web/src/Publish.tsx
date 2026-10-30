import { useEffect, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { api, ApiError, useRun } from "./api";
import { Loading } from "./components";

type Me = { signed_in: boolean; login: string | null; oauth_ready: boolean };
const ERR: Record<string, string> = {
  cancelled: "No permission was given, so nothing was published.",
  state: "The sign-in link expired or didn't match. Please try again.",
  session: "Your browser session expired. Please try again.",
  github: "GitHub didn't answer. Please try again in a minute.",
  not_configured: "Publishing isn't set up on this server yet. You can still download the diff and report.",
};

export function Connect() {
  const [p] = useSearchParams();
  const run = p.get("run") ?? "";
  const nav = useNavigate();
  const [me, setMe] = useState<Me | null>(null);
  const [err, setErr] = useState<ApiError | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => { api<Me>("/api/me").then(setMe).catch(setErr); }, []);
  const publish = async () => {
    setBusy(true); setErr(null);
    try { await api(`/api/runs/${run}/publish`, { method: "POST" }); nav(`/runs/${run}/pr`); }
    catch (e) { setErr(e as ApiError); setBusy(false); }
  };
  const e = p.get("error");
  return (
    <section className="check">
      {run && <p className="issue-ref"><Link to={`/runs/${run}`}>Back to the run</Link></p>}
      <h1>{me?.signed_in ? `Connected as ${me.login}` : "Connect GitHub to publish"}</h1>
      {e && <p className="notice warn">{ERR[e] ?? "Something went wrong. Please try again."}</p>}
      {!me?.signed_in && (
        <div className="card">
          <p>We'll ask GitHub for permission to:</p>
          <ul>
            <li>make a copy of the repository under your account (a <abbr title="A fork is your own copy of someone else's repository. It's free and stays under your account.">fork</abbr>), if you can't push to it directly,</li>
            <li>push one branch with the change you approved,</li>
            <li>open one <abbr title="A draft pull request is a proposal maintainers can review; it can't be merged until you mark it ready.">draft pull request</abbr>.</li>
          </ul>
          <p className="hint">We can't merge anything. The AI never sees this permission. Signing in also keeps your runs available on other devices.</p>
          <div className="row">
            {me?.oauth_ready === false ? <span className="notice warn">Publishing isn't set up on this server yet.</span>
              : <a className="button" href={`/auth/github/start?run=${encodeURIComponent(run)}`}>Connect with GitHub</a>}
            {run && <a className="button secondary" href={`/api/runs/${run}/diff.patch`}>Download the diff instead</a>}
          </div>
        </div>
      )}
      {me?.signed_in && run && (
        <div className="card">
          <p>We'll check that nothing changed upstream, re-apply your approved change on a clean copy, and open a draft pull request. If you can't push to the repository, we use your fork.</p>
          <div className="row"><button onClick={publish} disabled={busy}>{busy ? "Starting…" : "Publish draft pull request"}</button></div>
        </div>
      )}
      {err && <p className="notice warn">{err.message}</p>}
    </section>
  );
}

export function PrOpened() {
  const { id = "" } = useParams();
  const { run, events, error } = useRun(id);
  const fin = [...events].reverse().find((e) => e.type === "publish.finished")?.payload as Record<string, string> | undefined;
  if (error) return <section className="panel failed"><h1>Couldn't load this run</h1><p>{error.message}</p><Link className="button secondary" to="/my-runs">My runs</Link></section>;
  if (!run) return <Loading label="Loading the pull request…" />;
  if (run.status === "publishing" || !fin) return (
    <section className="panel loading" aria-busy="true" aria-live="polite"><h1>Publishing…</h1>
      <ol className="publish-steps">
        <li>Re-checking that nothing changed upstream</li><li>Applying your approved change on a clean copy</li>
        <li>Pushing the branch</li><li>Opening a draft pull request</li>
      </ol>
      <p className="hint">This usually takes under a minute. You can leave this page.</p></section>
  );
  if (fin.status === "failed") return (
    <section className="panel failed"><h1>Nothing was published</h1><p>{fin.message}</p>
      <div className="row"><Link className="button" to={`/connect?run=${id}`}>Try again</Link><a className="button secondary" href={`/api/runs/${id}/diff.patch`}>Download the diff</a></div></section>
  );
  if (fin.status === "branch_only") return (
    <section className="panel"><h1>Your branch is ready</h1>
      <p>The repository didn't let us open the pull request for you. Your change is pushed to your fork; click below and GitHub will open the pull request form, already filled in.</p>
      <a className="button" href={fin.compare_url}>Open the pull request form on GitHub</a></section>
  );
  return (
    <section className="check">
      <div className="chapter success">
        <span className="success-mark" aria-hidden />
        <h1>{fin.status === "updated" ? "Your draft pull request was updated" : "Draft pull request opened"}</h1>
        <p className="lede">On {run.issue.repo}, for issue #{run.issue.number}. It's a draft, so nothing merges until a maintainer decides.</p>
        <a className="button" href={fin.pr_url}>Open on GitHub</a>
        <p className="pr-url"><code>{fin.pr_url}</code></p>
        {run.pr?.fork_owner && <p className="hint">From your fork, {run.pr.fork_owner}/{run.issue.repo.split("/")[1]}.</p>}
      </div>
      <h2>What happens next</h2>
      <ol className="next">
        <li>Open your draft pull request on GitHub and read it once more.</li>
        <li>When you're happy, click <strong>Ready for review</strong> on GitHub.</li>
        <li>A maintainer may ask for changes. That's normal.</li>
        <li>If they do, come back and use <Link to={`/runs/${id}/review`}>Revise</Link>; we'll update the same pull request.</li>
      </ol>
      <p className="hint">Maintainers decide whether to merge. A closed pull request isn't automatically a failure.</p>
      <div className="row"><Link className="button secondary" to={`/runs/${id}`}>Back to the run</Link><Link className="button secondary" to="/my-runs">My runs</Link></div>
    </section>
  );
}
