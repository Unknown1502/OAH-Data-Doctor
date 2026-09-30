# 05 — Data and schemas

This file wins on schemas. Machine-readable JSON Schemas are in `schemas/`, generated from the Pydantic models by
`scripts/export_schemas.py`; `backend/tests/contract` fails if they drift.

## Finding (`schemas/finding.schema.json`)

| Field | Meaning |
|---|---|
| `id` | `F-<rule>-<sha256(rule, resource, discriminator)[:12]>`: deterministic, stable across runs on the same data |
| `rule_id`, `rule_version`, `title`, `category` | STRUCTURAL, STATISTICAL, SEMANTIC (also COMPARABILITY, CLAIM for future rules) |
| `severity` | INFO, WARNING, ERROR, CRITICAL |
| `confidence`, `confidence_label` | 0–1; high ≥ 0.85, medium ≥ 0.6, else low. The rule's spec documents how it is set |
| `scope` | `oah-ig` (id is an example in the OAH IG) or `third-party` (written to the shared sandbox by others) |
| `resource` | `resource_type`, `resource_id`, `fhir_path`, `display` |
| `related_resources` | other resources involved (e.g. the subgroup observations of a cohort check) |
| `summary` | one plain sentence, generated deterministically |
| `evidence` | `observed[]` (label, value, unit, fhir_path), `constraint`, `expected`, `measures{}`, `raw_excerpt` |
| `interpretation` | e.g. "Likely scale inconsistency (root cause unknown)." |
| `root_cause` | always `unknown` |
| `hypotheses[]` | labelled "(hypothesis — not verified)" |
| `remediation` | review by the data owner; never an automatic correction |
| `lineage` | optional: `source`, `locator`, `raw_row`, `matches{stat: bool}`, `statement` |
| `provenance` | `source` (kind, base_url, fetched_at, snapshot_id, manifest_sha256, fallback_reason), `resource_sha256`, `resource_version_id`, `resource_last_updated`, `rules_version`, `knowledge_version`, `ig_source` |

## Normalised records (internal)

`NormalizedObservation` keeps `raw` untouched and adds: `scope`, `indicator_key` (knowledge/indicators/registry.yaml), `medium`,
`stats[]` (observation-statistics components with published decimal precision), `value`, `effective_period` or
`effective_datetime`, `subject_ref`, `focus_refs`, `performer`, `device_ref`, `method`. `Cohort` is derived from `Group.characteristic`
(LOINC 46098-0 sex, LOINC 30525-0 age `valueRange` in UCUM `a`; open-ended upper bound = infinity).

## Comparison (`schemas/comparison.schema.json`) and claims (`schemas/claim.schema.json`, `schemas/claim_result.schema.json`)

See docs/COMPARABILITY_SPEC.md and docs/CLAIM_SAFETY_SPEC.md for semantics. A `ClaimResult` always has `reasons[]` and
`rule_trace[]`; BLOCKED results have `blocking_findings[]`.

## Snapshot

```
data/snapshots/<YYYY-MM-DDTHH-MM-SSZ>/
  manifest.json                      snapshot_id, source_url, fetched_at, completed_at, fhir_version, server_software,
                                     resource_counts, server_validations, ig_source {repo, commit}, knowledge_version, tool,
                                     files[{path, sha256, bytes}], manifest_sha256 (sha256 of the manifest without this field)
  metadata/capability_statement.json
  metadata/resource_counts.json      server $get-resource-counts (includes deleted versions; not used for counts)
  resources/<Type>/<id>.json         raw resource JSON as served (keys sorted, values unchanged)
  validation/Observation/<id>.json   server $validate OperationOutcome for each OAH-IG Observation
```

`verify_snapshot` recomputes every file's sha256 and the manifest digest; snapshots are verified before use and in CI.
`.gitattributes` stores evidence files byte-for-byte (no end-of-line conversion).

## FHIR OperationOutcome export

Bundle `type = collection`, one `OperationOutcome` per affected resource (`id` = `dd-<Type>-<id>`, narrative lists the findings).
Each finding becomes one `issue`:

| Issue field | Value |
|---|---|
| `severity` | CRITICAL → `error` (plus a `critical` coding in `details`), ERROR → `error`, WARNING → `warning`, INFO → `information` |
| `code` | `invariant` (statistical, cross-record), `value` (range), `code-invalid` (unit), `not-found` (reference), `structure` (profile, library), `business-rule` (definitions, synonyms, coordinates) |
| `details.coding` | system `https://github.com/oah-data-doctor/oah-data-doctor/rules` (placeholder canonical, see DECISIONS D-009), code = rule id |
| `details.text` | the finding summary |
| `diagnostics` | finding id, resource, constraint, observed values, confidence, interpretation |
| `expression` | FHIRPath relative to the resource, e.g. `Observation.component[4].value` |

Validated against the official R4 JSON schema (CI) and by the sandbox's HAPI `Bundle/$validate` (docs/VALIDATION.md).

## Knowledge layer

| File | Content |
|---|---|
| `knowledge/indicators/registry.yaml` | code → measure key, medium, kind, canonical unit; complement sets; subset relations |
| `knowledge/scientific/plausibility.yaml` | hard (impossible) and typical (unusual) bounds with rationale |
| `knowledge/scientific/thresholds.yaml` | WHO 2021 AQG, EU 2008/50/EC, EU 2020/2184 values with matrix, averaging period and source |
| `knowledge/terminology/units.yaml` | curated valid/invalid UCUM codes and explicit conversions (affine marked) |
| `knowledge/terminology/concept_maps.yaml` | measure relations: equivalent, related, broader |
| `knowledge/terminology/synonyms.yaml` | deterministic normalisation for near-synonym detection |
| `knowledge/oah/*` | IG example ids, temporary CodeSystem, profile constraints, upstream sample CSV, sources with sha256 |
| `knowledge/analyses/catalog.yaml` | the comparisons and claims computed on every run (inputs to the impact trace) |
