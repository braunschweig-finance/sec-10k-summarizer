import type { Report } from "./types";
import { SAMPLE_CAT } from "./sample";

// Set on Vercel to the Render address of the Python API. Empty means sample mode.
export const API_URL = (process.env.NEXT_PUBLIC_API_URL || "").replace(/\/$/, "");

export async function fetchReport(ticker: string): Promise<Report> {
  if (!API_URL) {
    if (ticker === "CAT") return SAMPLE_CAT;
    throw new Error(`Live lookups start once the API is online. For now the preview has Caterpillar (CAT) only.`);
  }
  const res = await fetch(`${API_URL}/api/company/${encodeURIComponent(ticker)}`);
  if (!res.ok) throw new Error((await res.json().catch(() => null))?.detail || `Request failed (${res.status})`);
  return res.json();
}

export async function fetchMemo(ticker: string): Promise<{ text: string; usage: { input: number; output: number } | null }> {
  if (!API_URL) throw new Error("The memo uses Gemini through the API, so it turns on once the API is online.");
  const res = await fetch(`${API_URL}/api/memo`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ticker }),
  });
  if (!res.ok) throw new Error((await res.json().catch(() => null))?.detail || `Request failed (${res.status})`);
  return res.json();
}

export async function downloadDocx(ticker: string, memo: string) {
  const res = await fetch(`${API_URL}/api/memo.docx`, {
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
