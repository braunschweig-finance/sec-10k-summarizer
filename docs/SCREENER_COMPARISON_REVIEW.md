# Screener comparison verification — November 9, 2026

Select two to four cached company rows in the screener and open the inline side-by-side comparison. Selected rows persist across filters and pagination within a dated snapshot; reloading or leaving the page clears them. Shared screener links preserve filters, not comparison selections.

The comparison uses the exact selected row metrics without new per-company requests, financial formulas, rankings or investment recommendations. Each column preserves its fiscal year end, cached price date, filing links, valuation provenance, missing-data notes, signed compensation and low-confidence/grade/upside caveats. Different periods and sectors are explicitly disclosed.

Selection and comparison are unavailable while results update, during a request failure or pending search. Snapshot changes clear selections. If the build date is unknown, different response objects cannot be combined. A selection remains removable at the four-company cap and from an empty filtered result set.

Validation:

- Production build and TypeScript passed; 45 tests passed (7 selection/snapshot tests and 38 existing context, URL and Terminal tests).
- Independent final review approved readiness gates, closing behavior, removal below two and dated/undated snapshot identity fixes. Initial review's readiness blocker was repaired before approval.
- Real-data browser checks verified disabled comparison with one selection, four-company cap, fifth checkbox disabled, deselection still enabled at cap, selection across pages and a no-match filter, and displayed metrics/date/source/caveat preservation.
- Opening focused the comparison heading; Close returned focus to Compare selected. Updating filters closed the view. Removing down to one hid it; Clear removed selection.
- At 390px, page width remained within the viewport and the named comparison region scrolled with keyboard arrows.

Known limits: snapshot identity relies on the API build timestamp for dated results; unknown build dates use response identity conservatively. No new snapshot-generation guarantees, persistent portfolio storage or comparison-sharing endpoint were introduced.
