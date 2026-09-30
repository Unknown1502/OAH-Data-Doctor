"""The evidence ladder of a claim: which rung the published data supports, from a deterministic verdict.

    Observation -> Description -> Comparison -> Association -> Causation

Each rung is `supported`, `conditional`, `unsupported`, `blocked` or `not_claimed`. Nothing here decides anything new:
it restates the engine's verdict, reasons and blocking findings per rung, so a reader sees how far the evidence reaches.
"""

from __future__ import annotations

from typing import Any

from datadoctor.domain.enums import ClaimType, ClaimVerdict
from datadoctor.domain.models import ClaimResult

RUNGS = [("observation", "Observation"), ("description", "Description"), ("comparison", "Comparison"),
         ("association", "Association"), ("causation", "Causation")]
CLAIMED_RUNG = {ClaimType.COMPARE_HIGHER: "comparison", ClaimType.TREND_INCREASE: "comparison",
                ClaimType.EXCEEDS_THRESHOLD: "comparison", ClaimType.ASSOCIATION: "association", ClaimType.CAUSAL: "causation"}
STATUS = {ClaimVerdict.SUPPORTED: "supported", ClaimVerdict.CONDITIONAL: "conditional",
          ClaimVerdict.UNSUPPORTED: "unsupported", ClaimVerdict.BLOCKED: "blocked"}


def ladder(r: ClaimResult) -> list[dict[str, Any]]:
    claimed = CLAIMED_RUNG[r.claim.type]
    blocked = r.verdict is ClaimVerdict.BLOCKED and bool(r.blocking_findings)
    first_reason = r.reasons[0] if r.reasons else ""
    out: list[dict[str, Any]] = []
    for key, label in RUNGS:
        if key in ("observation", "description"):
            if not r.inputs:
                status, why = "unsupported", "No published record matches the claim."
            elif blocked:
                status, why = "blocked", f"{len(r.blocking_findings)} integrity finding(s) on the input records; the values cannot be used as published."
            elif key == "observation":
                status, why = "supported", f"{len(r.inputs)} published record(s) found."
            else:
                status, why = "supported", "Each value can be reported as published, with its unit, place and period."
        elif key == claimed:
            status, why = STATUS[r.verdict], first_reason
        elif key == "association" and claimed == "causation":
            fallback = next((t["outcome"] for t in r.rule_trace if t.get("step") == "CLM-CAU-002"), None)
            status = STATUS.get(ClaimVerdict(fallback), "unsupported") if fallback else "unsupported"
            why = next((x for x in r.reasons if x.startswith("Even the weaker association claim")), "")
        else:
            status, why = "not_claimed", ""
        out.append({"level": key, "label": label, "status": status, "why": why, "claimed": key == claimed})
    return out


def highest_supported(rungs: list[dict[str, Any]]) -> str | None:
    """The highest rung the evidence supports (with or without caveats), or None."""
    ok = [r["label"] for r in rungs if r["status"] in ("supported", "conditional")]
    return ok[-1] if ok else None
