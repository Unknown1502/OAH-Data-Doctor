import { useId } from "react";
import { exact, unit as unitText } from "../lib/format";
import type { Severity } from "../lib/types";

export interface SeriesPoint {
  label: string; // year or date, as published
  value: number;
  worst: Severity | null;
}

const W = 760;
const H = 280;
const L = 78;
const R = 20;
const T = 34;
const B = 40;

const tickLabel = (v: number) => (Math.abs(v) >= 1e6 ? `${v / 1e6}M` : Math.abs(v) >= 1e4 ? `${v / 1e3}k` : exact(Number(v.toPrecision(3))));

/**
 * One published statistic over time, values plotted exactly as published. A logarithmic axis is used when the values
 * span more than two orders of magnitude (it is labelled); points with error or critical findings are drawn as red
 * diamonds, warnings as yellow circles. The shaded band is the physically possible range for the measure, when known.
 */
export default function SeriesChart({ points, unit, band, title, bandNote = null }: {
  points: SeriesPoint[];
  unit: string | null;
  band: { min?: number; max?: number } | null;
  title: string;
  bandNote?: string | null;
}) {
  const id = useId();
  const vals = points.map((p) => p.value);
  const positive = vals.every((v) => v > 0);
  const log = positive && Math.max(...vals) / Math.min(...vals) > 100;
  let lo: number;
  let hi: number;
  let step = 1;
  if (log) {
    lo = Math.floor(Math.log10(Math.min(...vals)));
    hi = Math.ceil(Math.log10(Math.max(...vals)));
    if (hi === lo) hi += 1;
  } else {
    // Round tick steps (1, 2 or 5 x 10^k) and room above the highest point for its label.
    const mn = Math.min(0, ...vals);
    const mx = Math.max(...vals);
    const raw = (mx - mn || Math.abs(mx) || 1) / 4;
    const e = 10 ** Math.floor(Math.log10(raw));
    step = (raw / e <= 1 ? 1 : raw / e <= 2 ? 2 : raw / e <= 5 ? 5 : 10) * e;
    lo = mn < 0 ? Math.floor(mn / step) * step : 0;
    hi = Math.ceil((mx + step * 0.35) / step) * step;
  }
  const y = (v: number) => {
    const t = log ? (Math.log10(Math.max(v, 10 ** lo)) - lo) / (hi - lo) : (v - lo) / (hi - lo);
    return T + (1 - t) * (H - T - B);
  };
  const x = (i: number) => (points.length === 1 ? (L + W - R) / 2 : L + (i * (W - L - R)) / (points.length - 1));
  const ticks = log
    ? Array.from({ length: hi - lo + 1 }, (_, i) => 10 ** (lo + i))
    : Array.from({ length: Math.round((hi - lo) / step) + 1 }, (_, i) => Number((lo + i * step).toPrecision(12)));

  // The band, clipped to the plotted range (a band above or below the data is not drawn).
  const clip = (v: number) => Math.min(H - B, Math.max(T, y(v)));
  const bandTop = band?.max !== undefined ? clip(band.max) : T;
  const bandBottom = band?.min !== undefined ? (log && band.min <= 0 ? H - B : clip(band.min)) : H - B;
  const showBand = band && bandBottom - bandTop > 1;
  const allOutside = !!band && points.every((p) => (band.max !== undefined && p.value > band.max) || (band.min !== undefined && p.value < band.min));

  const u = unitText(unit);
  const bad = points.filter((p) => p.worst === "CRITICAL" || p.worst === "ERROR");
  const desc = `${log ? "Logarithmic" : "Linear"} scale. ${points.map((p) => `${p.label}: ${exact(p.value)} ${u}${p.worst ? ` (${p.worst.toLowerCase()} finding)` : ""}`).join("; ")}.${
    band ? ` Shaded: physically possible range${band.max !== undefined ? ` up to ${exact(band.max)} ${u}` : ""}.` : ""
  }${bad.length ? ` ${bad.length} of ${points.length} points have error or critical findings.` : ""}`;

  return (
    <figure className="m-0">
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-labelledby={`${id}-t ${id}-d`} className="h-auto w-full">
        <title id={`${id}-t`}>{title}</title>
        <desc id={`${id}-d`}>{desc}</desc>
        {showBand && <rect x={L} y={bandTop} width={W - L - R} height={bandBottom - bandTop} fill="var(--band)" />}
        {showBand && (
          <text x={W - R - 4} y={bandBottom - 6} textAnchor="end" fontSize={12} fill="var(--algae)">
            physically possible
          </text>
        )}
        {ticks.map((t) => (
          <g key={t}>
            <line x1={L} x2={W - R} y1={y(t)} y2={y(t)} stroke="var(--line)" />
            <text x={L - 8} y={y(t) + 4} textAnchor="end" fontSize={12} fill="var(--ink-3)" className="readout">
              {tickLabel(t)}
            </text>
          </g>
        ))}
        <text x={14} y={T - 14} fontSize={12} fill="var(--ink-3)">
          {u}
          {log ? " (log scale: each line is ten times the one below)" : ""}
        </text>
        <polyline points={points.map((p, i) => `${x(i)},${y(p.value)}`).join(" ")} fill="none" stroke="var(--ink-3)" strokeWidth={1.5} />
        {points.map((p, i) => {
          const cx = x(i);
          const cy = y(p.value);
          const red = p.worst === "CRITICAL" || p.worst === "ERROR";
          return (
            <g key={`${p.label}-${i}`}>
              {red ? (
                <rect x={cx - 6.5} y={cy - 6.5} width={13} height={13} transform={`rotate(45 ${cx} ${cy})`} fill="var(--cinnabar)" />
              ) : (
                <circle cx={cx} cy={cy} r={6} fill={p.worst === "WARNING" ? "var(--sulfur)" : "var(--panel)"} stroke={p.worst === "WARNING" ? "var(--sulfur)" : "var(--ink)"} strokeWidth={2.2} />
              )}
              {points.length <= 12 && (
                <text x={cx} y={cy - 12} textAnchor="middle" fontSize={12} fill={red ? "var(--cinnabar)" : "var(--ink)"} fontWeight={red ? 700 : 500}
                  className="readout" stroke="var(--panel)" strokeWidth={4} paintOrder="stroke">
                  {exact(p.value)}
                </text>
              )}
              <text x={cx} y={H - B + 20} textAnchor="middle" fontSize={12} fill="var(--ink-2)" className="readout">
                {p.label}
              </text>
            </g>
          );
        })}
      </svg>
      {bandNote && (
        <figcaption className="mt-2 text-sm text-ink-2">
          {bandNote}
          {band && !showBand && (allOutside ? " Every plotted value lies far outside that range, so at this scale it is too thin to draw." : " At this scale that range is too thin to draw.")}
        </figcaption>
      )}
    </figure>
  );
}
