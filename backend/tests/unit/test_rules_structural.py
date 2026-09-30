"""Structural rules: STR-UNIT-001, STR-REF-001, STR-PROF-001, STR-LIB-001."""

from datadoctor.domain.enums import Severity
from tests.helpers import OAH, P, dataset, group, location, run, stats_obs, value_obs

# --- STR-UNIT-001 ------------------------------------------------------------------------------------

def test_unit001_missing_ucum_code_is_error():
    ds = dataset(stats_obs("PH", average=7.68, maximum=8.2, minimum=7.16, unit=None, system=OAH, code="ph", text="pH"))
    f = run("STR-UNIT-001", ds)
    assert len(f) == 1 and f[0].severity == Severity.ERROR
    assert f[0].evidence.measures["problem"] == "missing"


def test_unit001_invalid_ucum_code_suggests_fix():
    ds = dataset(stats_obs("PH", average=7.59, maximum=7.8, minimum=7.38, unit="pH", system=OAH, code="ph", text="pH"))
    f = run("STR-UNIT-001", ds)
    assert len(f) == 1 and f[0].evidence.measures["suggest"] == "[pH]"


def test_unit001_silent_on_valid_codes():
    assert run("STR-UNIT-001", dataset(stats_obs("T", average=19.8, maximum=21.1, minimum=18.5, median=19.8))) == []
    assert run("STR-UNIT-001", dataset(value_obs("O", 30.0))) == []


def test_unit001_one_finding_per_observation_not_per_component():
    ds = dataset(stats_obs("PH", average=7.6, maximum=8.2, minimum=7.1, median=7.6, std_dev=0.3, unit=None,
                           system=OAH, code="ph", text="pH"))
    assert len(run("STR-UNIT-001", ds)) == 1


# --- STR-REF-001 -------------------------------------------------------------------------------------

def test_ref001_unresolved_subject():
    ds = dataset(value_obs("O", 30.0, location="Loc-Missing"))
    f = run("STR-REF-001", ds)
    assert len(f) == 1 and "Location/Loc-Missing" in f[0].summary


def test_ref001_unresolved_focus_group():
    assert len(run("STR-REF-001", dataset(value_obs("O", 30.0, group="G-missing")))) == 1


def test_ref001_silent_when_all_resolve():
    assert run("STR-REF-001", dataset(group("G1", sex="male"), value_obs("O", 30.0, group="G1"))) == []


def test_ref001_ignores_types_not_ingested():
    obs = value_obs("O", 30.0)
    obs["performer"] = [{"reference": "Practitioner/123"}]  # Practitioner is not ingested -> not checked
    assert run("STR-REF-001", dataset(obs)) == []


# --- STR-PROF-001 ------------------------------------------------------------------------------------

def test_prof001_component_profile_without_performer():
    obs = stats_obs("T", average=19.8, maximum=21.1, minimum=18.5, median=19.8)
    del obs["performer"]
    f = run("STR-PROF-001", dataset(obs))
    assert len(f) == 1 and any("performer" in o.label for o in f[0].evidence.observed)


def test_prof001_location_mode_and_identifier():
    loc = location("L1")
    loc["mode"] = "kind"
    del loc["identifier"]
    f = run("STR-PROF-001", dataset(loc, with_default_location=False))
    assert len(f) == 1 and len(f[0].evidence.observed) == 2


def test_prof001_silent_on_conformant_resources():
    ds = dataset(group("G1", sex="male", low=18, high=29), value_obs("O", 3.0, group="G1"),
                 stats_obs("T", average=19.8, maximum=21.1, minimum=18.5, median=19.8))
    assert run("STR-PROF-001", ds) == []


def test_prof001_ignores_resources_without_oah_profile():
    obs = value_obs("O", 3.0)
    obs["meta"]["profile"] = ["https://example.org/other-profile"]
    obs["status"] = "preliminary"
    assert run("STR-PROF-001", dataset(obs)) == []


# --- STR-LIB-001 -------------------------------------------------------------------------------------

def _library(members: list[str], declared: int) -> dict:
    return {"resourceType": "Library", "id": "Lib", "status": "active", "title": "t", "url": "http://x", "date": "2025",
            "type": {"coding": [{"code": "asset-collection"}]}, "meta": {"profile": [P + "library-oah"]},
            "extension": [{"url": "http://hl7.eu/fhir/ig/oah/StructureDefinition/library-numberOfRecords", "valueInteger": declared}],
            "content": [{"contentType": "application/fhir+json", "url": m} for m in members]}


def test_lib001_declared_count_mismatch_and_unresolved_member():
    ds = dataset(value_obs("O1", 1.0), _library(["Observation/O1", "Observation/O-gone"], 3))
    f = run("STR-LIB-001", ds)
    assert len(f) == 1
    m = f[0].evidence.measures
    assert m["declared"] == 3 and m["listed"] == 2 and m["unresolved"] == ["Observation/O-gone"]


def test_lib001_silent_on_consistent_library():
    assert run("STR-LIB-001", dataset(value_obs("O1", 1.0), _library(["Observation/O1"], 1))) == []
