"""Builders for small, explicit FHIR fixtures used by rule tests."""

from __future__ import annotations

from typing import Any

from datadoctor.config import REPO_ROOT
from datadoctor.domain.enums import SourceKind
from datadoctor.domain.models import Dataset, SourceInfo
from datadoctor.knowledge.loader import load_knowledge
from datadoctor.normalization.normalizer import build_dataset

KN = load_knowledge(REPO_ROOT / "knowledge")
STATS = "http://terminology.hl7.org/CodeSystem/observation-statistics"
OAH = "http://hl7.eu/fhir/ig/oah/CodeSystem/temporarySystem-oah-eu"
AIR = "https://oneaquahealth.eu/air-parameters"
SNOMED = "http://snomed.info/sct"
P = "http://hl7.eu/fhir/ig/oah/StructureDefinition/"
UCUM = "http://unitsofmeasure.org"


def stats_obs(oid: str, *, average: Any = None, median: Any = None, minimum: Any = None, maximum: Any = None,
              std_dev: Any = None, unit: str | None = "Cel", system: str = SNOMED, code: str = "703421000",
              location: str = "Loc-T", year: int = 2013, text: str | None = "Temperature (water)") -> dict[str, Any]:
    comps = []
    for name, v in (("average", average), ("maximum", maximum), ("minimum", minimum), ("std-dev", std_dev), ("median", median)):
        if v is None:
            continue
        q: dict[str, Any] = {"value": v, "system": UCUM}
        if unit is not None:
            q["code"] = unit
            q["unit"] = unit
        comps.append({"code": {"coding": [{"system": STATS, "code": name}]}, "valueQuantity": q})
    res: dict[str, Any] = {
        "resourceType": "Observation", "id": oid, "status": "final",
        "meta": {"profile": [P + "observation-with-component-oah"]},
        "code": {"coding": [{"system": system, "code": code}]},
        "subject": {"reference": f"Location/{location}"},
        "effectivePeriod": {"start": f"{year}-01-01", "end": f"{year}-12-31"},
        "performer": [{"display": "Test Lab"}],
        "component": comps,
    }
    if text:
        res["code"]["text"] = text
    return res


def value_obs(oid: str, value: Any, *, unit: str = "%", system: str = OAH, code: str = "obesity", location: str = "Loc-T",
              group: str | None = None, year: int = 2024, profile: str = "observation-health-measure-oah",
              date: str | None = None) -> dict[str, Any]:
    res: dict[str, Any] = {
        "resourceType": "Observation", "id": oid, "status": "final",
        "meta": {"profile": [P + profile]},
        "code": {"coding": [{"system": system, "code": code}]},
        "subject": {"reference": f"Location/{location}"},
        "valueQuantity": {"value": value, "unit": unit, "system": UCUM, "code": unit},
    }
    if date:
        res["effectiveDateTime"] = date
    else:
        res["effectivePeriod"] = {"start": f"{year}-01-01", "end": f"{year}-12-31"}
    if group:
        res["focus"] = [{"reference": f"Group/{group}"}]
    return res


def location(lid: str, lat: float | None = 41.0, lon: float | None = 14.0, name: str | None = None) -> dict[str, Any]:
    res: dict[str, Any] = {"resourceType": "Location", "id": lid, "name": name or lid, "mode": "instance",
                           "identifier": [{"value": lid}], "meta": {"profile": [P + "location-oah"]}}
    if lat is not None and lon is not None:
        res["position"] = {"latitude": lat, "longitude": lon}
    return res


def group(gid: str, sex: str | None = None, low: float | None = None, high: float | None = None) -> dict[str, Any]:
    chars = []
    if sex:
        chars.append({"code": {"coding": [{"system": "http://loinc.org", "code": "46098-0"}]},
                      "valueCodeableConcept": {"coding": [{"system": "http://hl7.org/fhir/administrative-gender", "code": sex}]},
                      "exclude": False})
    if low is not None:
        rng: dict[str, Any] = {"low": {"value": low, "code": "a", "system": UCUM}}
        if high is not None:
            rng["high"] = {"value": high, "code": "a", "system": UCUM}
        chars.append({"code": {"coding": [{"system": "http://loinc.org", "code": "30525-0"}]}, "valueRange": rng, "exclude": False})
    return {"resourceType": "Group", "id": gid, "type": "person", "actual": False, "characteristic": chars,
            "meta": {"profile": [P + "group-oah"]}}


def dataset(*resources: dict[str, Any], with_default_location: bool = True) -> Dataset:
    raw: dict[str, dict[str, dict[str, Any]]] = {}
    for r in resources:
        raw.setdefault(r["resourceType"], {})[r["id"]] = r
    if with_default_location:
        raw.setdefault("Location", {}).setdefault("Loc-T", location("Loc-T"))
    src = SourceInfo(kind=SourceKind.FIXTURE, base_url="fixture://", fetched_at="2026-09-30T00:00:00Z")
    return build_dataset(raw, src, KN)


def run(rule_id: str, ds: Dataset) -> list[Any]:
    from datadoctor.rules.registry import run_rule

    return run_rule(rule_id, ds, KN)
