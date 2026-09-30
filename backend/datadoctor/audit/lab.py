"""What-if lab: re-run the deterministic rules on an edited COPY of one published observation.

The copy exists only for one request. Nothing is stored, nothing is written to the sandbox, and the published record is
never corrected: the lab shows, interactively, that the rules follow the numbers, and (with `server_validate`) that the
server's FHIR conformance check does not.
"""

from __future__ import annotations

import copy
import math
from typing import Any

from datadoctor.domain.models import Dataset, Finding, canonical_sha256
from datadoctor.knowledge.loader import Knowledge
from datadoctor.normalization.normalizer import normalize_observation
from datadoctor.rules.registry import load_rules, run_all

# Rules that judge one record's own numbers: always listed, fired or not, so the user sees what is being checked.
LAB_RULES = ("SEM-RANGE-001", "SEM-STAT-001", "SEM-STAT-002", "SEM-STAT-003", "SEM-STAT-004", "SEM-STAT-005",
             "SEM-STAT-006", "SEM-SCALE-001", "SEM-RANGE-002")
MAX_ABS = 1e12
_SEVERITY_RANK = {"CRITICAL": 0, "ERROR": 1, "WARNING": 2, "INFO": 3}


class LabError(ValueError):
    pass


def _stat_code(component: dict[str, Any]) -> str | None:
    codings = component.get("code", {}).get("coding", [])
    return codings[0].get("code") if codings else None


def editable_values(raw: dict[str, Any]) -> dict[str, float]:
    """The numbers a user may change: each statistic component, or the single value."""
    out: dict[str, float] = {}
    for comp in raw.get("component", []):
        code, q = _stat_code(comp), comp.get("valueQuantity")
        if code and q and isinstance(q.get("value"), int | float):
            out[code] = q["value"]
    if isinstance(raw.get("valueQuantity", {}).get("value"), int | float):
        out["value"] = raw["valueQuantity"]["value"]
    return out


def _clean(v: Any) -> int | float:
    if isinstance(v, bool) or not isinstance(v, int | float) or not math.isfinite(v) or abs(v) > MAX_ABS:
        raise LabError(f"values must be finite numbers within +-{MAX_ABS:g}")
    return int(v) if float(v).is_integer() and abs(v) < 1e15 else float(v)


def edited_copy(raw: dict[str, Any], values: dict[str, Any]) -> dict[str, Any]:
    allowed = editable_values(raw)
    unknown = sorted(set(values) - set(allowed))
    if unknown:
        raise LabError(f"this record has no editable value named {', '.join(unknown)}")
    res = copy.deepcopy(raw)
    for comp in res.get("component", []):
        code = _stat_code(comp)
        if code in values and comp.get("valueQuantity"):
            comp["valueQuantity"]["value"] = _clean(values[code])
    if "value" in values:
        res["valueQuantity"]["value"] = _clean(values["value"])
    return res


def _worst(findings: list[Finding]) -> str | None:
    return min((f.severity.value for f in findings), key=_SEVERITY_RANK.__getitem__, default=None)


def run_lab(ds: Dataset, kn: Knowledge, published: list[Finding], observation_id: str,
            values: dict[str, Any]) -> tuple[dict[str, Any], Dataset]:
    """Rules on the edited copy vs. the published record. Returns the result and the what-if dataset."""
    raw = ds.raw.get("Observation", {}).get(observation_id)
    if raw is None:
        raise LabError(f"Observation/{observation_id} is not in the current data")
    edited = edited_copy(raw, values)
    key = f"Observation/{observation_id}"
    whatif = ds.model_copy(update={
        "raw": {**ds.raw, "Observation": {**ds.raw["Observation"], observation_id: edited}},
        "observations": {**ds.observations, observation_id: normalize_observation(edited, kn)},
        "resource_sha256": {**ds.resource_sha256, key: canonical_sha256(edited)},
    })
    after = [f for f in run_all(whatif, kn) if f.resource.key == key]
    before = [f for f in published if f.resource.key == key]
    specs = {rid: r.spec for rid, r in load_rules().items()}
    fired_after = {f.rule_id: f for f in after}
    fired_before = {f.rule_id for f in before}
    ids = list(LAB_RULES) + sorted((set(fired_after) | fired_before) - set(LAB_RULES))
    checks = []
    for rid in ids:
        f = fired_after.get(rid)
        spec = specs[rid]
        checks.append({"rule_id": rid, "title": spec.title, "fired": f is not None, "was_fired": rid in fired_before,
                       "severity": f.severity.value if f else None, "summary": f.summary if f else None})
    return {
        "observation_id": observation_id,
        "values": editable_values(edited),
        "published_values": editable_values(raw),
        "changed": editable_values(edited) != editable_values(raw),
        "checks": checks,
        "findings_total": len(after),
        "worst": _worst(after),
        "published_findings_total": len(before),
        "edited_resource": edited,
    }, whatif


def for_server_validation(edited: dict[str, Any]) -> dict[str, Any]:
    """The copy sent to the server's `$validate`. The sandbox holds no OAH StructureDefinitions, so a declared OAH profile
    cannot be resolved there; dropping it validates against base FHIR R4, as the server's own instance check does."""
    res = copy.deepcopy(edited)
    res.get("meta", {}).pop("profile", None)
    return res
