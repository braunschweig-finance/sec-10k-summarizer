import type { Metadata } from "next";
import Screener from "@/components/Screener";

export const metadata: Metadata = {
  title: "Screener · SEC Financial & Corporate Governance Terminal",
  description:
    "Screen the cached research universe by sector, Company Grade, Pay Efficiency and peer-valuation upside. Cached snapshot only — no live SEC, price or AI calls.",
};

export default function ScreenerPage() {
  return <Screener />;
}
