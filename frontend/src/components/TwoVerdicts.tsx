import type { FindingCompact, OperationOutcome, Severity } from "../lib/types";
import { SEVERITY_ORDER, SEVERITY_TEXT } from "../lib/format";
import { useRun } from "./Shell";
import { SeverityShape } from "./ui";

// Coral only for critical evidence; the panel takes the colour of the worst finding, never a fixed alarm colour.
const PANEL: Record<Severity, string> = {
  CRITICAL: "border-cinnabar/50 bg-cinnabar-soft",
  ERROR: "border-ochre/50 bg-ochre-soft",
  WARNING: "border-sulfur/50 bg-sulfur-soft",
  INFO: "border-line bg-panel",
};
const TEXT: Record<Severity, string> = { CRITICAL: "text-cinnabar", ERROR: "text-ochre", WARNING: "text-sulfur", INFO: "text-slate" };

/**
 * The product in one picture: what the FHIR server's own validator says about a record, next to what
 * Data Doctor says. Both verdicts are real outputs for the same resource, each stated in one word first.
 */
export default function TwoVerdicts({
  serverOutcome,
  findings,
  record,
}: {
  serverOutcome: OperationOutcome | null | undefined;
  findings: Pick<FindingCompact, "severity" | "rule_id">[];
  record: string;
}) {
  const serverErrors = serverOutcome?.issue.filter((i) => i.severity === "error" || i.severity === "fatal") ?? [];
  const serverWord = !serverOutcome ? "Not checked" : serverErrors.length ? "Fail" : "Pass";
  const serverText = serverOutcome
    ? serverErrors.length
      ? `${serverErrors.length} error(s)`
      : serverOutcome.issue[0]?.diagnostics ?? "No errors"
    : "Not checked in this run";
  const ruleCount = useRun().status?.rule_count;
  const worst = SEVERITY_ORDER.find((s) => findings.some((f) => f.severity === s)) as Severity | undefined;
  const rules = Array.from(new Set(findings.map((f) => f.rule_id)));

  return (
    <div className="grid gap-3 sm:grid-cols-2" aria-label={`Two verdicts for ${record}`} role="group">
      <div className="rounded-lg border border-line bg-panel p-4">
        <p className="m-0 text-sm text-ink-2">FHIR server's own validator</p>
        <p className="m-0 mt-1 text-sm text-ink-3">Conformance: HAPI FHIR <code className="code">$validate</code>, base R4</p>
        <p className={`m-0 mt-3 flex items-center gap-2 text-xl font-bold ${serverWord === "Pass" ? "text-algae" : serverWord === "Fail" ? "text-cinnabar" : "text-ink-2"}`}>
          <span aria-hidden="true">{serverWord === "Pass" ? "✓" : serverWord === "Fail" ? "✕" : "–"}</span>
          <span>{serverWord}</span>
        </p>
        <p className="m-0 mt-1 text-ink-2">{serverText}</p>
      </div>
      <div className={`rounded-lg border p-4 ${worst ? PANEL[worst] : "border-line bg-panel"}`}>
        <p className="m-0 text-sm text-ink-2">OAH Data Doctor</p>
        <p className="m-0 mt-1 text-sm text-ink-3">Scientific consistency{ruleCount ? `, ${ruleCount} deterministic rules` : ", deterministic rules"}</p>
        <p className={`m-0 mt-3 flex items-center gap-2 text-xl font-bold ${worst ? TEXT[worst] : "text-algae"}`}>
          {worst ? <SeverityShape severity={worst} size={14} /> : <span aria-hidden="true">✓</span>}
          <span>{worst ? SEVERITY_TEXT[worst] : "No findings"}</span>
        </p>
        {findings.length > 0 && (
          <p className="m-0 mt-1 text-ink-2">
            {findings.length} finding{findings.length > 1 ? "s" : ""}: <span className="code">{rules.join(", ")}</span>
          </p>
        )}
      </div>
    </div>
  );
}
