# 06 — Test plan

## Layers

| Layer | Where | What it proves |
|---|---|---|
| Rule unit tests | `backend/tests/unit/test_rules_*.py` | Each rule fires on a positive case, stays silent on a clean negative, and handles edge cases (rounding, zeros, missing statistics, integer precision, unit conversion) |
| Engine unit tests | `test_comparability.py`, `test_claims.py` | Golden comparability cases; every claim type and verdict path; exact statistics (Mann–Kendall, Theil–Sen, Spearman) |
| Client tests | `test_fhir_client.py` | Read-only guard, host pinning, paging, retry and give-up, raw bodies returned verbatim |
| AI policy tests | `test_ai_policy.py`, `test_llm.py`, `test_anthropic_sdk_contract.py` | Template explanations are deterministic; ungrounded numbers and invented causes or corrections are rejected; no provider means templates; Ollama and OpenAI-compatible request shapes and error handling (mock transports); rules-first claim reading; user-supplied keys (validation, redaction, no echo in 422s, custom URLs off by default, per-request use) and the settings dialog end to end |
| Property tests | `backend/tests/property` | Hypothesis: real samples at any rounding never trigger identity rules; scale injections are always caught; determinism |
| Contract tests | `backend/tests/contract` | Committed JSON Schemas equal the models; real output validates; OperationOutcome validates against the FHIR R4 schema |
| Integration tests | `backend/tests/integration` | Snapshot verifies; anchor reproduces verbatim; lineage row; clean controls stay clean; determinism; trace counts exact and change with data; API endpoints; rendered documents agree with a fresh audit |
| End-to-end | `frontend/tests/demo.spec.ts` | The demo path in a real browser with external network blocked; axe-core WCAG 2.1 AA (light and dark); skip link |
| Evaluation | `scripts/evaluate.py` → docs/EVALUATION.md | Fault injection per rule; benign transformations as a false-positive check |
| Gate 0 | `datadoctor gate0` → docs/GATE0_REPORT.md | Live run, 20 random findings with raw evidence, independent re-derivation, human sign-off |

## Rule policy

Tests before rules: every rule was written after its failing tests (red → green). No rule ships without a negative test on
clean data. Every false positive found later gets a regression test named `..._regression_...` that reproduces the live case.
Three were found and fixed this way: ozone minima near zero, thresholds in parentheses, cross-unit comparison.

## Golden comparability cases

| Case | Expected |
|---|---|
| Benevento women 35–74 vs Oslo 18–29 (obesity vs BMI ≥ 30) | NOT (population), measure CONDITIONAL |
| Same measure, unit, day, device, two sites | DIRECT |
| Conductivity in mS/cm vs µS/cm, same kind of measurement | CONDITIONAL with an explicit ×1000 transformation |
| Clean vs broken annual summaries of the same measure | BLOCKED_BY_INTEGRITY |
| Mean vs median | NOT (aggregation); NOT outranks BLOCKED |
| CVD vs "diabetes, COPD or CVD" | NOT (broader measure) |

## Evaluation protocol

Controls are official records with no record-level finding. For each of 15 fault types up to 20 controls are sampled (seed
20260930), one fault is injected per run, all rules are re-run, and detection means the rule designed for the fault fires on the
modified record. Collateral findings on other controls are counted. Five benign transformations (unit conversion, rounding,
re-ordering, proportional jitter, dropping std-dev) must raise nothing. Wilson 95 % intervals are reported. The report states that
this measures sensitivity to known patterns, not real-world accuracy.

## Running

```bash
python tasks.py test       # backend (pytest with coverage)
python tasks.py e2e        # Playwright (installs Chromium on first run)
python tasks.py lint       # ruff, mypy, tsc
python tasks.py evaluate   # fault injection -> docs/EVALUATION.md
python tasks.py offline    # audit with an unreachable server (snapshot fallback) + e2e
```
