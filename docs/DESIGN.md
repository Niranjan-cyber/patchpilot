# PatchPilot design system v2: the graphite workspace

Redesigned on 2026-11-09 (second pass, human brief: "premium, interactive, not boring") with Taste (`references/app-screens.md`) and Impeccable (Operate mode, `reference/craft-floor.md`).
Implementation:
- `web/src/index.css`: all tokens at the top;
- `web/src/ui.tsx`: toasts, copy, modal, drawer, sliding indicators;
- `web/src/Workspace.tsx`: stage navigator, findings, activity log, run details;
- `web/src/DiffView.tsx`: the diff viewer;
- `web/src/components.tsx`: icons, status, proof.

**The rule still holds: evidence over decoration.** Every visible state comes from recorded backend data. "Not run" is never drawn as passed.

## What changed from v1 and why
| v1 rule | v2 | Reason |
|---|---|---|
| Light only, near-white sheet | **Dark graphite**, layered surfaces | Long review sessions next to an IDE. It matches the pitch deck, and depth reads better in layers. |
| No shadows | Shadows **only on floating layers** (dialogs, drawers, toasts, tooltips, hovered cards) | Elevation tells you what floats over the work. Resting panels stay flat. |
| Almost no motion | **One motion system** (below) | Motion now explains state changes and spatial moves: tabs, nav, expand, drawer. |
| Flat loading bars | Bars in the final layout with a slow shimmer | Same layout, no shift. The shimmer is off with reduced motion. |
| No syntax highlighting | **highlight.js** (core + python, ini/toml, yaml, json, markdown) | Reviewing code without it is slower. It costs about 20 KB gzipped. |
| Orange only on mark/running/focus | **Ember is the brand**: the primary action, the active stage and tab, running, the decision card | A product needs a recognisable lead colour. Blue handles links and information. |

## Tokens
- **Surfaces**, dark to light:
  - `--ground` #0b0c0e (frame and sidebar)
  - `--sheet` #111215 (workspace)
  - `--panel` #16171b (cards)
  - `--raised` #1c1d22 (controls)
  - `--hover` #22242a
  - `--code` #0d0e11 (code, logs, inputs)
- **Lines:** `--line` #24262c, `--line-soft` #1c1e23, `--line-strong` #33363d.
- **Text:** #ecedf0, muted #a2a5ad, faint #8a8d96, all ≥ 4.5:1 on `--panel`.
- **Brand:** ember #ff7a45 (hover #ff9466), with dark ink #1b0c05 on ember fills. **Info and links:** blue #7cb4ff.
- **Status:** pass #45d48f, fail #ff6b6b, warn #f2bd55. Each sits on an ~11% tint of itself with a ~33% line.
- **Type:**
  - IBM Plex Sans: 24/600 titles, 15/600 section heads, 14/21 body, 12–12.5 meta.
  - JetBrains Mono for code, paths, hashes, test IDs, logs and diffs.
  - Fixed-width digits everywhere.
- **Shape:** radius 4 for chips, 6 for controls, 8 for cards, 12 for the sheet and dialogs. 4px spacing base, 16px gap, 32px page padding (16 on a phone). Controls are 34px tall, and the main input is 44px.
- **Motion:**
  - durations: `--t-fast` 120ms (hover, press), `--t-mid` 200ms (tabs, nav pill, expand, route enter), `--t-slow` 320ms (drawer, dialog, toast);
  - easing: `--ease` cubic-bezier(.2,.8,.2,1) everywhere;
  - `prefers-reduced-motion` sets every duration to 0.

## Components
- **Shell:**
  - The sidebar sits on the frame. A **sliding pill** follows the active route.
  - "My runs" carries a **count only for runs waiting on your approval**.
  - A live-host dot shows that this is the demo machine.
  - On a phone, the sidebar becomes an animated sheet under a 52px bar. Escape closes it.
- **Run header and tabs** (`RunNav.tsx`): a breadcrumb, the title, a readiness badge, and the one next action (hidden on the screen it points to). Tabs: Overview · Change and approval · Publish, with a **sliding ember underline**. Stages you can't reach yet are greyed out.
- **Proof:** a red-tinted "original code" column and a green-tinted "after the fix" column, joined by an arrow, plus the base commit, the regression test ID and the existing-test count.
- **Stage navigator:**
  - A rail of status nodes. Each row shows the stage, its recorded headline, its duration and a status pill.
  - Rows **expand** to show the recorded evidence:
    - times, attempt, and the gate with a tooltip explaining it;
    - the test command, test IDs, the failure on the original code, the hypothesis, the policy result, regressions.
  - The running or failed stage opens by default.
- **Review findings:** the reviewer's concerns, coloured by severity (high red, medium amber, low blue). If none were recorded, the panel says so honestly; it never claims success.
- **Activity log:** a drawer (native `<dialog>`: focus trap, Escape, backdrop click) holding the run's real event stream.
- **Stop run:** a confirm dialog that states the consequence ("can never be published").
- **Diff viewer:**
  - a file navigator with per-file and total +/− counts;
  - files that collapse with animation, a sticky file header, New file and Deleted marks;
  - old and new line numbers, syntax highlighting, copy buttons for the path, the file diff and the whole diff;
  - horizontal scroll inside each file.
- **Copy and toasts:** every hash, run ID, test ID and command can be copied, and a toast confirms it. A clipboard that isn't available is reported, never faked.
- **Tooltips:** `data-tip` explains technical terms (gates, base commit, revision). They appear on hover and keyboard focus after a 350ms delay.
- **Overview:** an ember-lit launch panel (the issue input checks the link inline, accepts `owner/repo#123`, and `/` focuses it), then lanes built from the user's real runs: *Needs your attention*, *In progress*, *Recently finished*. Empty lanes explain what will appear.
- **States:** loading keeps the layout. Empty states say what will appear. Errors appear inside the failed block; the red frame is only for real failures.

## Still banned
Purple or blue gradient backgrounds, neon borders, glowing cards, glass panels, decorative blobs, emoji or text symbols as icons, fake metrics or activity, controls that do nothing, sample data without its label, a "passed" look on anything that didn't run.
