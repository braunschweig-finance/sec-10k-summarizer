"use client";

import { useEffect, useRef, useState } from "react";
import { animate, motion, useInView, useReducedMotion } from "motion/react";

/** Slow drifting glow behind the hero. Pure decoration. */
export function Aurora() {
  const reduce = useReducedMotion();
  const blobs = [
    { c: "var(--color-violet)", size: 520, x: [-80, 60, -80], y: [-40, 30, -40], left: "8%", top: "-10%", o: 0.32 },
    { c: "var(--color-brass)", size: 440, x: [40, -50, 40], y: [20, -30, 20], left: "55%", top: "-5%", o: 0.22 },
    { c: "var(--color-teal)", size: 380, x: [0, 70, 0], y: [30, -10, 30], left: "30%", top: "25%", o: 0.18 },
  ];
  return (
    <div aria-hidden className="pointer-events-none absolute inset-0 overflow-hidden">
      {blobs.map((b, i) => (
        <motion.div
          key={i}
          className="absolute rounded-full"
          style={{ width: b.size, height: b.size, left: b.left, top: b.top, background: b.c, opacity: b.o, filter: "blur(110px)" }}
          animate={reduce ? undefined : { x: b.x, y: b.y }}
          transition={{ duration: 18 + i * 4, repeat: Infinity, ease: "easeInOut" }}
        />
      ))}
      {/* faint ledger grid */}
      <div
        className="absolute inset-0 opacity-[0.07]"
        style={{
          backgroundImage:
            "linear-gradient(var(--color-paper) 1px, transparent 1px), linear-gradient(90deg, var(--color-paper) 1px, transparent 1px)",
          backgroundSize: "56px 56px",
          maskImage: "radial-gradient(ellipse at 50% 20%, black 20%, transparent 70%)",
          WebkitMaskImage: "radial-gradient(ellipse at 50% 20%, black 20%, transparent 70%)",
        }}
      />
    </div>
  );
}

/** Headline that rises in word by word on load. */
export function WordReveal({ text, accent }: { text: string; accent?: string }) {
  const words = text.split(" ");
  return (
    <>
      {words.map((w, i) => (
        <motion.span
          key={i}
          className={`inline-block ${w === accent ? "sheen" : ""}`}
          initial={{ y: "0.6em", opacity: 0, filter: "blur(8px)" }}
          animate={{ y: 0, opacity: 1, filter: "blur(0px)" }}
          transition={{ delay: 0.08 * i, duration: 0.6, ease: [0.2, 0.7, 0.2, 1] }}
        >
          {w}
          {i < words.length - 1 ? " " : ""}
        </motion.span>
      ))}
    </>
  );
}

/** Counts a figure like "33.8%", "1.44x" or "$67,589" up from zero. Non-numeric values ("N/A") show as-is. */
export function CountUp({ value, className }: { value: string; className?: string }) {
  const m = value.match(/^([^0-9-]*)(-?[\d,]*\.?\d+)(.*)$/);
  const ref = useRef<HTMLSpanElement>(null);
  const inView = useInView(ref, { once: true });
  const reduce = useReducedMotion();
  const [shown, setShown] = useState(value);

  useEffect(() => {
    if (!m || !inView || reduce) {
      setShown(value);
      return;
    }
    const [, pre, num, post] = m;
    const target = parseFloat(num.replace(/,/g, ""));
    const decimals = (num.split(".")[1] || "").length;
    const fmt = (n: number) =>
      pre + n.toLocaleString("en-US", { minimumFractionDigits: decimals, maximumFractionDigits: decimals }) + post;
    const controls = animate(0, target, { duration: 1.4, ease: [0.16, 1, 0.3, 1], onUpdate: (n) => setShown(fmt(n)) });
    return () => controls.stop();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value, inView, reduce]);

  return (
    <span ref={ref} className={`tnum ${className || ""}`}>
      {shown}
    </span>
  );
}

/** Tracks the cursor so .spotlight cards glow where the mouse is. */
export function onSpotlightMove(e: React.MouseEvent<HTMLElement>) {
  const r = e.currentTarget.getBoundingClientRect();
  e.currentTarget.style.setProperty("--mx", `${e.clientX - r.left}px`);
  e.currentTarget.style.setProperty("--my", `${e.clientY - r.top}px`);
}

/** Scrolling strip of the XBRL tags the app reads, like a market ticker. */
export function TickerTape() {
  const tags = [
    "us-gaap:Revenues",
    "us-gaap:CostOfGoodsAndServicesSold",
    "us-gaap:GrossProfit",
    "us-gaap:OperatingIncomeLoss",
    "us-gaap:AssetsCurrent",
    "us-gaap:LiabilitiesCurrent",
    "us-gaap:Liabilities",
    "us-gaap:StockholdersEquity",
    "DEF 14A · Lead Independent Director",
    "DEF 14A · Clawback Policy",
    "DEF 14A · Anti-Hedging",
    "DEF 14A · Say-on-Pay",
    "ecd:PeoActuallyPaidCompAmt",
  ];
  const row = [...tags, ...tags];
  return (
    <div aria-hidden className="relative overflow-hidden border-y border-line bg-panel/60 py-2.5">
      <div className="tape flex w-max gap-10 whitespace-nowrap font-mono text-xs text-muted">
        {row.map((t, i) => (
          <span key={i} className="flex items-center gap-2">
            <span className="h-1.5 w-1.5 rounded-full bg-brass/70" />
            {t}
          </span>
        ))}
      </div>
      <div className="pointer-events-none absolute inset-y-0 left-0 w-16 bg-gradient-to-r from-ink to-transparent" />
      <div className="pointer-events-none absolute inset-y-0 right-0 w-16 bg-gradient-to-l from-ink to-transparent" />
    </div>
  );
}
