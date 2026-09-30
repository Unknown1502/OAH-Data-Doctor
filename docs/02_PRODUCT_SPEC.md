# 02 — Product specification

## Capabilities

### Doctor
- Runs every rule in docs/04_RULES_CATALOG.md over the current dataset and returns findings sorted by severity.
- Each finding carries: id (deterministic), rule id and version, title, category, severity, confidence (0–1 and a label), scope
  (official IG example or third-party write), primary resource with FHIRPath, related resources, plain summary, evidence
  (observed values with FHIRPaths, formal constraint, expected behaviour, computed measures, raw excerpt), interpretation,
  root cause (`unknown`), labelled hypotheses, remediation, optional upstream lineage, and provenance.
- Severity: CRITICAL (impossible and large enough to distort any analysis), ERROR (values that cannot all be correct), WARNING
  (unusual or ambiguous), INFO (not used by current rules).

### Trace
- Builds a dependency graph from records to the analyses Data Doctor computes: data-set Libraries, indicator profiles (report),
  annual series (≥ 3 points, used by trend claims), catalog comparisons and claims, and any comparison or claim a user ran.
- For a finding, lists every reachable analysis and gives exact counts. It never estimates impact.

### Compare
- Input: two observations (and a statistic when they are annual summaries).
- Output: eight dimension results (PASS / CONDITIONAL / FAIL / N/A, each with a reason and rule id), a verdict (DIRECT,
  CONDITIONAL, NOT, BLOCKED_BY_INTEGRITY), required transformations, blocking findings and computed alternatives.
  See docs/COMPARABILITY_SPEC.md.

### Claim guardrail
- Input: a structured claim (COMPARE_HIGHER, TREND_INCREASE, EXCEEDS_THRESHOLD, ASSOCIATION, CAUSAL), built in a form or parsed
  from plain words. The parsed structure is always shown to the user.
- Output: verdict (SUPPORTED, CONDITIONAL, UNSUPPORTED, BLOCKED), reasons, rule trace, statistics, blocking findings and safe
  alternative wording. See docs/CLAIM_SAFETY_SPEC.md.

### Reporting
- JSON findings (schema-validated), FHIR OperationOutcome bundle (R4-validated), researcher report (Markdown and HTML),
  "what this data can and cannot support" table.

## Screens

| Screen | Purpose | Key elements |
|---|---|---|
| Data health (home) | Show, with a real record, why this matters, and give the state of the data | Anchor case headline computed from data; the server's verdict next to Data Doctor's; magnitude ruler; readout strip (checked, findings, safe records, flagged records that pass server validation); blocking findings by site; rules that fired; support status; catalog verdicts |
| Findings | Triage | Severity, rule, record-scope and text filters in the URL; sortable table of record, what is wrong, rule and confidence |
| Finding detail | Investigate one finding | Summary; magnitude ruler; two verdicts plus "ask the server now"; evidence table with FHIRPaths; measures; meaning (root cause unknown, hypotheses labelled "not verified", remediation); upstream lineage row; impact trace graph; plain-language explanation; related findings; raw FHIR; provenance; exports |
| Compare | Can two numbers be compared? | Catalog examples; two record pickers (filter + native listbox + statistic); verdict panel; dimension table; transformations; blocking findings; alternatives |
| Check a claim | Guard a sentence | Free-text claim with examples; structured builder; "how Data Doctor read your claim"; verdict panel; safe wording with copy; blocking findings; ordered rule trace |
| Report | Export | Four exports; support table |
| Sources and rules | Transparency | Current source; scan live, use snapshot, clear the analyses I ran; verified snapshots with hashes; full rule catalog; AI policy |

Global: source badge (Live + fetch time, or Snapshot + date, with the manifest hash on hover); fallback banner when live failed;
"Scan live sandbox" action; theme choice (system, light, dark).

## Behaviour requirements

- Startup shows the latest verified snapshot immediately (labelled Snapshot) and refreshes from the live sandbox in the background
  (`DD_SOURCE=auto`). If live fails, a banner says so and the snapshot stays.
- No screen shows a number that was not computed by the backend for the current run.
- Plain language, sentence case, no jargon without explanation. Units are shown typographically (µg/m³, °C).
- Accessibility: WCAG 2.1 AA (contrast, landmarks, skip link, labelled controls, keyboard-reachable scroll regions, visible
  focus, reduced motion respected, colour never the only carrier of meaning — severity also has a shape).
- Responsive to 360 px width.

## Acceptance

- Playwright demo path passes with every external request blocked; axe-core finds no serious or critical WCAG 2.1 AA violation
  on any main screen in light and dark mode.
- Golden comparability cases: Benevento 35–74 vs an Oslo non-overlapping band → NOT; identical measure/unit/cohort/period →
  DIRECT; unit-convertible → CONDITIONAL.
- Every claim verdict lists reasons and a rule trace; BLOCKED lists blocking findings; safe wording is offered.
