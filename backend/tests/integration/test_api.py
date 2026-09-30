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


# --- Bring your own model key ----------------------------------------------------------------------------------------

SECRET = "gsk_test_Secret123456"


class _FakeModel:
    name = "fake:model"

    def complete(self, system, user, *, max_tokens=1024):
        return "The published median lies below the published minimum, so these values cannot all be right."

    def complete_json(self, system, user, model_cls):
        return model_cls.model_validate({})

    def list_models(self):
        return ["model-a", "model-b"]


def test_provider_list_has_no_secrets_and_no_free_form_url(client):
    p = client.get("/api/llm/providers").json()
    ids = [x["id"] for x in p["providers"]]
    assert {"ollama", "groq", "gemini", "openrouter", "anthropic"} <= set(ids)
    assert "custom" not in ids and p["allow_custom_url"] is False  # off by default
    assert "api_key" not in str(p).lower()
    assert client.get("/api/status").json()["llm_user_keys"] is True


def test_users_own_model_is_used_for_their_request_only(client, monkeypatch):
    import datadoctor.api.main as api

    seen = []
    monkeypatch.setattr(api, "client_from_config", lambda cfg, st: seen.append(cfg) or _FakeModel())
    hero = client.get("/api/overview").json()["hero_finding"]["id"]
    cfg = {"provider": "groq", "model": "llama-3.1-8b-instant", "api_key": SECRET}
    out = client.post(f"/api/findings/{hero}/explain", json={"llm": cfg}).json()
    assert out["method"] == "llm:fake:model"
    assert seen[0].api_key.get_secret_value() == SECRET and SECRET not in repr(seen[0])
    # Without settings the server default applies (none in tests): the template.
    assert client.post(f"/api/findings/{hero}/explain", json={}).json()["method"] == "template"
    p = client.post("/api/claims/parse", json={"text": "Ozone and diabetes in Benevento", "llm": cfg}).json()
    assert p["method"].startswith("llm:fake:model") or p["method"].startswith("deterministic")


def test_bad_user_settings_are_explained_not_hidden(client):
    hero = client.get("/api/overview").json()["hero_finding"]["id"]
    r = client.post(f"/api/findings/{hero}/explain", json={"llm": {"provider": "groq"}})
    assert r.status_code == 400 and "needs an API key" in r.json()["detail"]
    r = client.post(f"/api/findings/{hero}/explain", json={"llm": {"provider": "custom", "base_url": "http://169.254.169.254/"}})
    assert r.status_code == 400 and "switched off" in r.json()["detail"]
    t = client.post("/api/llm/test", json={"provider": "nope", "api_key": SECRET}).json()
    assert t["ok"] is False and "Unknown provider" in t["error"] and SECRET not in str(t)


def test_connection_test_reports_models(client, monkeypatch):
    import datadoctor.api.main as api

    monkeypatch.setattr(api, "client_from_config", lambda cfg, st: _FakeModel())
    t = client.post("/api/llm/test", json={"provider": "groq", "api_key": SECRET}).json()
    assert t["ok"] and t["name"] == "fake:model" and t["models"] == ["model-a", "model-b"] and t["latency_ms"] >= 0


def test_validation_errors_never_echo_the_key(client):
    # Missing "provider": FastAPI's default 422 would include the whole llm object, key and all.
    r = client.post("/api/claims/parse", json={"text": "NO2 at site 01", "llm": {"api_key": SECRET}})
    assert r.status_code == 422 and SECRET not in r.text
    assert r.json()["detail"][0]["loc"] == ["body", "llm", "provider"]


def test_presets_carry_model_suggestions_and_models_can_be_listed(client, monkeypatch):
    import datadoctor.api.main as api

    presets = {p["id"]: p for p in client.get("/api/llm/providers").json()["providers"]}
    assert all(p["models"] and p["default_model"] in p["models"] for k, p in presets.items())
    monkeypatch.setattr(api, "client_from_config", lambda cfg, st: _FakeModel())
    assert client.post("/api/llm/models", json={"provider": "groq", "api_key": SECRET}).json() == {"models": ["model-a", "model-b"], "error": None}
    monkeypatch.undo()
    r = client.post("/api/llm/models", json={"provider": "gemini"}).json()
    assert r["models"] == [] and "needs an API key" in r["error"]
