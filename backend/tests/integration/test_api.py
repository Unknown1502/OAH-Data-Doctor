"""API tests against the committed snapshot (no network: DD_STARTUP_LIVE=0, DD_SOURCE=snapshot)."""

import os

import pytest

os.environ["DD_STARTUP_LIVE"] = "0"
os.environ["DD_SOURCE"] = "snapshot"

from fastapi.testclient import TestClient  # noqa: E402

from datadoctor.api.main import app  # noqa: E402


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c
        c.post("/api/analyses/reset")


def test_status_labels_snapshot(client):
    s = client.get("/api/status").json()
    assert s["has_run"] and s["source"]["kind"] == "snapshot" and s["source"]["manifest_sha256"]


def test_overview_numbers_are_computed(client):
    o = client.get("/api/overview").json()
    assert o["summary"]["findings_total"] == sum(o["summary"]["findings_by_severity"].values())
    assert o["hero_finding"]["resource"]["resource_id"] == "Obs-Almyros-TemperatureWater-2013"


def test_findings_filters(client):
    all_ = client.get("/api/findings").json()
    crit = client.get("/api/findings?severity=CRITICAL").json()
    assert 0 < crit["total"] < all_["total"]
    assert all(i["severity"] == "CRITICAL" for i in crit["items"])
    anchor = client.get("/api/findings?resource=Observation/Obs-Almyros-TemperatureWater-2013").json()
    assert {i["rule_id"] for i in anchor["items"]} >= {"SEM-STAT-001", "SEM-RANGE-001"}


def test_finding_detail_has_evidence_trace_and_server_verdict(client):
    fid = client.get("/api/overview").json()["hero_finding"]["id"]
    d = client.get(f"/api/findings/{fid}").json()
    assert d["raw"]["id"] == "Obs-Almyros-TemperatureWater-2013"
    assert d["server_validation"]["issue"][0]["severity"] == "information"
    assert d["impact"]["counts"]["claim"] >= 2
    assert d["explanation"]["method"] == "template"
    assert d["finding"]["lineage"]["matches"]["median"] is True


def test_unknown_finding_is_404(client):
    assert client.get("/api/findings/F-NOPE").status_code == 404


def test_compare_and_user_analysis_enters_the_trace(client):
    before = client.get("/api/trace/resource/Observation/Obs-WaterTemp-Almyros-2025-04-14").json()["counts"]["comparison"]
    r = client.post("/api/compare", json={"a": {"observation": "Obs-WaterTemp-Almyros-2025-04-14"},
                                          "b": {"observation": "Obs-WaterTemp-Giofyros-2025-04-14"}}).json()
    assert r["verdict"] == "DIRECT"
    after = client.get("/api/trace/resource/Observation/Obs-WaterTemp-Almyros-2025-04-14").json()["counts"]["comparison"]
    assert after == before + 1


def test_compare_rejects_unknown_record(client):
    assert client.post("/api/compare", json={"a": {"observation": "nope"}, "b": {"observation": "nope2"}}).status_code == 400


def test_parse_then_evaluate_claim(client):
    p = client.post("/api/claims/parse", json={"text": "Water temperature at Almyros increased from 2013 to 2020"}).json()
    assert p["claim"]["type"] == "TREND_INCREASE" and p["method"] == "deterministic"
    v = client.post("/api/claims", json={"claim": p["claim"]}).json()
    assert v["verdict"] == "BLOCKED" and v["blocking_findings"]


def test_parse_related_measure_fallback(client):
    p = client.post("/api/claims/parse", json={"text": "Obesity is higher in Benevento than in Oslo"}).json()
    assert p["claim"] and p["claim"]["object"].startswith("Obs-OS-bmi-above-30")
    v = client.post("/api/claims", json={"claim": p["claim"]}).json()
    assert v["verdict"] in ("CONDITIONAL", "UNSUPPORTED")


def test_parse_rejects_nonsense(client):
    p = client.post("/api/claims/parse", json={"text": "hello world"}).json()
    assert p["claim"] is None and p["problems"]


@pytest.mark.parametrize("name,ctype", [("findings.json", "json"), ("operation-outcome.json", "fhir+json"),
                                        ("report.md", "markdown"), ("report.html", "html"), ("support.json", "json")])
def test_reports(client, name, ctype):
    r = client.get(f"/api/reports/{name}")
    assert r.status_code == 200 and ctype in r.headers["content-type"]


def test_report_contains_only_computed_numbers(client):
    md = client.get("/api/reports/report.md").text
    o = client.get("/api/overview").json()["summary"]
    assert f"{o['findings_total']} findings" in md
    assert "{{" not in md  # no unfilled placeholders


def test_rules_catalog(client):
    rules = client.get("/api/rules").json()
    assert len(rules) == 19 and all(r["constraint"] and r["rationale"] for r in rules)
