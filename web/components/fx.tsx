"use client";

/** A figure such as "33.8%" or "$67,589", set in tabular numerals. (It used to count up from zero; figures now just sit still.) */
export function CountUp({ value, className }: { value: string; className?: string }) {
  return <span className={`tnum ${className || ""}`}>{value}</span>;
}

/**
 * Auditor's tick mark: a hand-drawn check, optionally with a letter keyed to a legend
 * ("a" agreed to the 10-K, "b" recalculated). `delay` staggers the one-time draw-in.
 */
export function Tick({ letter, delay = 0, className = "text-input" }: { letter?: string; delay?: number; className?: string }) {
  return (
    <span className={`inline-flex items-start ${className}`} aria-hidden>
      <svg viewBox="0 0 16 14" className="tick h-[0.85em] w-[0.95em]" fill="none">
        <path
          d="M1.5 7.5 C3 8.6 4.4 10.3 5.6 12.4 C7.6 7.6 10.6 3.6 14.6 1.2"
          stroke="currentColor"
          strokeWidth="1.8"
          strokeLinecap="round"
          strokeLinejoin="round"
          style={{ animationDelay: `${delay}s` }}
        />
      </svg>
      {letter && <span className="-ml-0.5 text-[0.62em] leading-none font-semibold italic">{letter}</span>}
    </span>
  );
}
