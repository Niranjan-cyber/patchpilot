# PatchPilot design system

Redesigned on 2026-11-09 (human request), using the Taste (app-screens) and Impeccable (Operate mode) skills in `.claude/skills/`.
It replaces the warm-dark deck look of 2026-10-30, which is in git history. It is implemented in `web/src/index.css` (tokens at the top) and `web/src/components.tsx`.

**The rule: evidence over decoration.** Colour goes on data and status, never on chrome. PatchPilot is a work tool: people check issues, read proof and diffs, and decide. It isn't a landing page.

## Direction
- **Style:** Taste `framed-sheet`. A labelled sidebar sits on a light neutral frame (`--ground`), and the page is a white sheet inset 8px with a 1px edge and no shadow.
- **Theme:** light only. The work is reading code, evidence and diffs, and the PR lands on GitHub, which is light by default. One theme done well beats two half done.
- **Face:**
  - the deck's orange appears only on the product mark, the *running* state and the focus ring;
  - primary actions are near-black;
  - the signature element is the **proof ledger**: the same regression test, 2 runs on the original code and 2 after the fix in a fresh sandbox, plus the existing-test count.

## Tokens
| Role | Token | Value |
|---|---|---|
| Frame / sheet / well / active | `--ground` `--surface` `--raised` `--active` | #f4f4f2 · #fff · #f7f7f5 · #e9e9e6 |
| Edges: card / row rule / control | `--border` `--rule` `--control` | #e4e4e0 · #eeeeeb · #cfcfca |
| Text: primary / secondary / meta (all ≥ 4.5:1) | `--text` `--muted` `--faint` | #161616 · #57574f · #66665e |
| Primary action | `--primary` | #18181a, white label |
| Accent: mark, running, focus | `--accent` `--accent-ink` `--accent-bg` | #e8652b · #a8401a · #fdf1ea |
| Pass / fail / warn / info pairs | `--pos*` `--neg*` `--warn*` `--info*` | pale fill, darker text of the same hue, 1px line |

- **Type:**
  - IBM Plex Sans 400/500/600 at 12 / 14 / 16 / 20 / 24. Titles are 24/600, body is 14/20, tabular figures everywhere.
  - IBM Plex Mono only for code, paths, IDs and diffs.
  - No uppercase tracked labels, no eyebrows, no index numbers.
- **Shape:** radius 4 for chips, 6 for controls, 8 for cards, 12 for the sheet. 1px edges and no shadows at rest. Spacing is on a 4px base: gap 16, card padding 20, page padding 32 (16 on a phone). Controls are 34px tall, form inputs 38px.
- **Layout:**
  - The sidebar is 232px wide.
  - Content is capped at 1180px.
  - The run workspace is `1fr 320px` (main + rail).
  - Below 1080px it becomes one column. Below 900px the sidebar folds into a 52px top bar with a menu sheet (Close stays visible; Escape closes it).

## Components
- **Status:** an icon plus a word in a pale pill, never colour alone.
  - Passed ✓, Failed ✕, Inconclusive !, Not run –, Running (a spinning ring; reduced motion stops it). Paused uses the warning pair, never the running orange.
  - Icons are drawn SVG (`Icon` in `components.tsx`, 16px, 1.5px stroke), never Unicode glyphs.
- **Run header (`RunNav.tsx`):** breadcrumb (My runs › repo #n), the issue title as h1, the readiness badge, and the one next action, which is hidden when it points at the current screen.
- **Run tabs, in workflow order:** Overview · Change and approval · Publish (or Pull request). A stage that isn't reachable yet is shown greyed and isn't a link.
- **Steps:** one ruled list with one status pill per row and no numbers. "Not run" stays visible and is never hidden or shown as passed.
- **Diff viewer (`DiffView.tsx`):**
  - a file list, and one collapsible section per file with +/− counts and New file / Deleted marks;
  - real old and new line numbers from the hunk headers, the sign in its own column, horizontal scroll inside each file, and the page never scrolls sideways.
  - No syntax highlighting yet (it would need a dependency).
- **States:**
  - Loading keeps the layout with flat grey bars (no shimmer).
  - Empty keeps the title and the frame, plus one sentence.
  - Errors appear inside the block that failed. Red frames are for real failures only; "eval not run" is an empty state.
- **Motion:** feedback only (hover, press, the running ring), with `prefers-reduced-motion` respected.

## Banned here
Gradients, glows, glass, decorative blobs, emoji or glyph icons, icon-in-a-tinted-square cards, rows of identical cards for list data, uppercase tracked labels, accent on chrome (the nav, every button), fake metrics or activity, sample data without the "Sample data" label.
