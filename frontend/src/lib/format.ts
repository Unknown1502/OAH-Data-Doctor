import type { ClaimVerdict, CmpVerdict, DimStatus, Severity } from "./types";

export function num(v: number | string | null | undefined): string {
  if (v === null || v === undefined || v === "") return "—";
  if (typeof v === "string") return v;
  if (Number.isInteger(v)) return v.toLocaleString("en-GB");
  const abs = Math.abs(v);
  const digits = abs >= 100 ? 1 : abs >= 1 ? 3 : 4;
  return v.toLocaleString("en-GB", { maximumFractionDigits: digits });
}

export const UNIT_DISPLAY: Record<string, string> = {
  Cel: "°C",
  "ug/m3": "µg/m³",
  "ug/L": "µg/L",
  "uS/cm": "µS/cm",
  "[pH]": "pH",
  "%": "%",
};
export const unit = (u: string | null | undefined) => (u ? UNIT_DISPLAY[u] ?? u : "");

export const SEVERITY_ORDER: Severity[] = ["CRITICAL", "ERROR", "WARNING", "INFO"];

export const SEVERITY_TEXT: Record<Severity, string> = {
  CRITICAL: "Critical",
  ERROR: "Error",
  WARNING: "Warning",
  INFO: "Info",
};

export const SEVERITY_MEANING: Record<Severity, string> = {
  CRITICAL: "Impossible values that would distort any analysis",
  ERROR: "Values that cannot all be correct",
  WARNING: "Unusual or ambiguous; check before use",
  INFO: "For information",
};

export const CMP_TEXT: Record<CmpVerdict, string> = {
  DIRECT: "Directly comparable",
  CONDITIONAL: "Comparable with caveats",
  NOT: "Not comparable",
  BLOCKED_BY_INTEGRITY: "Blocked by integrity findings",
};

export const CLAIM_TEXT: Record<ClaimVerdict, string> = {
  SUPPORTED: "Supported",
  CONDITIONAL: "Conditional",
  UNSUPPORTED: "Unsupported",
  BLOCKED: "Blocked",
};

export const DIM_TEXT: Record<DimStatus, string> = { PASS: "Pass", CONDITIONAL: "Caveat", FAIL: "Fail", "N/A": "Not applicable" };

export function tone(v: string): "good" | "caveat" | "bad" | "blocked" | "neutral" {
  if (["DIRECT", "SUPPORTED", "PASS", "USABLE"].includes(v)) return "good";
  if (["CONDITIONAL", "USABLE_WITH_CAVEATS", "PARTLY_USABLE"].includes(v)) return "caveat";
  if (["BLOCKED_BY_INTEGRITY", "BLOCKED", "NOT_USABLE", "FAIL"].includes(v)) return "blocked";
  if (["NOT", "UNSUPPORTED"].includes(v)) return "bad";
  return "neutral";
}

export function when(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso.replace(/Z?$/, "Z"));
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString("en-GB", { dateStyle: "medium", timeStyle: "short", timeZone: "UTC" }) + " UTC";
}

/** Render UCUM codes that appear inside computed prose in their typographic form. */
export function pretty(text: string | null | undefined): string {
  if (!text) return "";
  return text
    .replace(/\bug\/m3\b/g, "µg/m³")
    .replace(/\bug\/L\b/g, "µg/L")
    .replace(/\buS\/cm\b/g, "µS/cm")
    .replace(/\bCel\b/g, "°C")
    .replace(/\[pH\]/g, "pH");
}

export const sentence = (t: string) => (t ? t[0].toUpperCase() + t.slice(1) : t);

export function aggregationText(code: string): string {
  if (code === "point-measurement") return "single measurement";
  if (code === "annual-prevalence") return "annual prevalence";
  if (code === "single-value") return "single value";
  const m = code.match(/^(annual|period)-summary:(.+)$/);
  if (m) return `${m[1]} ${m[2] === "average" ? "mean" : m[2]}`;
  return code;
}
