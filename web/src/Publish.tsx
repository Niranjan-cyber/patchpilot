import { useEffect, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { api, ApiError, useRun } from "./api";
import { Loading, StatusIcon } from "./components";
import { Modal } from "./ui";
import FeedbackAssistant from "./FeedbackAssistant";

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
  const [consented, setConsented] = useState(false);
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
            <li>post the comment you approve on the issue, asking the maintainer whether they want the fix,</li>
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
      {me?.signed_in && run && <AskFirst run={run} />}
      {me?.signed_in && run && <ConsentCard run={run} onChange={setConsented} />}
      {me?.signed_in && run && (
        <div className="card">
          <h2>Then, if they say yes: open the pull request</h2>
          {!consented && <p className="hint">Available once a maintainer's yes (or your reason) is recorded above.</p>}
          <p>We'll check that nothing changed upstream, re-apply your approved change on a clean copy, and open a draft pull request. If you can't push to the repository, we use your fork.</p>
          <div className="row"><button className="secondary-btn" onClick={publish} disabled={busy || !consented}>{busy ? "Starting…" : "Publish draft pull request"}</button></div>
        </div>
      )}
      {err && <p className="notice warn">{err.message}</p>}
    </section>
  );
}

type Reply = { url: string; author: string; association: string; quote: string; positive: boolean; declined: boolean };
type Consent = { consent: { kind: string; source_url?: string | null; author?: string | null; quote?: string | null;
  attested_by_user?: boolean; override_reason?: string | null } | null; state: string; replies: Reply[]; why?: string | null;
  found?: { kind: string; source_url?: string | null; author?: string | null; quote?: string | null } | null };
const STATE: Record<string, string> = {
  none: "No maintainer has said yes yet. Ask them first (above).",
  waiting: "Waiting for a maintainer to reply to your comment. Silence isn't a yes.",
  replied: "A maintainer replied, but not with a clear yes. Read it, and record it below only if it agrees to your fix.",
  declined: "A maintainer declined. Respect that unless something new has changed their mind.",
  granted: "A maintainer's yes is on the issue. Use it to unlock publishing.",
};
const KIND: Record<string, string> = {
  maintainer_reply: "A maintainer replied yes", maintainer_request: "A maintainer asked for a fix",
  contributing_invites: "The project's contributing guide invites fixes like this", user_override: "You chose to publish without a maintainer's yes",
};

// status pill per DESIGN.md (icon + word); an override is a warning, never the "passed" green
const PILL: Record<string, [string, string]> = {
  recorded: ["passed", "Consent recorded"], override: ["inconclusive", "Override"], granted: ["passed", "Consent found"],
  replied: ["inconclusive", "Unclear reply"], waiting: ["not_run", "Waiting for a reply"], none: ["not_run", "Not asked yet"],
  declined: ["failed", "Declined"],
};
function ConsentPill({ state }: { state: string }) {
  const [s, word] = PILL[state] ?? ["not_run", state];
  return <span className={`status status-${s}`}><StatusIcon s={s} size={12} />{word}</span>;
}

/** Contracts v0.5 §2.2: publishing needs a maintainer's yes, an invitation, or the user's typed reason. */
function ConsentCard({ run, onChange }: { run: string; onChange: (ok: boolean) => void }) {
  const [st, setSt] = useState<Consent | null>(null);
  const [err, setErr] = useState<ApiError | null>(null);
  const [busy, setBusy] = useState(false);
  const [reason, setReason] = useState("");
  const [confirm, setConfirm] = useState(false);
  const show = (c: Consent) => { setSt(c); onChange(!!c.consent); };
  useEffect(() => { api<Consent>(`/api/runs/${run}/consent`).then(show).catch(setErr); }, [run]);
  const send = async (body: object) => {
    setBusy(true); setErr(null);
    try { show(await api<Consent>(`/api/runs/${run}/consent`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) })); }
    catch (e) { setErr(e as ApiError); } finally { setBusy(false); }
  };
  const k = st?.consent;
  return (
    <div className="card form">
      <div className="row"><h2>Maintainer's answer</h2>{st && <ConsentPill state={k?.kind === "user_override" ? "override" : st.state} />}</div>
      {k ? <p className={k.kind === "user_override" ? "notice warn" : "notice"}>{KIND[k.kind] ?? k.kind}{k.attested_by_user ? " (you confirmed their reply)" : ""}
          {k.quote && <>: "{k.quote}"</>}{k.source_url && <> <a href={k.source_url}>source</a></>}
          {k.override_reason && <>. Your reason: {k.override_reason}</>}</p>
        : st && <>
          <p>{STATE[st.state] ?? st.state}{st.why ? ` ${st.why}` : ""}</p>
          {st.replies.filter((r) => !r.declined).map((r) => (
            <div key={r.url} className="row">
              <p><strong>{r.author}</strong> <span className="hint">({r.association.toLowerCase()})</span>: "{r.quote}" <a href={r.url}>Open on GitHub</a></p>
              <button className="secondary-btn" disabled={busy} onClick={() => send({ attest_comment_url: r.url })}>They agreed: record this reply</button>
            </div>
          ))}
          {st.found && <p className="notice">{KIND[st.found.kind] ?? st.found.kind}{st.found.author ? ` (${st.found.author})` : ""}
            {st.found.quote && <>: "{st.found.quote}"</>}{st.found.source_url && <> <a href={st.found.source_url}>source</a></>}</p>}
          {/* found consent: one clear action, and no override beside it (the live test used the override by mistake) */}
          <div className="row">{st.found
            ? <button disabled={busy} onClick={() => send({})}>{busy ? "Recording…" : "Use this consent"}</button>
            : <button className="secondary-btn" disabled={busy} onClick={() => send({})}>{busy ? "Checking…" : "Check the issue for a reply"}</button>}</div>
          {!st.found && <details>
            <summary>Publish without a maintainer's yes</summary>
            <label>Why is it right to open this pull request anyway? (at least 20 characters)
              <textarea rows={2} value={reason} onChange={(e) => setReason(e.target.value)} maxLength={1000} /></label>
            <p className="hint">Your reason goes in the report as an override. It never appears in the pull request as if a maintainer asked.</p>
            <button className="secondary-btn" disabled={busy || reason.trim().length < 20} onClick={() => setConfirm(true)}>Record my reason</button>
          </details>}
        </>}
      {err && <p className="notice warn">{err.message}</p>}
      <Modal open={confirm} onClose={() => setConfirm(false)} title="Publish without a maintainer's yes?"
        actions={<>
          <button className="secondary" onClick={() => setConfirm(false)}>Go back</button>
          <button onClick={() => { setConfirm(false); send({ override_reason: reason }); }}>Record my reason</button>
        </>}>
        <p>This can't be undone for this run. Your reason goes in the report as an override, and the pull request will never claim a maintainer asked for it.</p>
      </Modal>
    </div>
  );
}

type Ask = { draft: string | null; pending: boolean; url?: string; error?: string };

/** Ask the maintainer on the issue before opening a PR (human decision 2026-11-09, after mcstatus #1238 was closed unasked). */
function AskFirst({ run }: { run: string }) {
  const [st, setSt] = useState<Ask | null>(null);
  const [text, setText] = useState("");
  const [err, setErr] = useState<ApiError | null>(null);
  const [confirm, setConfirm] = useState(false);
  const load = () => api<Ask>(`/api/runs/${run}/ask-maintainer`).then((a) => { setSt(a); setText((t) => t || a.draft || ""); }).catch(setErr);
  useEffect(() => { load(); }, [run]);
  useEffect(() => { if (st?.pending) { const t = setTimeout(load, 3000); return () => clearTimeout(t); } }, [st]);
  const post = async () => {
    setErr(null);
    try { await api(`/api/runs/${run}/ask-maintainer`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ body: text }) }); load(); }
    catch (e) { setErr(e as ApiError); }
  };
  if (!st) return err ? <p className="notice warn">{err.message}</p> : null;
  return (
    <div className="card form">
      <h2>First, ask the maintainer (recommended)</h2>
      <p>Many maintainers close pull requests they didn't ask for. Post this short comment on the issue, and open the pull request only if they say yes.</p>
      {st.url ? <p className="notice">Comment posted. <a href={st.url}>Open it on GitHub</a> and wait for a reply before opening the pull request.</p> : <>
        <label>Your comment (edit it so it sounds like you)
          <textarea rows={6} value={text} onChange={(e) => setText(e.target.value)} maxLength={2000} /></label>
        <div className="row"><button onClick={() => setConfirm(true)} disabled={st.pending || text.trim().length < 20}>{st.pending ? "Posting…" : "Post this comment on the issue"}</button></div>
      </>}
      {st.error && <p className="notice warn">{st.error}</p>}
      {err && <p className="notice warn">{err.message}</p>}
      <Modal open={confirm} onClose={() => setConfirm(false)} title="Post this comment on the issue?"
        actions={<>
          <button className="secondary" onClick={() => setConfirm(false)}>Keep editing</button>
          <button onClick={() => { setConfirm(false); post(); }}>Post comment</button>
        </>}>
        <p>It appears publicly on GitHub under your account, and you can ask only once per run. Edit or delete it on GitHub if you need to.</p>
      </Modal>
    </div>
  );
}

/** The PR's state as last read from GitHub (stored; no GitHub call), for the heading. The assistant below marks "seen". */
function usePrState(id: string) {
  const [f, setF] = useState<{ state: string | null } | null>(null);
  const [err, setErr] = useState(false);
  useEffect(() => { api<{ state: string | null }>(`/api/runs/${id}/feedback`).then(setF).catch(() => setErr(true)); }, [id]);
  return { f, err };
}

export function PrOpened() {
  const { id = "" } = useParams();
  const { run, events, error } = useRun(id);
  const fb = usePrState(id);
  const st = fb.f?.state;          // what GitHub says now; the publish event only knows what we opened
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
        {st !== "closed" && <span className="success-mark" aria-hidden />}
        <h1>{st === "merged" ? "Your pull request was merged" : st === "closed" ? "Your pull request was closed"
          : fin.status === "updated" ? "Your pull request was updated" : st === "draft" ? "Draft pull request opened" : "Pull request opened"}</h1>
        <p className="lede">On {run.issue.repo}, for issue #{run.issue.number}. {st === "merged" ? "A maintainer merged it."
          : st === "closed" ? "A maintainer closed it without merging. That isn't automatically a failure."
          : st === "draft" ? "It's a draft, so nothing merges until a maintainer decides."
          : st ? "A maintainer decides whether to merge it." : fb.err || fb.f?.tracked ? "We couldn't read its current status on GitHub."
          : "Checking GitHub…"}</p>
        <a className="button" href={fin.pr_url}>Open on GitHub</a>
        <p className="pr-url"><code>{fin.pr_url}</code></p>
        {run.pr?.fork_owner && <p className="hint">From your fork, {run.pr.fork_owner}/{run.issue.repo.split("/")[1]}.</p>}
      </div>
      <h2>Maintainer feedback</h2>
      <FeedbackAssistant id={id} />
      {st !== "merged" && st !== "closed" && <>
      <h2>What happens next</h2>
      <ol className="next">
        {st === "draft" && <>
        <li>Open your draft pull request on GitHub and read it once more.</li>
        <li>When you're happy, click <strong>Ready for review</strong> on GitHub.</li></>}
        <li>A maintainer may ask for changes. That's normal.</li>
        <li>If they do, come back and use <Link to={`/runs/${id}/review`}>Revise</Link>; we'll update the same pull request.</li>
      </ol></>}
      <p className="hint">Maintainers decide whether to merge. A closed pull request isn't automatically a failure.</p>
      <div className="row"><Link className="button secondary" to={`/runs/${id}`}>Back to the run</Link><Link className="button secondary" to="/my-runs">My runs</Link></div>
    </section>
  );
}
