# Comparability specification

Question answered: *can value A and value B be compared as the same quantity, and on what terms?*

## Dimensions

| Rule | Dimension | PASS | CONDITIONAL | FAIL |
|---|---|---|---|---|
| CMP-MEASURE | Measure identity | Same code, or different codes mapped `equivalent` (e.g. SNOMED 703421000 "Temperature (water)" and OAH #waterTemperature) | Mapped `related`: plausibly the same construct, definition differs or is unverified (obesity vs BMI ≥ 30; lab vs field conductivity) | Different measures, `broader` relation (CVD vs "diabetes, COPD or CVD"), or unmapped |
| CMP-UNIT | Unit | Same UCUM code | Different codes with an exact conversion in `knowledge/terminology/units.yaml` (transformation listed; affine conversions flagged) | Missing unit, or no explicit conversion |
| CMP-MEDIUM | Medium | Same (water, air, population health) | — | Different |
| CMP-POPULATION | Population | Same sex and identical age band, or both environmental (N/A) | Different sexes (valid only as a sex comparison), sex-specific vs all, or overlapping but different age bands (overlap reported) | Age bands do not overlap; only one side has a cohort |
| CMP-PERIOD | Period | Identical | Different periods: a comparison over time | Missing |
| CMP-AGGREGATION | Aggregation | Same kind and statistic (annual mean vs annual mean; annual prevalence vs annual prevalence) | — | Different statistics (mean vs median) or kinds (annual summary vs spot measurement) |
| CMP-METHOD | Method / performer | Same performer, device and method | Different or undocumented | — |
| CMP-INTEGRITY | Integrity | No finding on either record or its location | Warnings only (listed) | Any ERROR or CRITICAL finding on either record |

## Verdict

1. Any FAIL among the first seven dimensions → **NOT**. The values could not be compared even if the data were repaired.
2. Otherwise, integrity FAIL → **BLOCKED_BY_INTEGRITY**. Comparable in principle; blocked until the data owner reviews the records.
3. Otherwise, any CONDITIONAL → **CONDITIONAL**: comparable with the listed caveats and transformations.
4. Otherwise → **DIRECT**.

## Kinds of problem (how the console labels a dimension)

The labels restate the verdict rules above; they add no logic.

| Dimension result | Kind | Why |
|---|---|---|
| FAIL on measure, unit, medium, population, period or aggregation | **hard blocker** | verdict NOT: "no transformation can fix" it |
| FAIL on integrity | **blocked until reviewed** | comparable in principle; an input has an ERROR or CRITICAL finding |
| CONDITIONAL on unit | **transformable** | CONDITIONAL only when an exact conversion exists; the conversion is listed under transformations |
| any other CONDITIONAL | **contextual** | comparable with the stated caveat (related measure, different sexes or overlapping ages, comparison over time, undocumented method, warnings on inputs) |
| PASS or N/A | none | |

There is no "unknown" state: an undocumented method is CONDITIONAL with the reason "not documented", and a dimension that does
not apply (population for environmental data) is N/A.

## Supported alternatives (computed, never invented)

- Population FAIL: cohorts at B's site, for B's measure, whose age band overlaps A's (and whose sex matches or is "all").
- Aggregation FAIL with the same kind: compare the same statistic on both sides.
- Integrity FAIL: records of the same measure at the same site with no ERROR or CRITICAL finding (one suggestion per site and measure).
- Measure FAIL: records at B's site measuring A's measure or a related one; or an explicit statement that none exists.

## Examples on the OAH data (verdicts recomputed on every run)

- Almyros vs Giofyros water temperature, same day, same probe → DIRECT.
- Benevento women 35–74 obesity vs Oslo 18–29 BMI ≥ 30 → NOT (age bands do not overlap).
- Benevento women 35–74 obesity vs Oslo women (all ages) BMI ≥ 30 → CONDITIONAL (measure related, age overlap only, method undocumented).
- Almyros lab water temperature 2013 vs 2014 → BLOCKED_BY_INTEGRITY.
- Almyros 2020 lab conductivity median vs 2024 field probe → NOT (annual summary vs spot measurement).
