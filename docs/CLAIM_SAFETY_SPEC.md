# Claim safety specification

The guardrail judges a **structured claim**. Natural-language input is only a convenience: a deterministic keyword parser proposes a `ClaimIntent`
(an optional language model may only fill fields the rules left empty); a deterministic resolver maps it onto records that exist; the resulting
`StructuredClaim` is shown to the user; the verdict is computed from that structure alone.

## Verdicts

| Verdict | Meaning |
|---|---|
| SUPPORTED | Comparable, clean inputs, the direction holds, and the evidence criterion of the claim type is met |
| CONDITIONAL | The data point the claimed way, but only with stated caveats (warnings on inputs, conditional comparability, no uncertainty information, not statistically distinguishable) |
| UNSUPPORTED | The data contradict the claim or cannot address it (not comparable, too few points or sites, wrong indicator or averaging period, causal wording) |
| BLOCKED | An input record has an ERROR or CRITICAL integrity finding |

Every result has `reasons[]`, an ordered `rule_trace[]`, `statistics{}`, and `safe_alternatives[]` (wording that is safe to
publish). BLOCKED results list `blocking_findings[]`.

## Claim types

**COMPARE_HIGHER** (A > B). CLM-CMP-001 runs the comparability engine. NOT → UNSUPPORTED (with the engine's alternatives).
BLOCKED_BY_INTEGRITY → BLOCKED. CLM-DIR-001 checks the direction, converting units if needed; the opposite → UNSUPPORTED.
CLM-UNC-001: the only uncertainty the data allow is the published range. If A's minimum exceeds B's maximum and comparability is
DIRECT → SUPPORTED. Otherwise → CONDITIONAL ("descriptive only; no sample sizes or confidence intervals are published").

**TREND_INCREASE** (site × measure × statistic, years). CLM-TRD-001 needs ≥ 3 annual points (otherwise UNSUPPORTED).
CLM-INT-001: any point with an ERROR or CRITICAL finding → BLOCKED. Units must be constant. CLM-TRD-002: one-sided Mann–Kendall
with an exact permutation p-value for n ≤ 9 (normal approximation above), plus the Theil–Sen slope. Slope ≤ 0 → UNSUPPORTED;
p < 0.05 and no warnings → SUPPORTED; otherwise CONDITIONAL. Missing years are reported.

**EXCEEDS_THRESHOLD** (record statistic vs a named threshold). The threshold's indicator must match (else UNSUPPORTED). Integrity
of the record only; a site-coordinate warning does not change whether a value exceeds a limit. CLM-THR-001 checks the matrix: a
drinking-water standard applied to surface water is at most CONDITIONAL ("indicative only"). CLM-THR-002 checks the averaging
period: a calendar-year limit requires an annual mean, and a max-daily-8-hour target cannot be judged from annual summaries
(UNSUPPORTED). CLM-THR-003 compares after unit conversion. Above the limit with clean inputs → SUPPORTED, with the caveat that data
coverage is not published; any warning → CONDITIONAL.

**ASSOCIATION** (exposure measure vs outcome measure across sites). CLM-ASC-001 pairs sites with both measures. Fewer than 8
paired units → UNSUPPORTED. With n = 3 (the Benevento case) the smallest possible two-sided exact p-value of a rank correlation
is 2/3! = 0.33, so no association could ever be shown. The minimum of 8 is a conservative judgement, recorded in DECISIONS D-011. Exposure and outcome in different years and the ecological design are always
stated. At best CONDITIONAL: an ecological association never speaks for individuals.

**CAUSAL.** Always UNSUPPORTED. Aggregated observational indicators cannot establish causation (no individual exposure, no
temporal ordering, no confounder control). The weaker association claim is evaluated and reported (CLM-CAU-002) so the user sees
what *could* be said.

## Thresholds in the knowledge layer

WHO Global Air Quality Guidelines 2021 (annual PM2.5 5, PM10 15, NO2 10 µg/m³); Directive 2008/50/EC (annual NO2 40, PM10 40,
PM2.5 25, benzene 5 µg/m³; O3 target 120 µg/m³ as a maximum daily 8-hour mean); Directive (EU) 2020/2184 drinking-water parametric
values (nitrate 50 mg/L, arsenic 10 µg/L, conductivity 2500 µS/cm). Each carries its source, matrix and averaging period.
