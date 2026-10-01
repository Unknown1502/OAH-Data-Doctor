# Status

Updated 2026-10-01 (release candidate). Rendered numbers are in docs/numbers.json (from the committed snapshot) and
docs/EVALUATION.md; the verification log below records what was run today and what it returned.

## Phases

| Phase | State | Evidence |
|---|---|---|
| Discovery D1–D8 | Done | docs/DISCOVERY.md (requests, timestamps, excerpts) |
| P0 Repo, tooling, Gate 0 | Done, **human sign-off pending** | docs/GATE0_REPORT.md: gate criterion met (123 distinct official resources with ERROR/CRITICAL findings, threshold 10); 20 of 20 samples re-derived from the raw JSON by separate code. Needs a human verdict per sample (≥ 80 % true positives) |
| P1 Ingestion and normalisation | Done | Read-only async client, paging, retry, SQLite cache, verified snapshots, live/snapshot/auto; tests |
| P2 Rules engine | Done | Every rule in docs/04_RULES_CATALOG.md, tests first, positive/negative/edge per rule, property tests |
| P3 Dependency graph and trace | Done | Exact trace for the anchor; counts change when data change (tested) |
| P4 Comparability | Done | Eight dimensions; golden cases pass |
| P5 Claim guardrail | Done | Five claim types; every verdict path tested; evidence ladder computed by the engine |
| P6 Reporting and FHIR export | Done | OperationOutcome valid against the R4 schema and HAPI (docs/VALIDATION.md); JSON, Markdown, HTML, support table |
| P7 UI | Done | Investigation console; every finding opens with its evidence chain (D-029); axe-core WCAG 2.1 AA clean in light and dark |
| P8 Evaluation and hardening | Done | docs/EVALUATION.md; snapshot fallback with banner; logging |
| P9 Docs and submission | Done, needs the owner's final steps | README, docs/SUBMISSION.md, docs/DEMO_SCRIPT.md (rewritten 2026-10-01 against the current screens), 01–07, specs, decisions |

## Verification log, 2026-10-01 (release candidate)

All results below come from runs made on 2026-10-01, the final ones from 13:17 UTC; none is carried over from earlier days.

| Check | Command | Result |
|---|---|---|
| Backend tests | `python tasks.py test` | 259 passed, coverage 91 % |
| Lint and types | `python tasks.py lint` | ruff clean; mypy clean (49 files); TypeScript strict clean |
| Snapshot integrity | `python tools/oah_audit.py verify-snapshot` | `2026-09-30T09-08-55Z`: every file matches its sha256 |
| Production build | `vite build` (in `python tasks.py e2e`) | built; JS 463 kB (138 kB gzip), CSS 50 kB |
| Browser and accessibility | `python tasks.py e2e` | 34 passed, 1 skipped (the phone-drawer test does not apply to the desktop project); axe: no serious or critical violation on any page, light and dark |
| Acceptance, snapshot, model off | `DD_SOURCE=snapshot DD_LLM_PROVIDER=none python tasks.py run` + `python tasks.py acceptance` | 90/90 checks passed |
| Acceptance, live, model off | `DD_SOURCE=live DD_LLM_PROVIDER=none python tasks.py run` + `python tasks.py acceptance` | 91/91 checks passed |
| Responsive and themes | browser sweep of 9 screens at 1440×900, 1280×800, 1024×768, 768×1024, 390×844, dark and light | no console error, no 5xx, no horizontal overflow, theme applied |
| Fresh clone | `git clone` (short path), `python tasks.py setup` (73 s, new virtualenv and npm install), `test`, `lint`, `e2e`, snapshot `run` + `acceptance` | 253 passed, 1 skipped (the 6 Claude SDK contract tests need the optional `ai` extra); lint clean; e2e 34 passed, 1 skipped; acceptance 90/90; demo path walked with no page error |
| Offline | fresh clone, snapshot mode, model off, `DD_FHIR_BASE=http://127.0.0.1:9` (no reachable FHIR server) | acceptance 90/90 |
| Live failure is shown, never hidden | `DD_SOURCE=live` with an unreachable FHIR server | the page keeps the verified snapshot, labelled *Snapshot*, and the stages strip says *Audit failed … Failed: Connecting to the FHIR server* |
| Secrets and junk | regex scan of the whole git history, tracked files and the built bundle | no keys (only the deliberately fake test keys), no `.env`, no personal paths, no logs, caches or build output tracked |
| Sanitized history (dry run) | docs/07, "If permission is denied" | 651 raw-data objects removed, 0 left; recovered with two commands; tests pass again |

**Live audit** (run `run-20261001T132104Z-15fbeb`, source `https://sandbox.hl7europe.eu/oneaquahealth/fhir`, fetched
2026-10-01T13:20:59Z): 561 resources, 450 observations (385 official), 346 findings (125 critical, 212 error, 9 warning), 260 of
385 official records usable as published, 125 of 125 flagged official observations pass the server's own `$validate`.

**Hero record**, read directly at 2026-10-01T13:22:16Z: `Observation/Obs-Almyros-TemperatureWater-2013`, versionId 1,
lastUpdated 2025-11-15T15:39:36.751+00:00. `Observation.component[0..4].valueQuantity`: average 198000, maximum 211000,
minimum 185000, std-dev 18385, median 19.8 (UCUM `Cel`). `GET …/$validate`: information, "No issues detected during
validation". Findings: SEM-STAT-001 (critical; minimum / median = 185,000 / 19.8 = 9,343.4343), SEM-SCALE-001 (average /
median = 198,000 / 19.8 = 10,000, exactly 10⁴), SEM-STAT-003, SEM-RANGE-001. Root cause: unknown.

**Reproducibility**: a fresh snapshot (`2026-10-01T10-56-45Z`, taken into a scratch folder outside the repository, sha256
verified) audited with no language model gives the same 346 findings (same ids, severities, rules and resources), the same
calculation for every finding, the same verdicts for all 17 catalog comparisons and claims, and the same server-validation
summary as the committed snapshot. The live audits and both snapshots agree.

**Without the language model**: with `DD_LLM_PROVIDER=none`, and with Ollama configured but unreachable, the findings,
calculations and verdicts are unchanged; explanations fall back to the template with the reason shown, and claims are read
by the keyword rules (the trend claim is Blocked, the causal claim Unsupported).

## Open items (owner)

1. **Licence of the OneAquaHealth data in the repository: UNVERIFIED** (docs/07_DEMO_AND_SUBMISSION.md, "Open question").
   Do not push until the organisers answer whether sandbox data may be redistributed.
2. Confirm eligibility: the Devpost overview says "Students only"; the latest announcement allows individuals. Student
   status is unresolved (docs/07).
3. Human review of the 20 samples in docs/GATE0_REPORT.md (TRUE POSITIVE, FALSE POSITIVE or UNCERTAIN, with a reason).
4. Time one rehearsal and record the demo video (docs/DEMO_SCRIPT.md, about 4 minutes).
5. After the licence answer: push, add the video link to docs/SUBMISSION.md, submit on Devpost (deadline 2026-10-04 21:00 PDT).

## Risks

| Risk | Mitigation |
|---|---|
| Data licence not confirmed before the deadline | Ask the organisers now; the alternatives are listed in docs/07 (no snapshot in the repository, or a private repository) |
| Sandbox offline during judging (it was offline for a week in September) | Snapshot-first startup and automatic verified fallback with a banner; demo works offline |
| Third parties change sandbox data | Live runs are timestamped and hashed; the committed snapshot reproduces every published number |
| Judges cannot click a hosted demo | Video and repository; no hosted instance (would need the owner's approval) |
| Lighthouse score not measured | axe-core (the engine behind Lighthouse's accessibility audits) runs in CI with zero serious or critical violations |
| Hand-transcribed OAH profile constraints | Sources cited per profile; re-derive when the IG is republished |

## Decisions

See docs/DECISIONS.md (D-001 … D-030).
