# Status

Updated 2026-09-30. Numbers are in docs/numbers.json (rendered from the snapshot) and docs/EVALUATION.md.

## Phases

| Phase | State | Evidence |
|---|---|---|
| Discovery D1–D8 | Done | docs/DISCOVERY.md (requests, timestamps, excerpts) |
| P0 Repo, tooling, Gate 0 | Done, **human sign-off pending** | docs/GATE0_REPORT.md: 123 distinct official resources with ERROR/CRITICAL findings (threshold 10); 20/20 samples independently re-derived. Needs a human verdict per sample (≥ 80 % true positives) |
| P1 Ingestion and normalisation | Done | Read-only async client, paging, retry, SQLite cache, verified snapshots, live/snapshot/auto; tests |
| P2 Rules engine | Done | 19 rules, tests first, positive/negative/edge per rule, property tests; anchor fires SEM-STAT-001, SEM-STAT-003, SEM-SCALE-001, SEM-RANGE-001 |
| P3 Dependency graph and trace | Done | Exact trace for the anchor; counts change when data change (tested) |
| P4 Comparability | Done | Eight dimensions; golden cases pass |
| P5 Claim guardrail | Done | Five claim types; every verdict path tested; reasons, trace, blocking findings, safe wording |
| P6 Reporting and FHIR export | Done | OperationOutcome valid against the R4 schema and HAPI (docs/VALIDATION.md); JSON, Markdown, HTML, support table |
| P7 UI | Done | Seven screens; Playwright demo path offline; axe-core WCAG 2.1 AA clean in light and dark |
| P8 Evaluation and hardening | Done | docs/EVALUATION.md; snapshot fallback with banner; logging |
| P9 Docs and submission | Done, needs the owner's final steps | README, docs/SUBMISSION.md, docs/DEMO_SCRIPT.md, 01–07, specs, decisions |

## Test status

Backend: all tests pass (`python tasks.py test`), ruff and mypy clean. UI: all Playwright tests pass (`python tasks.py e2e`),
TypeScript strict mode clean.

## Open items (owner)

1. Human review and sign-off of the 20 samples in docs/GATE0_REPORT.md.
2. Record the demo video (docs/DEMO_SCRIPT.md).
3. Push to a public repository and fill the links in docs/SUBMISSION.md.
4. Optionally take a fresh snapshot on submission day (`python tasks.py snapshot`, then `python scripts/render_docs.py`).

## Risks

| Risk | Mitigation |
|---|---|
| Sandbox offline during judging (it was offline for a week in September) | Snapshot-first startup and automatic verified fallback with a banner; demo works offline |
| Third parties change sandbox data | Live runs are timestamped and hashed; the committed snapshot reproduces every published number |
| Lighthouse score not measured | axe-core (the engine behind Lighthouse's accessibility audits) runs in CI with zero serious or critical violations; a Lighthouse run was not performed |
| Hand-transcribed OAH profile constraints | Sources cited per profile; re-derive when the IG is republished |

## Decisions

See docs/DECISIONS.md (D-001 … D-018).
