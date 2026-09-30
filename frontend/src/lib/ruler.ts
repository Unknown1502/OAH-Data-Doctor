import type { FindingDetail } from "./types";
import type { RulerValue } from "../components/MagnitudeRuler";

const LEVEL = ["minimum", "maximum", "average", "median"];

/** Ruler inputs for a record: its level statistics (or single value), the possible band, and which values look off. */
export function rulerFor(d: FindingDetail): { values: RulerValue[]; unit: string | null; band: { min?: number; max?: number; label: string } | null; outliers: string[] } | null {
  const rec = d.record;
  if (!rec) return null;
  const values: RulerValue[] = rec.stats
    .filter((s) => LEVEL.includes(s.stat) && s.value !== null)
    .map((s) => ({ label: s.stat === "average" ? "mean" : s.stat, value: s.value as number }));
  if (!values.length && rec.value?.value != null) values.push({ label: "value", value: rec.value.value });
  if (values.length < 1) return null;
  const unit = rec.stats.find((s) => s.unit)?.unit ?? rec.value?.code ?? null;
  const sameUnit = !rec.canonical_unit || unit === rec.canonical_unit;
  const band = rec.hard && sameUnit ? { min: rec.hard.min, max: rec.hard.max, label: "physically possible" } : null;
  const m = d.finding.evidence.measures as Record<string, unknown>;
  let outliers = Array.isArray(m.outlying_statistics) ? (m.outlying_statistics as string[]).map((s) => (s === "average" ? "mean" : s)) : [];
  if (!outliers.length && band) {
    outliers = values.filter((v) => (band.max !== undefined && v.value > band.max) || (band.min !== undefined && v.value < band.min)).map((v) => v.label);
    if (outliers.length === values.length) outliers = [];
  }
  if (!outliers.length && d.finding.rule_id === "SEM-STAT-001") outliers = ["median"];
  if (!outliers.length && d.finding.rule_id === "SEM-STAT-002") outliers = ["mean"];
  return { values, unit, band, outliers };
}
