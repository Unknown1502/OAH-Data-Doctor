"""Snapshots round-trip, verify, detect tampering, and keep paths short (Windows MAX_PATH)."""

import asyncio
import json

import httpx
import pytest

from datadoctor.ingestion.fhir_client import FhirClient
from datadoctor.ingestion.snapshot import (
    FORMAT,
    SnapshotError,
    create_snapshot,
    load_snapshot,
    verify_snapshot,
)

BASE = "https://sandbox.example.org/fhir"
LONG_ID = "Obs-BN-BN3-hypercholesterolemia-treatment-Male-Age-35-74"


def handler(req: httpx.Request) -> httpx.Response:
    path = req.url.path
    if path.endswith("/metadata"):
        return httpx.Response(200, json={"resourceType": "CapabilityStatement", "fhirVersion": "4.0.1", "software": {"name": "HAPI"}})
    if path.endswith("$get-resource-counts"):
        return httpx.Response(200, json={"resourceType": "Parameters", "parameter": []})
    if path.endswith("$validate"):
        return httpx.Response(200, json={"resourceType": "OperationOutcome", "issue": [{"severity": "information", "code": "informational"}]})
    rtype = path.rsplit("/", 1)[-1]
    entries = []
    if rtype == "Observation":
        entries = [{"resource": {"resourceType": "Observation", "id": LONG_ID, "valueQuantity": {"value": 19.8}}},
                   {"resource": {"resourceType": "Observation", "id": "a", "valueQuantity": {"value": 198000}}}]
    return httpx.Response(200, json={"resourceType": "Bundle", "type": "searchset", "entry": entries, "link": []})


def _snapshot(tmp_path):
    async def go():
        async with FhirClient(BASE, None, delay_s=0, transport=httpx.MockTransport(handler)) as c:
            return await create_snapshot(c, tmp_path, ("Observation", "Location"), validate=lambda t, r: t == "Observation")

    return asyncio.run(go())


def test_snapshot_round_trips_exactly(tmp_path):
    root = _snapshot(tmp_path)
    manifest, raw, validation = load_snapshot(root)
    assert manifest["format"] == FORMAT
    assert raw["Observation"][LONG_ID]["valueQuantity"]["value"] == 19.8
    assert raw["Observation"]["a"]["valueQuantity"]["value"] == 198000
    assert raw["Location"] == {}
    assert set(validation) == {f"Observation/{LONG_ID}", "Observation/a"}
    assert manifest["resource_counts"] == {"Observation": 2, "Location": 0}


def test_snapshot_paths_do_not_depend_on_resource_ids(tmp_path):
    root = _snapshot(tmp_path)
    longest = max(len(p.relative_to(root).as_posix()) for p in root.rglob("*") if p.is_file())
    assert longest < 40  # e.g. "validation/Observation.ndjson"; ids never appear in paths


def test_tampering_is_detected(tmp_path):
    root = _snapshot(tmp_path)
    p = root / "resources" / "Observation.ndjson"
    p.write_text(p.read_text(encoding="utf-8").replace("19.8", "19.9"), encoding="utf-8")
    assert any("sha256 mismatch" in x for x in verify_snapshot(root))
    with pytest.raises(SnapshotError):
        load_snapshot(root)


def test_manifest_edit_is_detected(tmp_path):
    root = _snapshot(tmp_path)
    m = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    m["fetched_at"] = "2020-01-01T00:00:00Z"
    (root / "manifest.json").write_text(json.dumps(m), encoding="utf-8")
    assert "manifest digest mismatch" in verify_snapshot(root)
