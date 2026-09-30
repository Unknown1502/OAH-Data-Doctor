"""Claim guardrail: SUPPORTED / CONDITIONAL / UNSUPPORTED / BLOCKED for a structured research claim.

Deterministic. The verdict is always re-derived from the StructuredClaim shown to the user; a natural-language
parser (deterministic or LLM) may only *propose* that structure. Each verdict carries:
  - reasons (plain language), a rule trace (CLM-* steps with their outcome),
  - the blocking findings, and safe alternative wordings built from computed numbers.

Verdict ladder (docs/CLAIM_SAFETY_SPEC.md):
  BLOCKED      an input record has an ERROR/CRITICAL integrity finding
  UNSUPPORTED  the data contradict the claim, or cannot address it (not comparable, n too small, causal wording)
  CONDITIONAL  the data point the claimed way but only with caveats (warnings, conditional comparability,
               no uncertainty information, not statistically distinguishable)
  SUPPORTED    comparable, clean inputs, direction holds and the evidence criterion of the claim type is met
"""

from __future__ import annotations

import hashlib
from typing import Any

from datadoctor.claims.stats import mann_kendall, spearman, theil_sen
from datadoctor.comparability.engine import ComparisonError, compare, describe, findings_touching
from datadoctor.domain.enums import ClaimType, ClaimVerdict, ComparabilityVerdict, Severity
from datadoctor.domain.models import ClaimResult, Dataset, Finding, NormalizedObservation, StructuredClaim
from datadoctor.knowledge.loader import Knowledge
from datadoctor.rules.base import fmt

MIN_TREND_POINTS = 3
MIN_ASSOCIATION_UNITS = 8  # below this a rank correlation cannot reach p < 0.05 robustly; documented in CLAIM_SAFETY_SPEC
ALPHA = 0.05


class ClaimError(ValueError):
    pass


def _blocking(findings: list[Finding], keys: set[str]) -> tuple[list[Finding], list[Finding]]:
    touching = findings_touching(findings, keys)
    blocking = [f for f in touching if f.severity in (Severity.ERROR, Severity.CRITICAL) and f.resource.resource_type != "CodeSystem"]
    warnings = [f for f in touching if f not in blocking]
    return blocking, warnings


def _label(kn: Knowledge, key: str | None) -> str:
    return kn.indicators[key].label if key and key in kn.indicators else (key or "?")


def render(claim: StructuredClaim, ds: Dataset, kn: Knowledge) -> str:
    t = claim.type
    if t == ClaimType.COMPARE_HIGHER:
        try:
            a = describe(ds, kn, claim.subject or "", claim.statistic)
            b = describe(ds, kn, claim.object or "", claim.statistic)
            return f"{a.label} is higher than {b.label}"
        except ComparisonError:
            return f"{claim.subject} is higher than {claim.object}"
    loc = ds.locations.get(claim.location_id or "")
    where = loc.name if loc and loc.name else (claim.location_id or "")
    if t == ClaimType.TREND_INCREASE:
        return f"{claim.statistic or 'average'} {_label(kn, claim.indicator_key)} at {where} increased from {claim.year_from} to {claim.year_to}"
    if t == ClaimType.EXCEEDS_THRESHOLD:
        th = kn.thresholds.get(claim.threshold_id or "", {})
        try:
            a = describe(ds, kn, claim.subject or "", claim.statistic)
            return f"{a.label} exceeds {th.get('source', claim.threshold_id)} ({th.get('value')} {th.get('unit')})"
        except ComparisonError:
            return f"{claim.subject} exceeds {claim.threshold_id}"
    rel = "causes" if t == ClaimType.CAUSAL else "is associated with"
    return f"{_label(kn, claim.indicator_key)} {rel} {_label(kn, claim.outcome_indicator_key)}"


def _result(claim: StructuredClaim, ds: Dataset, kn: Knowledge, verdict: ClaimVerdict, reasons: list[str],
            trace: list[dict[str, Any]], *, claim_id: str | None = None, **kw: Any) -> ClaimResult:
    cid = claim_id or "clm-" + hashlib.sha256(claim.model_dump_json(exclude={"text"}).encode()).hexdigest()[:10]
    return ClaimResult(id=cid, claim=claim, claim_rendered=render(claim, ds, kn), verdict=verdict, reasons=reasons,
                       rule_trace=trace, **kw)


# ---------------------------------------------------------------------------------------------------


def _compare_higher(claim: StructuredClaim, ds: Dataset, kn: Knowledge, findings: list[Finding], cid: str | None) -> ClaimResult:
    trace: list[dict[str, Any]] = []
    if not claim.subject or not claim.object:
        raise ClaimError("COMPARE_HIGHER needs subject and object observations")
    cmp = compare(ds, kn, findings, claim.subject, claim.object, claim.statistic, claim.statistic)
    inputs = [f"Observation/{claim.subject}", f"Observation/{claim.object}"]
    trace.append({"step": "CLM-CMP-001", "check": "comparability", "outcome": cmp.verdict.value})
    a, b = cmp.a, cmp.b
    if cmp.verdict == ComparabilityVerdict.NOT:
        return _result(claim, ds, kn, ClaimVerdict.UNSUPPORTED,
                       [f"The two values are not comparable: {cmp.summary}"] + [d.reason for d in cmp.dimensions if d.status.value == "FAIL"],
                       trace, claim_id=cid, comparison=cmp, safe_alternatives=cmp.supported_alternatives, inputs=inputs)
    if cmp.verdict == ComparabilityVerdict.BLOCKED_BY_INTEGRITY:
        return _result(claim, ds, kn, ClaimVerdict.BLOCKED,
                       ["At least one input record fails integrity checks, so no conclusion can be drawn from it until the data owner reviews it."],
                       trace, claim_id=cid, comparison=cmp, blocking_findings=cmp.blocking_findings,
                       safe_alternatives=cmp.supported_alternatives, inputs=inputs)
    va, vb = a.value, b.value
    if va is None or vb is None:
        raise ClaimError("missing value")
    unit_dim = next(d for d in cmp.dimensions if d.rule_id == "CMP-UNIT")
    if unit_dim.status.value == "CONDITIONAL":
        va = va * unit_dim.details.get("factor", 1) + unit_dim.details.get("offset", 0)
    higher = va > vb
    trace.append({"step": "CLM-DIR-001", "check": "direction", "outcome": "holds" if higher else "does not hold",
                  "values": [va, vb]})
    stats: dict[str, Any] = {"a": va, "b": vb, "difference": round(va - vb, 6), "unit": b.unit}
    if not higher:
        return _result(claim, ds, kn, ClaimVerdict.UNSUPPORTED,
                       [f"The data show the opposite: {fmt(va)} vs {fmt(vb)} {b.unit or ''}."], trace, claim_id=cid,
                       comparison=cmp, statistics=stats, inputs=inputs,
                       safe_alternatives=[f"{b.label} ({fmt(vb)}) was higher than or equal to {a.label} ({fmt(va)}) {b.unit or ''}."])
    # Evidence criterion: non-overlapping observed ranges (for annual summaries) is the only uncertainty we can use.
    oa, ob = ds.observations[a.observation_id], ds.observations[b.observation_id]
    amin, bmax = oa.stat("minimum"), ob.stat("maximum")
    separated = bool(amin and bmax and amin.quantity.value is not None and bmax.quantity.value is not None
                     and amin.quantity.value > bmax.quantity.value)
    trace.append({"step": "CLM-UNC-001", "check": "uncertainty",
                  "outcome": "ranges separated" if separated else "no uncertainty information allows a test"})
    reasons = [f"{a.label}: {fmt(va)} vs {b.label}: {fmt(vb)} {b.unit or ''} (difference {fmt(round(va - vb, 4))})."]
    safe = [f"The published value for {a.label} ({fmt(va)}) is higher than for {b.label} ({fmt(vb)}) {b.unit or ''}; "
            "no sample sizes or confidence intervals are published, so the difference is descriptive only."]
    if cmp.verdict == ComparabilityVerdict.CONDITIONAL or not separated:
        why = []
        if cmp.verdict == ComparabilityVerdict.CONDITIONAL:
            why.append(f"comparability is conditional ({', '.join(d.dimension for d in cmp.dimensions if d.status.value == 'CONDITIONAL')})")
        if not separated:
            why.append("no sample size or confidence interval is published and the observed ranges overlap, so the difference cannot be tested")
        return _result(claim, ds, kn, ClaimVerdict.CONDITIONAL, reasons + ["Conditional because " + "; ".join(why) + "."],
                       trace, claim_id=cid, comparison=cmp, statistics=stats, safe_alternatives=safe + cmp.supported_alternatives,
                       inputs=inputs)
    return _result(claim, ds, kn, ClaimVerdict.SUPPORTED,
                   reasons + ["Directly comparable, clean inputs, and the entire observed range of A lies above that of B."],
                   trace, claim_id=cid, comparison=cmp, statistics=stats, safe_alternatives=safe, inputs=inputs)


def _series(ds: Dataset, claim: StructuredClaim) -> list[NormalizedObservation]:
    out = []
    for o in ds.observations.values():
        if o.subject_ref != f"Location/{claim.location_id}" or o.indicator_key != claim.indicator_key:
            continue
        if not (o.effective_period and o.effective_period.is_annual and o.year):
            continue
        if claim.year_from and o.year < claim.year_from or claim.year_to and o.year > claim.year_to:
            continue
        if o.stat(claim.statistic or "average"):
            out.append(o)
    return sorted(out, key=lambda o: o.year or 0)


def _trend(claim: StructuredClaim, ds: Dataset, kn: Knowledge, findings: list[Finding], cid: str | None) -> ClaimResult:
    stat = claim.statistic or "average"
    pts = _series(ds, claim)
    inputs = [o.key for o in pts]
    trace: list[dict[str, Any]] = [{"step": "CLM-TRD-001", "check": "series length", "outcome": len(pts)}]
    years = [o.year for o in pts]
    if len(pts) < MIN_TREND_POINTS:
        return _result(claim, ds, kn, ClaimVerdict.UNSUPPORTED,
                       [f"Only {len(pts)} annual value(s) found; a trend needs at least {MIN_TREND_POINTS}."], trace,
                       claim_id=cid, inputs=inputs, statistics={"years": years})
    blocking, warnings = _blocking(findings, set(inputs))
    trace.append({"step": "CLM-INT-001", "check": "integrity of every point", "outcome": f"{len(blocking)} blocking"})
    if blocking:
        bad = sorted({f.resource.resource_id for f in blocking if f.resource.resource_type == "Observation"})
        return _result(claim, ds, kn, ClaimVerdict.BLOCKED,
                       [f"{len(bad)} of {len(pts)} points in the series have ERROR/CRITICAL integrity findings "
                        f"({', '.join(sorted({f.rule_id for f in blocking}))}). A trend computed from them would be meaningless."],
                       trace, claim_id=cid, blocking_findings=sorted({f.id for f in blocking}), inputs=inputs,
                       statistics={"years": years, "values": [o.stat(stat).quantity.value for o in pts if o.stat(stat)]},
                       safe_alternatives=[f"No safe trend statement can be made for {_label(kn, claim.indicator_key)} here until "
                                          "the data owner reviews the flagged records."])
    units = {o.stat(stat).quantity.code for o in pts if o.stat(stat)}
    if len(units) > 1:
        return _result(claim, ds, kn, ClaimVerdict.UNSUPPORTED, [f"Units change within the series ({sorted(u or '?' for u in units)})."],
                       trace, claim_id=cid, inputs=inputs)
    ys = [o.stat(stat).quantity.value or 0.0 for o in pts if o.stat(stat)]
    xs = [float(o.year or 0) for o in pts]
    mk = mann_kendall(ys)
    slope = theil_sen(xs, ys)
    gaps = [y for y in range(int(xs[0]), int(xs[-1]) + 1) if y not in years]
    stats: dict[str, Any] = {"years": years, "values": ys, "mann_kendall": mk, "theil_sen_slope_per_year": slope,
                             "unit": units.pop(), "missing_years": gaps}
    trace.append({"step": "CLM-TRD-002", "check": "Mann-Kendall (one-sided)", "outcome": mk})
    unit = stats["unit"] or ""
    if slope is None or slope <= 0:
        return _result(claim, ds, kn, ClaimVerdict.UNSUPPORTED,
                       [f"No increase: Theil-Sen slope {fmt(slope)} {unit}/year (S = {mk['S']})."], trace, claim_id=cid,
                       statistics=stats, inputs=inputs,
                       safe_alternatives=[f"Between {years[0]} and {years[-1]} the annual {stat} did not increase (slope {fmt(slope)} {unit}/yr)."])
    p = float(mk["p_one_sided"])
    note_gaps = f" Years missing from the series: {gaps}." if gaps else ""
    if p < ALPHA and not warnings:
        return _result(claim, ds, kn, ClaimVerdict.SUPPORTED,
                       [f"Monotonic increase: Mann-Kendall S = {mk['S']}, exact one-sided p = {p:.4f} (n = {mk['n']}); "
                        f"Theil-Sen slope {fmt(round(slope, 6))} {unit}/year.{note_gaps}"], trace, claim_id=cid, statistics=stats, inputs=inputs,
                       safe_alternatives=[f"The annual {stat} increased by about {fmt(round(slope, 4))} {unit} per year between {years[0]} and {years[-1]} "
                                          f"(Mann-Kendall p = {p:.3f}, n = {mk['n']})."])
    why = (f"p = {p:.3f} is not below {ALPHA} with only n = {mk['n']} points" if p >= ALPHA
           else f"{len(warnings)} warning(s) on the inputs")
    return _result(claim, ds, kn, ClaimVerdict.CONDITIONAL,
                   [f"Upward tendency (slope {fmt(round(slope, 6))} {unit}/yr) but {why}.{note_gaps}"], trace, claim_id=cid,
                   statistics=stats, inputs=inputs,
                   safe_alternatives=[f"Values tended upward between {years[0]} and {years[-1]}, but the trend is not statistically "
                                      f"distinguishable from no trend (Mann-Kendall p = {p:.2f}, n = {mk['n']})."])


def _threshold(claim: StructuredClaim, ds: Dataset, kn: Knowledge, findings: list[Finding], cid: str | None) -> ClaimResult:
    th = kn.thresholds.get(claim.threshold_id or "")
    if th is None:
        raise ClaimError(f"unknown threshold {claim.threshold_id}")
    a = describe(ds, kn, claim.subject or "", claim.statistic)
    inputs = [f"Observation/{a.observation_id}"]
    trace: list[dict[str, Any]] = []
    if a.indicator_key != th["indicator"]:
        return _result(claim, ds, kn, ClaimVerdict.UNSUPPORTED,
                       [f"The threshold applies to {_label(kn, th['indicator'])}, not {a.measure_label}."], trace, claim_id=cid, inputs=inputs)
    # Only findings on the record itself matter here: a site-coordinate warning does not change whether a value exceeds a limit.
    blocking, warnings = _blocking(findings, set(inputs))
    trace.append({"step": "CLM-INT-001", "check": "integrity", "outcome": f"{len(blocking)} blocking, {len(warnings)} warnings"})
    if blocking:
        return _result(claim, ds, kn, ClaimVerdict.BLOCKED, ["The input record fails integrity checks."], trace, claim_id=cid,
                       blocking_findings=[f.id for f in blocking], inputs=inputs)
    caveats: list[str] = []
    obs = ds.observations[a.observation_id]
    matrix_ok = (th["matrix"] == "ambient-air" and a.medium.value == "air") or (th["matrix"] == "drinking-water" and a.medium.value == "water")
    if th["matrix"] == "drinking-water":
        caveats.append("This is a drinking-water standard applied to surface water: indicative only, not a compliance statement.")
    trace.append({"step": "CLM-THR-001", "check": "matrix", "outcome": th["matrix"]})
    if th["averaging"] == "calendar-year-mean":
        if not (obs.effective_period and obs.effective_period.is_annual and (a.statistic == "average")):
            return _result(claim, ds, kn, ClaimVerdict.UNSUPPORTED,
                           [f"The threshold is defined on a calendar-year mean; the value used is {a.aggregation}."], trace,
                           claim_id=cid, inputs=inputs)
    elif th["averaging"] == "max-daily-8h-mean":
        return _result(claim, ds, kn, ClaimVerdict.UNSUPPORTED,
                       ["The threshold is defined on maximum daily 8-hour means, which are not published; an annual summary cannot "
                        "show compliance or exceedance."], trace, claim_id=cid, inputs=inputs,
                       safe_alternatives=["Report the annual statistics descriptively without reference to the 8-hour target value."])
    trace.append({"step": "CLM-THR-002", "check": "averaging period", "outcome": th["averaging"]})
    if a.value is None or not a.unit:
        return _result(claim, ds, kn, ClaimVerdict.UNSUPPORTED, ["The value has no usable unit."], trace, claim_id=cid, inputs=inputs)
    conv = kn.convert(a.value, a.unit, th["unit"])
    if conv is None:
        return _result(claim, ds, kn, ClaimVerdict.UNSUPPORTED, [f"Cannot convert {a.unit} to {th['unit']}."], trace, claim_id=cid, inputs=inputs)
    v = conv[0]
    stats = {"value": v, "threshold": th["value"], "unit": th["unit"], "ratio": round(v / th["value"], 4), "source": th["source"]}
    trace.append({"step": "CLM-THR-003", "check": "value vs threshold", "outcome": "exceeds" if v > th["value"] else "does not exceed"})
    if v <= th["value"]:
        return _result(claim, ds, kn, ClaimVerdict.UNSUPPORTED,
                       [f"{fmt(v)} {th['unit']} does not exceed {th['value']} {th['unit']} ({th['source']})."], trace, claim_id=cid,
                       statistics=stats, inputs=inputs,
                       safe_alternatives=[f"The {a.label} ({fmt(v)} {th['unit']}) was below {th['source']} ({th['value']} {th['unit']})."])
    caveats.append("Data coverage (share of valid days) is not published; legal compliance assessment requires minimum coverage.")
    if warnings:
        caveats.insert(0, f"{len(warnings)} warning(s) touch this record ({', '.join(sorted({f.rule_id for f in warnings}))}).")
    verdict = ClaimVerdict.CONDITIONAL if (warnings or not matrix_ok or th["matrix"] == "drinking-water") else ClaimVerdict.SUPPORTED
    return _result(claim, ds, kn, verdict,
                   [f"{fmt(v)} {th['unit']} is {stats['ratio']}x the threshold of {th['value']} {th['unit']} ({th['source']})."] + caveats,
                   trace, claim_id=cid, statistics=stats, inputs=inputs,
                   safe_alternatives=[f"The published annual mean ({fmt(v)} {th['unit']}) was above {th['source']} "
                                      f"({th['value']} {th['unit']}); data coverage is not published."])


def _association(claim: StructuredClaim, ds: Dataset, kn: Knowledge, findings: list[Finding], cid: str | None) -> ClaimResult:
    trace: list[dict[str, Any]] = []
    exp_by_loc: dict[str, NormalizedObservation] = {}
    out_by_loc: dict[str, list[NormalizedObservation]] = {}
    for o in ds.observations.values():
        loc = o.subject_ref or ""
        if o.indicator_key == claim.indicator_key and o.stat("average") and o.effective_period and o.effective_period.is_annual:
            if claim.year_from and o.year != claim.year_from:
                continue
            exp_by_loc[loc] = o
        if o.indicator_key == claim.outcome_indicator_key and o.value is not None:
            out_by_loc.setdefault(loc, []).append(o)
    units = sorted(set(exp_by_loc) & set(out_by_loc))
    trace.append({"step": "CLM-ASC-001", "check": "paired spatial units", "outcome": len(units)})
    inputs = sorted({exp_by_loc[u].key for u in units} | {o.key for u in units for o in out_by_loc[u]})
    exp_years = sorted({exp_by_loc[u].year for u in units if exp_by_loc[u].year})
    out_years = sorted({o.year for u in units for o in out_by_loc[u] if o.year})
    stats: dict[str, Any] = {"paired_units": [u.split("/")[-1] for u in units], "exposure_years": exp_years, "outcome_years": out_years}
    reasons = []
    if exp_years and out_years and set(exp_years) != set(out_years):
        reasons.append(f"Exposure ({exp_years}) and outcome ({out_years}) refer to different years.")
    reasons.append("Ecological design: site-level aggregates cannot show that exposed individuals are the ones affected.")
    if len(units) < MIN_ASSOCIATION_UNITS:
        if units:
            pairs = [(exp_by_loc[u].stat("average").quantity.value, [o.value.value for o in out_by_loc[u] if o.value]) for u in units]  # type: ignore[union-attr]
            stats["pairs"] = pairs
        return _result(claim, ds, kn, ClaimVerdict.UNSUPPORTED,
                       [f"Only {len(units)} site(s) have both {_label(kn, claim.indicator_key)} and {_label(kn, claim.outcome_indicator_key)}; "
                        f"at least {MIN_ASSOCIATION_UNITS} paired units are needed for a meaningful association test."] + reasons,
                       trace, claim_id=cid, statistics=stats, inputs=inputs,
                       safe_alternatives=[f"Describe the {len(units)} sites side by side without inferring an association."])
    blocking, _ = _blocking(findings, set(inputs))
    if blocking:
        return _result(claim, ds, kn, ClaimVerdict.BLOCKED, ["Input records fail integrity checks."], trace, claim_id=cid,
                       blocking_findings=[f.id for f in blocking], inputs=inputs)
    xs = [exp_by_loc[u].stat("average").quantity.value or 0.0 for u in units]  # type: ignore[union-attr]
    ys = [sum(o.value.value or 0 for o in out_by_loc[u] if o.value) / len(out_by_loc[u]) for u in units]
    sp = spearman(xs, ys)
    stats["spearman"] = sp
    verdict = ClaimVerdict.CONDITIONAL if (sp["p_two_sided"] is not None and float(sp["p_two_sided"]) < ALPHA) else ClaimVerdict.UNSUPPORTED
    return _result(claim, ds, kn, verdict, [f"Spearman rho = {sp['rho']} (p = {sp['p_two_sided']}, n = {sp['n']})."] + reasons,
                   trace, claim_id=cid, statistics=stats, inputs=inputs)


def _causal(claim: StructuredClaim, ds: Dataset, kn: Knowledge, findings: list[Finding], cid: str | None) -> ClaimResult:
    assoc = _association(claim.model_copy(update={"type": ClaimType.ASSOCIATION}), ds, kn, findings, None)
    trace = [{"step": "CLM-CAU-001", "check": "causal wording", "outcome": "not supportable from aggregated observational data"},
             {"step": "CLM-CAU-002", "check": "fallback: association", "outcome": assoc.verdict.value}]
    return _result(claim, ds, kn, ClaimVerdict.UNSUPPORTED,
                   ["Aggregated observational indicators cannot establish causation: there is no individual-level exposure, "
                    "no temporal ordering and no control of confounders (age, smoking, income, ...).",
                    f"Even the weaker association claim is {assoc.verdict.value}: {assoc.reasons[0]}"],
                   trace, claim_id=cid, statistics=assoc.statistics, inputs=assoc.inputs,
                   safe_alternatives=assoc.safe_alternatives or [
                       f"'{_label(kn, claim.indicator_key)} and {_label(kn, claim.outcome_indicator_key)} were both measured in these areas' "
                       "— without any causal or associative wording."])


def evaluate_claim(claim: StructuredClaim, ds: Dataset, kn: Knowledge, findings: list[Finding], claim_id: str | None = None) -> ClaimResult:
    handlers = {ClaimType.COMPARE_HIGHER: _compare_higher, ClaimType.TREND_INCREASE: _trend,
                ClaimType.EXCEEDS_THRESHOLD: _threshold, ClaimType.ASSOCIATION: _association, ClaimType.CAUSAL: _causal}
    try:
        return handlers[claim.type](claim, ds, kn, findings, claim_id)
    except ComparisonError as exc:
        raise ClaimError(str(exc)) from exc
