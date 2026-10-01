# Decisions

Format: context, options, choice, consequence.

**D-001 Repository location and package name.** The workspace held only the brief. Options: build in the workspace root, or in a
clean subfolder. Choice: `oah-data-doctor/` as its own git repository, Python package `datadoctor` (not `app`, to avoid a
generic import name). Consequence: the planning files (`prompt.md`, `build.md`) stay outside the public repository.

**D-002 Missing brief documents.** The master prompt referenced docs 01–07 and a seed script that were not supplied. Choice:
author them from the master prompt and from discovery, and mark this in 01. Consequence: rule IDs and behaviour are defined by
us. The prompt's expectation that the anchor would fire "SEM-STAT-001..004" was not forced: the rules fire what mathematics
proves (the SD bound, STAT-004, is attained exactly by n = 2 and correctly does not fire).

**D-003 `tools/oah_audit.py`.** Written as the runnable CLI entry (adds `backend/` to `sys.path`, delegates to `datadoctor.cli`).

**D-004 Proceed past Gate 0 before human sign-off.** Context: the user asked for an autonomous, complete build against a hard
deadline; the gate requires a human to review 20 samples. Evidence at the time: 123 distinct official resources with
ERROR/CRITICAL findings (threshold ≥ 10), and 20/20 sampled findings independently re-derived from raw JSON. Choice: continue
building, with the human sign-off left explicitly open in docs/GATE0_REPORT.md and flagged in STATUS. Consequence: the
submission checklist requires the sign-off.

**D-005 Scope by IG example ids.** Third-party projects wrote resources (some claiming OAH profiles) to the shared sandbox.
Choice: an official record is one whose id is an Instance in the IG's FSH at the pinned commit. Findings carry `scope`.

**D-006 Knowledge from the IG source, not the IG website.** The website returned 404 and the server hosts no profiles.
Choice: `scripts/build_knowledge.py` derives instance ids, CodeSystem concepts and the upstream CSV from GitHub at commit
`b907cf0869b5`, recording sha256 of every input. Profile constraints are transcribed by hand from FSH, with file references.

**D-007 Precision-aware tolerance.** Rounded published values raise false alarms if compared exactly. Choice: allow half a unit in
the last published decimal; an exact zero uses the record's finest precision (JSON drops trailing zeros); non-zero integers keep
±0.5 (conservative). Validated by property tests.

**D-008 SEM-SCALE-001 v1.1 (after Gate 0 pre-review).** v1.0 compared all four location statistics and flagged normal ozone
minima near zero. Choice: compare mean and median only; use min and max only to say which central value sits with the record.

**D-009 OperationOutcome coding system.** No canonical URL exists for our rules. Choice: a placeholder canonical
(`https://github.com/oah-data-doctor/oah-data-doctor/rules`), documented, to be replaced by the published repository URL.

**D-010 Verdict precedence NOT > BLOCKED_BY_INTEGRITY.** If two values could never be compared, repairing the data would not
change that. Reporting NOT first prevents a misleading "fix the data and you can compare".

**D-011 Association minimum of 8 paired units.** Below 8 an exact rank test has too few permutations to be informative. Chosen
conservatively; with the OAH data (3 sites) every association claim is UNSUPPORTED, which matches the data's actual power.

**D-012 Threshold claims ignore location-level warnings.** A shared-coordinate warning is relevant to spatial comparisons, not to
whether one value exceeds a limit. Comparisons still consider location findings.

**D-013 Cross-record rules convert units (SEM-XREC-001 and SEM-TEMP-001 v1.1).** Found by the fault-injection evaluation (benign
µg/m³ → mg/m³ conversion raised false positives). Values are converted to the canonical unit via the explicit table, and pairs that
cannot be converted are never compared.

**D-014 Port 8321.** Port 8000 was occupied on the development machine; 8321 avoids common collisions.

**D-015 No HL7 Java validator.** Java is not available in the build environment. Base R4 validity of our output is checked with the
official R4 JSON schema (CI) and the sandbox's HAPI `$validate`; OAH profile checks run locally (STR-PROF-001).

**D-016 LLM default off; model `claude-opus-5` when on (superseded in part by D-022).** The product must work without an LLM. When enabled, the current default
model is used with low effort; grounding checks make model quality non-critical for correctness. Server-side refusal fallbacks
are not configured because any refusal already falls back to the deterministic template.

**D-017 Snapshot-first startup.** The API loads the latest verified snapshot at startup (instant, offline-safe, labelled
Snapshot) and refreshes from live in the background. This keeps the demo robust against the sandbox's instability.

**D-018 Readouts in the UI face, code in mono.** A monospace face spaced decimal points and thousands separators awkwardly. Numeric
readouts use Bricolage Grotesque at 82 % width with tabular figures; Azeret Mono is reserved for identifiers (FHIRPath, ids, hashes).

**D-019 Snapshots as NDJSON (format 2).** The fresh-clone test failed on Windows: per-resource file names built from long ids
exceeded the 260-character path limit in deep folders. Choice: one NDJSON file per resource type (the FHIR Bulk Data format),
one canonical resource per line. The existing snapshot was repacked with `repack_snapshot`, which verifies the old snapshot,
writes the new one, and aborts unless every resource's canonical sha256 and every validation outcome is unchanged. The manifest
records the previous manifest hash under `repacked`.

**D-020 Live runs fetch the server's own verdict for flagged records.** Verification with live data showed that server
`$validate` outcomes existed only in snapshots, so on live data the UI could not show "the server calls this valid". Choice: after a
live audit, ask `$validate` (GET, read-only) about every flagged official observation, 4 in flight at most, spaced by the polite
delay, cached for 15 minutes (about 40 s for a full live audit, a few seconds when cached). Failure never breaks the audit.

**D-021 Support table keeps consolidated collections unless they are fully duplicated.** Verification of the rendered report
showed the "can / cannot support" table had no "do not use" row: skipping every `*-All` / `*FullResults` library had dropped the
Almyros lab chemistry (only in `Library-Almyros-FullResults`) and all of Oslo (only in `Library-Oslo-All`). A (library, indicator)
row is now dropped only when smaller collections already contain all of its records.

**D-022 Free language models first; rules before the model.** A paid API should not be needed to try the optional features.
`ai/llm.py` now supports a free local model through Ollama (default `qwen2.5:3b`), any OpenAI-compatible endpoint (free hosted
tiers) and Claude, behind one interface. Tried on 2026-09-30 with `qwen2.5:3b` on the snapshot, the small model misread
"Almyros water got warmer between 2013 and 2020" as a two-place comparison and added "correction needed" to one rephrasing.
Three changes follow. The claim reader is now rules-first (the model only fills fields the keyword rules left empty), and the
rules gained the comparative-trend, "makes ... sick" and "fine particles" patterns. Rephrasings that state a cause or correction
absent from the finding are discarded, like ungrounded numbers; a hedged cause ("could be due to") is tolerated only when the finding lists unverified hypotheses, because rejecting it made the rephrasing unusable on exactly the findings that have one. The model is kept loaded for 30 minutes between calls
(`keep_alive`) because a cold start took about 45 s. The verdict path is unchanged: no model output reaches it without passing
the resolver.

**D-023 Users can bring their own model key, kept in their browser.** Setting a key in the server's `.env` excludes
everyone who uses a hosted instance, such as judges. A "Language model" dialog now lets any user pick a provider preset and
paste their own key, with a connection test that lists the models the key can use. The key is kept in the browser (tab
only unless the user chooses to remember it) and travels in the body of that user's own requests; the server uses it for
the one call, never stores or logs it, and redacts it from provider errors. FastAPI's default 422 body echoes submitted
values, so validation errors now report only location and reason. Users choose providers, not URLs, to rule out
server-side request forgery on a hosted instance; free-form endpoints need `DD_LLM_ALLOW_CUSTOM_URL=true`.

**D-024 A what-if lab on real records, and the server asked about the same numbers.** Judges and users did not see the point
from static screens. The home page now lets anyone edit the anchor record's statistics; the rules re-run on a copy (the
published data and the audit are never changed) and a checklist shows each rule pass or fail. "Ask the real FHIR server" POSTs
the edited copy to `Observation/$validate`, which validates and stores nothing, at most once every 2 s whoever asks. The copy's
`meta.profile` is removed first: the sandbox holds no StructureDefinitions (DISCOVERY D1), so the declared OAH profile would
only produce "profile not found" errors unrelated to the numbers; without it the server validates against base R4, as its own
instance check does. It accepted a mean of 999,999,999 °C, a median of −500 °C and a standard deviation of −5 (DISCOVERY D3).
Trying the lab exposed two faults of our own, both fixed with tests: no rule caught a negative standard deviation (new
SEM-STAT-006, CRITICAL; a new fault type in the evaluation), and large numbers were printed in scientific notation in eight
published finding summaries ("differ by 1.67633e+06"; now "1,676,332.35").

**D-025 Users can check their own data.** Data Doctor was only useful for the one sandbox. `POST /api/check`, the *Check your
data* page and `datadoctor check <file>` accept a FHIR resource, a Bundle, a JSON array or NDJSON (at most 5 MB and 2,000
resources; other resource types are skipped with a note). The records join the published dataset for one request, so references
resolve and series rules compare them with the published years; an uploaded id equal to a published one replaces that record for
this check only, and an unchanged copy is labelled as such. Findings are reported for the uploaded records only, nothing is
stored, and the CLI exits with status 1 on an ERROR or CRITICAL finding so it can gate a data pipeline.

**D-026 Show the data itself, exactly as published.** Findings alone left people asking whether the data was real. *The
data* page lists the source (server, live or verified snapshot, fetch time, checksum, third-party resources counted but
never judged), the monitoring places, series over time and every official record, each with a link to the same record on the
FHIR server. Values are shown with every published decimal (no rounding, no unit conversion): `exact()` in the UI, `stats` as
published in `/api/observations`. Annual summaries and single measurements of the same measure are never drawn as one series;
a point's colour is its record's most severe finding, which the chart says, because a plausible median can sit on a record
with an impossible mean. When the physically possible band is too thin to draw at the chart's scale, the caption says so.

**D-027 The frontend as one investigation, and what it will not fake.** Following the frontend brief, the console now reads
as one investigation: what was scanned and found, the top finding, its evidence, what it would contaminate, whether it can be
compared, what may be claimed, the report. Changes: IBM Plex Sans for prose and IBM Plex Mono for IDs, FHIRPaths and numeric
evidence; dark by default (light and system remain); grouped navigation, a phone bottom bar and Ctrl+K search over what the
audit actually read and found; the top bar states live or snapshot, "fetched N min ago" or "sha256 verified", with Retry live
and Continue with the snapshot when the live source fails. The finding page opens with what is wrong (observed values), why
(the broken constraint and factor) and "Root cause: unknown", then the evidence with its provenance (resource, rule, source,
retrieval time), and a side drawer with the record exactly as served, the flagged fields highlighted from the finding's
FHIRPaths. Audits report their real stages (connecting, each resource type with its count, the rules, the server's
$validate, the analyses) from the backend; no percentages or timers. The claim guardrail adds an evidence ladder
(Observation, Description, Comparison, Association, Causation) computed by the engine from the verdict
(`claims/ladder.py`), not in the browser, and a checklist of what was understood and how each dimension held up. Comparison
rows open to show what A and B published for that dimension; alternatives are marked supported, needing a transformation,
or not valid. Trace nodes are buttons: selecting one highlights its path and lists what it depends on and what uses it.
Not done, on purpose: no single "data health %" (there is no verified score; the real "260 of 385 official records usable as
published" is shown instead); no "reviewed/unreviewed" filter (the system has no review state); only JSON for raw resources
(the server is read as JSON; no Turtle or XML is fetched); no zoom or pan for the trace (it has a handful of nodes; it scrolls
and is keyboard operable); PDF is the browser's print-to-PDF with a print stylesheet (no server-side PDF renderer).

**D-028 One visual system, defined once.** The frontend refinement brief asked for a calmer, more coherent console, not a
new concept. Every colour, radius, spacing step, shadow, transition and layer is now a token in `frontend/src/styles.css`
(`--color-bg`, `--color-sidebar`, `--color-surface`, `--color-surface-elevated`, `--color-border`, `--color-border-subtle`,
`--color-text-primary|secondary|muted`, `--color-accent`, `--color-accent-muted`, `--color-success`, `--color-warning`,
`--color-error`, `--color-critical`, `--color-critical-surface`, `--color-info`, `--radius-sm|md|lg`, `--space-1..8`,
`--shadow-overlay`, `--transition-fast|drawer`, `--z-sticky|nav|overlay`), each with dark and light values; the older
utility names (`bg-chalk`, `text-ink`, `text-cinnabar`, ...) are aliases of them, so no component holds a colour. Dark uses the
brief's palette exactly, with one change: muted text is #7A9298 instead of #6F898F, because #6F898F measures 4.38:1 on the
surface colour and 4.09:1 on the elevated surface, below WCAG AA; #7A9298 is at least 4.63:1 on every dark surface. Meaning, not decoration: cyan marks
interaction and selection only; coral marks contradiction and impossible evidence only (on Data health, only the impossible
value in the headline and the "flagged, yet server-valid" metric are coral). The sidebar has strong uppercase group labels
(12.5 px, weight 700, 0.1em tracking, secondary text) over 14.7 px items with 17 px Lucide icons, a restrained active state,
and a utility footer: source status, the independence note, the language-model control (moved out of the top bar, which now
holds only the live/snapshot status, Search and Scan) and an icon-only theme control (Dark, Light, System; remembered). On a
phone the sidebar is a drawer and the bottom bar stays. New primitives in `components/ui.tsx`: SeverityBadge ("STATISTICAL ·
CRITICAL", with a shape so it never relies on colour), SectionLabel, Metric, PageHeader, EmptyState. Findings is an
investigation queue with category, rule, place, indicator and record filters (place and indicator come from the observations
the audit read). The finding page reads What is wrong, Evidence, Why it matters, Safe conclusion (derived from severity, the
same rule the support table uses), Suggested action, What this affects. The report is an "Evidence integrity report" in nine
numbered sections, with provenance and every rule applied. Not done, on purpose: comparability has no "Unknown" state, because
the engine has none (an undocumented method is Conditional, with the reason given; a dimension that does not apply, such as
population for water data, is "Not applicable"); Findings has no live/snapshot filter, because one audit is one or the other
and the page states which; rows carry no per-finding timestamp or review status, because the system records neither (the
audit time is shown once).


**D-029 Every finding proves itself.** The finding page opens with a six-step evidence chain: observed values, the
calculation, its result, the rule broken (what must hold, and the same constraint with the published numbers in it),
the conclusion, and the root cause (always "unknown", with any hypothesis marked "not verified"). The arithmetic is written
out by `backend/datadoctor/audit/calculation.py` from the finding's own evidence, and only from it. Every shown result is a
measure the rule already computed, every operand is a published value or another measure, and numbers show every digit the
rule kept (198,000 − 19.8 = 197,980.2, not a rounded 197,980). It changes no rule, verdict or finding id, and it adds no
logic: rules that do no arithmetic (units, references, profiles, definitions, series breaks) show no calculation step.
"Exactly 10⁴" is said only when the ratio is 10^k; the rules' power-of-ten signature (within about 4.7 %) is shown as
"within 5 % of 10⁴". Tests check that every result equals its measure, that redoing each step's arithmetic from its
operands gives the shown result, and that no calculation names a cause or a corrected value
(`tests/integration/test_calculation.py`, `test_api.py`, and a browser test comparing the screen to the API).

**D-030 Release-candidate fixes (no rule, verdict or finding changed).** (1) The two verdict panels state their verdict in one
word first: the FHIR server's "Pass" (no error issues from `$validate`; "Fail" or "Not checked" otherwise) and Data Doctor's
worst severity ("Critical"). The Data Doctor panel was always coral; it now takes the colour of the worst finding, so coral keeps
meaning "critical". (2) Each comparability dimension shows its kind of problem (hard blocker, transformable, contextual, blocked
until reviewed), restating the engine's own semantics (docs/COMPARABILITY_SPEC.md, "Kinds of problem"); there is no "unknown"
state because the engine has none. (3) An audit with zero findings says "Audit complete — no findings" instead of the empty-filter
message. (4) The Gate 0 form offers TRUE POSITIVE, FALSE POSITIVE or UNCERTAIN with a reason and a reviewer per sample (an
uncertain verdict does not count towards the 80 % threshold); a test checks that no verdict is ever pre-filled.

