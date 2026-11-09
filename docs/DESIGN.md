# PatchPilot design system v3: calm and light

Redesigned on 2026-11-09, third pass. The human's brief: "it looks very cluttered and very hard to understand; make it easy and visually appealing".
Built with `taste` (`references/app-screens.md`) and `impeccable` (distill + craft-floor) only. **`frontend-design` is not used** (human decision, 2026-11-09).
Implementation:
- `web/src/index.css`: all tokens at the top;
- `web/src/App.tsx`: Overview, run page;
- `web/src/Workspace.tsx`: stages, findings, activity, details;
- `web/src/ui.tsx`: toasts, copy, modal, drawer, sliding indicators;
- `web/src/DiffView.tsx`: the diff.

**Rules that still hold:**
- Evidence over decoration. Every state shown comes from recorded backend data.
- "Not run" is never drawn as passed.

## The three rules of v3
1. **One column, one story per screen.** The run page reads top to bottom:
   - title;
   - **where it stands** (one decision block);
   - proof;
   - likely cause;
   - what PatchPilot did;
   - *More details* (collapsed).

   No side rail.
2. **One filled button per screen.** The decision block holds the only primary action. The header carries none, and nothing is repeated.
3. **Colour only says something.**
   - Burnt orange marks the action and the active place.
   - Green, red and amber are used only for status.
   - Stages that passed show a small check with no pill. Only exceptions (failed, running, not run) get a word pill, so problems stand out.

## What changed from v2 and why
| v2 | v3 | Reason |
|---|---|---|
| Dark graphite | **Light**: white sheet on a soft grey frame | Easier to read for first-time contributors, on a projector, and in daylight. Human choice. |
| Two columns plus a side rail of five cards | **One column, 820px** | The side rail split attention; the next step appeared twice. |
| Action in the header **and** in a side card | One decision block with a badge, a sentence and an action | It says once what to do next. |
| A pill on every stage (8 identical green "Passed") | Check icon only for passed; pills for exceptions | Repetition hid the one row that mattered. |
| Empty findings and extra-checks panels always shown | Shown only when they hold something; otherwise under *More details* | Empty panels are noise. |
| Overview: three empty lanes, a checks card, 16 sample buttons | Issue box → *How it works* (4 steps) → *Your runs* (only if you have any) → *See example outcomes* (collapsed) | A first-time visitor has one thing to do. |
| "Estimate" chips, the `/` hint, "0s" durations | Removed or replaced by a plain sentence | Small labels added reading without meaning. |

## Tokens
- **Surfaces:**
  - `--ground` #f4f5f7 (frame, sidebar)
  - `--sheet`/`--panel` #ffffff
  - `--raised` #f5f6f8 (quiet blocks, hover)
  - `--code` #f8f9fb
- **Lines:** `--line` #e4e7eb, `--line-soft` #eef0f2, `--line-strong` #d0d5dc. A line or a tone step, never both.
- **Text:** #15171a, muted #50565f, faint #6b717b, all ≥ 4.5:1 on white.
- **Brand:**
  - primary fill `--ember` #c2410c (white label, 5.2:1), hover #a8380a;
  - `--accent` #e8590c for the mark, focus ring, tab ink and icons;
  - `--ember-tint` #fff3eb behind the decision block when you have something to do.
- **Links:** ink, underlined in `--line-strong`; ember on hover.
- **Status** (pale pairs):
  - pass #157a3c on #ebf7ef
  - fail #be2329 on #fdeeee
  - warn #8a5300 on #fdf6e3
  - running ember on its tint
  - sample/info #1d4ed8 on #eef3ff (the "Sample data" label only)
- **Type:**
  - IBM Plex Sans at 13 / 15 / 18 / 26 / 34: 34 for the Overview title, 26 for page titles, 22 for the decision line, 18 for section heads, 15 body.
  - JetBrains Mono only for code, paths, hashes and test IDs.
- **Shape:**
  - radius: 999 for pills and run chips, 6 for controls, 10 for blocks, 14 for the decision block and the sheet;
  - spacing: 36px between run-page sections, 48px on the Overview;
  - controls 36px tall, the issue input 48px.
- **Shadows:** only on what floats (dialogs, drawer, toasts, tooltips) and on the active nav pill.
- **Motion:** unchanged from v2.
  - durations 120 / 200 / 320ms; easing `--ease` cubic-bezier(.2,.8,.2,1);
  - nav pill, tab ink, expand, route enter;
  - all of it off under `prefers-reduced-motion`.

## Components
- **Decision block** (`.decision`, `.decision.act` when it's your turn): the readiness badge (the only `.badge` on the page), one line saying where the run stands, one sentence, then the action and *Download report*.
  - While a run is working, it holds the live status and *Stop run*, which confirms in a dialog.
- **Proof:** two pale tiles, red "Before the fix" and green "After the fix", with run chips. Below: the test ID and the existing-tests sentence.
- **What PatchPilot did:** one bordered list.
  - A row expands to its recorded evidence.
  - A failed or running stage opens by default.
- **Likely cause:** plain text with the cited locations as links and one honesty line ("Written by AI and checked against the code it cites. It can still be wrong.").
- **More details:** run details with copy buttons, extra checks that didn't run, and the activity log drawer.
- **Overview:** issue box, *How it works* (one bordered strip split into 4, not 4 cards), *Your runs*, *See example outcomes*.
- **Review:** the diff on the left and the decision form on the right (a work surface, so two columns stay). The own-words hint appears only once you start typing.

## Still banned
Gradients, glows, glass, decorative blobs, emoji or text symbols as icons, eyebrow labels, index numbers, fake metrics or activity, controls that do nothing, sample data without its label, a "passed" look on anything that didn't run, and **more than one filled button on a screen**.
