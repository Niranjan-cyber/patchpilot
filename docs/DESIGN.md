# PatchPilot visual design system

Dark, technical, warm. High-contrast typography with a restrained orange signal. The same system as the pitch deck.
**Core rule:** near-black surfaces, warm off-white text, orange for actions and proof states.

The human chose this system on 2026-10-30. It replaces the earlier black / white / green analysis (see git history).
It is implemented in `web/src/index.css`.

## Colour tokens
| Token | Hex | Use |
|---|---|---|
| Canvas / primary | `#0F0B08` | page background |
| Surface / raised | `#19110D` | cards, panels, chapters |
| Surface / elevated | `#21140F` | inputs, nested surfaces, hover |
| Border | `#2E221B` / `#3A2C23` | 1px warm borders (normal / strong) |
| Brand orange | `#E8652B` | primary buttons, active nav, passed steps, progress |
| Orange highlight | `#F08A57` | links, labels, focus ring, hover |
| Text / primary | `#F2EDE8` | headings and body |
| Text / secondary | `#C9BDB3` | supporting copy |
| Text / muted | `#A89C92` | hints, metadata |
| Light panel | `#FBFAF8` / `#1B1410` | architecture and docs only, sparingly |

**Semantic colours:** red and green appear only as product pass/fail, as in the proof strip, diffs and check chips.
They are never brand colour: fail `#D63A2C` (text `#F2877C`), pass `#2F8A46` (text `#7FC98A`), warning `#E9B65A`.

## Gradient and texture
- **Hero glow:** one faint burnt-orange ellipse over `#0F0B08`, on the home hero only. The hero's right column is the real proof from tinycalc PR #4 (no mock data), not decoration.
- **App screens:** mostly solid. No heavy shadows, glass effects or decorative gradients.

## Typography
- **Inter** 400/700 is the primary UI family. The scale is 52 (hero) / 36 / 22 / 16 / 15 / 14.
- **JetBrains Mono** 400/500 is only for things that are literally code: test IDs, file paths, repo refs, diffs, logs and step numbers. Labels, step status, badges and table headers are Inter, sentence case, never uppercase-tracked (2026-10-30 polish: the all-caps mono eyebrows read as template chrome).

## Shape and spacing
- **Spacing:** 8px base (0.5 / 1 / 1.5 / 2 / 3 / 4 rem).
- **Radius:** 8px for controls, 12px for cards, 16px for chapters, and pills for badges and chips.
- **Borders:** 1px warm.
- **Focus:** a visible 2px orange-highlight ring.
- **Motion:** respects `prefers-reduced-motion`.

## Components
- **Primary button:** orange fill, dark text `#1B1410`. **Secondary:** transparent with a strong border, which turns orange on hover.
- **Chapter:** a raised surface with a 16px radius that holds what the screen is about: the run verdict and proof strip, the review header, or the PR success.
- **Proof strip:** the one bold element. The same test, red twice on the original code and green twice after the fix.
- **Timeline:** numbered mono markers (orange when passed, red when failed, a pulsing ring while running), joined by a line that turns orange as steps pass.
