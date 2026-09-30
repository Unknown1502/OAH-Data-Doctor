"""Loads the knowledge layer (knowledge/*.yaml|json) into typed, read-only lookups.

The knowledge version is the sha256 of every knowledge file, so each finding records exactly which
plausibility bounds, thresholds and code maps it was judged against.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from datadoctor.domain.enums import Medium


@dataclass(frozen=True)
class IndicatorDef:
    key: str
    label: str
    medium: Medium
    kind: str
    canonical_unit: str


@dataclass(frozen=True)
class Relation:
    a: str
    b: str
    relationship: str
    note: str
    when_codes_differ: bool = False


@dataclass
class Knowledge:
    root: Path
    version: str
    indicators: dict[str, IndicatorDef]
    code_index: dict[tuple[str, str], str]  # (system url, code) -> indicator key
    complements: list[dict[str, Any]]
    subsets: list[dict[str, Any]]
    plausibility: dict[str, Any]
    thresholds: dict[str, dict[str, Any]]
    units_valid: set[str]
    units_invalid: dict[str, dict[str, str]]
    conversions: list[dict[str, Any]]
    relations: list[Relation]
    synonyms: dict[str, Any]
    profile_constraints: dict[str, Any]
    catalog: dict[str, Any]
    ig_instances: set[str]
    ig_commit: str
    codesystem: dict[str, dict[str, Any]]  # code -> {display, definition, fsh_line}
    codesystem_url: str
    upstream_dir: Path
    sources: dict[str, Any] = field(default_factory=dict)

    # -- lookups -------------------------------------------------------------------------------------
    def indicator_for(self, system: str | None, code: str | None) -> IndicatorDef | None:
        if not system or not code:
            return None
        key = self.code_index.get((system, code))
        return self.indicators.get(key) if key else None

    def hard_bounds(self, ind: IndicatorDef) -> dict[str, Any] | None:
        spec = self.plausibility.get("indicators", {}).get(ind.key, {}).get("hard")
        return spec or self.plausibility.get("kinds", {}).get(ind.kind, {}).get("hard")

    def typical_bounds(self, ind: IndicatorDef) -> dict[str, Any] | None:
        return self.plausibility.get("indicators", {}).get(ind.key, {}).get("typical")

    def convert(self, value: float, from_unit: str, to_unit: str) -> tuple[float, dict[str, Any]] | None:
        """Convert with the explicit table only. Returns (value, conversion-record) or None if not convertible."""
        if from_unit == to_unit:
            return value, {"from": from_unit, "to": to_unit, "factor": 1}
        for c in self.conversions:
            if c["from"] == from_unit and c["to"] == to_unit:
                return value * c["factor"] + c.get("offset", 0), c
        return None

    def relation(self, a: str, b: str) -> Relation | None:
        for r in self.relations:
            if (r.a, r.b) in ((a, b), (b, a)):
                return r
        return None

    def normalise_definition(self, text: str) -> str:
        t = text.lower().strip()
        for p in self.synonyms.get("strip_prefixes", []):
            if t.startswith(p.lower()):
                t = t[len(p):]
        for src, dst in self.synonyms.get("replace", {}).items():
            t = re.sub(rf"\b{re.escape(src.lower())}\b", dst.lower(), t)
        return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 >=<.%/-]", " ", t)).strip()


def _read_yaml(path: Path) -> Any:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _version(root: Path) -> str:
    h = hashlib.sha256()
    for p in sorted(root.rglob("*")):
        if p.is_file():
            h.update(p.relative_to(root).as_posix().encode())
            h.update(p.read_bytes().replace(b"\r\n", b"\n"))  # line-ending independent across checkouts
    return h.hexdigest()[:16]


@lru_cache(maxsize=4)
def load_knowledge(root: Path) -> Knowledge:
    reg = _read_yaml(root / "indicators" / "registry.yaml")
    systems = reg["systems"]
    indicators: dict[str, IndicatorDef] = {}
    code_index: dict[tuple[str, str], str] = {}
    for key, spec in reg["indicators"].items():
        indicators[key] = IndicatorDef(key=key, label=spec["label"], medium=Medium(spec["medium"]),
                                       kind=spec["kind"], canonical_unit=spec["canonical_unit"])
        for c in spec["codes"]:
            code_index[(systems[c["system"]], str(c["code"]))] = key

    units = _read_yaml(root / "terminology" / "units.yaml")
    rel = _read_yaml(root / "terminology" / "concept_maps.yaml")
    ig = json.loads((root / "oah" / "ig_instances.json").read_text(encoding="utf-8"))
    cs = json.loads((root / "oah" / "codesystem_temporarySystem-oah-eu.json").read_text(encoding="utf-8"))
    thresholds = _read_yaml(root / "scientific" / "thresholds.yaml")["thresholds"]
    for tid, t in thresholds.items():
        t["id"] = tid

    return Knowledge(
        root=root,
        version=_version(root),
        indicators=indicators,
        code_index=code_index,
        complements=reg.get("complements", []),
        subsets=reg.get("subsets", []),
        plausibility=_read_yaml(root / "scientific" / "plausibility.yaml"),
        thresholds=thresholds,
        units_valid=set(units["valid"]),
        units_invalid=units.get("invalid", {}),
        conversions=units.get("conversions", []),
        relations=[Relation(a=r["a"], b=r["b"], relationship=r["relationship"], note=r.get("note", ""),
                            when_codes_differ=bool(r.get("when_codes_differ", False))) for r in rel["relations"]],
        synonyms=_read_yaml(root / "terminology" / "synonyms.yaml"),
        profile_constraints=_read_yaml(root / "oah" / "profile_constraints.yaml"),
        catalog=_read_yaml(root / "analyses" / "catalog.yaml"),
        ig_instances={i["id"] for i in ig["instances"]},
        ig_commit=ig["commit"],
        codesystem={c["code"]: c for c in cs["concepts"]},
        codesystem_url=cs["url"],
        upstream_dir=root / "oah" / "upstream",
        sources=json.loads((root / "oah" / "sources.json").read_text(encoding="utf-8")),
    )
