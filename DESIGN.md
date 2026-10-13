# DESIGN.md — Gestión de Vacaciones G&J

## The world

**Institutional ledger.** The interface is an internal instrument of record.
It should read the way a well-kept administrative register reads: ordered
columns, honest totals, no ornament that does not carry information. The visual
authority is G&J's own corporate navy — not a SaaS teal, not a purple gradient,
not a template.

Expression lives in *precision*, not decoration: a hairline rule that lands
exactly on the grid, a tabular numeral column that never jumps when it updates,
a status chip whose color is earned by data rather than sprinkled for interest.

Surface mode: **Operate** (the visitor completes a task). Scanability,
consistency, and native expectations outrank expression. Brand lives in the
details.

## Color

Committed tokens. Raw hex does not appear in components.

| Token | Value | Use |
|---|---|---|
| `--brand-900` | `#0B2942` | Sidebar surface, headline ink on light |
| `--brand-800` | `#103A5E` | Sidebar hover, deep rule |
| `--brand-700` | `#16456D` | Primary action, active nav, focus ring |
| `--brand-600` | `#1D5B8F` | Primary hover |
| `--brand-100` | `#E4EDF5` | Selected row, quiet chip |
| `--brand-050` | `#F4F8FB` | Page background |
| `--ink` | `#111C26` | Body text (15.4:1 on `--surface`) |
| `--ink-muted` | `#5A6B7B` | Secondary text (5.4:1 on `--surface`) |
| `--surface` | `#FFFFFF` | Cards, table body |
| `--line` | `#D5DEE6` | Hairline borders, no shadow to do a line's job |
| `--ok` | `#0F6B4F` | Aprobada (7.0:1) |
| `--warn` | `#8A5A00` | Pendiente (6.1:1) |
| `--danger` | `#A81F2B` | Rechazada, destructive action (7.7:1) |
| `--info` | `#0F5C7A` | Informative (7.4:1) |

Rules:

- **Contrast floor 4.5:1** for every text/background pair, 3:1 for UI borders
  that carry meaning. The values above are all measured, not estimated.
- **Status is never color alone.** Every chip carries a glyph and a word;
  every chart series carries a label.
- **No gradients.** No drop shadows on cards; a `1px var(--line)` border
  separates surfaces. Depth comes from the sidebar being darker, not from
  floating.
- Dark mode is **not shipped** in this iteration. Half-done dark mode is worse
  than none; when it ships it ships as a full token set.

## Typography

- **Family:** `Inter` (variable, self-hosted/fallback chain), falling back to
  `system-ui, -apple-system, "Segoe UI", Roboto, sans-serif`. No second family
  — this is an instrument, not a magazine.
- **Numeric:** `font-variant-numeric: tabular-nums` on every figure that
  updates: day counts, totals, table numerics, KPI values.
- **Scale:** 12 / 13 / 15 / 17 / 20 / 28 / 34 px. Body 15px, line-height 1.5.
  Nothing below 12px carries meaning.
- **Weights:** 400 body, 500 labels/buttons, 600 headings, 600 for KPI values.
  No 700+ headlines; hierarchy comes from size and color, not shouting.
- **Measure:** prose blocks cap at 68ch.

## Layout

- **Grid:** 12-column, 24px gutter, `--space` scale `4 8 12 16 24 32 48 64`.
- **App shell:** fixed top bar (56px) + fixed left sidebar (240px, collapsing
  to a 64px rail below 1200px, off-canvas drawer below 768px) + a single
  scrolling content column, `max-width: 1320px`, 24px horizontal padding.
- **Tables are the primary instrument.** Header sticky, rows 44px min, zebra
  via a single `--brand-050` tint on alternate rows, right-aligned numerics,
  horizontal scroll inside the card — never a page-level horizontal scrollbar.
- **Targets:** 44×44px minimum for every interactive element, 8px minimum
  between adjacent targets.

## Motion

Restrained, and it always says something.

| Purpose | Duration | Easing |
|---|---|---|
| Hover / focus / chip state | 140ms | `ease-out` |
| Panel, drawer, sidebar rail | 220ms | `cubic-bezier(.4, 0, .2, 1)` |
| Row/list entrance (stagger 40ms) | 260ms | `cubic-bezier(.2, .8, .2, 1)` |
| Toast (sweetalert2) | library default, unmodified |

- Motion never gates content: the final state renders immediately under
  `prefers-reduced-motion: reduce`.
- Animate `transform` and `opacity` only. No `width`/`height`/`top` animation.
- No motion on the login form itself — the user is waiting for a network round
  trip; a bouncing field competes with the only thing that matters.

## Components

- **Button** — three intents (primary, secondary/outline, danger) × default
  and loading. Loading disables the control and keeps its width (no layout
  shift) with an inline spinner plus `aria-busy`.
- **Field** — always a visible `<label>`; placeholder is never the label.
  Helper text above the error, error below the field with an icon + text and
  `aria-describedby`, `aria-invalid` on the input. Errors are announced once,
  not per keystroke; validation fires on submit and on blur.
- **Status chip** — `ok` / `warn` / `danger` / `info` / neutral, icon + label,
  4px radius, 2px vertical padding.
- **Card** — `--surface`, `1px var(--line)`, 6px radius, 20px padding, optional
  44px header with a title and one action.
- **Empty state** — icon, one sentence of what would appear here, one action.
  Never a bare "No data".

## Interaction rules

- **Protected routes render nothing until the session is confirmed.** A
  redirect decision is made from a verified server response, never from a token
  the client merely possesses.
- The login form posts once per submit; while in flight the button is disabled
  and `aria-busy`. Repeated failures change nothing about what the page reveals.
- One failure message for every credential failure — wrong email, wrong
  password, inactive account, and unknown account are indistinguishable to the
  visitor. The remaining-attempts and lockout state is communicated as a rate
  limit, not as a hint about which accounts exist.
- Sign-out clears client state and revokes the server-side token.
- Session expiry (401) surfaces one message and returns to login; it never
  loops.

## Bans

Emoji as icons. Raw hex in components. Placeholder-as-label. Color-only status.
Icon-only buttons without an accessible name. Gradients. Card drop shadows.
Decorative motion. `localStorage` for session tokens. Any credential, driver
name, or server name in client code. `dangerouslySetInnerHTML`.
