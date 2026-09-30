# Validation of Data Doctor's emitted FHIR

Run `run-20260930T093014Z-5695cc` (source: snapshot `2026-09-30T09-08-55Z`); validated 2026-09-30T09:30:16Z.

Artefact: `Bundle` (type `collection`) with 131 `OperationOutcome` resources and 346 issues (one per finding).

## 1. FHIR R4 JSON schema (offline)

Schema: `schemas/fhir/fhir.schema.json.zip`, downloaded from https://hl7.org/fhir/R4/fhir.schema.json.zip (sha256 `75e5560da3cf503895a44c8ca7af17a83b4cca6c2cb5ba1883d2aec0d1cb5ac6`).

Result: **0 schema errors**.

Also enforced in CI by `backend/tests/contract/test_contracts.py`.

## 2. HAPI FHIR validator on the OAH sandbox (online)

Request: `POST https://sandbox.hl7europe.eu/oneaquahealth/fhir/Bundle/$validate` → HTTP 200.

| Severity | Diagnostics (truncated) | Count |
|---|---|---|
| information | No issues detected during validation | 1 |

Scope of these checks: base FHIR R4 structure, cardinality, value sets and data types of the emitted resources. They do not (and cannot) validate the scientific content of the findings, which is covered by the rule tests.
