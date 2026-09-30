import { useId } from "react";
import { num, unit as unitText } from "../lib/format";

export interface RulerValue {
  label: string;
  value: number;
}

interface Props {
  values: RulerValue[];
  unit: string | null;
  band?: { min?: number; max?: number; label: string } | null;
  outliers?: string[];
  caption?: string;
  animate?: boolean;
}

const W = 760;
const H = 190;
const PAD_X = 34;
const AXIS_Y = 118;

const decadeLabel = (k: number) => {
  const v = 10 ** k;
  if (k >= 6) return `${v / 1e6}M`;
  if (k >= 3) return `${v / 1e3}k`;
  return v >= 1 ? String(v) : String(Number(v.toPrecision(1)));
};

/**
 * Plots each published statistic of one record on a log10 axis. Values that belong to the same data should
 * sit together; a statistic decades away is the visual signature of a scale inconsistency. The shaded band is
 * the physically possible range for the measure (from the knowledge layer), when one is known.
 */
export default function MagnitudeRuler({ values, unit, band, outliers = [], caption, animate = true }: Props) {
  const id = useId();
  const plotted = values.filter((v) => v.value > 0);
  const skipped = values.filter((v) => !(v.value > 0));
  if (plotted.length === 0) return null;

  const logs = plotted.map((v) => Math.log10(v.value));
  const bandLogs = [band?.min && band.min > 0 ? Math.log10(band.min) : null, band?.max ? Math.log10(band.max) : null].filter(
    (x): x is number => x !== null,
  );
  let lo = Math.floor(Math.min(...logs, ...bandLogs) - 0.3);
  let hi = Math.ceil(Math.max(...logs, ...bandLogs) + 0.3);
  if (hi - lo < 3) {
    lo -= 1;
    hi += 1;
  }
  const x = (lg: number) => PAD_X + ((lg - lo) / (hi - lo)) * (W - 2 * PAD_X);

  // Place labels on alternating rows when they would collide.
  const placed = plotted
    .map((v) => ({ ...v, px: x(Math.log10(v.value)), odd: outliers.includes(v.label) }))
    .sort((a, b) => a.px - b.px);
  const rows: number[] = [];
  let lastPx = -1e9;
  let row = 0;
  for (const p of placed) {
    row = p.px - lastPx < 118 ? (row + 1) % 3 : 0;
    rows.push(row);
    lastPx = p.px;
  }

  const bandX0 = band ? x(band.min && band.min > 0 ? Math.log10(band.min) : lo) : 0;
  const bandX1 = band ? x(band.max ? Math.log10(band.max) : hi) : 0;

  const oddPts = placed.filter((p) => p.odd);
  const restPts = placed.filter((p) => !p.odd);
  let gap: { x0: number; x1: number; factor: number } | null = null;
  if (oddPts.length && restPts.length) {
    const o = oddPts[0];
    const nearest = restPts.reduce((a, b) => (Math.abs(b.px - o.px) < Math.abs(a.px - o.px) ? b : a));
    gap = { x0: Math.min(o.px, nearest.px), x1: Math.max(o.px, nearest.px), factor: Math.max(o.value, nearest.value) / Math.min(o.value, nearest.value) };
  }

  const u = unitText(unit);
  const desc = `Log-scale plot. ${placed.map((p) => `${p.label} ${num(p.value)} ${u}`).join("; ")}.${
    band ? ` Shaded band: ${band.label}.` : ""
  }${gap ? ` The ${oddPts[0].label} is about ${num(Math.round(gap.factor))} times away from the other values.` : ""}`;

  return (
    <figure className="m-0">
      <svg
        viewBox={`0 0 ${W} ${H}`}
        role="img"
        aria-labelledby={`${id}-t ${id}-d`}
        className={`w-full h-auto ${animate ? "ruler-animate" : ""}`}
      >
        <title id={`${id}-t`}>Order-of-magnitude ruler{caption ? `: ${caption}` : ""}</title>
        <desc id={`${id}-d`}>{desc}</desc>
        {band && (
          <g>
            <rect x={bandX0} y={AXIS_Y - 30} width={Math.max(2, bandX1 - bandX0)} height={44} fill="var(--band)" rx={4} />
            <text x={bandX0 + 6} y={AXIS_Y + 30} fontSize={12} fill="var(--algae)">
              {band.label}
            </text>
          </g>
        )}
        <line x1={PAD_X} x2={W - PAD_X} y1={AXIS_Y} y2={AXIS_Y} stroke="var(--line-strong)" strokeWidth={1.5} />
        {Array.from({ length: hi - lo + 1 }, (_, i) => lo + i).map((k) => (
          <g key={k}>
            <line x1={x(k)} x2={x(k)} y1={AXIS_Y - 6} y2={AXIS_Y + 6} stroke="var(--line-strong)" />
            {k < hi &&
              [2, 5].map((m) => (
                <line key={m} x1={x(k + Math.log10(m))} x2={x(k + Math.log10(m))} y1={AXIS_Y - 3} y2={AXIS_Y + 3} stroke="var(--line)" />
              ))}
            <text x={x(k)} y={AXIS_Y + 50} textAnchor="middle" fontSize={12} fill="var(--ink-3)" className="readout">
              {decadeLabel(k)}
            </text>
          </g>
        ))}
        {gap && (
          <g>
            <path
              d={`M${gap.x0} 30 L${gap.x0} 24 L${gap.x1} 24 L${gap.x1} 30`}
              fill="none"
              stroke="var(--cinnabar)"
              strokeWidth={1.5}
            />
            <text x={(gap.x0 + gap.x1) / 2} y={17} textAnchor="middle" fontSize={13} fontWeight={700} fill="var(--cinnabar)" className="readout">
              ×{num(Math.round(gap.factor))}
            </text>
          </g>
        )}
        {placed.map((p, i) => {
          const ly = 50 + rows[i] * 18;
          const color = p.odd ? "var(--cinnabar)" : "var(--ink)";
          return (
            <g key={p.label}>
              <line x1={p.px} x2={p.px} y1={ly + 4} y2={AXIS_Y - 8} stroke={color} strokeWidth={1} strokeDasharray={p.odd ? "0" : "2 3"} />
              {p.odd ? (
                <rect x={p.px - 7} y={AXIS_Y - 7} width={14} height={14} transform={`rotate(45 ${p.px} ${AXIS_Y})`} fill="var(--cinnabar)" />
              ) : (
                <circle cx={p.px} cy={AXIS_Y} r={6.5} fill="var(--panel)" stroke={color} strokeWidth={2.5} />
              )}
              <text x={p.px} y={ly} textAnchor="middle" fontSize={13} fill={color} fontWeight={p.odd ? 700 : 500} stroke="var(--panel)" strokeWidth={5} paintOrder="stroke" strokeLinejoin="round">
                {p.label} <tspan className="readout">{num(p.value)}</tspan>
              </text>
            </g>
          );
        })}
      </svg>
      <figcaption className="mt-1 text-sm text-ink-3">
        Logarithmic scale: each tick is ten times the one before{u ? `, values in ${u}` : ""}.
        {skipped.length > 0 && ` Not shown (zero cannot be placed on a log scale): ${skipped.map((s) => s.label).join(", ")}.`}
      </figcaption>
    </figure>
  );
}
