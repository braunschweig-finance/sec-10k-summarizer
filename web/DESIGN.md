# Design system: the working paper

The site looks like an auditor's working paper, because that is what it does: it takes figures from a filing,
recalculates from them, and shows where each one came from. Every color and typeface carries that meaning.

## Color tokens (`app/globals.css`)

| Token | Hex | Use it for | Contrast on `page` |
| --- | --- | --- | --- |
| `page` | `#e4eadf` | The page: columnar-pad green | |
| `sheet` | `#f8faf5` | Cards, tables, the masthead: sheets laid on the page | |
| `rule` | `#b7c4b0` | Borders and table rules | |
| `ink` | `#17241d` | Body text, and any figure the app **calculated** | 13.1 : 1 |
| `muted` | `#4f5e56` | Secondary text | 5.6 : 1 |
| `input` | `#1a47a0` | Figures **copied as filed** (blue, as in a financial model), links, focus ring | 7.0 : 1 |
| `pass` | `#256b3c` | Discussed, positive, verified | 5.3 : 1 |
| `note` | `#835200` | Caveats: medium flags, reworded risks, disclaimers | 5.4 : 1 |
| `flag` | `#b0261c` | Red flags, errors, "not found". Also the red margin line | 5.5 : 1 |
| `orig` | `#74368a` | Pay Efficiency, the project's own metric | 6.5 : 1 |

Rules:
- Blue means "a number as filed". Don't use `input` for a ratio, fair value or score; those are `ink`.
- Red is only for problems. Don't use it for decoration (the single exceptions are the masthead's double rule and
  the working paper's margin line, both taken from a real columnar pad).
- No gradients, glows or blurs.

Chart series (`components/charts.tsx`, `SERIES`): `a` blue `#1A47A0`, `b` ochre `#A35F00`, `c` purple `#74368A`.
Lines are always labeled or dashed too, so color is never the only cue.

## Type

| Face | Utility | Use it for |
| --- | --- | --- |
| Public Sans (the U.S. government's typeface) | default, `font-display` | Everything the app says. Headings 700-800 |
| Public Sans, tabular lining figures | `figures` | Every number, ticker and date, so columns line up |
| Source Serif 4 | `filed` | Text quoted from a filing (proxy sentences, 10-K quotes, 8-K text) |

- Labels are sentence case (`.eyebrow` is small, semibold, muted). No tracked-out capitals.
- No monospace anywhere.

## Shape and motion

- Corners: `rounded` (4px) on sheets, `rounded-sm` (2px) on buttons, inputs and badges. Dots stay round.
- One shadow, on the hero working paper only.
- One orchestrated moment: the tick marks on the working paper draw in once on load (`.tick`). Everything else
  appears as it is. Motion that answers a click (tab fade, accordion open) is fine. `prefers-reduced-motion` turns
  the tick drawing off.

## Components

- **Tick** (`components/fx.tsx`): auditor's check mark, optional letter keyed to a legend (`a` agreed to the 10-K,
  `b` recalculated). Blue next to a filed figure, black next to a calculated one.
- **WorkingPaper** (`components/Terminal.tsx`): the hero. Two filed figures, the margin worked from them, and the
  tick legend. Shows the company being looked at, or the Caterpillar example before a lookup.
- **Tabs**: plain text with a 3px ink underline on the active one.
- **Notices**: a sheet with a 4px left border in `input` (sample data), `flag` (errors) or `note` (caveats).

## Copy

- Say what a thing does in plain words ("Look up", "Reading filings…"), no slogans.
- No arrows on buttons. `↗` only marks a link that opens EDGAR in a new tab.
