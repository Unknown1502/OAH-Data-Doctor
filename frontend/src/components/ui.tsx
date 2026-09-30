import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { CLAIM_TEXT, CMP_TEXT, SEVERITY_TEXT, tone, when } from "../lib/format";
import type { ClaimVerdict, CmpVerdict, Severity, SourceInfo } from "../lib/types";

const SEV_STYLE: Record<Severity, string> = {
  CRITICAL: "text-cinnabar bg-cinnabar-soft",
  ERROR: "text-ochre bg-ochre-soft",
  WARNING: "text-sulfur bg-sulfur-soft",
  INFO: "text-slate bg-slate-soft",
};

/** Severity is carried by shape + text, never colour alone. */
export function SeverityShape({ severity, size = 12 }: { severity: Severity; size?: number }) {
  const s = size;
  const common = { width: s, height: s, viewBox: "0 0 12 12", "aria-hidden": true as const, className: "inline-block shrink-0 align-[-1px]" };
  if (severity === "CRITICAL") return <svg {...common}><rect x="2" y="2" width="8" height="8" transform="rotate(45 6 6)" fill="currentColor" /></svg>;
  if (severity === "ERROR") return <svg {...common}><path d="M6 1 L11 11 H1 Z" fill="currentColor" /></svg>;
  if (severity === "WARNING") return <svg {...common}><circle cx="6" cy="6" r="4.5" fill="currentColor" /></svg>;
  return <svg {...common}><circle cx="6" cy="6" r="4" fill="none" stroke="currentColor" strokeWidth="1.8" /></svg>;
}

export function SeverityTag({ severity }: { severity: Severity }) {
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-sm font-semibold ${SEV_STYLE[severity]}`}>
      <SeverityShape severity={severity} />
      {SEVERITY_TEXT[severity]}
    </span>
  );
}

const TONE_STYLE = {
  good: "bg-algae-soft text-algae border-algae/40",
  caveat: "bg-sulfur-soft text-sulfur border-sulfur/40",
  bad: "bg-slate-soft text-slate border-slate/40",
  blocked: "bg-cinnabar-soft text-cinnabar border-cinnabar/40",
  neutral: "bg-sunk text-ink-2 border-line",
};

export function Verdict({ value, size = "md" }: { value: CmpVerdict | ClaimVerdict | string; size?: "md" | "lg" }) {
  const text = (CMP_TEXT as Record<string, string>)[value] ?? (CLAIM_TEXT as Record<string, string>)[value] ?? value;
  const t = tone(value);
  const glyph = { good: "✓", caveat: "≈", bad: "≠", blocked: "⊘", neutral: "·" }[t];
  const sizing = size === "lg" ? "text-lg px-4 py-1.5" : "text-sm px-2.5 py-0.5";
  return (
    <span className={`inline-flex items-center gap-1.5 whitespace-nowrap rounded-full border font-semibold ${sizing} ${TONE_STYLE[t]}`}>
      <span aria-hidden="true">{glyph}</span>
      {text}
    </span>
  );
}

/** A status label using the verdict tone system with its own words (e.g. "Pass", "Usable"). */
export function Chip({ text, toneOf }: { text: string; toneOf: string }) {
  const t = tone(toneOf);
  const glyph = { good: "✓", caveat: "≈", bad: "≠", blocked: "⊘", neutral: "–" }[t];
  return (
    <span className={`inline-flex items-center gap-1.5 whitespace-nowrap rounded-full border px-2.5 py-0.5 text-sm font-semibold ${TONE_STYLE[t]}`}>
      <span aria-hidden="true">{glyph}</span>
      {text}
    </span>
  );
}

export function SourceBadge({ source, compact = false }: { source: SourceInfo | null | undefined; compact?: boolean }) {
  if (!source) return <span className="text-sm text-ink-3">No data loaded</span>;
  const live = source.kind === "live";
  return (
    <span
      className={`inline-flex items-center gap-2 rounded-full border px-3 py-1 text-sm ${
        live ? "border-algae/50 bg-algae-soft text-algae" : "border-karst/40 bg-karst-soft text-karst"
      }`}
      title={source.manifest_sha256 ? `Snapshot manifest sha256 ${source.manifest_sha256}` : source.base_url}
    >
      <span aria-hidden="true" className={`inline-block h-2 w-2 rounded-full ${live ? "bg-algae" : "bg-karst"}`} />
      <span className="font-semibold">{live ? "Live" : "Snapshot"}</span>
      {!compact && <span className="text-ink-2">{live ? `fetched ${when(source.fetched_at)}` : `of ${when(source.fetched_at)}`}</span>}
    </span>
  );
}

export function Readout({ label, value, note, tone: t }: { label: string; value: ReactNode; note?: ReactNode; tone?: "bad" | "good" }) {
  return (
    <div className="min-w-0">
      <dt className="text-sm text-ink-2">{label}</dt>
      <dd className={`m-0 readout text-2xl font-semibold ${t === "bad" ? "text-cinnabar" : t === "good" ? "text-algae" : "text-ink"}`}>{value}</dd>
      {note && <dd className="m-0 text-sm text-ink-3">{note}</dd>}
    </div>
  );
}

export function Panel({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <div className={`rounded-xl border border-line bg-panel ${className}`}>{children}</div>;
}

export function Loading({ what }: { what: string }) {
  return (
    <p role="status" className="py-10 text-ink-3">
      Loading {what}…
    </p>
  );
}

export function ErrorNote({ error, action }: { error: string; action?: ReactNode }) {
  return (
    <div role="alert" className="rounded-lg border border-cinnabar/40 bg-cinnabar-soft px-4 py-3 text-cinnabar">
      <p className="m-0 font-semibold">{error}</p>
      {action && <div className="mt-2">{action}</div>}
    </div>
  );
}

export function FindingLink({ id, children }: { id: string; children: ReactNode }) {
  return (
    <Link to={`/findings/${encodeURIComponent(id)}`} className="text-karst underline decoration-karst/40 underline-offset-2 hover:decoration-karst">
      {children}
    </Link>
  );
}

export function Button({
  children,
  onClick,
  kind = "secondary",
  type = "button",
  disabled,
  ariaDescribedBy,
}: {
  children: ReactNode;
  onClick?: () => void;
  kind?: "primary" | "secondary" | "quiet";
  type?: "button" | "submit";
  disabled?: boolean;
  ariaDescribedBy?: string;
}) {
  const styles = {
    primary: "bg-karst text-chalk border-karst hover:brightness-110",
    secondary: "bg-panel text-ink border-line-strong hover:bg-sunk",
    quiet: "bg-transparent text-karst border-transparent hover:bg-karst-soft",
  }[kind];
  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled}
      aria-describedby={ariaDescribedBy}
      className={`inline-flex items-center gap-2 rounded-lg border px-3.5 py-2 text-[0.95rem] font-semibold transition-[filter,background] disabled:cursor-not-allowed disabled:opacity-50 ${styles}`}
    >
      {children}
    </button>
  );
}

export function useDocumentTitle(title: string) {
  if (typeof document !== "undefined") document.title = `${title} | OAH Data Doctor`;
}
