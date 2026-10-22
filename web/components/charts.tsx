"use client";

import { useEffect, useId, useRef, useState } from "react";
import { motion } from "motion/react";

// Series colors for multi-line charts, from the site palette: filing blue, ledger green, ink. Checked for
// color-blind separation (they differ in lightness as well as hue) and contrast on the white sheet.
export const SERIES = { blue: "#1f47b8", green: "#2c7a4b", ink: "#1b2230" };

const PAD = { top: 16, right: 96, bottom: 28, left: 64 };

/** Width of the chart's box in CSS pixels, so the SVG draws 1:1 and its text stays the same size at any width. */
function useWidth(fallback = 640) {
  const ref = useRef<HTMLDivElement>(null);
  const [w, setW] = useState(fallback);
  useEffect(() => {
    if (!ref.current) return;
    const ro = new ResizeObserver(([e]) => e.contentRect.width > 0 && setW(Math.round(e.contentRect.width)));
    ro.observe(ref.current);
    return () => ro.disconnect();
  }, []);
  return [ref, w] as const;
}

/** Rounds the top of an axis up to 1, 2, 2.5 or 5 times a power of ten, so gridlines land on plain numbers. */
function niceMax(v: number) {
  if (v <= 0) return 1;
  const p = 10 ** Math.floor(Math.log10(v));
  return ([1, 2, 2.5, 5, 10].find((m) => m * p >= v) ?? 10) * p;
}

// "FY2021" -> "FY21" when the years would otherwise run into each other on a phone
const shortYear = (l: string, room: number) => (room < 56 ? l.replace(/^FY20(\d\d)$/, "FY$1") : l);

function niceMin(v: number) {
  return v >= 0 ? 0 : -niceMax(-v);
}

function Tooltip({ x, y, title, rows }: { x: number; y: number; title: string; rows: { color: string; name: string; value: string }[] }) {
  // Positioned in % of the chart box so it follows the responsive SVG
  const flip = x > 60;
  return (
    <div
      role="status"
      className="pointer-events-none absolute z-10 min-w-36 rounded-lg border border-rule bg-page/95 px-3 py-2 text-xs shadow-xl"
      style={{ left: `${x}%`, top: `${y}%`, transform: `translate(${flip ? "calc(-100% - 12px)" : "12px"}, -50%)` }}
    >
      <div className="mb-1 font-figures text-muted">{title}</div>
      {rows.map((r) => (
        <div key={r.name} className="flex items-center gap-2">
          <span className="h-0.5 w-3 rounded" style={{ background: r.color }} />
          <span className="tnum font-figures font-semibold text-ink">{r.value}</span>
          <span className="text-muted">{r.name}</span>
        </div>
      ))}
    </div>
  );
}

export type LineSeries = { name: string; color: string; values: (number | null)[] };

/** Lines on one shared axis, with a crosshair that reads every series at the hovered year. */
export function LineChart({
  labels,
  series,
  format,
  height = 260,
  ariaLabel,
}: {
  labels: string[];
  series: LineSeries[];
  format: (v: number) => string;
  height?: number;
  ariaLabel: string;
}) {
  const [hover, setHover] = useState<number | null>(null);
  const svgRef = useRef<SVGSVGElement>(null);
  const [box, W] = useWidth();
  const all = series.flatMap((s) => s.values.filter((v): v is number => v !== null));
  if (!all.length) return <div ref={box} className="text-sm text-muted">Not enough reported data to chart.</div>;
  const lo = niceMin(Math.min(...all));
  const hi = niceMax(Math.max(...all) * 1.1);
  const iw = W - PAD.left - PAD.right;
  const ih = height - PAD.top - PAD.bottom;
  const x = (i: number) => PAD.left + (labels.length === 1 ? iw / 2 : (i / (labels.length - 1)) * iw);
  const y = (v: number) => PAD.top + ih - ((v - lo) / (hi - lo)) * ih;
  const ticks = [0, 1, 2, 3, 4].map((k) => lo + ((hi - lo) * k) / 4);

  // Series name at the end of each line, nudged apart so close lines don't print on top of each other
  const ends = series
    .map((s) => {
      const last = s.values.map((v, i) => [v, i] as const).filter(([v]) => v !== null).pop();
      return last ? { s, i: last[1], y: y(last[0] as number) } : null;
    })
    .filter((e): e is NonNullable<typeof e> => e !== null)
    .sort((a, b) => a.y - b.y);
  for (let k = 1; k < ends.length; k++) ends[k].y = Math.max(ends[k].y, ends[k - 1].y + 13);

  function onMove(e: React.PointerEvent) {
    const box = svgRef.current?.getBoundingClientRect();
    if (!box) return;
    const px = ((e.clientX - box.left) / box.width) * W;
    let best = 0;
    labels.forEach((_, i) => Math.abs(x(i) - px) < Math.abs(x(best) - px) && (best = i));
    setHover(best);
  }

  return (
    <div ref={box} className="relative">
      <svg
        ref={svgRef}
        viewBox={`0 0 ${W} ${height}`}
        className="w-full touch-none select-none"
        role="img"
        aria-label={ariaLabel}
        onPointerMove={onMove}
        onPointerDown={onMove}
        onPointerLeave={() => setHover(null)}
      >
        {ticks.map((t) => (
          <g key={t}>
            <line x1={PAD.left} x2={W - PAD.right} y1={y(t)} y2={y(t)} stroke="var(--color-rule)" strokeDasharray={t === 0 ? undefined : "2 4"} />
            <text x={PAD.left - 8} y={y(t)} dy="0.32em" textAnchor="end" className="fill-muted font-figures text-[10px]">
              {format(t)}
            </text>
          </g>
        ))}
        {labels.map((l, i) => (
          <text key={l} x={x(i)} y={height - 8} textAnchor="middle" className="fill-muted font-figures text-[10px]">
            {shortYear(l, iw / labels.length)}
          </text>
        ))}
        {hover !== null && <line x1={x(hover)} x2={x(hover)} y1={PAD.top} y2={PAD.top + ih} stroke="var(--color-muted)" strokeWidth={1} />}
        {series.map((s) => {
          const pts = s.values.map((v, i) => (v === null ? null : ([x(i), y(v)] as const)));
          // A missing year breaks the line instead of drawing through it
          const d = pts.reduce((acc, p, i) => (p ? acc + `${i && pts[i - 1] ? "L" : "M"}${p[0]},${p[1]}` : acc), "");
          return (
            <g key={s.name}>
              <motion.path
                d={d}
                fill="none"
                stroke={s.color}
                strokeWidth={2}
                strokeLinejoin="round"
                strokeLinecap="round"
                initial={{ pathLength: 0 }}
                animate={{ pathLength: 1 }}
                transition={{ duration: 1.1, ease: [0.16, 1, 0.3, 1] }}
              />
              {pts.map((p, i) =>
                p ? <circle key={i} cx={p[0]} cy={p[1]} r={hover === i ? 5 : 4} fill={s.color} stroke="var(--color-sheet)" strokeWidth={2} /> : null
              )}
            </g>
          );
        })}
        {ends.map((e) => (
          <text key={e.s.name} x={x(e.i) + 10} y={e.y} dy="0.32em" className="fill-ink text-[11px]">
            {e.s.name}
          </text>
        ))}
      </svg>
      {hover !== null && (
        <Tooltip
          x={(x(hover) / W) * 100}
          y={50}
          title={labels[hover]}
          rows={series.map((s) => ({ color: s.color, name: s.name, value: s.values[hover] === null ? "Not reported" : format(s.values[hover]!) }))}
        />
      )}
    </div>
  );
}

/** Single-series bars from zero, value on hover and printed above each bar. */
export function BarChart({
  labels,
  values,
  format,
  color = "var(--color-blue)",
  height = 240,
  ariaLabel,
}: {
  labels: string[];
  values: (number | null)[];
  format: (v: number) => string;
  color?: string;
  height?: number;
  ariaLabel: string;
}) {
  const [hover, setHover] = useState<number | null>(null);
  const [box, W] = useWidth();
  const nums = values.filter((v): v is number => v !== null);
  if (!nums.length) return <div ref={box} className="text-sm text-muted">Not enough reported data to chart.</div>;
  const lo = niceMin(Math.min(...nums));
  const hi = niceMax(Math.max(...nums) * 1.12);
  const pad = { ...PAD, right: 16 };
  const iw = W - pad.left - pad.right;
  const ih = height - pad.top - pad.bottom;
  const slot = iw / labels.length;
  const bw = Math.min(72, slot * 0.6);
  const y = (v: number) => pad.top + ih - ((v - lo) / (hi - lo)) * ih;
  const ticks = [0, 1, 2, 3, 4].map((k) => lo + ((hi - lo) * k) / 4);

  return (
    <div ref={box} className="relative">
      <svg viewBox={`0 0 ${W} ${height}`} className="w-full select-none" role="img" aria-label={ariaLabel} onPointerLeave={() => setHover(null)}>
        {ticks.map((t) => (
          <g key={t}>
            <line x1={pad.left} x2={W - pad.right} y1={y(t)} y2={y(t)} stroke="var(--color-rule)" strokeDasharray={t === 0 ? undefined : "2 4"} />
            <text x={pad.left - 8} y={y(t)} dy="0.32em" textAnchor="end" className="fill-muted font-figures text-[10px]">
              {format(t)}
            </text>
          </g>
        ))}
        {labels.map((l, i) => {
          const v = values[i];
          const cx = pad.left + slot * i + slot / 2;
          const top = v === null ? y(0) : Math.min(y(v), y(0));
          const h = v === null ? 0 : Math.abs(y(v) - y(0));
          return (
            <g key={l} onPointerEnter={() => setHover(i)} onFocus={() => setHover(i)} tabIndex={0} className="outline-none">
              {/* hit area: the whole column, not just the painted bar */}
              <rect x={cx - slot / 2} y={pad.top} width={slot} height={ih} fill="transparent" />
              <motion.rect
                x={cx - bw / 2}
                width={bw}
                rx={4}
                fill={color}
                opacity={hover === null || hover === i ? 1 : 0.55}
                initial={{ y: y(0), height: 0 }}
                animate={{ y: top, height: h }}
                transition={{ duration: 0.9, delay: 0.08 * i, ease: [0.16, 1, 0.3, 1] }}
              />
              {v !== null && (
                <text x={cx} y={top - 6} textAnchor="middle" className="tnum fill-ink font-figures text-[10px]">
                  {format(v)}
                </text>
              )}
              <text x={cx} y={height - 8} textAnchor="middle" className="fill-muted font-figures text-[10px]">
                {shortYear(l, slot)}
              </text>
            </g>
          );
        })}
      </svg>
      {hover !== null && (
        <Tooltip
          x={((pad.left + slot * hover + slot / 2) / W) * 100}
          y={40}
          title={labels[hover]}
          rows={[{ color, name: ariaLabel, value: values[hover] === null ? "Not reported" : format(values[hover]!) }]}
        />
      )}
    </div>
  );
}

/** Every peer as a dot on one line, the company as a larger marker. Values past the edges are pinned to the edge. */
export function DotStrip({ values, mark, markLabel, median }: { values: number[]; mark: number; markLabel: string; median: number }) {
  const id = useId();
  const [hover, setHover] = useState<number | null>(null);
  const [box, width] = useWidth();
  const height = 92;
  const left = 16;
  const right = 16;
  // Most companies sit between 0% and a few percent; a handful run far higher, so the axis stops at 5% (or the company's
  // value, up to 25%). A company past that is pinned to the edge with its value written next to it.
  const CAP = 25;
  const lo = Math.min(0, Math.max(-CAP, mark));
  const hi = Math.max(5, Math.ceil(Math.min(CAP, mark)));
  const pinned = mark > hi ? "right" : mark < lo ? "left" : null;
  const x = (v: number) => left + ((Math.min(hi, Math.max(lo, v)) - lo) / (hi - lo)) * (width - left - right);
  // About 6 labels whatever the range, so they never run into each other
  const step = [1, 2, 5, 10].find((s) => (hi - lo) / s <= 6) ?? 10;
  const ticks = Array.from({ length: Math.floor((hi - lo) / step) + 1 }, (_, k) => Math.ceil(lo / step) * step + k * step).filter((t) => t <= hi);
  const beyond = values.filter((v) => v > hi).length;
  const below = values.filter((v) => v < lo).length;
  // Stack dots that land on the same pixel column so the crowd near zero stays readable
  const used = new Map<number, number>();
  const dots = values.map((v) => {
    const col = Math.round(x(v) / 7);
    const n = used.get(col) ?? 0;
    used.set(col, n + 1);
    return { v, cx: x(v), cy: 52 - (n % 5) * 7 };
  });

  return (
    <div ref={box} className="relative">
      <svg viewBox={`0 0 ${width} ${height}`} className="w-full select-none" role="img" aria-labelledby={id} onPointerLeave={() => setHover(null)}>
        <title id={id}>{`${markLabel} compared with ${values.length} peer companies`}</title>
        <line x1={left} x2={width - right} y1={60} y2={60} stroke="var(--color-rule)" />
        <line x1={x(median)} x2={x(median)} y1={20} y2={64} stroke="var(--color-muted)" strokeDasharray="2 3" />
        <text x={x(median)} y={14} textAnchor="middle" className="fill-muted font-figures text-[10px]">
          median
        </text>
        {dots.map((d, i) => (
          <circle
            key={i}
            cx={d.cx}
            cy={d.cy}
            r={hover === i ? 4.5 : 3}
            fill="var(--color-muted)"
            opacity={0.6}
            onPointerEnter={() => setHover(i)}
          />
        ))}
        <motion.g initial={{ scale: 0 }} animate={{ scale: 1 }} transition={{ type: "spring", stiffness: 300, damping: 15, delay: 0.4 }} style={{ originX: `${x(mark)}px`, originY: "52px" }}>
          <circle cx={x(mark)} cy={52} r={7} fill="var(--color-ink)" stroke="var(--color-sheet)" strokeWidth={2} />
        </motion.g>
        {pinned && (
          <text x={x(mark) + (pinned === "right" ? -12 : 12)} y={40} textAnchor={pinned === "right" ? "end" : "start"} className="fill-ink font-figures text-[11px] font-bold">
            {pinned === "right" ? `${mark.toFixed(1)}% (off the scale) →` : `← ${mark.toFixed(1)}% (off the scale)`}
          </text>
        )}
        {ticks.map((t) => (
          <text key={t} x={x(t)} y={78} textAnchor="middle" className="fill-muted font-figures text-[10px]">
            {t}%
          </text>
        ))}
        {beyond > 0 && (
          <text x={width - right} y={90} textAnchor="end" className="fill-muted font-figures text-[10px]">
            {beyond} above {hi}% shown at the edge
          </text>
        )}
        {below > 0 && (
          <text x={left} y={90} className="fill-muted font-figures text-[10px]">
            {below} below {lo}% shown at the edge
          </text>
        )}
      </svg>
      {hover !== null && (
        <Tooltip
          x={(dots[hover].cx / width) * 100}
          y={40}
          title="Peer company"
          rows={[{ color: "var(--color-muted)", name: "Pay Efficiency", value: `${dots[hover].v.toFixed(2)}%` }]}
        />
      )}
    </div>
  );
}

/** Two lines with their own axes (left and right) over the same years, e.g. Pay Efficiency against the share price. */
export function DualAxisChart({
  labels,
  left,
  right,
  height = 260,
  ariaLabel,
}: {
  labels: string[];
  left: LineSeries & { format: (v: number) => string };
  right: LineSeries & { format: (v: number) => string };
  height?: number;
  ariaLabel: string;
}) {
  const [hover, setHover] = useState<number | null>(null);
  const svgRef = useRef<SVGSVGElement>(null);
  const [box, W] = useWidth();
  const pad = { top: 16, right: 64, bottom: 28, left: 64 };
  const nums = (s: LineSeries) => s.values.filter((v): v is number => v !== null);
  if (!nums(left).length || !nums(right).length) return <div ref={box} className="text-sm text-muted">Not enough reported data to chart.</div>;
  const iw = W - pad.left - pad.right;
  const ih = height - pad.top - pad.bottom;
  const x = (i: number) => pad.left + (labels.length === 1 ? iw / 2 : (i / (labels.length - 1)) * iw);
  const scale = (s: LineSeries) => {
    const lo = niceMin(Math.min(...nums(s)));
    const hi = niceMax(Math.max(...nums(s)) * 1.1);
    return { lo, hi, y: (v: number) => pad.top + ih - ((v - lo) / (hi - lo)) * ih };
  };
  const L = scale(left);
  const R = scale(right);
  const ticks = [0, 1, 2, 3, 4];

  function onMove(e: React.PointerEvent) {
    const b = svgRef.current?.getBoundingClientRect();
    if (!b) return;
    const px = ((e.clientX - b.left) / b.width) * W;
    let best = 0;
    labels.forEach((_, i) => Math.abs(x(i) - px) < Math.abs(x(best) - px) && (best = i));
    setHover(best);
  }

  const line = (s: LineSeries, y: (v: number) => number, dashed: boolean) => {
    const pts = s.values.map((v, i) => (v === null ? null : ([x(i), y(v)] as const)));
    const d = pts.reduce((acc, p, i) => (p ? acc + `${i && pts[i - 1] ? "L" : "M"}${p[0]},${p[1]}` : acc), "");
    return (
      <g key={s.name}>
        <motion.path
          d={d}
          fill="none"
          stroke={s.color}
          strokeWidth={2}
          strokeDasharray={dashed ? "6 4" : undefined}
          strokeLinejoin="round"
          initial={{ pathLength: 0 }}
          animate={{ pathLength: 1 }}
          transition={{ duration: 1.1, ease: [0.16, 1, 0.3, 1] }}
        />
        {pts.map((p, i) => (p ? <circle key={i} cx={p[0]} cy={p[1]} r={hover === i ? 5 : 4} fill={s.color} stroke="var(--color-sheet)" strokeWidth={2} /> : null))}
      </g>
    );
  };

  return (
    <div ref={box} className="relative">
      <svg
        ref={svgRef}
        viewBox={`0 0 ${W} ${height}`}
        className="w-full touch-none select-none"
        role="img"
        aria-label={ariaLabel}
        onPointerMove={onMove}
        onPointerDown={onMove}
        onPointerLeave={() => setHover(null)}
      >
        {ticks.map((k) => {
          const yy = pad.top + ih - (ih * k) / 4;
          return (
            <g key={k}>
              <line x1={pad.left} x2={W - pad.right} y1={yy} y2={yy} stroke="var(--color-rule)" strokeDasharray={k === 0 ? undefined : "2 4"} />
              <text x={pad.left - 8} y={yy} dy="0.32em" textAnchor="end" className="font-figures text-[10px]" fill={left.color}>
                {left.format(L.lo + ((L.hi - L.lo) * k) / 4)}
              </text>
              <text x={W - pad.right + 8} y={yy} dy="0.32em" className="font-figures text-[10px]" fill={right.color}>
                {right.format(R.lo + ((R.hi - R.lo) * k) / 4)}
              </text>
            </g>
          );
        })}
        {labels.map((l, i) => (
          <text key={l} x={x(i)} y={height - 8} textAnchor="middle" className="fill-muted font-figures text-[10px]">
            {shortYear(l, iw / labels.length)}
          </text>
        ))}
        {hover !== null && <line x1={x(hover)} x2={x(hover)} y1={pad.top} y2={pad.top + ih} stroke="var(--color-muted)" strokeWidth={1} />}
        {line(left, L.y, false)}
        {line(right, R.y, true)}
      </svg>
      {hover !== null && (
        <Tooltip
          x={(x(hover) / W) * 100}
          y={50}
          title={labels[hover]}
          rows={[left, right].map((s) => ({ color: s.color, name: s.name, value: s.values[hover] === null ? "Not reported" : s.format(s.values[hover]!) }))}
        />
      )}
    </div>
  );
}
