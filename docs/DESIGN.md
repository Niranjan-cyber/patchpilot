# PatchPilot design system v4: Soft & Friendly

Redesigned on 2026-11-09 as a full replacement of v3. The human's brief was "very bland, no design; I want simple but visually appealing, with very good animations, so anyone can work here". The human chose the Soft & Friendly direction, Tailwind v4 and `motion`.
Built with `taste` (app-screens) and `impeccable` only. **`frontend-design` is not used.**

## Implementation
- `web/src/index.css`: Tailwind v4 `@theme` tokens, base styles, and `@layer components` for the shared classes (buttons, cards, status pills, diff, tables). The e2e tests select on these class names, so keep them.
- `web/src/motion.tsx`: the one spring, plus `Stagger`/`Item` for rise-in sections.
- `web/src/App.tsx`: the top-bar shell, Home (hero, live example card, how it works, your runs, examples), and the run page.
- `web/src/components.tsx`: mark, status, `LiveStatus` (8-segment progress), `ProofPanel` and `RunDot` (the signature element).
- `web/src/Workspace.tsx`: the stage timeline. `web/src/RunNav.tsx`: tabs with a shared-layout pill.

## Rules
1. **Every hue has one job:**
   - **peach** is your action, and "your turn";
   - **mint** means passed;
   - **rose** means failed;
   - **butter** means look at this;
   - **lavender** means working, sample or info.

   Status is always an icon plus a word.
2. **Tone, not lines.** White rounded cards (28px) sit on a warm paper ground (#f7f4f0). No borders or shadows at rest. Shadows are only for what floats (the example card, dialogs, toasts).
3. **One shape for controls.** Buttons are pills. The primary button is a peach fill with an ink label (9.6:1); secondary buttons are a soft grey fill.
4. **The signature is red to green.** The same test runs fail on the original code, then pass in a fresh sandbox. These run chips pop in one after another (Proof section, Home example card).
5. **The decision block is tinted by state:** peach when it's your turn, mint when verified, butter for attention, rose when blocked, lavender while working. It shows a large status disc.
6. **Motion is feedback and orientation:**
   - page rise;
   - staggered sections;
   - a sliding nav and tab pill (`layoutId`);
   - chips that pop;
   - progress bars that fill;
   - expand/collapse by grid rows;
   - press-scale on buttons;
   - spring toasts.

   `MotionConfig reducedMotion="user"` plus the CSS reduced-motion rule turn the travel off.
7. **Honesty rules still hold.**
   - Unknown is never shown as passed.
   - Sample data always carries its label.
   - Failures are never empty.

## Tokens
- **Type:** Bricolage Grotesque (headings, display: 64 on Home, 38 page titles, 21 sections) and Plus Jakarta Sans (body 15.5). JetBrains Mono is for code, paths and IDs only.
- **Ink:** #24201d, muted #5f5853 (6.6:1), faint #766f69 (4.8:1).
- **Colour scales:** peach, mint, rose, butter and lavender, each with 50/100/300/500/700 steps. Use 50 and 100 for areas and 700 for text on them.
- **Radius:** 999 (controls, pills), 16 (fields), 18 (tiles), 28 (cards), 32 (decision block, example card).
- **Ease:** `cubic-bezier(.22,1,.36,1)`. Spring: stiffness 260, damping 26.

## Banned
- Gradients and glass.
- Emoji as icons.
- Fake metrics.
- Controls that do nothing.
- Sample data without its label.
- A "passed" look on anything that didn't run.
