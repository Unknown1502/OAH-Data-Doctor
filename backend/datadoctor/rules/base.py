"""Rule framework: specs, registry, precision-aware numeric helpers and the finding factory.

A rule is a pure function of (Dataset, Knowledge) -> list[Finding]. Rules never mutate the dataset,
never perform I/O and never call an LLM. Each rule declares its severity logic, confidence logic and
applicability in its RuleSpec (rendered into docs/04_RULES_CATALOG.md and GET /api/rules).
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass, field
from typing import Any

from datadoctor.domain.enums import Category, Scope, Severity
from datadoctor.domain.models import (
    Dataset,
    Evidence,
    Finding,
    NormalizedObservation,
    ObservedValue,
    Provenance,
    ResourceRef,
    StatComponent,
    confidence_label,
)
from datadoctor.knowledge.loader import Knowledge

REMEDIATION_REVIEW = ("Do not use these values in analysis until the data owner has reviewed the source record. "
                      "Data Doctor never corrects values automatically.")


@dataclass(frozen=True)
class RuleSpec:
    id: str
    version: str
    title: str
    category: Category
    severity: str  # human description of severity logic, e.g. "ERROR; CRITICAL if off by >= 10x"
    confidence: str  # human description of confidence logic
    applies_to: str
    constraint: str
    rationale: str
    references: tuple[str, ...] = field(default_factory=tuple)

    def as_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["category"] = self.category.value
        d["references"] = list(self.references)
        return d


RuleFn = Callable[["RuleContext"], Iterable[Finding]]


@dataclass(frozen=True)
class Rule:
    spec: RuleSpec
    fn: RuleFn

    def evaluate(self, ctx: RuleContext) -> list[Finding]:
        return list(self.fn(ctx))


REGISTRY: dict[str, Rule] = {}


def rule(spec: RuleSpec) -> Callable[[RuleFn], RuleFn]:
    def deco(fn: RuleFn) -> RuleFn:
        if spec.id in REGISTRY:
            raise ValueError(f"duplicate rule id {spec.id}")
        REGISTRY[spec.id] = Rule(spec, fn)
        return fn

    return deco


def rules_version() -> str:
    """Hash of every registered rule spec: changes whenever a rule's contract changes."""
    specs = sorted((r.spec.as_dict() for r in REGISTRY.values()), key=lambda d: d["id"])
    return hashlib.sha256(json.dumps(specs, sort_keys=True).encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------------------------------
# Precision-aware numerics
# ---------------------------------------------------------------------------------------------------


def record_decimals(obs: NormalizedObservation) -> int:
    ds = [s.quantity.decimals for s in obs.stats if s.quantity.decimals is not None]
    return max(ds) if ds else 0


def tolerance(value: float | None, decimals: int | None, record_dec: int = 0) -> float:
    """Half a unit in the last published decimal place.

    A published 19.8 stands for any true value in [19.75, 19.85). JSON serialisation drops trailing zeros,
    so an exact zero carries no precision information; for zero we fall back to the record's finest precision.
    Non-zero integers keep +-0.5 (the conservative choice: larger tolerance, fewer false positives).
    """
    if value is None:
        return 0.0
    d = decimals if decimals is not None else 0
    if value == 0:
        d = max(d, record_dec)
    return 0.5 * 10 ** (-d)


def stat_tol(s: StatComponent | None, record_dec: int) -> float:
    if s is None:
        return 0.0
    return tolerance(s.quantity.value, s.quantity.decimals, record_dec)


def order_factor(a: float, b: float) -> float | None:
    """How many times larger the larger of two positive numbers is. None if either is <= 0."""
    if a <= 0 or b <= 0:
        return None
    return max(a, b) / min(a, b)


def power_of_ten_signature(factor: float | None) -> dict[str, Any]:
    if factor is None or factor < 10:
        return {"exact_power_of_ten": False}
    lg = math.log10(factor)
    k = round(lg)
    return {"log10_factor": round(lg, 4), "exact_power_of_ten": k >= 1 and abs(lg - k) < 0.02, "k": k}


def fmt(v: float | int | None) -> str:
    if v is None:
        return "—"
    if isinstance(v, float) and v.is_integer() and abs(v) < 1e15:
        return f"{int(v):,}"
    if isinstance(v, float) and abs(v) >= 1e6:  # "1,676,332.35", never "1.67633e+06", in text people read
        return f"{v:,.2f}".rstrip("0").rstrip(".")
    return f"{v:,.6g}" if isinstance(v, float) else f"{v:,}"


# ---------------------------------------------------------------------------------------------------
# Context & factory
# ---------------------------------------------------------------------------------------------------


@dataclass
class RuleContext:
    ds: Dataset
    kn: Knowledge
    rules_version: str

    def observations(self, *, only_stats: bool = False) -> list[NormalizedObservation]:
        obs = sorted(self.ds.observations.values(), key=lambda o: o.id)
        return [o for o in obs if o.stats] if only_stats else obs

    def unit_of(self, obs: NormalizedObservation) -> str | None:
        units = {s.quantity.code for s in obs.stats if s.quantity.code} | ({obs.value.code} if obs.value and obs.value.code else set())
        return units.pop() if len(units) == 1 else None

    def display(self, obs: NormalizedObservation) -> str:
        label = self.kn.indicators[obs.indicator_key].label if obs.indicator_key else (obs.code_text or obs.code_display or obs.code or "Observation")
        loc_id = (obs.subject_ref or "").split("/")[-1]
        loc = self.ds.locations.get(loc_id)
        where = loc.name if loc and loc.name else loc_id
        parts = [label, where]
        if obs.focus_refs:
            g = self.ds.groups.get(obs.focus_refs[0].split("/")[-1])
            if g:
                parts.append(g.label)
        if obs.year:
            parts.append(str(obs.year) if (obs.effective_period and obs.effective_period.is_annual) else (obs.effective_datetime or str(obs.year)))
        return ", ".join(p for p in parts if p)

    def make(
        self,
        spec: RuleSpec,
        *,
        resource: ResourceRef,
        severity: Severity,
        confidence: float,
        summary: str,
        evidence: Evidence,
        interpretation: str,
        discriminator: str = "",
        related: list[ResourceRef] | None = None,
        hypotheses: list[str] | None = None,
        remediation: str = REMEDIATION_REVIEW,
        scope: Scope | None = None,
    ) -> Finding:
        key = resource.key
        raw_type, raw_id = resource.resource_type, resource.resource_id
        raw = self.ds.raw.get(raw_type, {}).get(raw_id)
        meta = (raw or {}).get("meta", {})
        if scope is None:
            scope = Scope.OAH_IG if raw_id in self.kn.ig_instances else Scope.THIRD_PARTY
            if related and scope is Scope.THIRD_PARTY and any(r.resource_id in self.kn.ig_instances for r in related):
                scope = Scope.OAH_IG
        return Finding(
            id=Finding.make_id(spec.id, key, discriminator),
            rule_id=spec.id,
            rule_version=spec.version,
            title=spec.title,
            category=spec.category,
            severity=severity,
            confidence=round(confidence, 3),
            confidence_label=confidence_label(confidence),
            scope=scope,
            resource=resource,
            related_resources=related or [],
            summary=summary,
            evidence=evidence,
            interpretation=interpretation,
            hypotheses=hypotheses or [],
            remediation=remediation,
            provenance=Provenance(
                source=self.ds.source,
                resource_sha256=self.ds.resource_sha256.get(key),
                resource_version_id=meta.get("versionId"),
                resource_last_updated=meta.get("lastUpdated"),
                rules_version=self.rules_version,
                knowledge_version=self.kn.version,
                ig_source=f"https://github.com/hl7-eu/oah@{self.kn.ig_commit[:12]}",
            ),
        )


def obs_ref(obs: NormalizedObservation, path: str | None = None, display: str | None = None) -> ResourceRef:
    return ResourceRef(resource_type="Observation", resource_id=obs.id, fhir_path=path, display=display)


def observed(s: StatComponent) -> ObservedValue:
    return ObservedValue(label=s.stat, value=s.quantity.value, unit=s.quantity.code or s.quantity.unit, fhir_path=s.fhir_path)


def stats_excerpt(obs: NormalizedObservation) -> list[dict[str, Any]]:
    return [obs.raw["component"][s.index] for s in obs.stats]
