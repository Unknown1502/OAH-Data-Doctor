"""The "Download the data" button, end to end without a network.

A fake OneAquaHealth (sandbox and IG repository) serves exactly what the committed snapshot holds. Saving the data on this
computer must write a new verified snapshot and reproduce the committed snapshot's audit, finding for finding, with the
lineage that needs the IG's source spreadsheet."""

import asyncio
import json
import shutil
from pathlib import Path

import httpx

from datadoctor.api.state import AppState
from datadoctor.audit.service import audit_dataset
from datadoctor.config import REPO_ROOT, Settings
from datadoctor.domain.enums import SourceKind
from datadoctor.ingestion.snapshot import list_snapshots, load_snapshot
from datadoctor.ingestion.source import load_from_snapshot
from datadoctor.knowledge.loader import load_knowledge
from datadoctor.normalization.normalizer import build_dataset

BASE = "https://sandbox.example.org/fhir"
SPREADSHEET = "Almyros_gov_chem_analysis.csv"
ANCHOR = "Obs-Almyros-TemperatureWater-2013"


def fake_oah(snapshot: Path, spreadsheet: bytes) -> httpx.MockTransport:
    _, raw, validation = load_snapshot(snapshot)
    capability = json.loads((snapshot / "metadata" / "capability_statement.json").read_text(encoding="utf-8"))

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.host == "raw.githubusercontent.com":
            return httpx.Response(200, content=spreadsheet)
        path = req.url.path.removeprefix("/fhir/")
        if path == "metadata":
            return httpx.Response(200, json=capability)
        if path.endswith("/$validate"):
            rtype, rid, _ = path.split("/")
            return httpx.Response(200, json=validation[f"{rtype}/{rid}"])
        if "/" in path or path.startswith("$"):
            return httpx.Response(404, json={"resourceType": "OperationOutcome", "issue": []})
        entries = [{"resource": r} for r in raw.get(path, {}).values()]
        return httpx.Response(200, json={"resourceType": "Bundle", "type": "searchset", "entry": entries, "link": []})

    return httpx.MockTransport(handler)


def test_saving_the_data_reproduces_the_committed_snapshot(tmp_path):
    committed_dir = REPO_ROOT / "data" / "snapshots"
    committed = list_snapshots(committed_dir)[0]
    knowledge = tmp_path / "knowledge"
    shutil.copytree(REPO_ROOT / "knowledge", knowledge, ignore=shutil.ignore_patterns("upstream"))
    spreadsheet = (REPO_ROOT / "knowledge" / "oah" / "upstream" / SPREADSHEET).read_bytes()
    settings = Settings(fhir_base=BASE, data_dir=tmp_path / "data", knowledge_dir=knowledge, http_delay_s=0.0, http_retries=0)

    async def go():
        st = AppState(settings)
        assert not (knowledge / "oah" / "upstream" / SPREADSHEET).exists()
        res = await st.start_local_copy(transport=fake_oah(committed_dir / committed["snapshot_id"], spreadsheet))
        return st, res

    st, res = asyncio.run(go())

    # the IG spreadsheet, byte for byte, and a new verified snapshot with the same content
    assert (knowledge / "oah" / "upstream" / SPREADSHEET).read_bytes() == spreadsheet
    [saved] = list_snapshots(settings.snapshots_dir)
    assert saved["resource_counts"] == committed["resource_counts"]
    assert saved["server_validations"] == committed["server_validations"]
    assert res.source.kind is SourceKind.SNAPSHOT and res.source.snapshot_id == saved["snapshot_id"]

    # the same audit as the committed snapshot, finding for finding, including the lineage
    kn = load_knowledge(knowledge)
    raw, source, validation = load_from_snapshot(Settings(data_dir=REPO_ROOT / "data"), committed["snapshot_id"])
    baseline = audit_dataset(build_dataset(raw, source, kn, validation), kn)
    assert {f.id for f in res.findings} == {f.id for f in baseline.findings}
    assert any(f.lineage for f in res.findings if f.resource.resource_id == ANCHOR)

    # every stage the UI shows actually happened
    assert st.scan["running"] is False and st.scan["error"] is None and st.scan["mode"] == "download"
    stages = {s["id"]: s["state"] for s in st.scan["stages"]}
    assert set(stages.values()) == {"done"}
    assert {f"ig:{SPREADSHEET}", "fetch:Observation", "validate:Observation", "write", "rules"} <= set(stages)


def test_a_failed_download_is_reported_and_leaves_no_snapshot(tmp_path):
    settings = Settings(fhir_base=BASE, data_dir=tmp_path / "data", knowledge_dir=REPO_ROOT / "knowledge",
                        http_delay_s=0.0, http_retries=0)
    down = httpx.MockTransport(lambda req: httpx.Response(503, text="Service Unavailable"))

    async def go():
        st = AppState(settings)
        try:
            await st.start_local_copy(transport=down)
        except Exception as exc:  # noqa: BLE001
            return st, exc
        return st, None

    st, exc = asyncio.run(go())
    assert exc is not None
    assert st.scan["running"] is False and "503" in st.scan["error"]
    assert "running" not in {s["state"] for s in st.scan["stages"]}
    assert list_snapshots(settings.snapshots_dir) == []
