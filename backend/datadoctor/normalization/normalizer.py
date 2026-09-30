"""Raw FHIR -> typed internal models.

Never drops information: every normalised object keeps `raw` (the untouched resource) for evidence.
Never corrects values: numbers are carried exactly as published, with their published decimal precision.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from datadoctor.domain.enums import Medium, Scope
from datadoctor.domain.models import (
    Cohort,
    Dataset,
    NormalizedLibrary,
    NormalizedLocation,
    NormalizedObservation,
    Period,
    Quantity,
    SourceInfo,
    StatComponent,
    canonical_sha256,
)
from datadoctor.knowledge.loader import Knowledge

STATS_SYSTEM = "http://terminology.hl7.org/CodeSystem/observation-statistics"
LOINC_SEX = "46098-0"
LOINC_AGE = "30525-0"


def decimals_of(value: float | int | None) -> int | None:
    """Decimal places of a published number (19.8 -> 1, 198000 -> 0, 0.0057 -> 4)."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return 0
    exp = Decimal(repr(value)).as_tuple().exponent
    return max(0, -int(exp)) if isinstance(exp, int) else None


def to_quantity(q: dict[str, Any] | None) -> Quantity | None:
    if q is None:
        return None
    v = q.get("value")
    return Quantity(value=float(v) if v is not None else None, unit=q.get("unit"), code=q.get("code"),
                    system=q.get("system"), decimals=decimals_of(v))


def scope_of(resource_id: str, kn: Knowledge) -> Scope:
    return Scope.OAH_IG if resource_id in kn.ig_instances else Scope.THIRD_PARTY


def _concept_text(cc: dict[str, Any] | None) -> str | None:
    if not cc:
        return None
    if cc.get("text"):
        return str(cc["text"])
    for c in cc.get("coding", []):
        if c.get("display") or c.get("code"):
            return str(c.get("display") or c.get("code"))
    return None


def normalize_observation(raw: dict[str, Any], kn: Knowledge) -> NormalizedObservation:
    codings = raw.get("code", {}).get("coding", [])
    chosen = next((c for c in codings if kn.indicator_for(c.get("system"), c.get("code"))), codings[0] if codings else {})
    ind = kn.indicator_for(chosen.get("system"), chosen.get("code"))

    stats: list[StatComponent] = []
    other = 0
    for i, comp in enumerate(raw.get("component", [])):
        ccodes = comp.get("code", {}).get("coding", [])
        stat = next((c.get("code") for c in ccodes if c.get("system") == STATS_SYSTEM), None)
        if stat and "valueQuantity" in comp:
            q = to_quantity(comp["valueQuantity"])
            if q is not None:
                stats.append(StatComponent(index=i, stat=stat, quantity=q))
        else:
            other += 1

    period = None
    if "effectivePeriod" in raw:
        period = Period(start=raw["effectivePeriod"].get("start"), end=raw["effectivePeriod"].get("end"))

    performers = [p.get("display") or p.get("reference") or "" for p in raw.get("performer", [])]
    value_text = None
    if "valueCodeableConcept" in raw:
        value_text = _concept_text(raw["valueCodeableConcept"])
    elif "valueString" in raw:
        value_text = raw["valueString"]

    return NormalizedObservation(
        id=raw["id"],
        scope=scope_of(raw["id"], kn),
        profiles=raw.get("meta", {}).get("profile", []),
        code_system=chosen.get("system"),
        code=chosen.get("code"),
        code_display=chosen.get("display"),
        code_text=raw.get("code", {}).get("text"),
        indicator_key=ind.key if ind else None,
        medium=ind.medium if ind else Medium.UNKNOWN,
        subject_ref=raw.get("subject", {}).get("reference"),
        focus_refs=[f.get("reference") for f in raw.get("focus", []) if f.get("reference")],
        performer=[p for p in performers if p],
        device_ref=(raw.get("device") or {}).get("reference"),
        method=_concept_text(raw.get("method")),
        effective_period=period,
        effective_datetime=raw.get("effectiveDateTime"),
        value=to_quantity(raw.get("valueQuantity")),
        value_text=value_text,
        stats=stats,
        other_components=other,
        raw=raw,
    )


def normalize_group(raw: dict[str, Any]) -> Cohort:
    sex = None
    low = high = None
    parts = []
    for ch in raw.get("characteristic", []):
        if ch.get("exclude"):
            continue  # exclusion criteria are not used by OAH cohorts (DISCOVERY.md D4); kept in raw
        codes = {c.get("code") for c in ch.get("code", {}).get("coding", [])}
        if LOINC_SEX in codes:
            vcc = ch.get("valueCodeableConcept", {})
            sex = next((c.get("code") for c in vcc.get("coding", [])), None)
        if LOINC_AGE in codes and "valueRange" in ch:
            rng = ch["valueRange"]
            low = rng.get("low", {}).get("value")
            high = rng.get("high", {}).get("value")
    if sex:
        parts.append(sex.capitalize())
    if low is not None and high is not None:
        parts.append(f"{low:g}-{high:g} y")
    elif low not in (None, 0):
        parts.append(f"{low:g}+ y")
    label = ", ".join(parts) if parts else "All persons"
    return Cohort(group_id=raw["id"], sex=sex, age_low=low, age_high=high, label=label)


def normalize_location(raw: dict[str, Any], kn: Knowledge) -> NormalizedLocation:
    pos = raw.get("position") or {}
    return NormalizedLocation(id=raw["id"], scope=scope_of(raw["id"], kn), name=raw.get("name"),
                              latitude=pos.get("latitude"), longitude=pos.get("longitude"),
                              part_of=(raw.get("partOf") or {}).get("reference"), raw=raw)


def normalize_library(raw: dict[str, Any], kn: Knowledge) -> NormalizedLibrary:
    size = records = None
    for ext in raw.get("extension", []):
        if ext.get("url", "").endswith("/library-size"):
            size = ext.get("valueQuantity", {}).get("value")
        if ext.get("url", "").endswith("/library-numberOfRecords"):
            records = ext.get("valueInteger")
    members = [c["url"] for c in raw.get("content", []) if isinstance(c.get("url"), str) and "/" in c["url"]
               and not c["url"].startswith("http")]
    return NormalizedLibrary(id=raw["id"], scope=scope_of(raw["id"], kn), title=raw.get("title"),
                             declared_size=size, declared_records=records, member_refs=members, raw=raw)


def build_dataset(raw: dict[str, dict[str, dict[str, Any]]], source: SourceInfo, kn: Knowledge,
                  server_validation: dict[str, Any] | None = None) -> Dataset:
    obs = {i: normalize_observation(r, kn) for i, r in raw.get("Observation", {}).items()}
    locs = {i: normalize_location(r, kn) for i, r in raw.get("Location", {}).items()}
    groups = {i: normalize_group(r) for i, r in raw.get("Group", {}).items()}
    libs = {i: normalize_library(r, kn) for i, r in raw.get("Library", {}).items()}
    hashes = {f"{t}/{i}": canonical_sha256(r) for t, rs in raw.items() for i, r in rs.items()}
    upstream = {}
    for p in sorted(kn.upstream_dir.glob("*.csv")):
        upstream[p.name] = p.read_text(encoding="utf-8-sig")
    return Dataset(source=source, raw=raw, observations=obs, locations=locs, groups=groups, libraries=libs,
                   resource_sha256=hashes, server_validation=server_validation or {}, upstream_files=upstream)
