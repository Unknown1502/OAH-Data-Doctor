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
