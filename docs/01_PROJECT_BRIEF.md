# 01 — Project brief

> The master build prompt referred to a package of documents (01–07) and a seed script that were not supplied with the brief.
> These documents were written during the build from the master prompt and from what discovery established on the live
> sandbox (docs/DISCOVERY.md). Where a fact could not be verified it is marked UNVERIFIED. This file wins on facts.

## Context

- **OneAquaHealth (OAH)** is an EU Horizon Europe project on the health of urban freshwater ecosystems and the people who live
  around them (One Health). Pilot sites used in the FHIR sandbox: the Almyros and Giofyros streams (Crete), Benevento (Italy)
  and Nordre Aker (Oslo).
- **HL7 Europe** publishes the OAH FHIR Implementation Guide (`hl7.eu.fhir.oah`, FHIR R4, version 0.1.0-ci-build) and runs a
  HAPI FHIR 8.2.0 sandbox at `https://sandbox.hl7europe.eu/oneaquahealth/fhir` with example data: annual water-chemistry
  summaries, field probe measurements, air-quality summaries and cohort-level health prevalence.
- **IEEE OneAquaHealth Global Hackathon 2026** (Devpost). Seven tracks; this project targets Track 7, *Digital Health Standards*
  ("FHIR models, AI agents, and integration frameworks"). Judging: impact and mission alignment 30 %, innovation 20 %, technical
  implementation 20 %, usability 15 %, feasibility and scalability 15 %. Submission deadline 2026-10-04 21:00 PDT.

## Problem

FHIR conformance checks that data has the right *shape*. It cannot check that values can be *true*: that a median lies within
its own minimum and maximum, that liquid water is below 100 °C, that PM2.5 does not exceed PM10, that a pooled prevalence lies
between its subgroups, or that two indicators describe the same population. One Health research joins environmental and health
data from different laboratories, cities and definitions. A silent inconsistency becomes a trend, a comparison or a claim. On the
OAH sandbox the server's own `$validate` accepts a water temperature of 198,000 °C.

## Users and jobs

| User | Job | What Data Doctor gives them |
|---|---|---|
| Researcher | "Can I use these numbers, and what can I say?" | Findings, comparability verdicts, claim verdicts with safe wording |
| Data steward / data owner | "What is wrong in what we published, exactly where?" | Findings with FHIRPath, evidence, lineage to the source file, OperationOutcome export |
| Standards community (HL7 / IG authors) | "What should the IG constrain better?" | Definition/unit contradictions, synonym divergence, unit-code problems |
| Hackathon judges | "Does it work on the real data, honestly?" | Live/snapshot runs, computed numbers, evaluation, tests |

## Scope

In scope: read-only auditing of the OAH sandbox (Observation, Location, Group, Library, Organization, Device, Provenance);
deterministic rules; impact trace; comparability; claim guardrail; reports including FHIR OperationOutcome; web UI; offline snapshots.

Out of scope: correcting data (never done), writing to the sandbox (never done), generic validation of all of FHIR, causal
inference, statistical modelling beyond small exact tests, user accounts.

## Success criteria

- Real findings on real data, each with evidence, verified by independent re-derivation and human review (Gate 0).
- The anchor record reproduced verbatim from the live sandbox.
- Trace, compare and claim guardrail working end-to-end in the UI.
- Every number in the UI, README and submission computed from a run.
- Works offline from a verified snapshot; live mode shows its fetch time.

## Principles

1. Honesty over impressiveness. 2. Root cause unknown unless proven. 3. Never modify source data. 4. Deterministic core.
5. Evidence with every finding. 6. Label live vs snapshot everywhere. 7. Tests before rules. 8. No secrets.
9. Attribution and scope. 10. Disclose AI assistance. 11. Do not overclaim.
