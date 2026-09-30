"""Contract tests: published JSON Schemas match the models, real output validates, FHIR export validates against R4."""

import asyncio
import json
import zipfile
from functools import lru_cache

import jsonschema
import pytest

from datadoctor.audit.analyses import run_catalog
from datadoctor.audit.service import AuditResult, run_audit
from datadoctor.config import REPO_ROOT, Settings
from datadoctor.domain.models import ClaimResult, Comparison, Finding, StructuredClaim
from datadoctor.knowledge.loader import load_knowledge
from datadoctor.reporting.operation_outcome import operation_outcome_bundle

SCHEMAS = REPO_ROOT / "schemas"
MODELS = {"finding": Finding, "comparison": Comparison, "claim": StructuredClaim, "claim_result": ClaimResult,
          "audit_result": AuditResult}


@lru_cache(maxsize=1)
def _run():
    snaps = sorted(p.name for p in (REPO_ROOT / "data" / "snapshots").iterdir() if (p / "manifest.json").exists())
    if not snaps:
        pytest.skip("no snapshot")
    res, ds = asyncio.run(run_audit(Settings(), "snapshot", snaps[-1]))
    return res, ds


@lru_cache(maxsize=1)
def _fhir_schema():
    with zipfile.ZipFile(SCHEMAS / "fhir" / "fhir.schema.json.zip") as z:
        return json.loads(z.read("fhir.schema.json"))


@pytest.mark.parametrize("name", sorted(MODELS))
def test_committed_schema_matches_model(name):
    committed = json.loads((SCHEMAS / f"{name}.schema.json").read_text(encoding="utf-8"))
    generated = MODELS[name].model_json_schema()
    committed.pop("$schema", None)
    committed.pop("$id", None)
    assert committed == json.loads(json.dumps(generated)), f"schemas/{name}.schema.json is stale: run scripts/export_schemas.py"


def test_real_findings_validate_against_published_schema():
    res, _ = _run()
    schema = json.loads((SCHEMAS / "finding.schema.json").read_text(encoding="utf-8"))
    for f in res.findings[:60]:
        jsonschema.validate(json.loads(f.model_dump_json()), schema)


def test_every_finding_carries_required_evidence():
    res, _ = _run()
    for f in res.findings:
        assert f.rule_id and f.resource.resource_type and f.resource.resource_id
        assert f.evidence.constraint and f.evidence.expected
        assert 0 < f.confidence <= 1 and f.severity
        assert f.provenance is not None and f.provenance.source.kind.value == "snapshot"
        assert f.root_cause == "unknown"
        assert "Data Doctor never corrects" in f.remediation or "data owner" in f.remediation.lower() or "IG authors" in f.remediation


def test_comparisons_and_claims_validate():
    res, ds = _run()
    an = run_catalog(ds, load_knowledge(REPO_ROOT / "knowledge"), res.findings)
    cs = json.loads((SCHEMAS / "comparison.schema.json").read_text(encoding="utf-8"))
    rs = json.loads((SCHEMAS / "claim_result.schema.json").read_text(encoding="utf-8"))
    for c in an.comparisons:
        jsonschema.validate(json.loads(c.model_dump_json()), cs)
    for r in an.claims:
        jsonschema.validate(json.loads(r.model_dump_json()), rs)
        assert r.reasons and r.rule_trace


def test_operation_outcome_bundle_validates_against_fhir_r4_schema():
    res, _ = _run()
    sample = res.findings[:25] + [f for f in res.findings if f.resource.resource_type != "Observation"]
    bundle = operation_outcome_bundle(sample, res.run_id, res.created_at)
    jsonschema.Draft6Validator(_fhir_schema()).validate(bundle)
    oo = bundle["entry"][0]["resource"]
    assert oo["resourceType"] == "OperationOutcome"
    assert all(i["expression"][0].split(".")[0] in ("Observation", "Location", "CodeSystem", "Library", "Group") for i in oo["issue"])


def test_operation_outcome_severity_mapping_is_valid_fhir():
    res, _ = _run()
    bundle = operation_outcome_bundle(res.findings, res.run_id, res.created_at)
    sev = {i["severity"] for e in bundle["entry"] for i in e["resource"]["issue"]}
    assert sev <= {"fatal", "error", "warning", "information"}
    assert len(bundle["entry"]) == len({f.resource.key for f in res.findings})
