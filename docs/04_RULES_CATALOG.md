# 04 — Rules catalog

Generated from the rule registry by `scripts/render_docs.py` (rules version `3f658dbba610a441`). This file is the authoritative description of rule behaviour; it cannot drift from the code because it is rendered from it.

Principles shared by every rule:

- Pure function of the dataset and the knowledge layer; no I/O, no LLM, deterministic finding ids.
- Numbers are compared within half a unit of their last published decimal (an exact zero uses the record's finest precision), so rounding alone never raises a finding.
- Root cause is always `unknown`. Patterns that suggest a cause are attached as explicitly labelled, unverified hypotheses.
- Every finding carries rule id and version, resource, FHIRPath, observed values, constraint, confidence, severity, provenance and remediation ("review by the data owner").

Findings per rule refer to snapshot `2026-09-30T09-08-55Z`.

| Rule | Title | Category | Severity | Findings in snapshot |
|---|---|---|---|---|
| [SEM-CODE-001](#sem-code-001) | Near-synonymous indicators report different values | Semantic | WARNING | 1 |
| [SEM-COHORT-001](#sem-cohort-001) | Pooled value outside the range of its subgroups | Semantic | ERROR | 0 |
| [SEM-COHORT-002](#sem-cohort-002) | Complementary shares do not add up to 100 % | Semantic | ERROR | 0 |
| [SEM-DEF-001](#sem-def-001) | Indicator definition contradicts the published unit | Semantic | WARNING | 1 |
| [SEM-RANGE-001](#sem-range-001) | Physically or definitionally impossible value | Semantic | CRITICAL | 24 |
| [SEM-RANGE-002](#sem-range-002) | Unusual value (possible, but outside the typical range) | Semantic | WARNING | 4 |
| [SEM-SCALE-001](#sem-scale-001) | Mean and median differ by orders of magnitude | Statistical | ERROR | 101 |
| [SEM-SPATIAL-001](#sem-spatial-001) | Distinct sites share identical coordinates | Semantic | WARNING | 1 |
| [SEM-STAT-001](#sem-stat-001) | Median outside the reported [minimum, maximum] | Statistical | ERROR | 100 |
| [SEM-STAT-002](#sem-stat-002) | Mean outside the reported [minimum, maximum] | Statistical | ERROR | 52 |
| [SEM-STAT-003](#sem-stat-003) | Mean–median gap exceeds the standard deviation | Statistical | ERROR | 51 |
| [SEM-STAT-004](#sem-stat-004) | Standard deviation incompatible with the reported range | Statistical | ERROR | 0 |
| [SEM-STAT-005](#sem-stat-005) | Minimum greater than maximum | Statistical | ERROR | 0 |
| [SEM-STAT-006](#sem-stat-006) | Negative standard deviation | Statistical | CRITICAL | 0 |
| [SEM-TEMP-001](#sem-temp-001) | Scale break within a time series | Semantic | ERROR | 1 |
| [SEM-XREC-001](#sem-xrec-001) | Sub-fraction exceeds its super-fraction (PM2.5 > PM10) | Semantic | ERROR when any statistic exceeds by > 10 % (relative) | 4 |
| [STR-LIB-001](#str-lib-001) | Data-set Library inconsistent with its declared contents | Structural | ERROR | 0 |
| [STR-PROF-001](#str-prof-001) | Resource violates its declared OAH profile | Structural | ERROR | 0 |
| [STR-REF-001](#str-ref-001) | Reference does not resolve | Structural | ERROR | 0 |
| [STR-UNIT-001](#str-unit-001) | Quantity without a valid UCUM unit code | Structural | ERROR if the code is missing or known-invalid | 6 |

## SEM-CODE-001

**Near-synonymous indicators report different values** (v1.0, semantic)

- **Must hold:** for the same site, cohort and period, synonymous indicators report the same value (within rounding)
- **Applies to:** Pairs of codes in the OAH CodeSystem whose normalised displays are identical
- **Severity:** WARNING
- **Confidence:** 0.8 — synonymy is decided by deterministic text normalisation (knowledge/terminology/synonyms.yaml)
- **Why:** Two indicators that read the same but disagree leave a researcher unable to pick the right one.
- **Tests:** `backend/tests/unit/test_rules_domain.py` (positive, negative and edge cases)

## SEM-COHORT-001

**Pooled value outside the range of its subgroups** (v1.0, semantic)

- **Must hold:** min(subgroups) <= pooled <= max(subgroups) (within published precision)
- **Applies to:** Prevalence observations with the same site, indicator and period whose cohorts form a partition (male + female of the same ages, or age bands exactly tiling the pooled age range)
- **Severity:** ERROR
- **Confidence:** 0.9 — any pooled proportion is a weighted average of the proportions of a partition
- **Why:** A weighted average of numbers cannot lie outside them, whatever the (unpublished) group sizes.
- **Tests:** `backend/tests/unit/test_rules_crossrecord.py` (positive, negative and edge cases)

## SEM-COHORT-002

**Complementary shares do not add up to 100 %** (v1.0, semantic)

- **Must hold:** |sum - 100| <= sum of rounding half-units
- **Applies to:** Complement sets (e.g. long-term disease / no long-term disease; the four BMI bands) observed for the same site, cohort and period
- **Severity:** ERROR
- **Confidence:** 0.9 — complements are exhaustive and exclusive by definition (knowledge/indicators/registry.yaml)
- **Why:** Mutually exclusive, exhaustive categories partition a population.
- **Tests:** `backend/tests/unit/test_rules_crossrecord.py` (positive, negative and edge cases)

## SEM-DEF-001

**Indicator definition contradicts the published unit** (v1.0, semantic)

- **Must hold:** a concept defined as a rate 'per 100,000 inhabitants' is not published in '%' (per 100)
- **Applies to:** Observations coded with the OAH temporary CodeSystem; one finding for the whole CodeSystem
- **Severity:** WARNING
- **Confidence:** 0.9 — the contradiction is textual and explicit in the CodeSystem
- **Why:** A share per 100 and a rate per 100,000 differ by a factor of 1,000; a reader cannot know which applies.
- **Tests:** `backend/tests/unit/test_rules_domain.py` (positive, negative and edge cases)

## SEM-RANGE-001

**Physically or definitionally impossible value** (v1.0, semantic)

- **Must hold:** hard.min <= value <= hard.max, after explicit unit conversion to the canonical unit
- **Applies to:** Observations whose code maps to an indicator with hard bounds (knowledge/scientific/plausibility.yaml)
- **Severity:** CRITICAL
- **Confidence:** 0.97 — bounds are physical limits (e.g. liquid water cannot exceed 100 C) or definitions (0-100 %)
- **Why:** Values outside hard bounds cannot be real measurements of the stated quantity.
- **Tests:** `backend/tests/unit/test_rules_domain.py` (positive, negative and edge cases)

## SEM-RANGE-002

**Unusual value (possible, but outside the typical range)** (v1.0, semantic)

- **Must hold:** typical.min <= value <= typical.max
- **Applies to:** Indicators with a documented typical range; not reported when SEM-RANGE-001 already fires
- **Severity:** WARNING
- **Confidence:** 0.6 — typical ranges describe common conditions, not limits
- **Why:** Unusual is not impossible: the finding asks for confirmation and states why the value may be real.
- **Tests:** `backend/tests/unit/test_rules_domain.py` (positive, negative and edge cases)

## SEM-SCALE-001

**Mean and median differ by orders of magnitude** (v1.1, statistical)

- **Must hold:** 1/100 < mean/median < 100
- **Applies to:** Observations publishing a positive average and median
- **Severity:** ERROR
- **Confidence:** 0.9 when the ratio is an exact power of ten (a scale signature); 0.75 otherwise
- **Why:** Mean and median are both measures of the centre of the same data; a ratio >= 100 is essentially never produced by real environmental data and an exact power of ten is the signature of a scale mix-up. Extremes (min/max) are NOT compared with each other or with the centre: a pollutant minimum near zero is normal (v1.1, after Gate-0 pre-review). Min/max are only used to say which of the two central values sits with the rest of the record.
- **Tests:** `backend/tests/unit/test_rules_statistical.py` (positive, negative and edge cases)

## SEM-SPATIAL-001

**Distinct sites share identical coordinates** (v1.0, semantic)

- **Must hold:** distinct monitoring sites have distinct positions (5 decimal places, ~1 m)
- **Applies to:** Location resources with a position; parent/child (partOf) pairs are excluded
- **Severity:** WARNING
- **Confidence:** 0.85 — could be a deliberate placeholder, which is itself worth documenting
- **Why:** Spatial analyses (distance to exposure, mapping, spatial joins) cannot distinguish these sites.
- **Tests:** `backend/tests/unit/test_rules_domain.py` (positive, negative and edge cases)

## SEM-STAT-001

**Median outside the reported [minimum, maximum]** (v1.0, statistical)

- **Must hold:** minimum <= median <= maximum (within half a unit of the last published decimal)
- **Applies to:** Observations with observation-statistics components median, minimum and maximum
- **Severity:** ERROR; CRITICAL when the median is >= 10x away from the violated bound
- **Confidence:** 0.95 — a mathematical identity; residual uncertainty only in statistic labelling
- **Why:** The median is an order statistic of the data; it is bounded by the smallest and largest value.
- **Tests:** `backend/tests/unit/test_rules_statistical.py` (positive, negative and edge cases)

## SEM-STAT-002

**Mean outside the reported [minimum, maximum]** (v1.0, statistical)

- **Must hold:** minimum <= mean <= maximum (within published precision)
- **Applies to:** Observations with observation-statistics components average, minimum and maximum
- **Severity:** ERROR; CRITICAL when the mean is >= 10x away from the violated bound
- **Confidence:** 0.95 — a mathematical identity
- **Why:** An arithmetic mean is a convex combination of the data, so it lies within their range.
- **Tests:** `backend/tests/unit/test_rules_statistical.py` (positive, negative and edge cases)

## SEM-STAT-003

**Mean–median gap exceeds the standard deviation** (v1.0, statistical)

- **Must hold:** |mean - median| <= SD
- **Applies to:** Observations publishing average, median and std-dev
- **Severity:** ERROR
- **Confidence:** 0.9 — holds for every distribution with finite variance, for population and sample SD
- **Why:** Hotelling & Solomons (1932): |mu - m| <= sigma. The sample SD (Bessel) is >= the population SD, so the bound also holds with the sample SD.
- **References:** Hotelling H, Solomons LM. The limits of a measure of skewness. Ann Math Stat 1932;3:141-142.
- **Tests:** `backend/tests/unit/test_rules_statistical.py` (positive, negative and edge cases)

## SEM-STAT-004

**Standard deviation incompatible with the reported range** (v1.0, statistical)

- **Must hold:** SD <= (max - min)/sqrt(2); and SD = 0 when min = max
- **Applies to:** Observations publishing std-dev, minimum and maximum
- **Severity:** ERROR
- **Confidence:** 0.9 — the bound is attained only by n = 2 samples at the extremes
- **Why:** For data inside [min, max] the sample SD is maximised by two points at the extremes, giving range/sqrt(2); if every value is equal the SD must be zero.
- **Tests:** `backend/tests/unit/test_rules_statistical.py` (positive, negative and edge cases)

## SEM-STAT-005

**Minimum greater than maximum** (v1.0, statistical)

- **Must hold:** minimum <= maximum
- **Applies to:** Observations publishing minimum and maximum
- **Severity:** ERROR
- **Confidence:** 0.95
- **Why:** By definition.
- **Tests:** `backend/tests/unit/test_rules_statistical.py` (positive, negative and edge cases)

## SEM-STAT-006

**Negative standard deviation** (v1.0, statistical)

- **Must hold:** SD >= 0
- **Applies to:** Observations publishing std-dev
- **Severity:** CRITICAL
- **Confidence:** 0.99
- **Why:** A standard deviation is the square root of a variance, so it can never be negative. Checked on its own, because a record may publish a standard deviation without a minimum and maximum (added after the what-if lab showed that no rule caught it).
- **Tests:** `backend/tests/unit/test_rules_statistical.py` (positive, negative and edge cases)

## SEM-TEMP-001

**Scale break within a time series** (v1.1, semantic)

- **Must hold:** within a series whose other points agree within 10x, no point is >= 100x from their median
- **Applies to:** Annual summary statistics for the same site and indicator with >= 3 years
- **Severity:** ERROR
- **Confidence:** 0.8 — the other years agree within 10x while this one is >= 100x away
- **Why:** Environmental levels do not jump by orders of magnitude for one year and return; a scale/unit slip is far likelier.
- **Tests:** `backend/tests/unit/test_rules_crossrecord.py` (positive, negative and edge cases)

## SEM-XREC-001

**Sub-fraction exceeds its super-fraction (PM2.5 > PM10)** (v1.1, semantic)

- **Must hold:** for each published statistic: stat(PM2.5) <= stat(PM10)
- **Applies to:** Annual summaries of a subset/superset pair (knowledge: PM2.5 within PM10) at the same site and year
- **Severity:** ERROR when any statistic exceeds by > 10 % (relative); WARNING otherwise
- **Confidence:** 0.7 — impossible for co-located measurements on the same days; different data coverage could explain it
- **Why:** If PM2.5_d <= PM10_d every day, every order statistic and the mean preserve the inequality.
- **Tests:** `backend/tests/unit/test_rules_crossrecord.py` (positive, negative and edge cases)

## STR-LIB-001

**Data-set Library inconsistent with its declared contents** (v1.0, structural)

- **Must hold:** declared numberOfRecords = number of listed members, and every member resolves
- **Applies to:** Library resources listing FHIR members in Library.content (asset collections)
- **Severity:** ERROR
- **Confidence:** 0.9
- **Why:** Researchers select data through these collections; a wrong count or missing member silently changes a study population.
- **Tests:** `backend/tests/unit/test_rules_structural.py` (positive, negative and edge cases)

## STR-PROF-001

**Resource violates its declared OAH profile** (v1.0, structural)

- **Must hold:** cardinality, fixed values and reference targets from the OAH FSH at the pinned commit
- **Applies to:** Resources whose meta.profile names an OAH profile (Observation, Group, Library, Location)
- **Severity:** ERROR
- **Confidence:** 0.9 — constraints hand-transcribed from FSH
- **Why:** The sandbox cannot validate OAH profiles itself (profiles not loaded on the server).
- **Tests:** `backend/tests/unit/test_rules_structural.py` (positive, negative and edge cases)

## STR-REF-001

**Reference does not resolve** (v1.0, structural)

- **Must hold:** every relative reference points to a resource present on the server
- **Applies to:** Relative references to ingested resource types (Observation, Location, Group, Library, Organization, Device, Provenance); Library.content is covered by STR-LIB-001
- **Severity:** ERROR
- **Confidence:** 0.9 (resolution is checked within the ingested snapshot)
- **Why:** A dangling reference silently drops context (site, cohort, device) from any analysis.
- **Tests:** `backend/tests/unit/test_rules_structural.py` (positive, negative and edge cases)

## STR-UNIT-001

**Quantity without a valid UCUM unit code** (v1.0, structural)

- **Must hold:** Quantity.system = UCUM and Quantity.code is a valid UCUM expression
- **Applies to:** Every Quantity with a value (Observation.value and components); one finding per Observation
- **Severity:** ERROR if the code is missing or known-invalid; WARNING if merely unrecognised by our curated table
- **Confidence:** 0.95 for missing/known-invalid; 0.6 for unrecognised (curated table, not a full UCUM parser)
- **Why:** Without a machine-readable unit, a value cannot be compared, converted or range-checked.
- **Tests:** `backend/tests/unit/test_rules_structural.py` (positive, negative and edge cases)

## Comparability dimensions (CMP-*)

CMP-MEASURE, CMP-UNIT, CMP-MEDIUM, CMP-POPULATION, CMP-PERIOD, CMP-AGGREGATION, CMP-METHOD, CMP-INTEGRITY. See docs/COMPARABILITY_SPEC.md.

## Claim guardrail steps (CLM-*)

CLM-CMP-001, CLM-DIR-001, CLM-UNC-001, CLM-TRD-001/002, CLM-INT-001, CLM-THR-001/002/003, CLM-ASC-001, CLM-CAU-001/002. See docs/CLAIM_SAFETY_SPEC.md.
