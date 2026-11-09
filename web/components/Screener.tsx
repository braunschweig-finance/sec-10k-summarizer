"use client";

import { useEffect, useRef, useState } from "react";
import { API_URL } from "@/lib/api";
import { DEFAULT_SCREENER_STATE, parseScreenerUrl, serializeScreenerUrl, type ScreenerUrlState } from "@/lib/screenerUrl";
import {
  PAGE_SIZES,
  SCREENER_GRADES,
  fetchScreener,
  type ScreenerData,
  type ScreenerQuery,
  type ScreenerRow,
} from "@/lib/screener";

// The /screener page: a dense table over the cached research snapshot (GET /api/screener, docs/SCREENER_CONTRACT.md).
// Every figure shown comes from the snapshot — nothing here is computed, estimated or invented.
// States are deliberately plain and distinct: loading, error + retry, snapshot unavailable, no match, data.

const GRADE_STYLE: Record<string, string> = {
  A: "border-teal/50 text-teal",
  B: "border-teal/30 text-teal",
  C: "border-line text-paper",
  D: "border-rose/30 text-rose",
  F: "border-rose/50 text-rose",
};

const fmtInt = (n: number) => n.toLocaleString("en-US");

const URL_KEYS = ["search", "sector", "grade", "max_pay_efficiency_pct", "min_upside_pct", "sort", "order", "limit", "offset"];

function screenUrl(state: ScreenerUrlState): URL {
  const url = new URL(window.location.href);
  URL_KEYS.forEach((key) => url.searchParams.delete(key));
  new URLSearchParams(serializeScreenerUrl(state)).forEach((value, key) => url.searchParams.set(key, value));
  return url;
}

function fmtDate(iso: string | null): string {
  if (!iso) return "unknown date";
  const d = new Date(iso);
  return isNaN(d.getTime()) ? iso : d.toLocaleDateString("en-US", { year: "numeric", month: "short", day: "numeric" });
}

const na = (reason: string | undefined) => <span className="text-muted" title={reason || undefined}>N/A</span>;

export default function Screener() {
  const [searchText, setSearchText] = useState("");
  const [search, setSearch] = useState(""); // committed search, debounced
  const [sector, setSector] = useState("");
  const [grade, setGrade] = useState("");
  const [maxPay, setMaxPay] = useState("");
  const [minUpside, setMinUpside] = useState("");
  const [sort, setSort] = useState<ScreenerUrlState["sort"]>("ticker");
  const [order, setOrder] = useState<"asc" | "desc">("asc");
  const [limit, setLimit] = useState(50);
  const [offset, setOffset] = useState(0);

  const [data, setData] = useState<ScreenerData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [retryTick, setRetryTick] = useState(0);
  const requestId = useRef(0);
  const [initialized, setInitialized] = useState(false);
  const searchTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [copyMessage, setCopyMessage] = useState("");
  const [manualUrl, setManualUrl] = useState("");
  const manualInput = useRef<HTMLInputElement>(null);
  const copyId = useRef(0);

  const cancelSearch = () => {
    if (searchTimer.current !== null) clearTimeout(searchTimer.current);
    searchTimer.current = null;
  };
  const restoreState = (state: ScreenerUrlState) => {
    cancelSearch();
    ++copyId.current;
    setSearchText(state.search);
    setSearch(state.search);
    setSector(state.sector);
    setGrade(state.grade);
    setMaxPay(state.maxPay);
    setMinUpside(state.minUpside);
    setSort(state.sort);
    setOrder(state.order);
    setLimit(state.limit);
    setOffset(state.offset);
    setCopyMessage("");
    setManualUrl("");
  };

  // Read browser state only after mounting; the first request must use these filters.
  useEffect(() => {
    const restore = () => {
      restoreState(parseScreenerUrl(window.location.search));
      setInitialized(true);
    };
    restore();
    window.addEventListener("popstate", restore);
    return () => {
      cancelSearch();
      ++requestId.current;
      ++copyId.current;
      window.removeEventListener("popstate", restore);
    };
  }, []);

  useEffect(() => {
    if (!initialized) return;
    ++copyId.current;
    const url = screenUrl({ search, sector, grade, maxPay, minUpside, sort, order, limit, offset });
    if (url.href !== window.location.href) window.history.replaceState(window.history.state, "", url.href);
    setCopyMessage("");
    setManualUrl("");
  }, [initialized, search, sector, grade, maxPay, minUpside, sort, order, limit, offset]);

  useEffect(() => {
    if (manualUrl) {
      manualInput.current?.focus();
      manualInput.current?.select();
    }
  }, [manualUrl]);

  const copyScreenLink = async () => {
    const id = ++copyId.current;
    const url = screenUrl({ search, sector, grade, maxPay, minUpside, sort, order, limit, offset }).href;
    setCopyMessage("");
    setManualUrl("");
    try {
      await navigator.clipboard.writeText(url);
      if (id !== copyId.current) return;
      setCopyMessage("Screen link copied.");
    } catch {
      if (id !== copyId.current) return;
      setCopyMessage("Could not copy the screen link. Select and copy the URL below manually.");
      setManualUrl(url);
    }
  };

  // Every filter, sort, order, page-size or page change is one snapshot request.
  // A request id guards the response: a stale response can never overwrite a newer filter set.
  useEffect(() => {
    if (!initialized || !API_URL) return;
    const id = ++requestId.current;
    setLoading(true);
    setError(null);
    const normalized = parseScreenerUrl(serializeScreenerUrl({ search, sector, grade, maxPay, minUpside, sort, order, limit, offset }));
    const q: ScreenerQuery = { sort: normalized.sort, order: normalized.order, limit: normalized.limit, offset: normalized.offset };
    if (normalized.search) q.search = normalized.search;
    if (normalized.sector) q.sector = normalized.sector;
    if (normalized.grade) q.grade = normalized.grade as ScreenerQuery["grade"];
    if (normalized.maxPay !== "") q.max_pay_efficiency_pct = Number(normalized.maxPay);
    if (normalized.minUpside !== "") q.min_upside_pct = Number(normalized.minUpside);
    fetchScreener(q)
      .then((d) => {
        if (requestId.current !== id) return;
        setData(d);
        setLoading(false);
      })
      .catch((e) => {
        if (requestId.current !== id) return;
        setError((e as Error).message);
        setLoading(false);
      });
    return () => { ++requestId.current; };
  }, [initialized, API_URL, search, sector, grade, maxPay, minUpside, sort, order, limit, offset, retryTick]);

  // Changing any filter (or the page size) goes back to the first page.
  const resetPage = () => setOffset(0);
  const onSortClick = (key: ScreenerUrlState["sort"]) => {
    if (key === sort) setOrder((o) => (o === "asc" ? "desc" : "asc"));
    else {
      setSort(key);
      setOrder("asc");
    }
    resetPage();
  };
  const resetAll = () => {
    restoreState(DEFAULT_SCREENER_STATE);
  };

  const matched = data?.matched ?? 0;
  const first = data && data.rows.length ? Math.min(data.offset + 1, matched) : 0;
  const last = data ? Math.min(data.offset + data.rows.length, matched) : 0;
  const pages = Math.max(1, Math.ceil(matched / limit));
  const page = Math.floor(offset / limit) + 1;
  const lowCount = data ? data.rows.filter((r) => r.valuation_confidence === "low").length : 0;
  const missingNote = (r: ScreenerRow) => (r.missing.length ? r.missing.join(" · ") : undefined);
  const caveats = (r: ScreenerRow, prefix: string) => r.missing
    .filter((reason) => reason.startsWith(prefix))
    .map((reason) => reason.replace(/^[^:]+:\s*/, ""))
    .join(" · ");

  const field = "min-h-11 min-w-0 w-full rounded-xl border border-line bg-ink px-3 py-2 text-base sm:text-sm outline-none focus:border-brass";
  const selectField =
    "min-h-11 min-w-0 max-w-full rounded-xl border border-line bg-ink px-2.5 py-2 text-base sm:text-sm text-paper outline-none focus:border-brass";
  const button = "min-h-11 rounded-xl border border-line px-3.5 py-2 text-sm transition-colors hover:border-brass focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brass disabled:opacity-40 disabled:hover:border-line";

  return (
    <main className="min-h-screen min-w-0">
      <section className="gutter mx-auto flex min-w-0 w-full max-w-6xl flex-col gap-6 py-12 [overflow-wrap:anywhere]">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div className="flex flex-col gap-2">
            <span className="eyebrow">Company screener · cached snapshot</span>
            <h1 className="text-4xl font-extrabold tracking-tight sm:text-5xl">Screen the universe</h1>
          </div>
          <a href="/" className="rounded-full border border-line px-4 py-2 text-sm hover:border-brass">
            ← Terminal
          </a>
        </div>

        {!API_URL ? (
          // Sample mode: there is no snapshot to screen, so say so instead of showing invented rows.
          <div className="flex flex-col gap-3 rounded-2xl border border-line bg-panel p-6">
            <h2 className="text-lg font-bold">Screener is offline in this preview</h2>
            <p className="text-sm text-muted">
              The screener reads the cached research snapshot from the data API, so it turns on once the API is online. No sample
              rows are shown — there is nothing here to screen yet.
            </p>
          </div>
        ) : (
          <>
            <form
              className="grid min-w-0 grid-cols-1 gap-3 rounded-2xl border border-line bg-panel p-4 min-[400px]:grid-cols-2 sm:grid-cols-3 lg:grid-cols-6"
              onSubmit={(e) => e.preventDefault()}
            >
              <div className="min-w-0 flex flex-col gap-1 min-[400px]:col-span-2 sm:col-span-3 lg:col-span-2">
                <label htmlFor="sc-search" className="eyebrow">
                  Search ticker or name
                </label>
                <input
                  id="sc-search"
                  value={searchText}
                  onChange={(e) => {
                    const value = e.target.value;
                    ++copyId.current;
                    setCopyMessage("");
                    setManualUrl("");
                    setSearchText(value);
                    cancelSearch();
                    searchTimer.current = setTimeout(() => {
                      searchTimer.current = null;
                      setSearch(value.trim().slice(0, 100));
                      setOffset(0);
                    }, 350);
                  }}
                  maxLength={100}
                  placeholder="e.g. CAT or Caterpillar"
                  autoComplete="off"
                  className={field}
                />
              </div>
              <div className="flex flex-col gap-1">
                <label htmlFor="sc-sector" className="eyebrow">
                  Sector
                </label>
                <select
                  id="sc-sector"
                  value={sector}
                  onChange={(e) => {
                    setSector(e.target.value);
                    resetPage();
                  }}
                  className={selectField}
                >
                  <option value="">All sectors</option>
                  {sector && !data?.sectors.includes(sector) && <option value={sector}>{sector}</option>}
                  {(data?.sectors ?? []).map((s) => (
                    <option key={s} value={s}>
                      {s}
                    </option>
                  ))}
                </select>
              </div>
              <div className="flex flex-col gap-1">
                <label htmlFor="sc-grade" className="eyebrow">
                  Company Grade
                </label>
                <select
                  id="sc-grade"
                  value={grade}
                  onChange={(e) => {
                    setGrade(e.target.value);
                    resetPage();
                  }}
                  className={selectField}
                >
                  <option value="">All grades</option>
                  {SCREENER_GRADES.map((g) => (
                    <option key={g} value={g}>
                      Grade {g}
                    </option>
                  ))}
                </select>
              </div>
              <div className="flex flex-col gap-1">
                <label htmlFor="sc-maxpay" className="eyebrow">
                  Max Pay Efficiency %
                </label>
                <input
                  id="sc-maxpay"
                  type="number"
                  step="0.1"
                  inputMode="decimal"
                  value={maxPay}
                  onChange={(e) => {
                    setMaxPay(e.target.value);
                    resetPage();
                  }}
                  placeholder="e.g. 2.0"
                  className={field}
                />
              </div>
              <div className="flex flex-col gap-1">
                <label htmlFor="sc-upside" className="eyebrow">
                  Min upside vs peers %
                </label>
                <input
                  id="sc-upside"
                  type="number"
                  step="1"
                  inputMode="decimal"
                  value={minUpside}
                  onChange={(e) => {
                    setMinUpside(e.target.value);
                    resetPage();
                  }}
                  placeholder="e.g. 5"
                  className={field}
                />
              </div>
              <div className="flex flex-wrap items-end gap-3 min-[400px]:col-span-2 sm:col-span-3 lg:col-span-6">
                <button type="button" onClick={resetAll} className={button}>
                  Reset all filters
                </button>
                <button
                  type="button"
                  onClick={copyScreenLink}
                  disabled={!initialized || searchText.trim().slice(0, 100) !== search}
                  className={button}
                >
                  Copy screen link
                </button>
                <p role="status" aria-live="polite" className="w-full text-sm text-muted">{copyMessage}</p>
                {manualUrl && (
                  <div className="flex w-full min-w-0 flex-col gap-1">
                    <label htmlFor="sc-manual-url" className="text-sm text-muted">Screen link for manual copying</label>
                    <input
                      ref={manualInput}
                      id="sc-manual-url"
                      type="text"
                      readOnly
                      value={manualUrl}
                      onFocus={(e) => e.currentTarget.select()}
                      className={field}
                    />
                  </div>
                )}
              </div>
            </form>

            <p role="status" className="text-sm text-muted">
              {loading
                ? "Reading the cached snapshot…"
                : error
                  ? ""
                  : data
                    ? `${fmtInt(data.matched)} of ${fmtInt(data.total)} companies match the current filters`
                    : "Loading the snapshot…"}
            </p>

            {error && (
              <div role="alert" className="flex flex-col gap-3 rounded-2xl border border-rose/30 bg-rose/10 p-5">
                <p className="text-sm text-rose">{error}</p>
                <button
                  type="button"
                  onClick={() => setRetryTick((t) => t + 1)}
                  className="self-start rounded-xl bg-paper px-4 py-2 text-sm font-medium text-ink"
                >
                  Try again
                </button>
              </div>
            )}

            {!error && loading && !data && (
              <div className="overflow-hidden rounded-2xl border border-line">
                <div className="h-11 border-b border-line bg-panel" />
                {Array.from({ length: 8 }).map((_, i) => (
                  <div key={i} className="flex animate-pulse items-center gap-4 border-b border-line px-4 py-3.5">
                    <div className="h-3 w-14 rounded bg-line" />
                    <div className="h-3 flex-1 rounded bg-line/60" />
                    <div className="h-3 w-24 rounded bg-line" />
                    <div className="h-3 w-12 rounded bg-line" />
                    <div className="h-3 w-16 rounded bg-line/60" />
                  </div>
                ))}
              </div>
            )}

            {!error && data && !data.available && (
              <div className="flex flex-col gap-3 rounded-2xl border border-line bg-panel p-6">
                <h2 className="text-lg font-bold">Screener snapshot unavailable</h2>
                <p className="text-sm text-muted">
                  The cached snapshot wasn&apos;t found on the server, so no rows are shown — nothing below is a sample or an estimate.
                </p>
                {data.warnings.map((w) => (
                  <p key={w} className="text-sm text-brass">
                    {w}
                  </p>
                ))}
                <button
                  type="button"
                  onClick={() => setRetryTick((t) => t + 1)}
                  className="self-start rounded-xl bg-paper px-4 py-2 text-sm font-medium text-ink"
                >
                  Try again
                </button>
              </div>
            )}

            {!error && data && data.available && data.rows.length === 0 && !loading && (
              <div className="flex flex-col gap-3 rounded-2xl border border-line bg-panel p-6">
                <h2 className="text-lg font-bold">No match</h2>
                <p className="text-sm text-muted">No companies in the snapshot match the current filters. Loosen or clear them.</p>
                <button type="button" onClick={resetAll} className={`${button} self-start`}>
                  Clear all filters
                </button>
              </div>
            )}

            {!error && data && data.available && data.rows.length > 0 && (
              <div className="flex min-w-0 max-w-full flex-col gap-3">
                <div className="flex flex-wrap items-center gap-x-5 gap-y-1 text-xs text-muted">
                  <span>
                    Snapshot built <span className="text-paper">{fmtDate(data.built_at)}</span>
                  </span>
                  <span>
                    Coverage of {fmtInt(data.total)}: Pay Efficiency {fmtInt(data.coverage.pay_efficiency_pct)} · Company Grade{" "}
                    {fmtInt(data.coverage.grade)} · peer upside {fmtInt(data.coverage.upside_pct)}
                  </span>
                  <span>Prices are cached; each row shows its price date</span>
                </div>

                {data.warnings.length > 0 && (
                  <div className="flex flex-col gap-1 rounded-xl border border-brass/30 bg-brass/10 px-4 py-3 text-sm text-brass">
                    {data.warnings.map((w) => (
                      <p key={w}>{w}</p>
                    ))}
                  </div>
                )}

                <p id="screener-scroll-help" className="text-xs leading-relaxed text-muted">
                  <span className="lg:hidden">Swipe horizontally to see all columns. </span>
                  Keyboard: focus the table area and use the left and right arrow keys to scroll.
                </p>
                <div
                  className="min-w-0 max-w-full overflow-x-auto rounded-2xl border border-line focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brass"
                  role="region"
                  aria-label="Company screener results"
                  aria-describedby="screener-scroll-help"
                  tabIndex={0}
                  aria-busy={loading}
                >
                  <table className="w-full min-w-[1020px] text-sm [overflow-wrap:normal]">
                    <thead className="bg-panel text-muted">
                      <tr>
                        <SortTh label="Company" k="ticker" sort={sort} order={order} onSort={onSortClick} />
                        <SortTh label="Name" k="name" sort={sort} order={order} onSort={onSortClick} />
                        <SortTh label="Sector" k="sector" sort={sort} order={order} onSort={onSortClick} />
                        <th scope="col" className="px-3 py-2.5 text-left font-medium">
                          FY end
                        </th>
                        <SortTh label="Pay Efficiency %" k="pay_efficiency_pct" sort={sort} order={order} onSort={onSortClick} align="text-right" />
                        <SortTh label="Company Grade" k="grade_score" sort={sort} order={order} onSort={onSortClick} align="text-right" />
                        <SortTh label="Upside vs peers" k="upside_pct" sort={sort} order={order} onSort={onSortClick} align="text-right" />
                        <th scope="col" className="px-3 py-2.5 text-left font-medium">
                          Price (cached)
                        </th>
                        <th scope="col" className="px-3 py-2.5 text-left font-medium">
                          Sources
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.rows.map((r) => (
                        <tr key={r.ticker} className="border-t border-line hover:bg-panel/70">
                          <td className="px-3 py-2">
                            <a
                              href={`/?ticker=${encodeURIComponent(r.ticker)}`}
                              className="font-mono text-brass hover:underline"
                              title={`Open ${r.name} in the terminal`}
                            >
                              {r.ticker}
                            </a>
                          </td>
                          <td className="px-3 py-2">{r.name}</td>
                          <td className="px-3 py-2 text-muted">{r.sector ?? "—"}</td>
                          <td className="whitespace-nowrap px-3 py-2 font-mono text-xs text-muted">{r.fy_end ?? "—"}</td>
                          <td
                            className="tnum px-3 py-2 text-right font-mono"
                            title={r.pay_efficiency_pct === null ? missingNote(r) : "CEO pay actually paid ÷ operating income; stays signed, so a negative value is not better efficiency"}
                          >
                            {r.pay_efficiency_pct === null ? (
                              na(missingNote(r))
                            ) : (
                              <span className={`whitespace-nowrap ${r.pay_efficiency_pct < 0 ? "text-muted" : ""}`}>
                                {r.pay_efficiency_pct.toFixed(2)}%
                              </span>
                            )}
                          </td>
                          <td className="px-3 py-2 text-right" title={r.grade === null ? missingNote(r) : caveats(r, "grade.") || undefined}>
                            {r.grade === null ? (
                              na(missingNote(r))
                            ) : (
                              <span className="inline-flex items-center gap-1.5">
                                <span
                                  className={`inline-flex h-6 min-w-6 items-center justify-center rounded-md border px-1 font-mono text-xs font-bold ${GRADE_STYLE[r.grade] ?? "border-line text-paper"}`}
                                >
                                  {r.grade}
                                </span>
                                {r.grade_score !== null && (
                                  <span className="tnum font-mono text-xs text-muted">{r.grade_score.toFixed(0)}</span>
                                )}
                              </span>
                            )}
                            {r.grade !== null && caveats(r, "grade.") && (
                              <p className="mt-1 max-w-64 text-left text-xs leading-relaxed text-muted">{caveats(r, "grade.")}</p>
                            )}
                          </td>
                          <td
                            className="tnum px-3 py-2 text-right font-mono"
                            title={
                              r.upside_pct === null
                                ? missingNote(r)
                                : r.sources.valuation_source
                                  ? `Source: ${r.sources.valuation_source}`
                                  : "Peer-valuation upside vs the cached price"
                            }
                          >
                            {r.upside_pct === null ? (
                              na(missingNote(r))
                            ) : (
                              <span className={`whitespace-nowrap ${r.upside_pct >= 0 ? "text-teal" : "text-rose"}`}>
                                {r.upside_pct >= 0 ? "+" : ""}
                                {r.upside_pct.toFixed(1)}%
                              </span>
                            )}
                            {r.upside_pct !== null && caveats(r, "upside_pct:") && (
                              <p className="mt-1 max-w-64 text-left text-xs leading-relaxed text-muted">{caveats(r, "upside_pct:")}</p>
                            )}
                            {r.valuation_confidence === "low" && (
                              <span
                                className="ml-1.5 align-middle rounded border border-brass/40 bg-brass/10 px-1 py-0.5 font-sans text-[10px] text-brass"
                                title="Low-confidence valuation estimate — not a reliable investment signal"
                              >
                                low
                              </span>
                            )}
                          </td>
                          <td
                            className="whitespace-nowrap px-3 py-2 font-mono text-xs text-muted"
                            title={r.price_date ? `Cached close on ${r.price_date}` : "No cached price in the snapshot"}
                          >
                            {r.price_date ?? "—"}
                          </td>
                          <td className="px-3 py-2">
                            <span className="flex gap-2 font-mono text-xs">
                              {r.sources.financials_url && (
                                <a
                                  href={r.sources.financials_url}
                                  target="_blank"
                                  rel="noreferrer"
                                  className="text-teal hover:underline"
                                >
                                  10-K
                                </a>
                              )}
                              {r.sources.proxy_url && (
                                <a
                                  href={r.sources.proxy_url}
                                  target="_blank"
                                  rel="noreferrer"
                                  className="text-teal hover:underline"
                                >
                                  14A
                                </a>
                              )}
                              {r.sources.valuation_source && (
                                <span className="cursor-help text-muted" title={`Valuation source: ${r.sources.valuation_source}`}>
                                  src
                                </span>
                              )}
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>

                <div className="flex flex-wrap items-center justify-between gap-3 text-sm">
                  <span className="text-muted">
                    Showing {first}–{last} of {fmtInt(matched)} matched · {fmtInt(data.total)} in snapshot
                  </span>
                  <div className="flex min-w-0 w-full flex-wrap items-center gap-2 sm:w-auto">
                    <label htmlFor="sc-size" className="text-muted">
                      Rows per page
                    </label>
                    <select
                      id="sc-size"
                      value={limit}
                      onChange={(e) => {
                        setLimit(parseInt(e.target.value, 10));
                        setOffset(0);
                      }}
                      className={selectField}
                    >
                      {PAGE_SIZES.map((n) => (
                        <option key={n} value={n}>
                          {n}
                        </option>
                      ))}
                    </select>
                    <button type="button" className={button} disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - limit))}>
                      ← Prev
                    </button>
                    <span className="whitespace-nowrap font-mono text-xs text-muted">
                      page {page} of {pages}
                    </span>
                    <button
                      type="button"
                      className={button}
                      disabled={offset + limit >= matched}
                      onClick={() => setOffset(offset + limit)}
                    >
                      Next →
                    </button>
                  </div>
                </div>

                <div className="flex flex-col gap-1 text-xs leading-relaxed text-muted">
                  <p>
                    Rows open the company in the terminal. Every number comes from the cached snapshot: Pay Efficiency and the Company
                    Grade are the same figures as the terminal&apos;s tabs, and the Company Grade is the overall grade (governance, red
                    flags, insiders and value vs peers), not a governance-only score. Upside compares the cached price to the
                    peer-valuation estimate. No live SEC, price or AI calls are made while screening.
                  </p>
                  <p>
                    N/A means the snapshot has no value for that field — hover a cell for the reason. Pay Efficiency stays signed: a
                    negative value can reflect negative compensation actually paid; it does not mean better efficiency.
                    {lowCount > 0 && ` ${lowCount} row${lowCount > 1 ? "s" : ""} on this page carry a low-confidence valuation tag, which is not a reliable investment signal.`}
                  </p>
                </div>
              </div>
            )}
          </>
        )}
      </section>

      <footer className="gutter mx-auto flex min-w-0 w-full max-w-6xl flex-wrap justify-between gap-4 border-t border-line py-8 text-sm text-muted [overflow-wrap:anywhere]">
        <span>
          <a href="/" className="hover:text-paper">
            ← Back to the terminal
          </a>{" "}
          · Data from SEC EDGAR
        </span>
        <span className="font-mono text-xs">Screener: cached snapshot · no live calls</span>
      </footer>
    </main>
  );
}

function SortTh({
  label,
  k,
  sort,
  order,
  onSort,
  align = "text-left",
}: {
  label: string;
  k: ScreenerUrlState["sort"];
  sort: ScreenerUrlState["sort"];
  order: "asc" | "desc";
  onSort: (k: ScreenerUrlState["sort"]) => void;
  align?: string;
}) {
  const active = sort === k;
  return (
    <th
      scope="col"
      aria-sort={active ? (order === "asc" ? "ascending" : "descending") : "none"}
      className={`px-3 py-2.5 font-medium ${align}`}
    >
      <button type="button" onClick={() => onSort(k)} className={`inline-flex min-h-11 items-center gap-1 rounded focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brass hover:text-paper ${active ? "text-paper" : ""}`}>
        {label}
        <span aria-hidden className="text-[10px]">
          {active ? (order === "asc" ? "▲" : "▼") : "↕"}
        </span>
      </button>
    </th>
  );
}
