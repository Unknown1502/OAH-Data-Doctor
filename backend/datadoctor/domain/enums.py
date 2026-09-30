"""Closed vocabularies used across the domain. Values are part of the public JSON contract (schemas/)."""

from enum import Enum


class Severity(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"

    @property
    def rank(self) -> int:
        return ["INFO", "WARNING", "ERROR", "CRITICAL"].index(self.value)


class Category(str, Enum):
    STRUCTURAL = "STRUCTURAL"
    SEMANTIC = "SEMANTIC"
    STATISTICAL = "STATISTICAL"
    COMPARABILITY = "COMPARABILITY"
    CLAIM = "CLAIM"


class SourceKind(str, Enum):
    LIVE = "live"
    SNAPSHOT = "snapshot"
    FIXTURE = "fixture"


class Scope(str, Enum):
    """Whether a resource is an official OAH IG example or was written to the shared sandbox by a third party."""

    OAH_IG = "oah-ig"
    THIRD_PARTY = "third-party"


class Medium(str, Enum):
    WATER = "water"
    AIR = "air"
    POPULATION_HEALTH = "population-health"
    FIELD_ASSESSMENT = "field-assessment"
    UNKNOWN = "unknown"


class ComparabilityVerdict(str, Enum):
    DIRECT = "DIRECT"
    CONDITIONAL = "CONDITIONAL"
    NOT = "NOT"
    BLOCKED_BY_INTEGRITY = "BLOCKED_BY_INTEGRITY"


class DimensionStatus(str, Enum):
    PASS = "PASS"
    CONDITIONAL = "CONDITIONAL"
    FAIL = "FAIL"
    NOT_APPLICABLE = "N/A"


class ClaimType(str, Enum):
    COMPARE_HIGHER = "COMPARE_HIGHER"
    TREND_INCREASE = "TREND_INCREASE"
    EXCEEDS_THRESHOLD = "EXCEEDS_THRESHOLD"
    ASSOCIATION = "ASSOCIATION"
    CAUSAL = "CAUSAL"


class ClaimVerdict(str, Enum):
    SUPPORTED = "SUPPORTED"
    CONDITIONAL = "CONDITIONAL"
    UNSUPPORTED = "UNSUPPORTED"
    BLOCKED = "BLOCKED"
