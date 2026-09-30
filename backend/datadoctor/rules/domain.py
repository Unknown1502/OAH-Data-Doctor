"""Domain-knowledge rules: physics, definitions and terminology that FHIR conformance cannot see.

Principle: unusual != impossible. SEM-RANGE-001 (CRITICAL) fires only outside physical/definitional bounds;
SEM-RANGE-002 (WARNING) reports values that are merely unusual, with the reason they could still be real.
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterator
from itertools import combinations

from datadoctor.domain.enums import Category, Severity
from datadoctor.domain.models import Evidence, Finding, NormalizedObservation, ObservedValue, ResourceRef
from datadoctor.knowledge.loader import IndicatorDef
from datadoctor.rules.base import RuleContext, RuleSpec, fmt, obs_ref, record_decimals, rule, tolerance

LEVEL_STATS = ("minimum", "maximum", "average", "median")


def lower_label(label: str) -> str:
    """'Water temperature' -> 'water temperature', but keep acronyms such as 'pH' or 'PM10' intact."""
    return label if len(label) > 1 and label[1].isupper() else label[:1].lower() + label[1:]


def _levels(ctx: RuleContext, obs: NormalizedObservation, ind: IndicatorDef) -> tuple[list[tuple[str, float, float, str | None]], str]:
    """(label, canonical value, canonical tolerance, fhir_path) for every level value; plus a note on unit handling."""
    rd = record_decimals(obs)
    items = []
    if obs.value is not None and obs.value.value is not None:
        items.append(("value", obs.value.value, obs.value.decimals, obs.value.code, "Observation.valueQuantity"))
    for s in obs.stats:
        if s.stat in LEVEL_STATS and s.quantity.value is not None:
            items.append((s.stat, s.quantity.value, s.quantity.decimals, s.quantity.code, s.fhir_path))
    out = []
    note = ""
    for label, v, dec, code, path in items:
        unit = code
        if unit == "pH":
            unit = "[pH]"
        if unit is None and ind.canonical_unit == "[pH]":
            unit = "[pH]"
            note = "unit code missing; pH scale assumed (pH has no other unit)"
        if unit is None:
            continue
        conv = ctx.kn.convert(v, unit, ind.canonical_unit)
        if conv is None:
            continue
        cv, rec = conv
        tol = tolerance(v, dec, rd) * abs(rec.get("factor", 1))
        out.append((label, cv, tol, path))
    return out, note


SPEC_R1 = RuleSpec(
    id="SEM-RANGE-001", version="1.0", title="Physically or definitionally impossible value",
    category=Category.SEMANTIC, severity="CRITICAL",
    confidence="0.97 — bounds are physical limits (e.g. liquid water cannot exceed 100 C) or definitions (0-100 %)",
    applies_to="Observations whose code maps to an indicator with hard bounds (knowledge/scientific/plausibility.yaml)",
    constraint="hard.min <= value <= hard.max, after explicit unit conversion to the canonical unit",
    rationale="Values outside hard bounds cannot be real measurements of the stated quantity.",
)
SPEC_R2 = RuleSpec(
    id="SEM-RANGE-002", version="1.0", title="Unusual value (possible, but outside the typical range)",
    category=Category.SEMANTIC, severity="WARNING",
    confidence="0.6 — typical ranges describe common conditions, not limits",
    applies_to="Indicators with a documented typical range; not reported when SEM-RANGE-001 already fires",
    constraint="typical.min <= value <= typical.max",
    rationale="Unusual is not impossible: the finding asks for confirmation and states why the value may be real.",
)


def _range(ctx: RuleContext, spec: RuleSpec, hard: bool) -> Iterator[Finding]:
    for obs in ctx.observations():
        ind = ctx.kn.indicators.get(obs.indicator_key or "")
        if ind is None:
            continue
        levels, note = _levels(ctx, obs, ind)
        hb = ctx.kn.hard_bounds(ind)
        bounds = hb if hard else ctx.kn.typical_bounds(ind)
        if not bounds or not levels:
            continue

        def outside(lv: tuple[str, float, float, str | None], b: dict | None) -> bool:
            if not b:
                return False
            _, v, tol, _ = lv
            return ("min" in b and v < b["min"] - tol) or ("max" in b and v > b["max"] + tol)

        bad = [lv for lv in levels if outside(lv, bounds)]
        if not bad:
            continue
        if not hard and any(outside(lv, hb) for lv in levels):
            continue  # impossible values are SEM-RANGE-001's finding
        lo, hi = bounds.get("min"), bounds.get("max")
        rng = f"{fmt(lo) if lo is not None else '-inf'} to {fmt(hi) if hi is not None else '+inf'} {ind.canonical_unit}"
        vals = ", ".join(f"{lab} {fmt(v)}" for lab, v, _, _ in bad)
        yield ctx.make(
            spec,
            resource=obs_ref(obs, bad[0][3], ctx.display(obs)),
            severity=Severity.CRITICAL if hard else Severity.WARNING,
            confidence=0.97 if hard else 0.6,
            summary=(f"{ctx.display(obs)}: {vals} {ind.canonical_unit} — "
                     + (f"impossible for {lower_label(ind.label)} (possible range {rng})." if hard else
                        f"unusual for {lower_label(ind.label)} (typical {rng}), but not impossible.")),
            evidence=Evidence(
                observed=[ObservedValue(label=lab, value=v, unit=ind.canonical_unit, fhir_path=p) for lab, v, _, p in bad],
                constraint=f"{ind.label} within {rng}",
                expected=bounds.get("rationale", ""),
                measures={"bounds": {k: v for k, v in bounds.items() if k != "rationale"}, "canonical_unit": ind.canonical_unit,
                          "unit_note": note or "values converted with the explicit table in knowledge/terminology/units.yaml"},
                raw_excerpt=obs.raw.get("valueQuantity") or [obs.raw["component"][s.index] for s in obs.stats][:5],
            ),
            interpretation=("Impossible value for this quantity (root cause unknown)." if hard else
                            "Unusual value: confirm with the data owner before treating it as an error."),
            remediation=("Exclude from analysis until the data owner confirms the value. " if hard else
                         "Confirm the site conditions (e.g. brackish or saline water) with the data owner. ")
                        + "Data Doctor never corrects values automatically.",
        )


@rule(SPEC_R1)
def impossible_values(ctx: RuleContext) -> Iterator[Finding]:
    yield from _range(ctx, SPEC_R1, hard=True)


@rule(SPEC_R2)
def unusual_values(ctx: RuleContext) -> Iterator[Finding]:
    yield from _range(ctx, SPEC_R2, hard=False)


SPEC_DEF = RuleSpec(
    id="SEM-DEF-001", version="1.0", title="Indicator definition contradicts the published unit",
    category=Category.SEMANTIC, severity="WARNING",
    confidence="0.9 — the contradiction is textual and explicit in the CodeSystem",
    applies_to="Observations coded with the OAH temporary CodeSystem; one finding for the whole CodeSystem",
    constraint="a concept defined as a rate 'per 100,000 inhabitants' is not published in '%' (per 100)",
    rationale="A share per 100 and a rate per 100,000 differ by a factor of 1,000; a reader cannot know which applies.",
)
_PER_100K = re.compile(r"per\s*100[.,\s]?000", re.I)


@rule(SPEC_DEF)
def definition_unit_contradiction(ctx: RuleContext) -> Iterator[Finding]:
    affected: dict[str, list[NormalizedObservation]] = defaultdict(list)
    for obs in ctx.observations():
        if obs.code_system != ctx.kn.codesystem_url or obs.code not in ctx.kn.codesystem:
            continue
        concept = ctx.kn.codesystem[obs.code]
        if _PER_100K.search(concept.get("definition", "")) and obs.value is not None and obs.value.code == "%":
            affected[obs.code].append(obs)
    if not affected:
        return
    all_obs = [o for obs_list in affected.values() for o in obs_list]
    codes = sorted(affected)
    example = ctx.kn.codesystem[codes[0]]
    yield ctx.make(
        SPEC_DEF,
        resource=ResourceRef(resource_type="CodeSystem", resource_id="temporarySystem-oah-eu",
                             fhir_path=f"CodeSystem.concept.where(code='{codes[0]}').definition",
                             display="Temporary OAH Code System"),
        related=[obs_ref(o) for o in sorted(all_obs, key=lambda o: o.id)],
        severity=Severity.WARNING, confidence=0.9,
        summary=(f"{len(codes)} health indicators ({len(all_obs)} observations) are defined as 'cases per 100,000 "
                 f"inhabitants' in the OAH CodeSystem but every value is published in '%'. Per-100 and per-100,000 "
                 f"differ by a factor of 1,000."),
        evidence=Evidence(
            observed=[ObservedValue(label=c, value=ctx.kn.codesystem[c]["definition"][:160]) for c in codes[:6]],
            constraint="concept definition unit == published unit",
            expected="A percentage indicator is defined as a percentage.",
            measures={"codes": codes, "observations": len(all_obs),
                      "example_definition": example["definition"], "fsh_line": example.get("fsh_line")},
        ),
        interpretation="Ambiguous indicator definition: which denominator applies cannot be determined from the data.",
        remediation="Ask the IG authors to align concept definitions with the published unit.",
    )


SPEC_CODE = RuleSpec(
    id="SEM-CODE-001", version="1.0", title="Near-synonymous indicators report different values",
    category=Category.SEMANTIC, severity="WARNING",
    confidence="0.8 — synonymy is decided by deterministic text normalisation (knowledge/terminology/synonyms.yaml)",
    applies_to="Pairs of codes in the OAH CodeSystem whose normalised displays are identical",
    constraint="for the same site, cohort and period, synonymous indicators report the same value (within rounding)",
    rationale="Two indicators that read the same but disagree leave a researcher unable to pick the right one.",
)


@rule(SPEC_CODE)
def near_synonyms(ctx: RuleContext) -> Iterator[Finding]:
    used = sorted({o.code for o in ctx.observations() if o.code_system == ctx.kn.codesystem_url and o.code in ctx.kn.codesystem})
    by_norm: dict[str, list[str]] = defaultdict(list)
    for c in used:
        by_norm[ctx.kn.normalise_definition(ctx.kn.codesystem[c]["display"])].append(c)
    index: dict[tuple[str, str, tuple[str, ...], int | None], NormalizedObservation] = {}
    for o in ctx.observations():
        if o.code and o.value is not None and o.value.value is not None:
            index[(o.code, o.subject_ref or "", tuple(o.focus_refs), o.year)] = o
    for norm, codes in sorted(by_norm.items()):
        for c1, c2 in combinations(sorted(codes), 2):
            pairs, divergent = 0, []
            for (code, subj, focus, year), o1 in sorted(index.items()):
                if code != c1:
                    continue
                o2 = index.get((c2, subj, focus, year))
                if o2 is None or o1.value is None or o2.value is None:
                    continue
                pairs += 1
                v1, v2 = o1.value.value or 0.0, o2.value.value or 0.0
                if abs(v1 - v2) > tolerance(v1, o1.value.decimals) + tolerance(v2, o2.value.decimals):
                    divergent.append((o1, o2))
            if not divergent:
                continue
            first = divergent[0]
            yield ctx.make(
                SPEC_CODE,
                resource=ResourceRef(resource_type="CodeSystem", resource_id="temporarySystem-oah-eu",
                                     fhir_path=f"CodeSystem.concept.where(code='{c1}' or code='{c2}')",
                                     display=f"#{c1} vs #{c2}"),
                related=[obs_ref(o) for pair in divergent for o in pair],
                discriminator=f"{c1}|{c2}", severity=Severity.WARNING, confidence=0.8,
                summary=(f"'{ctx.kn.codesystem[c1]['display']}' (#{c1}) and '{ctx.kn.codesystem[c2]['display']}' (#{c2}) "
                         f"read as the same indicator, yet disagree in {len(divergent)} of {pairs} matched site/cohort/period "
                         f"pairs (e.g. {fmt(first[0].value.value if first[0].value else None)}% vs "
                         f"{fmt(first[1].value.value if first[1].value else None)}%)."),
                evidence=Evidence(
                    observed=[ObservedValue(label=f"{ctx.display(a)} (#{c1} vs #{c2})",
                                            value=f"{fmt(a.value.value if a.value else None)} vs {fmt(b.value.value if b.value else None)}")
                              for a, b in divergent[:8]],
                    constraint="synonymous definitions -> equal values",
                    expected="Indicators with the same meaning report the same number.",
                    measures={"normalised_definition": norm, "matched_pairs": pairs, "divergent_pairs": len(divergent)},
                ),
                interpretation="Two indicators appear to measure the same construct but disagree; the distinction is undocumented.",
                remediation="Ask the IG authors to document how the two definitions differ, or merge them.",
            )


SPEC_SPATIAL = RuleSpec(
    id="SEM-SPATIAL-001", version="1.0", title="Distinct sites share identical coordinates",
    category=Category.SEMANTIC, severity="WARNING",
    confidence="0.85 — could be a deliberate placeholder, which is itself worth documenting",
    applies_to="Location resources with a position; parent/child (partOf) pairs are excluded",
    constraint="distinct monitoring sites have distinct positions (5 decimal places, ~1 m)",
    rationale="Spatial analyses (distance to exposure, mapping, spatial joins) cannot distinguish these sites.",
)


@rule(SPEC_SPATIAL)
def shared_coordinates(ctx: RuleContext) -> Iterator[Finding]:
    clusters: dict[tuple[float, float], list[str]] = defaultdict(list)
    for loc in sorted(ctx.ds.locations.values(), key=lambda x: x.id):
        if loc.latitude is None or loc.longitude is None:
            continue
        clusters[(round(loc.latitude, 5), round(loc.longitude, 5))].append(loc.id)
    for (lat, lon), ids in sorted(clusters.items()):
        parents = {ctx.ds.locations[i].part_of for i in ids}
        distinct = [i for i in ids if f"Location/{i}" not in parents]
        if len(distinct) < 2:
            continue
        names = [ctx.ds.locations[i].name or i for i in distinct]
        yield ctx.make(
            SPEC_SPATIAL,
            resource=ResourceRef(resource_type="Location", resource_id=distinct[0], fhir_path="Location.position",
                                 display=names[0]),
            related=[ResourceRef(resource_type="Location", resource_id=i, display=ctx.ds.locations[i].name) for i in distinct],
            discriminator=f"{lat},{lon}", severity=Severity.WARNING, confidence=0.85,
            summary=f"{len(distinct)} distinct sites ({names[0]} ... {names[-1]}) all have the position {lat}, {lon}.",
            evidence=Evidence(
                observed=[ObservedValue(label=n, value=f"{lat}, {lon}", fhir_path="Location.position") for n in names],
                constraint="distinct sites -> distinct coordinates",
                expected="Each monitoring site carries its own position.",
                measures={"latitude": lat, "longitude": lon, "sites": len(distinct)},
            ),
            interpretation="Site positions are not usable for spatial analysis; they may be a shared placeholder (hypothesis).",
            remediation="Ask the data owner for the true site coordinates.",
        )
