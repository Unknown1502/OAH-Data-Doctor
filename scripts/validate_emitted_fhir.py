"""Validate Data Doctor's own FHIR output (OperationOutcome bundle) twice and record the evidence in docs/VALIDATION.md:

1. offline, against the official FHIR R4 JSON schema (schemas/fhir/fhir.schema.json.zip);
2. online, with the sandbox's HAPI FHIR validator: POST {base}/Bundle/$validate (read-only; nothing is stored).
"""

from __future__ import annotations

import asyncio
import datetime as dt
import json
import sys
import zipfile
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

import jsonschema  # noqa: E402

from datadoctor.audit.service import run_audit  # noqa: E402
from datadoctor.config import get_settings  # noqa: E402
from datadoctor.ingestion.fhir_client import FhirClient  # noqa: E402
from datadoctor.reporting.operation_outcome import operation_outcome_bundle  # noqa: E402


async def main() -> None:
    st = get_settings()
    res, _ = await run_audit(st, "snapshot")
    bundle = operation_outcome_bundle(res.findings, res.run_id, res.created_at)
    with zipfile.ZipFile(ROOT / "schemas" / "fhir" / "fhir.schema.json.zip") as z:
        schema = json.loads(z.read("fhir.schema.json"))
    errors = sorted(jsonschema.Draft6Validator(schema).iter_errors(bundle), key=str)
    now = dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    online: dict = {}
    async with FhirClient(st.fhir_base, None, delay_s=0.5) as client:
        status, text = await client.request("POST", "Bundle/$validate", body=bundle)
        oo = json.loads(text)
        online = {"status": status, "issues": Counter((i.get("severity"), (i.get("diagnostics") or "")[:140]) for i in oo.get("issue", []))}
    lines = [
        "# Validation of Data Doctor's emitted FHIR", "",
        f"Run `{res.run_id}` (source: snapshot `{res.source.snapshot_id}`); validated {now}.", "",
        f"Artefact: `Bundle` (type `collection`) with {len(bundle['entry'])} `OperationOutcome` resources and "
        f"{sum(len(e['resource']['issue']) for e in bundle['entry'])} issues (one per finding).", "",
        "## 1. FHIR R4 JSON schema (offline)", "",
        "Schema: `schemas/fhir/fhir.schema.json.zip`, downloaded from https://hl7.org/fhir/R4/fhir.schema.json.zip "
        "(sha256 `75e5560da3cf503895a44c8ca7af17a83b4cca6c2cb5ba1883d2aec0d1cb5ac6`).", "",
        f"Result: **{len(errors)} schema errors**." + ("" if not errors else " First: " + str(errors[0])[:300]), "",
        "Also enforced in CI by `backend/tests/contract/test_contracts.py`.", "",
        "## 2. HAPI FHIR validator on the OAH sandbox (online)", "",
        f"Request: `POST {st.fhir_base}/Bundle/$validate` → HTTP {online['status']}.", "",
        "| Severity | Diagnostics (truncated) | Count |", "|---|---|---|",
        *[f"| {sev} | {msg.replace('|', '/')} | {n} |" for (sev, msg), n in sorted(online["issues"].items())],
        "",
        "Scope of these checks: base FHIR R4 structure, cardinality, value sets and data types of the emitted resources. "
        "They do not (and cannot) validate the scientific content of the findings, which is covered by the rule tests.", "",
    ]
    (ROOT / "docs" / "VALIDATION.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    asyncio.run(main())
