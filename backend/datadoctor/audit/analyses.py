"""Evaluates the analyses catalog (knowledge/analyses/catalog.yaml) for a run: every verdict is recomputed."""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel

from datadoctor.claims.engine import ClaimError, evaluate_claim
from datadoctor.comparability.engine import ComparisonError, compare
from datadoctor.domain.models import ClaimResult, Comparison, Dataset, Finding, StructuredClaim
from datadoctor.knowledge.loader import Knowledge

log = logging.getLogger(__name__)


class CatalogEntry(BaseModel):
    id: str
    title: str
    kind: str
    ok: bool
    error: str | None = None


class AnalysesResult(BaseModel):
    comparisons: list[Comparison]
    claims: list[ClaimResult]
    catalog: list[CatalogEntry]


def run_catalog(ds: Dataset, kn: Knowledge, findings: list[Finding], extra_comparisons: list[dict[str, Any]] | None = None,
                extra_claims: list[dict[str, Any]] | None = None) -> AnalysesResult:
    comparisons: list[Comparison] = []
    claims: list[ClaimResult] = []
    entries: list[CatalogEntry] = []
    for spec in list(kn.catalog.get("comparisons", [])) + list(extra_comparisons or []):
        try:
            comparisons.append(compare(ds, kn, findings, spec["a"]["observation"], spec["b"]["observation"],
                                       spec["a"].get("statistic"), spec["b"].get("statistic"), comparison_id=spec["id"]))
            entries.append(CatalogEntry(id=spec["id"], title=spec.get("title", spec["id"]), kind="comparison", ok=True))
        except ComparisonError as exc:  # the record may be absent from this dataset (e.g. deleted on the server)
            entries.append(CatalogEntry(id=spec["id"], title=spec.get("title", spec["id"]), kind="comparison", ok=False, error=str(exc)))
    for spec in list(kn.catalog.get("claims", [])) + list(extra_claims or []):
        try:
            claims.append(evaluate_claim(StructuredClaim(**spec["claim"]), ds, kn, findings, claim_id=spec["id"]))
            entries.append(CatalogEntry(id=spec["id"], title=spec.get("title", spec["id"]), kind="claim", ok=True))
        except (ClaimError, ComparisonError, KeyError) as exc:
            entries.append(CatalogEntry(id=spec["id"], title=spec.get("title", spec["id"]), kind="claim", ok=False, error=str(exc)))
    return AnalysesResult(comparisons=comparisons, claims=claims, catalog=entries)
