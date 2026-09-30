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

**D-016 LLM default off; model `claude-opus-5` when on.** The product must work without an LLM. When enabled, the current default
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
