"use client";

import { useEffect, useRef, useState } from "react";
import { animate, useInView, useReducedMotion } from "motion/react";

/** Counts a figure like "33.8%", "1.44x" or "$67,589" up from zero. Non-numeric values ("N/A") show as-is. */
export function CountUp({ value, className, duration = 0.9 }: { value: string; className?: string; duration?: number }) {
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
    const controls = animate(0, target, { duration, ease: [0.16, 1, 0.3, 1], onUpdate: (n) => setShown(fmt(n)) });
    return () => controls.stop();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value, inView, reduce]);

  return (
    <span ref={ref} className={`tnum ${className || ""}`}>
      {shown}
    </span>
  );
}
