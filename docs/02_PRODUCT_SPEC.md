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
| Data health (home) | Show, with a real record, why this matters, and give the state of the data | Most important finding first: headline computed from data (only the impossible value in coral); evidence and the two verdicts ("Pass" vs "Critical"); what it may affect; dataset status and supporting metrics (checked, findings, usable as published, flagged yet server-valid); what-if lab; blocking findings by site; rules that fired; catalog verdicts |
| Findings | Triage | Investigation queue: severity, category, rule, place, indicator, records and text filters in the URL; one dense row per finding (severity, finding, record, place, rule and field); zero-findings and empty-filter states |
| Finding detail | Investigate one finding | Evidence chain (observed, calculation, result, rule broken, conclusion, root cause unknown with hypotheses "not verified"); two verdicts plus "ask the server now"; evidence (magnitude ruler, values with FHIRPaths, measures, provenance); why it matters; safe conclusion; suggested action; upstream lineage; what this affects (impact trace); plain-language or AI explanation; what-if lab; related findings; raw FHIR drawer; exports |
| Compare | Can two numbers be compared? | Catalog examples; two record pickers (filter + native listbox + statistic); verdict panel; comparability matrix with each problem's kind (hard blocker, transformable, contextual, blocked until reviewed); transformations; blocking findings; what you can do instead |
| Check a claim | Guard a sentence | Free-text claim read live by keyword rules, with examples; structured builder; "how Data Doctor read your claim"; verdict panel; evidence ladder (observation to causation); safe wording with copy; blocking findings; ordered rule trace |
| Report | Evidence integrity report | Dataset, source, mode, audit timestamp; executive finding; dataset health; critical findings; scientific consequences (support table); comparability; claim safety; provenance; rules applied; technical appendix (exports, limitations); print to PDF |
| The data | Browse what was published | Provenance of the copy; monitoring places; values over time; every official record exactly as published, with a link to it on the FHIR server |
| Check your data | Bring FHIR data from anywhere | Paste or drop a resource, Bundle, JSON array or NDJSON; checked in memory, never stored; the command line and whole-server options |
| Sources & rules | Transparency | Current source; scan live, use snapshot, clear the analyses I ran; verified snapshots with hashes; full rule catalog; AI policy |

Global: top bar with the source state (Live + "fetched N min ago", or Snapshot + capture time + "sha256 verified"), Search
(Ctrl+K) and "Scan live sandbox"; audit stages strip; fallback banner when live failed; sidebar grouped under Investigate and
Data, with the source status, the language-model control and an icon-only theme menu (dark, light, system) at the bottom; on a
phone, a menu drawer and a bottom bar.

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
