import type { FindingCompact, OperationOutcome, Severity } from "../lib/types";
import { SEVERITY_ORDER } from "../lib/format";
import { useRun } from "./Shell";
import { SeverityShape } from "./ui";

/**
 * The product in one picture: what the FHIR server's own validator says about a record, next to what
 * Data Doctor says. Both verdicts are real outputs for the same resource.
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
      <div className="rounded-xl border border-line bg-panel p-4">
        <p className="m-0 text-sm text-ink-2">FHIR server's own validator</p>
        <p className="m-0 mt-1 text-sm text-ink-3">HAPI FHIR <code className="code">$validate</code>, base R4</p>
        <p className={`m-0 mt-3 flex items-center gap-2 text-lg font-semibold ${serverOutcome && !serverErrors.length ? "text-algae" : "text-ink-2"}`}>
          <span aria-hidden="true">{serverOutcome && !serverErrors.length ? "✓" : "–"}</span>
          {serverText}
        </p>
      </div>
      <div className="rounded-xl border-2 border-cinnabar/60 bg-cinnabar-soft p-4">
        <p className="m-0 text-sm text-ink-2">OAH Data Doctor</p>
        <p className="m-0 mt-1 text-sm text-ink-3">Scientific consistency{ruleCount ? `, ${ruleCount} deterministic rules` : ", deterministic rules"}</p>
        <p className="m-0 mt-3 flex items-center gap-2 text-lg font-semibold text-cinnabar">
          {worst && <SeverityShape severity={worst} size={14} />}
          {findings.length ? `${findings.length} finding${findings.length > 1 ? "s" : ""}: ${rules.join(", ")}` : "No findings"}
        </p>
      </div>
    </div>
  );
}
