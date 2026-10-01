# Devpost submission: OAH Data Doctor

> Numbers in this file are rendered by `scripts/render_docs.py` from snapshot `2026-09-30T09-08-55Z`. Before submitting, add the
> public repository URL and the video link, and confirm the Gate 0 human sign-off in docs/GATE0_REPORT.md.

**Tagline:** FHIR tells you whether data is shaped correctly. Data Doctor tells you whether it makes scientific sense, and what you can safely conclude from it.

**Track:** 7, Digital Health Standards.

**Track alignment statement.** Track 7, Digital Health Standards, asks participants to "enable interoperability across
systems" against "fragmented data and lack of standards", with "FHIR models, AI agents, and integration frameworks".
Interoperable data is only useful if it is also *trustworthy*: FHIR-conformant records can still carry scientifically
inconsistent evidence that flows into downstream analysis. Data Doctor is an **evidence-integrity layer above FHIR** on the
OneAquaHealth FHIR sandbox. It does not replace FHIR validation; it adds what conformance cannot check: whether published values
can be true, what an inconsistent record would affect, whether two indicators can be compared, and which research claims the
evidence supports. Results come back as standard FHIR `OperationOutcome` resources with FHIRPath pointers, validated against R4.
**The core audit is deterministic; AI is an optional explanation layer** that never decides a finding or a verdict.

## Project description

### The problem

OneAquaHealth publishes water, air and population-health indicators from urban streams and cities (Almyros and Giofyros in
Crete, Benevento in Italy, Nordre Aker in Oslo) as HL7 FHIR, so researchers can study environmental and human health together:
the One Health idea. But FHIR validation only checks that a record has the right *shape*. It cannot tell that a water
temperature of 198,000 °C is impossible, or that a median of 19.8 °C cannot sit below a minimum of
185,000 °C. On the OneAquaHealth sandbox, 125 records that cannot be right as published all pass the
server's own validator. Errors like these flow silently into trends, cross-city comparisons and published claims.

### Our solution

OAH Data Doctor is a read-only scientific integrity layer on top of FHIR. It reads the OneAquaHealth FHIR server (or any FHIR R4
server, or a file you bring) and answers four questions:

1. **Can this value be true?** 20 deterministic rules check physics, statistics and definitions, and point to the exact
   field (FHIRPath), the published values and the constraint they break.
2. **What would it contaminate?** An impact trace lists the data sets, series, comparisons and claims that use a flagged record.
3. **Can these two numbers be compared?** Eight dimensions (measure, unit, medium, population, period, aggregation, method,
   integrity) give a verdict: direct, conditional, not comparable, or blocked by broken records.
4. **Can I say this?** A claim guardrail judges a researcher's sentence against the data and offers wording the data supports.

Results come back as standard FHIR `OperationOutcome` resources, so existing FHIR tools can use them. No AI decides any finding or
verdict, nothing is ever changed on the server, and the root cause of a problem is never guessed.

### Target users

- **Data stewards and publishers of OneAquaHealth data**, the partners who load monitoring results into FHIR. They get a
  prioritised list of records to review, with the exact field and, where the source file is known, the line where the value
  first appears.
- **One Health researchers and public-health analysts** who combine stream, air and health indicators across cities. They learn
  which records they can use, which comparisons are valid and which claims the data supports, before they publish.
- **FHIR integrators and implementers** (Track 7). They can add a scientific check to a data pipeline (the `check` command exits
  with an error status when it finds an error or a critical problem) or point Data Doctor at another FHIR server.
- **Teams preparing data for the platform**, including monitoring and citizen-science programmes. They can paste or drop a file
  in the browser and see its problems before it is shared; nothing is stored.

### Expected impact

Measured on the OneAquaHealth sandbox (snapshot `2026-09-30T09-08-55Z`):

- 125 of 385 official records are not safe to use as published, and 125 of them pass
  the FHIR server's own validation. 260 can be used as published.
- 346 findings (125 critical), each with the field and values a data owner needs to correct the record.
- In a fault-injection test the rules caught 271 of 271 planted errors, and raised 0 new
  findings on 100 records after harmless changes.

What we expect once it is used (expectations, not measured outcomes):

- **It identifies evidence that may be unsafe for downstream scientific use**, before that evidence reaches an analysis, a
  dashboard or a decision about urban waters.
- **It makes scientific consistency problems inspectable and reproducible**, so data owners get a precise review list and can
  correct problems at the source.
- **It helps researchers determine which comparisons and claims the available evidence supports**, checked against the data's
  real limits (population, period, method, integrity) instead of being taken on trust.
- **It is a reusable building block for the standard**: because the output is FHIR, the same checks could run as a
  `$validate`-style operation on any OneAquaHealth server.

It does not make all OneAquaHealth data trustworthy or guarantee scientific correctness: it shows which published evidence fails
which check, and what can still be concluded.

## Alignment with the OneAquaHealth mission

OneAquaHealth works for healthy waters, healthy ecosystems and healthy communities by combining technology, citizen science and
the One Health approach for urban freshwater ecosystems, and the hackathon asks participants to use AI, data platforms and digital
health standards "to improve the accuracy, reliability, and interoperability of ecosystem data". Data Doctor addresses the
reliability part directly: data integrity, then reliable indicators, then reliable cross-site comparisons, then responsible
research claims, and so better evidence for environmental and One Health decisions. It checks the water, air and health indicators
the project publishes, shows which conclusions about streams and communities the data can support, and makes a single scale error
visible before it can turn into a false trend or a false link between water quality and health. It is built on the project's own FHIR Implementation Guide (knowledge derived from the IG source at a
pinned commit) and its sandbox, and it returns results in FHIR, so it strengthens the standards-based infrastructure the project
is building rather than replacing it.

## Feasibility and scalability

- **Runs today.** Two commands set it up and run it on a laptop (`python tasks.py setup`, `python tasks.py run`). A full audit of the sandbox snapshot (561 resources)
  takes about two seconds; a live audit adds the time to read the server. A sha256-verified snapshot lets it work offline.
- **Any FHIR server.** One setting (`DD_FHIR_BASE`) points it at another FHIR R4 server, read-only (GET and `$validate` only).
  Statistical and structural rules apply to any data; physical-range rules use an indicator registry
  (`knowledge/indicators/registry.yaml`) that can be extended.
- **Fits into pipelines.** `python tools/oah_audit.py check data.ndjson` exits with status 1 on an error, so it can stop bad data
  before publication. Reports come as JSON, Markdown/HTML and a FHIR OperationOutcome bundle.
- **Cheap to run.** Deterministic rules and no paid service. The optional language model only rewords explanations; it is free
  and local through Ollama, or simply off.
- **Grows rule by rule.** Each rule is a small, versioned function with its own tests, and is checked by the fault-injection
  evaluation.
- **Next steps that reuse the same engine:** more FHIR resource types and data sets, scheduled audits, and integration into
  research and data pipelines; none of this is built yet.
- **Known limits.** The findings page loads every finding at once, which is fine for hundreds but would need paging for very large
  servers. OAH profile checks are transcribed from the IG source, because the sandbox hosts no profiles.

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
- 259 backend tests and 35 end-to-end tests, including offline runs and WCAG 2.1 AA accessibility checks.
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

- Repository: https://github.com/Unknown1502/OAH-Data-Doctor
- Demo video: (add the link; script in docs/DEMO_SCRIPT.md)
