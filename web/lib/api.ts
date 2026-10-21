import type { Governance, PayEfficiency, Report, RiskSummary, Trends, Valuation } from "./types";
import { SAMPLE_CAT } from "./sample";

// Set on Vercel to the Render address of the Python API. Empty means sample mode.
export const API_URL = (process.env.NEXT_PUBLIC_API_URL || "").replace(/\/$/, "");

// fetch() throws a bare "Failed to fetch" when the API can't be reached or the server died mid-request
// (a crash or restart sends no CORS headers, so the browser hides the real status). A quick /health check
// tells "the server is down or starting" apart from "it's up, so this one request failed".
async function callApi(path: string, init?: RequestInit) {
  try {
    // Longer than the API's own 90-second SEC time limit, so its clearer error arrives first
    return await fetch(`${API_URL}${path}`, { ...init, signal: AbortSignal.timeout(150_000) });
  } catch (e) {
    if ((e as Error).name === "TimeoutError")
      throw new Error("The data server didn't answer within 2.5 minutes. Try again; finished SEC lookups are kept, so a retry is usually faster.");
    const up = await fetch(`${API_URL}/health`, { signal: AbortSignal.timeout(8_000) }).then((r) => r.ok).catch(() => false);
    throw new Error(
      up
        ? "The data server dropped this request partway through, most likely because it restarted while reading the filing. It's back up now, so try again."
        : "The data server isn't answering right now. It's either restarting or waking up, which takes about a minute, so try again shortly."
    );
  }
}

// The API answers errors with {"detail": "..."}. Anything else (an HTML page from Render's proxy, say) means the
// server itself was restarting or overloaded, not that the company's data is missing.
async function errorText(res: Response, what: string) {
  const detail = (await res.json().catch(() => null))?.detail;
  if (typeof detail === "string") return detail;
  if ([502, 503, 504].includes(res.status))
    return `The data server is restarting or busy (HTTP ${res.status}), so ${what} didn't load. This isn't about the company; try again in a minute.`;
  return `${what[0].toUpperCase()}${what.slice(1)} failed (HTTP ${res.status}).`;
}

export async function fetchReport(ticker: string): Promise<Report> {
  if (!API_URL) {
    if (ticker === "CAT") return SAMPLE_CAT;
    throw new Error(`Live lookups start once the API is online. For now the preview has Caterpillar (CAT) only.`);
  }
  const res = await callApi(`/api/company/${encodeURIComponent(ticker)}`);
  if (!res.ok) throw new Error(await errorText(res, "the 10-K"));
  return { ...(await res.json()), governance: null, payEfficiency: null };
}

export async function fetchGovernance(ticker: string): Promise<Governance> {
  const res = await callApi(`/api/governance/${encodeURIComponent(ticker)}`);
  if (!res.ok) throw new Error(await errorText(res, "the proxy statement"));
  return res.json();
}

export async function fetchPayEfficiency(ticker: string): Promise<PayEfficiency> {
  const res = await callApi(`/api/pay-efficiency/${encodeURIComponent(ticker)}`);
  if (!res.ok) throw new Error(await errorText(res, "Pay Efficiency"));
  return res.json();
}

export async function fetchTrends(ticker: string): Promise<Trends> {
  if (!API_URL) throw new Error("Five-year trends load from the 10-Ks once the API is online.");
  const res = await callApi(`/api/trends/${encodeURIComponent(ticker)}`);
  if (!res.ok) throw new Error(await errorText(res, "the trends"));
  return res.json();
}

export async function fetchRisks(ticker: string): Promise<RiskSummary> {
  if (!API_URL) throw new Error("The 10-K summary reads each year's risk factors from SEC once the API is online.");
  const res = await callApi(`/api/risks/${encodeURIComponent(ticker)}`);
  if (!res.ok) throw new Error(await errorText(res, "the 10-K summary"));
  return res.json();
}

export async function fetchValuation(ticker: string): Promise<Valuation> {
  if (!API_URL) throw new Error("The fair value estimate compares live prices across the Russell 1000, so it turns on once the API is online.");
  const res = await callApi(`/api/valuation/${encodeURIComponent(ticker)}`);
  if (!res.ok) throw new Error(await errorText(res, "the fair value estimate"));
  return res.json();
}

// Excel or PDF of the ratios, Pay Efficiency, peer ranking and trends, built by the API from the same data as the page
export async function downloadExport(ticker: string, kind: "xlsx" | "pdf") {
  const res = await callApi(`/api/export/${encodeURIComponent(ticker)}.${kind}`);
  if (!res.ok) throw new Error((await res.json().catch(() => null))?.detail || `Couldn't build the file (${res.status})`);
  saveBlob(await res.blob(), `${ticker}_SEC_Terminal.${kind}`);
}

export async function fetchMemo(ticker: string): Promise<{ text: string; usage: { input: number; output: number } | null }> {
  if (!API_URL) throw new Error("The memo uses Gemini through the API, so it turns on once the API is online.");
  const res = await callApi(`/api/memo`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ticker }),
  });
  if (!res.ok) throw new Error((await res.json().catch(() => null))?.detail || `Request failed (${res.status})`);
  return res.json();
}

export async function downloadDocx(ticker: string, memo: string) {
  const res = await callApi(`/api/memo.docx`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ticker, memo }),
  });
  if (!res.ok) throw new Error(`Couldn't build the Word file (${res.status})`);
  saveBlob(await res.blob(), `${ticker}_Institutional_Research_Brief.docx`);
}

export function saveBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}
