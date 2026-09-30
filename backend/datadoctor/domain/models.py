"""Core domain models.

Rules of this module (see docs/03_ARCHITECTURE.md §Dependency rules):
- no I/O, no HTTP, no SQLite, no LLM — pure data;
- every model is JSON-serialisable and mirrors a schema in schemas/.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from pydantic import BaseModel, Field

from datadoctor.domain.enums import (
    Category,
    ClaimType,
    ClaimVerdict,
    ComparabilityVerdict,
    DimensionStatus,
    Medium,
    Scope,
    Severity,
    SourceKind,
)

# ---------------------------------------------------------------------------
# Provenance
# ---------------------------------------------------------------------------


class SourceInfo(BaseModel):
    """Where a dataset came from. Always shown to the user; snapshot data is never presented as live."""

    kind: SourceKind
    base_url: str
    fetched_at: str  # ISO-8601 UTC of the fetch (live) or of the snapshot creation
    snapshot_id: str | None = None
    manifest_sha256: str | None = None
    fallback_reason: str | None = None  # set when live was requested but a snapshot was served


class Provenance(BaseModel):
    source: SourceInfo
    resource_sha256: str | None = None
    resource_version_id: str | None = None
    resource_last_updated: str | None = None
    rules_version: str
    knowledge_version: str
    ig_source: str


# ---------------------------------------------------------------------------
# Findings
# ---------------------------------------------------------------------------


class ResourceRef(BaseModel):
    resource_type: str
    resource_id: str
    fhir_path: str | None = None
    display: str | None = None

    @property
    def key(self) -> str:
        return f"{self.resource_type}/{self.resource_id}"


class ObservedValue(BaseModel):
    label: str
    value: float | int | str | None
    unit: str | None = None
    fhir_path: str | None = None


class Evidence(BaseModel):
    observed: list[ObservedValue] = Field(default_factory=list)
    constraint: str  # formal statement of what must hold, e.g. "minimum <= median <= maximum"
    expected: str  # plain-language expectation
    measures: dict[str, Any] = Field(default_factory=dict)  # computed quantities (ratios, tolerances...)
    raw_excerpt: dict[str, Any] | list[Any] | None = None


class LineageRecord(BaseModel):
    """Upstream evidence: where the same values appear before FHIR conversion. Never a root-cause claim."""

    source: str
    locator: str
    raw_row: str
    matches: dict[str, bool]
    statement: str


class Finding(BaseModel):
    id: str
    rule_id: str
    rule_version: str
    title: str
    category: Category
    severity: Severity
    confidence: float = Field(ge=0.0, le=1.0)
    confidence_label: str
    scope: Scope
    resource: ResourceRef
    related_resources: list[ResourceRef] = Field(default_factory=list)
    summary: str
    evidence: Evidence
    interpretation: str
    root_cause: str = "unknown"
    hypotheses: list[str] = Field(default_factory=list)
    remediation: str
    lineage: LineageRecord | None = None
    provenance: Provenance | None = None

    @staticmethod
    def make_id(rule_id: str, resource_key: str, discriminator: str = "") -> str:
        digest = hashlib.sha256(f"{rule_id}|{resource_key}|{discriminator}".encode()).hexdigest()[:12]
        return f"F-{rule_id}-{digest}"


def confidence_label(value: float) -> str:
    if value >= 0.85:
        return "high"
    if value >= 0.6:
        return "medium"
    return "low"


# ---------------------------------------------------------------------------
# Normalised FHIR content
# ---------------------------------------------------------------------------


class Quantity(BaseModel):
    value: float | None
    unit: str | None = None
    code: str | None = None
    system: str | None = None
    decimals: int | None = None  # decimal places in the published representation (precision)


class StatComponent(BaseModel):
    """One `Observation.component` carrying a summary statistic (observation-statistics code system)."""

    index: int
    stat: str  # average | median | minimum | maximum | std-dev | ...
    quantity: Quantity

    @property
    def fhir_path(self) -> str:
        return f"Observation.component[{self.index}].valueQuantity"


class Period(BaseModel):
    start: str | None = None
    end: str | None = None

    @property
    def year(self) -> int | None:
        if self.start and self.end and self.start[:4] == self.end[:4]:
            return int(self.start[:4])
        if self.start and not self.end:
            return int(self.start[:4])
        return None

    @property
    def is_annual(self) -> bool:
        return bool(
            self.start and self.end and self.start[5:] in ("", "01-01") and self.end[5:] in ("", "12-31")
            and self.start[:4] == self.end[:4]
        )


class Cohort(BaseModel):
    group_id: str
    sex: str | None = None  # male | female | None (all)
    age_low: float | None = None
    age_high: float | None = None  # None = open-ended
    label: str

    def age_interval(self) -> tuple[float, float]:
        return (self.age_low if self.age_low is not None else 0.0, self.age_high if self.age_high is not None else float("inf"))


class NormalizedObservation(BaseModel):
    id: str
    scope: Scope
    profiles: list[str]
    code_system: str | None
    code: str | None
    code_display: str | None
    code_text: str | None
    indicator_key: str | None  # canonical measure key from knowledge/indicators/registry.yaml
    medium: Medium
    subject_ref: str | None
    focus_refs: list[str] = Field(default_factory=list)
    performer: list[str] = Field(default_factory=list)
    device_ref: str | None = None
    method: str | None = None
    effective_period: Period | None = None
    effective_datetime: str | None = None
    value: Quantity | None = None
    value_text: str | None = None
    stats: list[StatComponent] = Field(default_factory=list)
    other_components: int = 0
    raw: dict[str, Any]

    @property
    def key(self) -> str:
        return f"Observation/{self.id}"

    def stat(self, name: str) -> StatComponent | None:
        for s in self.stats:
            if s.stat == name:
                return s
        return None

    @property
    def year(self) -> int | None:
        if self.effective_period:
            return self.effective_period.year
        if self.effective_datetime:
            return int(self.effective_datetime[:4])
        return None


class NormalizedLocation(BaseModel):
    id: str
    scope: Scope
    name: str | None
    latitude: float | None
    longitude: float | None
    part_of: str | None
    raw: dict[str, Any]


class NormalizedLibrary(BaseModel):
    id: str
    scope: Scope
    title: str | None
    declared_size: float | None
    declared_records: int | None
    member_refs: list[str]
    raw: dict[str, Any]


class Dataset(BaseModel):
    """Everything one audit run sees: raw resources + normalised views + the source it came from."""

    source: SourceInfo
    raw: dict[str, dict[str, dict[str, Any]]]  # resourceType -> id -> raw JSON
    observations: dict[str, NormalizedObservation]
    locations: dict[str, NormalizedLocation]
    groups: dict[str, Cohort]
    libraries: dict[str, NormalizedLibrary]
    resource_sha256: dict[str, str]  # "Type/id" -> sha256 of canonical JSON
    server_validation: dict[str, Any] = Field(default_factory=dict)  # "Type/id" -> OperationOutcome from $validate
    upstream_files: dict[str, str] = Field(default_factory=dict)  # logical name -> file text (e.g. IG source CSV)

    def resolve(self, reference: str) -> dict[str, Any] | None:
        if "/" not in reference:
            return None
        rtype, rid = reference.split("/", 1)
        return self.raw.get(rtype, {}).get(rid)

    def counts(self) -> dict[str, int]:
        return {t: len(v) for t, v in sorted(self.raw.items())}


def canonical_sha256(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


# ---------------------------------------------------------------------------
# Comparability
# ---------------------------------------------------------------------------


class IndicatorDescriptor(BaseModel):
    """A comparable unit: one observation (optionally one statistic of it), described in researcher terms."""

    observation_id: str
    statistic: str | None = None  # for component observations: which summary statistic is being compared
    label: str
    indicator_key: str | None
    measure_label: str | None
    medium: Medium
    unit: str | None
    value: float | None
    location_id: str | None
    location_name: str | None
    cohort: Cohort | None
    period: Period | None
    aggregation: str
    method: str | None


class DimensionResult(BaseModel):
    dimension: str
    rule_id: str
    status: DimensionStatus
    reason: str
    details: dict[str, Any] = Field(default_factory=dict)


class Comparison(BaseModel):
    id: str
    a: IndicatorDescriptor
    b: IndicatorDescriptor
    verdict: ComparabilityVerdict
    dimensions: list[DimensionResult]
    blocking_findings: list[str] = Field(default_factory=list)
    transformations: list[str] = Field(default_factory=list)
    supported_alternatives: list[str] = Field(default_factory=list)
    summary: str


# ---------------------------------------------------------------------------
# Claims
# ---------------------------------------------------------------------------


class StructuredClaim(BaseModel):
    type: ClaimType
    subject: str | None = None  # observation id (A) or series key
    object: str | None = None  # observation id (B) for COMPARE_HIGHER / ASSOCIATION outcome
    statistic: str | None = None
    location_id: str | None = None
    indicator_key: str | None = None
    outcome_indicator_key: str | None = None
    threshold_id: str | None = None
    year_from: int | None = None
    year_to: int | None = None
    text: str | None = None  # the original natural-language text, if any


class ClaimResult(BaseModel):
    id: str
    claim: StructuredClaim
    claim_rendered: str
    verdict: ClaimVerdict
    reasons: list[str]
    rule_trace: list[dict[str, Any]]
    blocking_findings: list[str] = Field(default_factory=list)
    comparison: Comparison | None = None
    statistics: dict[str, Any] = Field(default_factory=dict)
    safe_alternatives: list[str] = Field(default_factory=list)
    inputs: list[str] = Field(default_factory=list)  # observation keys consumed
    ladder: list[dict[str, Any]] = Field(default_factory=list)  # evidence ladder, restated from the verdict (claims/ladder.py)
    supported_up_to: str | None = None  # highest rung the evidence supports, e.g. "Description"
