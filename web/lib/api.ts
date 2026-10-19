import type { Governance, PayEfficiency, Report, Trends } from "./types";
import { SAMPLE_CAT } from "./sample";

// Set on Vercel to the Render address of the Python API. Empty means sample mode.
export const API_URL = (process.env.NEXT_PUBLIC_API_URL || "").replace(/\/$/, "");

// fetch() throws a bare "Failed to fetch" when the API can't be reached (asleep, crashed, or blocking the site)
async function callApi(path: string, init?: RequestInit) {
  try {
    // Longer than the API's own 90-second SEC time limit, so its clearer error arrives first
    return await fetch(`${API_URL}${path}`, { ...init, signal: AbortSignal.timeout(150_000) });
  } catch {
    throw new Error(
      "Couldn't reach the data server. On the free plan it sleeps when nobody uses it and takes about a minute to wake up, so try again in a minute."
    );
  }
}

export async function fetchReport(ticker: string): Promise<Report> {
  if (!API_URL) {
    if (ticker === "CAT") return SAMPLE_CAT;
    throw new Error(`Live lookups start once the API is online. For now the preview has Caterpillar (CAT) only.`);
  }
  const res = await callApi(`/api/company/${encodeURIComponent(ticker)}`);
  if (!res.ok) throw new Error((await res.json().catch(() => null))?.detail || `Request failed (${res.status})`);
  return { ...(await res.json()), governance: null, payEfficiency: null };
}

export async function fetchGovernance(ticker: string): Promise<Governance> {
  const res = await callApi(`/api/governance/${encodeURIComponent(ticker)}`);
  if (!res.ok) throw new Error((await res.json().catch(() => null))?.detail || `Request failed (${res.status})`);
  return res.json();
}

export async function fetchPayEfficiency(ticker: string): Promise<PayEfficiency> {
  const res = await callApi(`/api/pay-efficiency/${encodeURIComponent(ticker)}`);
  if (!res.ok) throw new Error((await res.json().catch(() => null))?.detail || `Request failed (${res.status})`);
  return res.json();
}

export async function fetchTrends(ticker: string): Promise<Trends> {
  if (!API_URL) throw new Error("Five-year trends load from the 10-Ks once the API is online.");
  const res = await callApi(`/api/trends/${encodeURIComponent(ticker)}`);
  if (!res.ok) throw new Error((await res.json().catch(() => null))?.detail || `Request failed (${res.status})`);
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
