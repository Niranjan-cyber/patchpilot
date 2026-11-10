import { useEffect, useState } from "react";
import { api, ApiError } from "./api";
import { RUNS_CHANGED } from "./Progress";

type Item = { id: string; source: "review" | "comment" | "ci"; author: string | null; at: string | null; url: string | null;
  quote: string; unread: boolean; path: string | null; line: number | null; new: boolean; category: string | null; label: string;
  meaning: string | null; why: string | null; reply: string | null; change: string | null; needs_judgement: boolean | null };
type Assist = { state: "ok" | "empty" | "no_pr" | "unavailable"; items: Item[]; model_ok: boolean | null; plan: string[] | null;
  pr_state?: string | null; partial?: boolean; total?: number; hidden_ids?: string[] };

const tone = (i: Item) => i.category === "ci" ? "badge-bad" : i.category === "non_actionable" ? "" : i.category ? "badge-warn" : "";
const pickable = (i: Item) => i.category !== "non_actionable" && !i.unread;

function Request({ i, picked, toggle }: { i: Item; picked: boolean; toggle: () => void }) {
  return (
    <li className={`fb-item${i.new ? " is-new" : ""}`}>
      <div className="fb-head">
        <span className={`badge ${tone(i)}`}>{i.label}</span>
        <span>{i.author ?? "GitHub Actions"}{i.at && <span className="hint">, {new Date(i.at).toLocaleString()}</span>}</span>
        {i.new && <strong className="new-tag">New</strong>}
        {i.needs_judgement && <span className="badge badge-warn">Needs your judgement</span>}
        {i.url && <a href={i.url}>Open on GitHub</a>}
      </div>
      {i.path && <p className="hint"><code>{i.path}{i.line ? `:${i.line}` : ""}</code></p>}
      {i.unread ? <p className="hint">Text not read yet. Open it on GitHub; we'll read it on the next check.</p>
        : i.quote ? <blockquote className="fb-quote">{i.quote}</blockquote> : i.source !== "ci" && <p className="hint">This review has no text.</p>}
      {i.meaning ? <dl className="fb-explain">
        <dt>What it means</dt><dd>{i.meaning}</dd>
        {i.why && <><dt>Why it matters</dt><dd>{i.why}</dd></>}
        {i.change && <><dt>Proposed change</dt><dd><pre>{i.change}</pre></dd></>}
        {i.reply && <><dt>Draft reply <span className="hint">(not posted; copy it if you want it)</span></dt><dd>{i.reply}</dd></>}
      </dl> : !i.unread && i.quote && i.category !== "non_actionable" && <p className="hint">Not classified yet, so read the comment yourself. We ask again next time you open this page.</p>}
      {pickable(i) && (
        <label className="fb-pick"><input type="checkbox" checked={picked} onChange={toggle} /> Include in the revision plan</label>
      )}
    </li>
  );
}

/** #102: maintainer feedback explained, read-only. Nothing here posts, pushes or dismisses on GitHub. */
export default function FeedbackAssistant({ id }: { id: string }) {
  const [a, setA] = useState<Assist | null>(null);
  const [err, setErr] = useState<ApiError | null>(null);
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const [saved, setSaved] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const load = () => {
    setErr(null);
    api<Assist>(`/api/runs/${id}/feedback/assist`).then((x) => {
      setA(x);
      const can = new Set(x.items.filter(pickable).map((i) => i.id));
      setPicked(new Set((x.plan ?? []).filter((k) => can.has(k))));   // a saved id no longer on the PR can't block a save
      window.dispatchEvent(new Event(RUNS_CHANGED));                       // the heading re-reads the state this just refreshed
      // seen = what's shown here, plus the older items the "latest 20" notice covers; a failed "seen" is silent
      api(`/api/runs/${id}/feedback/seen`, { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ids: [...x.items.map((i) => i.id), ...(x.hidden_ids ?? [])] }) })
        .then(() => window.dispatchEvent(new Event(RUNS_CHANGED))).catch(() => null);
    }).catch(setErr);
  };
  useEffect(load, [id]);
  if (err) return <div className="notice warn"><p>Couldn't load the feedback: {err.message}</p><button className="linklike" onClick={load}>Try again</button></div>;
  if (!a) return <p className="hint" aria-busy="true">Reading the pull request on GitHub…</p>;
  if (a.state === "unavailable") return <p className="notice warn">GitHub didn't answer, so the feedback is unavailable right now. <button className="linklike" onClick={load}>Check again</button></p>;
  if (a.state !== "ok") return <p className="hint">No maintainer feedback yet. We check every 10 minutes and flag anything new in My runs.</p>;
  const act = a.items.filter((i) => i.category !== "non_actionable");
  const rest = a.items.filter((i) => i.category === "non_actionable");
  const hidden = a.hidden_ids?.length ?? 0;
  const toggle = (k: string) => { const s = new Set(picked); s.has(k) ? s.delete(k) : s.add(k); setPicked(s); setSaved(null); };
  const save = () => {
    setSaving(true);
    api<{ evidence_id: string }>(`/api/runs/${id}/feedback/plan`, { method: "PUT", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ item_ids: [...picked] }) }).then(() => setSaved(`Saved ${picked.size} request${picked.size > 1 ? "s" : ""}.`))
      .catch((e: ApiError) => setSaved(e.message)).finally(() => setSaving(false));
  };
  return (
    <div className="fb">
      {a.pr_state === null && <p className="notice warn">GitHub didn't answer on the last check, so this is the feedback from the check before. <button className="linklike" onClick={load}>Check again</button></p>}
      {a.pr_state === "review_unavailable" && <p className="notice warn">We couldn't read the reviews on the last check, so the review status is unavailable. Earlier feedback is kept below.</p>}
      {a.partial && a.pr_state && a.pr_state !== "review_unavailable" && <p className="notice warn">Part of the pull request couldn't be read on the last check, so this list may be incomplete.</p>}
      {a.model_ok === false && <p className="notice warn">Some items aren't classified yet; the comments are shown as written. We ask again next time you open this page.</p>}
      {hidden > 0 && <p className="hint">Showing the latest {a.items.length} of {a.total}. The {hidden} older one{hidden > 1 ? "s are" : " is"} on GitHub.</p>}
      {act.length ? <ul className="fb-list">{act.map((i) => <Request key={i.id} i={i} picked={picked.has(i.id)} toggle={() => toggle(i.id)} />)}</ul>
        : <p className="hint">Nothing to change: the feedback so far is thanks, approvals or notes.</p>}
      {!!rest.length && <details className="fb-rest"><summary>{rest.length} comment{rest.length > 1 ? "s" : ""} with nothing to change</summary>
        <ul className="fb-list">{rest.map((i) => <Request key={i.id} i={i} picked={false} toggle={() => null} />)}</ul></details>}
      {act.some(pickable) && <div className="fb-plan">
        <h3>Revision plan</h3>
        <p className="hint">Tick the requests to work on. The plan is saved for Revise; nothing is posted to GitHub.</p>
        <div className="row"><button onClick={save} disabled={!picked.size || saving}>{saving ? "Saving…" : `Save plan (${picked.size})`}</button>
          {saved && <span role="status">{saved}</span>}</div>
      </div>}
    </div>
  );
}
