# Design tokens

Extracted from the design source files in `docs/design/source/*.dc.html` and checked against the screenshots
in `docs/design/*.png`. Every value cites where it came from (`File:line`, first or most representative
occurrence). The designs use inline styles, so these names are ours; the values are the designers'.

`apps/web/tailwind.config.ts` maps these tokens one to one. Change a value here first, then in the config.

## Colour

### Text and neutrals

| Token | Hex | Used for | Source |
| --- | --- | --- | --- |
| `ink` | `#17211D` | Primary text, headings, numbers | `Main.dc.html:18` (root `color`) |
| `ink-2` | `#33403B` | Nav items, table cells, secondary text on white | `Main.dc.html:42` |
| `muted` | `#4A5752` | Labels, subtitles, table headers, captions | `Main.dc.html:73`, `:89`, `:166` |
| `muted-2` | `#5C6863` | Quieter meta text, icons, counts, "/ 5" suffix, empty score "—" | `Main.dc.html:33`, `:121`, `:235` |
| `subtle` | `#6B7772` | "Not included" in plan tables | `Plans.dc.html:164` |
| `line-strong` | `#A9B4AF` | Dashed drop-zone and "add" borders | `Upload.dc.html:302`, `Rubrics.dc.html:194` |
| `line-input` | `#CFD6D3` | Input and secondary-button borders | `Main.dc.html:92`, `:97` |
| `line` | `#DDE2E0` | Panel borders, sidebar border, pressed segmented button ring | `Main.dc.html:20`, `:108`, `:155` |
| `line-subtle` | `#E6EAE8` | Dividers inside panels, plan card border, stage card border | `Main.dc.html:70`, `:109`, `:152` |
| `track` | `#EEF1F0` | Table row dividers, progress-bar tracks | `Main.dc.html:72`, `:178`, `:213` |
| `fill` | `#F1F3F2` | Segmented control background | `Main.dc.html:154` |
| `fill-2` | `#E9ECEB` | Timeline section labels on the report page | `Analysis.dc.html:142` |
| `surface` | `#FFFFFF` | Panels, sidebar, inputs | `Main.dc.html:20`, `:108` |
| `surface-subtle` | `#F8F9F8` | Campus switcher, neutral stage cards | `Main.dc.html:30`, `:254` |
| `surface-faint` | `#FAFBFA` | Waveform background, unselected option cards | `Analysis.dc.html:154`, `Setup.dc.html:191` |
| `page` | `#F3F5F4` | Page background behind panels | `Main.dc.html:13`, `:18` |

### Primary (brand blue)

| Token | Hex | Used for | Source |
| --- | --- | --- | --- |
| `primary` | `#2546B8` | Primary button, links, focus ring, active marks | `Main.dc.html:14`, `:101` |
| `primary-hover` | `#1A3490` | Link hover; also text on primary tints (active nav, "Transcribing" chip) | `Main.dc.html:14`, `:38`, `:228` |
| `primary-tint` | `#E8EDFB` | Active nav background, in-progress chip background | `Main.dc.html:38`, `:228` |
| `primary-tint-subtle` | `#F3F6FD` | In-progress stage cards | `Main.dc.html:256` |
| `primary-tint-strong` | `#DCE3F7` | Avatar background, in-progress stage card border | `Main.dc.html:76`, `:256` |
| `primary-border` | `#B9C6EE` | Selected option-card border | `Setup.dc.html:191` |
| `primary-disabled` | `#C9D2EE` | Disabled primary button background | `Rubrics.dc.html:98` |
| `primary-disabled-ink` | `#33407A` | Disabled primary button text | `Rubrics.dc.html:98` |
| `primary-chart` | `#3A57C4` | Teacher bars in the talk-time chart | `Analysis.dc.html:352` |
| `brand-accent` | `#F2B35B` | Amber bar in the logo mark only | `Main.dc.html:25` |

### Status

| Token | Hex | Used for | Source |
| --- | --- | --- | --- |
| `success` | `#1E6B4B` | Positive deltas, "Analysed" chip text, scores ≥ 3.5 (overview) | `Main.dc.html:112`, `:227`, `:238` |
| `success-bar` | `#2E8B62` | Progress and score bars in the good band | `Analysis.dc.html:275` |
| `success-tint` | `#E3F2EA` | "Analysed" / "Live" / "Ready" chip background | `Main.dc.html:227`, `Rubrics.dc.html:233` |
| `warning` | `#8A5200` | Mid-band score text (3.0–3.49 on overview), "Changed in draft" | `Main.dc.html:237`, `Rubrics.dc.html:157` |
| `warning-ink` | `#7A4300` | Text on warning tints ("Needs review" chip, Reviews badge) | `Main.dc.html:51`, `:230`, `:258` |
| `warning-tint` | `#FDEBD3` | "Needs review" / "Calibrating" chip, Reviews badge | `Main.dc.html:51`, `:230` |
| `warning-tint-subtle` | `#FDF1DE` | Mid-band score chip background | `Analysis.dc.html:276` |
| `warning-surface` | `#FEF6EC` | "Needs review" stage card background | `Main.dc.html:258` |
| `warning-border` | `#F7DDB8` | "Needs review" stage card border | `Main.dc.html:258` |
| `danger` | `#B42318` | Low scores (< 3), error text | `Main.dc.html:236`, `Upload.dc.html:264` |
| `danger-bar` | `#C8372B` | Progress and score bars in the low band | `Analysis.dc.html:277` |
| `danger-tint` | `#FBE9E7` | Low-score chip and error icon background | `Analysis.dc.html:277`, `Upload.dc.html:264` |

### Conversation types

| Token | Hex | Type | Source |
| --- | --- | --- | --- |
| `type-teaching` | `#2546B8` | Teaching (same value as `primary`) | `Main.dc.html:64`, `:232` |
| `type-reception` | `#D9831F` | Reception (also the mid-band score bar) | `Main.dc.html:65`, `:232`; `Analysis.dc.html:276` |
| `type-counselling` | `#1E7A55` | Counselling (close to, but not the same as, `success`) | `Main.dc.html:66`, `:232`; `Setup.dc.html:173` |
| `type-meeting` | `#7A4DB8` | Meetings | `Main.dc.html:67`, `:232`; `Setup.dc.html:175` |
| `type-sales` | `#0F7C8C` | Sales | `Main.dc.html:68`, `:232`; `Setup.dc.html:176` |

Speaker colours on the report page: teacher `#3A57C4` (`primary-chart`), students `#E39A3B`
(`Analysis.dc.html:133`, `:352`), token `speaker-students`.

## Typography

**Family:** `'Instrument Sans', 'Segoe UI', system-ui, sans-serif` (`Main.dc.html:18`). The designs load it
from Google Fonts (`Main.dc.html:10`); the app self-hosts it with `@fontsource/instrument-sans` instead, so
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

`outline: 2px solid #2546B8; outline-offset: 2px` on `:focus-visible` for buttons, links, inputs, selects and
textareas, plus `label:focus-within` for the upload zone and `label:has(input[type=radio]:focus-visible)` for
option cards. Source: line 15 of every design file (`Main.dc.html:15`, `Upload.dc.html:15`,
`Setup.dc.html:15-16`).

## Touch size

Minimum touch target **44px**. In the designs, header inputs and buttons, the campus switcher and primary
actions are 44px (`Main.dc.html:30`, `:92`, `:97`, `:101`).

**Gap in the designs:** nav rows are 40px (`Main.dc.html:38`), conversation-type rows 36px (`:64`) and
segmented-control buttons 32px (`:155`). These are below 44px. The spike matches the design; P6.1 needs a
decision (raise them to 44px, or accept them as desktop-only).

## Status chips

Pill: `padding 3px 9px`, radius `full`, 12.5px / 600, with a 6px dot in the text colour
(`Main.dc.html:187`).

| Status | Text | Background | Source |
| --- | --- | --- | --- |
| Analysed | `success` `#1E6B4B` | `success-tint` `#E3F2EA` | `Main.dc.html:227` |
| Transcribing | `primary-hover` `#1A3490` | `primary-tint` `#E8EDFB` | `Main.dc.html:228` |
| Analysing | `primary-hover` `#1A3490` | `primary-tint` `#E8EDFB` | `Main.dc.html:229` |
| Needs review | `warning-ink` `#7A4300` | `warning-tint` `#FDEBD3` | `Main.dc.html:230` |
| Live (rubric) | `success` | `success-tint` | `Rubrics.dc.html:233` |
| Calibrating (rubric) | `warning-ink` | `warning-tint` | `Rubrics.dc.html:234` |

**Not in the designs:** "Failed" and "Uploading" chips (P6.1 lists both). The nearest source styles are the
upload rows: error = `danger` on `danger-tint`, uploading = `primary-hover` on `primary-tint`
(`Upload.dc.html:261`, `:264`). Use those unless the designer says otherwise.

Badge (nav count): `min-width 22px`, `padding 1px 7px`, radius `full`, 12px / 600, `warning-ink` on
`warning-tint` (`Main.dc.html:51`).

**Box sizing:** the design files leave most elements at the browser default (`content-box`); only the sidebar,
main area and a few wrappers set `border-box`. Tailwind uses `border-box` everywhere, so a padded element with a
`min-width` renders smaller unless the padding is added in: the badge above is 36px wide in the screenshot
(22 + 7 + 7). The search field in the header is 46px tall in the screenshot (44px + 1px borders); the app keeps
it at the 44px token.

Type marker: 8×8px square, radius `xs`, in the type colour (`Main.dc.html:64`, `:183`).

## Score colour bands — open question

The two screens disagree:

| Screen | Low (`danger`) | Mid (`warning`) | Good (`success`) | Source |
| --- | --- | --- | --- | --- |
| Overview table | < 3.0 | 3.0 – 3.49 | ≥ 3.5 | `Main.dc.html:233-239` |
| Report score chips | < 3.0 | 3.0 – 3.99 | ≥ 4.0 | `Analysis.dc.html:274-278` |

The spike follows the overview. Pick one rule before P6.1 builds `ScoreChip`.
