# Design tokens

**UI v2 (since 2026-10-27).** Colours and the font come from the v2 screens in `docs/design/v2/` (`01-overview.png`,
`02-recordings.png`, `03-lesson-report.png`, `04-sales-report.png`, `05-reviews.png`, rendered from the designer's
PDF, which is too large for the repository). The owner gave the main values; tints and bar colours were sampled from
the PDF's pixels. Sizes, radii, spacing and the focus ring below are still the v1
values from `docs/design/source/*.dc.html` (`File:line`) until a page's v2 restyle changes them.

`apps/web/tailwind.config.ts` maps these tokens one to one. Change a value here first, then in the config.

## Colour

Text on every background below meets WCAG AA (4.5:1) for normal text.

### Text and neutrals

| Token | Hex | Used for |
| --- | --- | --- |
| `ink` | `#121521` | Primary text, headings, numbers; the signed-in person's avatar |
| `ink-2` | `#3D414C` | Nav items, table cells, secondary text on white |
| `ink-raised` | `#262B3E` | Chips on an ink surface (the sales report's "Next step agreed" card) |
| `muted` | `#5F6677` | Labels, subtitles, table headers, captions |
| `muted-2`, `subtle` | `#686F7F` | Quieter meta text, icons, counts |
| `line` | `#E4E7EC` | Panel borders, sidebar border, empty score-dash segments |
| `line-input` | `#D7D8DC` | Input and secondary-button borders |
| `line-strong` | `#B8BDC7` | Dashed drop-zone borders |
| `line-subtle` | `#ECEEF2` | Dividers inside panels |
| `track` | `#EEF0F3` | Bar tracks; the speaker strip where nobody speaks |
| `fill`, `fill-2` | `#F1F2F5`, `#E9EBEF` | Segmented-control background, timeline section labels |
| `surface` | `#FFFFFF` | Panels, sidebar, inputs |
| `surface-subtle` | `#F6F7F9` | Plan block, metric cards inside panels, timeline lanes |
| `surface-faint` | `#FAFBFC` | Unselected option cards |
| `page` | `#F6F7F9` | Page ground behind panels |

### Primary and speakers

One blue (owner, 2026-10-27): the primary colour is also the staff speaker's colour.

| Token | Hex | Used for |
| --- | --- | --- |
| `primary` | `#3346D3` | Primary button, links, focus ring, active nav text, Reviews badge |
| `primary-hover` | `#2536B0` | Hover; text on primary tints |
| `primary-tint` | `#EEF0FC` | Active nav background, org mark, "Try next time" box |
| `primary-tint-subtle` | `#F5F5FD` | Selected list item |
| `primary-tint-strong` | `#DDE2F8` | Stronger tint |
| `primary-border` | `#B9C1F0` | Selected option-card border |
| `primary-disabled`, `primary-disabled-ink` | `#C9CEF2`, `#2F3A86` | Disabled primary button |
| `speaker-staff` | `#3346D3` | The analysed staff member in SpeakerStrip and the logo |
| `speaker-other` | `#F2A33A` | Everyone else (students, client, visitor); also `brand-accent` in the logo |

### Score tones and status

| Token | Hex | Used for |
| --- | --- | --- |
| `success` | `#0B6343` | Good-band score text, positive deltas, "Ready" |
| `success-bar` | `#1F9A6B` | Score dashes and bars in the good band |
| `success-tint` | `#DDF1E6` | Good-band chips and heatmap cells, "Handled" |
| `warning`, `warning-ink` | `#7A4A00` | Mid-band score text, "Disputed", "Needs review", other-speaker labels |
| `warning-bar` | `#E8A23F` | Score dashes in the mid band |
| `warning-tint` | `#FCEBCF` | Mid-band chips and heatmap cells |
| `warning-tint-subtle` | `#FEF6E9` | Softer amber fill |
| `warning-surface` | `#FEFAF1` | Quote boxes on the deal card, highlighted transcript lines, the proposer's card |
| `warning-border` | `#ECD9B8` | Border of those boxes |
| `danger` | `#A12B12` | Low-band score text, errors, "Failed", "Open" |
| `danger-bar` | `#DB532E` | Score dashes in the low band |
| `danger-tint` | `#FBE2DB` | Low-band chips and heatmap cells |

### Conversation types

| Token | Hex | Type |
| --- | --- | --- |
| `type-teaching` | `#3346D3` | Teaching (same as `primary`) |
| `type-reception` | `#F2A33A` | Reception |
| `type-counselling` | `#1E7A55` | Counselling |
| `type-meeting` | `#7A4DB8` | Meetings |
| `type-sales` | `#0F7C8C` | Sales |

## Typography

**Family:** `Geist, 'Segoe UI', system-ui, sans-serif` (UI v2). The app self-hosts it with `@fontsource/geist`, so
pages make no requests to an outside font service.

**Weights:** 400, 500, 600, 700 (`Main.dc.html:10`). 600 is the workhorse for emphasis (143 uses across the
sources), 700 for the page title, wordmark and avatar initials, 500 for table headers and suffixes.

**Base:** 14px, line-height 1.45, `font-variant-numeric: tabular-nums` on the whole page (`Main.dc.html:18`).

| Token | Size | Line height / tracking | Used for | Source |
| --- | --- | --- | --- | --- |
| `2xs` | 11px | — | Speaker badge initials | `Analysis.dc.html:149` |
| `xs` | 11.5px | — | Section labels in setup, timeline ticks | `Setup.dc.html:95`, `Analysis.dc.html:160` |
| `caption` | 12px | — | Meta text, counts, badges, stage notes | `Main.dc.html:33`, `:51`, `:143` |
| `small` | 12.5px | — | Deltas, table headers, person line, chips | `Main.dc.html:112`, `:166`, `:187` |
| `sm` | 13px | — | Labels, secondary body, segmented buttons | `Main.dc.html:110`, `:155` |
| `table` | 13.5px | — | Table body, coaching list | `Main.dc.html:164`, `:210` |
| `base` | 14px | 1.45 | Body | `Main.dc.html:18` |
| `md` | 15px | — | Option-card titles | `Setup.dc.html:55` |
| `lg` | 16px | — | Panel headings (h2) | `Main.dc.html:133` |
| `brand` | 17px | -0.01em | Wordmark | `Main.dc.html:28` |
| `xl` | 18px | — | Large panel headings | `Upload.dc.html:93`, `Rubrics.dc.html:156` |
| `2xl` | 20px | — | Stage counts, small metrics | `Main.dc.html:141` |
| `3xl` | 24px | -0.015em | Plan names | `Plans.dc.html:85` |
| `title` | 26px | 1.2 / -0.015em | Page title (h1) | `Main.dc.html:88` |
| `metric` | 28px | -0.02em | Metric-strip numbers | `Main.dc.html:111` |
| `hero` | 44px | 1 / -0.03em | Report headline score | `Analysis.dc.html:102` |

## Radii

| Token | Value | Used for | Source |
| --- | --- | --- | --- |
| `xs` | 2px | Type swatches, logo bars | `Main.dc.html:64` |
| `sm` | 3px | Legend swatches | `Analysis.dc.html:133` |
| `md` | 6px | Waveform, timeline | `Analysis.dc.html:154` |
| `seg` | 7px | Segmented-control buttons | `Main.dc.html:155` |
| `DEFAULT` | 8px | Buttons, inputs, nav items, logo | `Main.dc.html:30`, `:92`, `:101` |
| `seg-outer` | 9px | Segmented-control track | `Main.dc.html:154` |
| `card` | 10px | Stage cards, plan card | `Main.dc.html:70`, `:138` |
| `panel` | 12px | Panels | `Main.dc.html:108`, `:131` |
| `full` | 999px | Chips, badges, avatars, progress bars | `Main.dc.html:51`, `:72`, `:187` |

## Spacing

The sources use a 2px-based scale. The common steps (by number of uses) are 2, 4, 6, 8, 10, 12, 14, 16, 18, 20,
24, 28, 40 and 48 px. Tailwind's default 4px scale covers most of these; the config adds `0.5` → 2px (default),
`1.5` → 6px (default), `2.5` → 10px (default), `3.5` → 14px (default), `4.5` → 18px (added) so the odd steps
need no arbitrary values.

| Where | Value | Source |
| --- | --- | --- |
| Sidebar padding | 20px 14px | `Main.dc.html:20` |
| Sidebar width | 232px | `Main.dc.html:20` |
| Main padding | 28px clamp(16px, 3vw, 40px) 48px | `Main.dc.html:84` |
| Gap between main sections | 24px | `Main.dc.html:84`, `:149` |
| Panel padding | 18px 20px | `Main.dc.html:109`, `:131` |
| Table cell padding | 12px (20px at row ends) | `Main.dc.html:178` |
| Header control gap | 10px | `Main.dc.html:91` |

## Focus ring

`outline: 2px solid #3346D3; outline-offset: 2px` (`primary`) on `:focus-visible` for buttons, links, inputs,
selects and textareas, plus `label:focus-within` for the upload zone and `label:has(input[type=radio]:focus-visible)` for
option cards. Source: line 15 of every design file (`Main.dc.html:15`, `Upload.dc.html:15`,
`Setup.dc.html:15-16`).

## Touch size

Minimum touch target **44px**. In the designs, header inputs and buttons, the campus switcher and primary
actions are 44px (`Main.dc.html:30`, `:92`, `:97`, `:101`).

**Gap in the designs:** nav rows are 40px (`Main.dc.html:38`), conversation-type rows 36px (`:64`) and
segmented-control buttons 32px (`:155`). These are below 44px. The spike matches the design; P6.1 needs a
decision (raise them to 44px, or accept them as desktop-only).

## Status chips

Still the v1 pill until the Recordings restyle (v2 shows a dot and coloured text with no background,
`02-recordings.png`): `padding 3px 9px`, radius `full`, 12.5px / 600, with a 6px dot in the text colour
(`Main.dc.html:187`).
The token names are unchanged, so the hex values below are the v2 ones.

| Status | Text | Background |
| --- | --- | --- |
| Analysed | `success` `#0B6343` | `success-tint` `#DDF1E6` |
| Transcribing, Analysing, Uploading | `primary-hover` `#2536B0` | `primary-tint` `#EEF0FC` |
| Needs review | `warning-ink` `#7A4A00` | `warning-tint` `#FCEBCF` |
| Failed | `danger` `#A12B12` | `danger-tint` `#FBE2DB` |
| Live (rubric) | `success` | `success-tint` |
| Calibrating (rubric) | `warning-ink` | `warning-tint` |

Badge (nav count, UI v2): `min-width 22px`, `padding 1px 7px`, radius `full`, 12px / 600, white on `primary`.

**Box sizing:** the design files leave most elements at the browser default (`content-box`); only the sidebar,
main area and a few wrappers set `border-box`. Tailwind uses `border-box` everywhere, so a padded element with a
`min-width` renders smaller unless the padding is added in: the badge above is 36px wide in the screenshot
(22 + 7 + 7). The search field in the header is 46px tall in the screenshot (44px + 1px borders); the app keeps
it at the 44px token.

Type marker: 8×8px square, radius `xs`, in the type colour (`Main.dc.html:64`, `:183`).

## Score colour bands

UI v2 rule (owner, 2026-10-27; the coaching legend in `v2/01-overview.png`), in `apps/web/src/design/score.ts`:

| Low (`danger`) | Mid (`warning`) | Good (`success`) |
| --- | --- | --- |
| below 3.0 | 3.0 to 3.7 | 3.8 and above |

The cut is on the one-decimal value people see, so 3.75 (shown as 3.8) is good. It replaces the v1 rule (good
from 4.0).
