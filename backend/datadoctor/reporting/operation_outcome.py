"""FHIR R4 export: one OperationOutcome per affected resource, collected in a Bundle (type = collection).

Mapping (docs/05_DATA_AND_SCHEMAS.md §OperationOutcome):
  severity  CRITICAL -> error (details carries "critical"), ERROR -> error, WARNING -> warning, INFO -> information
  code      invariant (statistical / cross-record), value (range), code-invalid (unit), not-found (reference),
            structure (profile), business-rule (definitions, synonyms, coordinates)
  details   coding = Data Doctor rule id in the rules CodeSystem; text = plain-language summary
  expression FHIRPath relative to the affected resource (e.g. Observation.component[4].value)
Only base R4 elements are used, so the output validates against the R4 JSON schema and a base-R4 validator.
"""

from __future__ import annotations

import html
import re
import uuid
from collections import defaultdict
from typing import Any

from datadoctor.domain.enums import Severity
from datadoctor.domain.models import Finding

RULES_SYSTEM = "https://github.com/oah-data-doctor/oah-data-doctor/rules"  # placeholder canonical, see DECISIONS D-009
NS = uuid.UUID("6f1c2d9e-7a4b-4c1e-9d52-0a1b2c3d4e5f")

_SEV = {Severity.CRITICAL: "error", Severity.ERROR: "error", Severity.WARNING: "warning", Severity.INFO: "information"}


def _issue_code(rule_id: str) -> str:
    if rule_id.startswith("SEM-RANGE"):
        return "value"
    if rule_id == "STR-UNIT-001":
        return "code-invalid"
    if rule_id == "STR-REF-001":
        return "not-found"
    if rule_id.startswith("STR-"):
        return "structure"
    if rule_id in ("SEM-DEF-001", "SEM-CODE-001", "SEM-SPATIAL-001"):
        return "business-rule"
    return "invariant"


def _expression(f: Finding) -> str:
    path = f.resource.fhir_path or f.resource.resource_type
    path = re.sub(r"\.valueQuantity$", ".value", path)
    if not path.startswith(f.resource.resource_type):
        path = f"{f.resource.resource_type}.{path}"
    return path


def _issue(f: Finding) -> dict[str, Any]:
    observed = "; ".join(f"{o.label}={o.value}{(' ' + o.unit) if o.unit else ''}" for o in f.evidence.observed[:8])
    codings = [{"system": RULES_SYSTEM, "code": f.rule_id, "display": f.title}]
    if f.severity == Severity.CRITICAL:
        codings.append({"system": RULES_SYSTEM + "/severity", "code": "critical", "display": "Critical"})
    return {
        "severity": _SEV[f.severity],
        "code": _issue_code(f.rule_id),
        "details": {"coding": codings, "text": f.summary},
        "diagnostics": (f"[{f.id}] {f.resource.key}: constraint '{f.evidence.constraint}' violated. Observed: {observed}. "
                        f"Confidence {f.confidence} ({f.confidence_label}). {f.interpretation}"),
        "expression": [_expression(f)],
    }


def _narrative(key: str, findings: list[Finding]) -> dict[str, str]:
    rows = "".join(f"<li><b>{html.escape(f.rule_id)}</b> ({html.escape(f.severity.value)}): {html.escape(f.summary)}</li>"
                   for f in findings)
    return {"status": "generated",
            "div": f'<div xmlns="http://www.w3.org/1999/xhtml"><p>OAH Data Doctor findings for {html.escape(key)}</p><ul>{rows}</ul></div>'}


def operation_outcome_bundle(findings: list[Finding], run_id: str, created_at: str) -> dict[str, Any]:
    by_res: dict[str, list[Finding]] = defaultdict(list)
    for f in findings:
        by_res[f.resource.key].append(f)
    entries = []
    for key, fs in sorted(by_res.items()):
        oid = re.sub(r"[^A-Za-z0-9\-.]", "-", f"dd-{key.replace('/', '-')}")[:64]
        oo = {"resourceType": "OperationOutcome", "id": oid, "text": _narrative(key, fs), "issue": [_issue(f) for f in fs]}
        entries.append({"fullUrl": f"urn:uuid:{uuid.uuid5(NS, run_id + key)}", "resource": oo})
    return {
        "resourceType": "Bundle",
        "id": re.sub(r"[^A-Za-z0-9\-.]", "-", run_id)[:64],
        "meta": {"lastUpdated": created_at.replace("Z", "+00:00")},
        "type": "collection",
        "timestamp": created_at.replace("Z", "+00:00"),
        "entry": entries,
    }
