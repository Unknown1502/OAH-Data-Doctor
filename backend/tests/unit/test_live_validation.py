"""Live runs ask the server's own $validate about flagged official records; snapshot runs keep their stored verdicts."""

import asyncio

import httpx
import pytest

import datadoctor.audit.service as service
from datadoctor.audit.service import audit_dataset, complete_live_validation
from datadoctor.config import Settings
from datadoctor.domain.enums import SourceKind
from datadoctor.domain.models import SourceInfo
from datadoctor.ingestion.fhir_client import FhirClient
from datadoctor.normalization.normalizer import build_dataset
from tests.helpers import KN, location, stats_obs

ANCHOR = "Obs-Almyros-TemperatureWater-2013"  # an official IG example id, so it is in scope
CALLS: list[str] = []


def _ok(req: httpx.Request) -> httpx.Response:
    CALLS.append(req.url.path)
    return httpx.Response(200, json={"resourceType": "OperationOutcome",
                                     "issue": [{"severity": "information", "code": "informational",
                                                "diagnostics": "No issues detected during validation"}]})


def _dataset(kind: SourceKind):
    raw = {"Observation": {ANCHOR: stats_obs(ANCHOR, average=198000, maximum=211000, minimum=185000, std_dev=18385, median=19.8,
                                               location="Loc-Almyros")},
           "Location": {"Loc-Almyros": location("Loc-Almyros")}}
    src = SourceInfo(kind=kind, base_url="https://sandbox.example.org/fhir", fetched_at="2026-09-30T11:00:00Z")
    return build_dataset(raw, src, KN)


@pytest.fixture()
def mocked(monkeypatch, tmp_path):
    CALLS.clear()

    def factory(transport_handler):
        class Client(FhirClient):
            def __init__(self, base_url, cache=None, **kw):
                kw.pop("transport", None)
                super().__init__(base_url, cache, transport=httpx.MockTransport(transport_handler), **{**kw, "delay_s": 0})

        monkeypatch.setattr(service, "FhirClient", Client)
        return Settings(data_dir=tmp_path, fhir_base="https://sandbox.example.org/fhir")

    return factory


def test_live_run_fetches_server_verdicts_for_flagged_records(mocked):
    settings = mocked(_ok)
    ds = _dataset(SourceKind.LIVE)
    res = asyncio.run(complete_live_validation(settings, ds, audit_dataset(ds, KN), KN))
    assert [f"/fhir/Observation/{ANCHOR}/$validate"] == CALLS
    assert res.summary.server_validation == {"validated_total": 1, "validated_with_errors": 0,
                                             "flagged_observations_validated": 1,
                                             "flagged_observations_passing_server_validation": 1}


def test_snapshot_run_is_left_untouched(mocked):
    settings = mocked(_ok)
    ds = _dataset(SourceKind.SNAPSHOT)
    res = asyncio.run(complete_live_validation(settings, ds, audit_dataset(ds, KN), KN))
    assert CALLS == [] and res.summary.server_validation == {}


def test_server_failure_never_breaks_the_audit(mocked):
    settings = mocked(lambda req: httpx.Response(503))
    ds = _dataset(SourceKind.LIVE)
    before = audit_dataset(ds, KN)
    res = asyncio.run(complete_live_validation(settings, ds, before, KN))
    assert res.findings == before.findings and res.summary.server_validation == {}
