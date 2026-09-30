# Devpost submission: OAH Data Doctor

> Numbers in this file are rendered by `scripts/render_docs.py` from snapshot `2026-09-30T09-08-55Z`. Before submitting, add the
> public repository URL and the video link, and confirm the Gate 0 human sign-off in docs/GATE0_REPORT.md.

**Tagline:** FHIR tells you whether data is shaped correctly. Data Doctor tells you whether it makes scientific sense, and what you can safely conclude from it.

**Track:** 7, Digital Health Standards.

**Track alignment statement.** Track 7 asks for interoperability through FHIR models and integration frameworks.
Interoperable data is only useful if it is also *trustworthy*. Data Doctor sits on the OneAquaHealth FHIR sandbox and adds the
layer that conformance validation cannot provide: it checks that published values can be true, traces what an inconsistent record
would contaminate, decides whether two indicators can be compared, and guards the claims researchers make. It returns its results
as standard FHIR `OperationOutcome` resources with FHIRPath pointers, validated against R4.

## Inspiration

We opened the anchor record of the OneAquaHealth sandbox: the 2013 water temperature of the Almyros stream in Crete. It reports an
annual mean of 198,000 °C next to a median of 19.8 °C, and the server's own FHIR validator says
"No issues detected". Nothing in FHIR conformance can notice that a median cannot lie outside its own minimum and maximum, or
that liquid water cannot be 198,000 °C. One Health research joins environmental and health data from different cities and
laboratories, and one silent scale error can turn into a published trend, a wrong comparison or a false causal claim.

## What it does

- **Doctor.** 20 deterministic rules find structural, statistical and domain problems, each with the exact FHIRPath,
  observed values, the constraint broken, confidence and provenance. The sandbox's own validator accepted all 385
  official observations we sent it. Data Doctor flags 125 of 385 as unsafe to use as published, and
  125 of those passed the server's validation.
- **Trace.** Shows exactly which data sets, annual series, comparisons and claims consume a flagged record. It never estimates.
- **Compare.** Eight dimensions (measure, unit, medium, population, period, aggregation, method, integrity) lead to a verdict of
  direct, conditional, not comparable, or blocked by integrity, with alternatives computed from records that exist.
- **Claim guardrail.** Type a claim in plain words. It is parsed into a structured claim that is shown back to you, then
  judged by rules: supported, conditional, unsupported or blocked, with the reasons and the wording that *is* safe to use.
- **Reports.** JSON findings, a FHIR OperationOutcome bundle, a researcher report (Markdown/HTML) and a "what this data can and
  cannot support" table.

What it found, all computed and all "cause unknown": 346 findings (125 critical, 212 error,
9 warning). Among them: 100 records with a median outside [min, max]; 101 records whose mean
and median differ by at least 100× (62 of them by an exact power of ten); 24 physically impossible values; 4
site-years where PM2.5 exceeds PM10; health indicators defined "per 100,000 inhabitants" but published in %; and
12 monitoring sites sharing one coordinate. The anchor's values also appear in the IG's source spreadsheet,
so the problem predates FHIR conversion.

## How we built it

Python 3.11 with FastAPI and Pydantic, and a read-only async FHIR client (paging, retries, SQLite cache, sha256-verified snapshots).
Knowledge is derived reproducibly from the OAH IG source at a pinned commit: example ids, CodeSystem definitions and profile
constraints. Rules are pure functions in a registry, with precision-aware tolerances. The comparability engine and claim guardrail
use exact small-sample statistics (Mann–Kendall permutation test, Theil–Sen slope, Spearman). A dependency graph drives the
impact trace. The React and TypeScript console (Vite, Tailwind) has a log-scale "magnitude ruler" that makes scale errors visible
at a glance. An optional language model, free and local through Ollama by default (or any OpenAI-compatible endpoint, or Claude), only
rephrases computed findings: any number, cause or correction it adds is detected and the text is discarded.

## Challenges we ran into

- The sandbox's DNS record disappeared for about a week during the hackathon. We built live/snapshot handling with verified
  fallback, and every screen says which one you are looking at.
- The IG website was offline and the server hosts no profiles, so `$validate` cannot check OAH profiles. We derived the checkable
  constraints from the IG's FSH source at a pinned commit.
- Rounding. Published values are rounded, and naive checks raise false alarms. Every comparison allows half a unit in the last
  published decimal, and property-based tests prove that no real sample can trigger an identity rule.
- Our own false positives. Pre-review of live findings caught two rule defects (ozone minima near zero; thresholds in
  parentheses stripped from definitions), and the fault-injection evaluation caught a third (comparisons across units). All three
  were fixed with regression tests before submission.

## Accomplishments that we're proud of

- 271 of 271 injected faults detected (95 % CI 98.6–100.0 %), and 0 new findings on
  100 records after benign transformations. We say plainly that this measures rule sensitivity, not real-world accuracy.
- 249 backend tests and 29 end-to-end tests, including offline runs and WCAG 2.1 AA accessibility checks.
- Our FHIR output validates against R4 (0 schema errors; HAPI: no issues).
- Honesty by construction: no hand-typed numbers (these documents are rendered from a run), root cause always "unknown",
  read-only access, and live and snapshot data always labelled.

## What we learned

A validator answers "is this well-formed?"; researchers need "can this be true, and what can I say?". Small, provable checks
(order statistics, subset relations, partitions) find more real problems than large generic rule sets. Showing *where* a value
first appears (lineage) is far more useful to a data owner than guessing *why* it is wrong.

## What's next

- Run Data Doctor as a `$validate`-style FHIR operation, so any OAH server can return scientific findings next to conformance issues.
- Load the OAH profiles into a full FHIR validator once the IG is republished.
- Publish uncertainty (n, confidence intervals, data coverage) in OAH Observations, so claims between cohorts can be tested.
- Work with the data owners on the Almyros chemistry summaries and the Benevento site coordinates.

## Built with

python, fastapi, pydantic, httpx, sqlite, hl7-fhir-r4, fhirpath, hypothesis, pytest, react, typescript, vite, tailwindcss,
playwright, axe-core, ollama (optional), claude (optional)

## AI disclosure

We used Claude (Anthropic) as an AI coding assistant for code, tests and documentation, under human direction. The product
uses no AI to detect problems or decide verdicts.

## Links

- Repository: (add the public GitHub URL)
- Demo video: (add the link; script in docs/DEMO_SCRIPT.md)
