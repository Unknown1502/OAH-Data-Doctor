"""Comparability engine: can two published indicators be compared, and on what terms?

Eight dimensions (docs/COMPARABILITY_SPEC.md), each PASS / CONDITIONAL / FAIL / N/A:
  CMP-MEASURE, CMP-UNIT, CMP-MEDIUM, CMP-POPULATION, CMP-PERIOD, CMP-AGGREGATION, CMP-METHOD, CMP-INTEGRITY
Verdict precedence: any FAIL in 1-7 -> NOT;  else integrity FAIL -> BLOCKED_BY_INTEGRITY;
                    else any CONDITIONAL -> CONDITIONAL;  else DIRECT.
NOT outranks BLOCKED: if two indicators could never be compared, repairing the data would not change that.
Every "supported alternative" is computed from records that exist in the current dataset.
"""

from __future__ import annotations

import hashlib
from typing import Any

from datadoctor.domain.enums import ComparabilityVerdict, DimensionStatus, Severity
from datadoctor.domain.models import (
    Cohort,
    Comparison,
    Dataset,
    DimensionResult,
    Finding,
    IndicatorDescriptor,
    NormalizedObservation,
)
from datadoctor.knowledge.loader import Knowledge

PASS, COND, FAIL, NA = DimensionStatus.PASS, DimensionStatus.CONDITIONAL, DimensionStatus.FAIL, DimensionStatus.NOT_APPLICABLE


class ComparisonError(ValueError):
    pass


def _aggregation(obs: NormalizedObservation, statistic: str | None) -> str:
    if obs.stats:
        span = "annual" if obs.effective_period and obs.effective_period.is_annual else "period"
        return f"{span}-summary:{statistic or '?'}"
    if obs.effective_datetime:
        return "point-measurement"
    if obs.value is not None and obs.value.code == "%" and obs.effective_period and obs.effective_period.is_annual:
        return "annual-prevalence"
    return "single-value"


def describe(ds: Dataset, kn: Knowledge, observation_id: str, statistic: str | None = None) -> IndicatorDescriptor:
    obs = ds.observations.get(observation_id)
    if obs is None:
        raise ComparisonError(f"Observation/{observation_id} is not in the current dataset")
    value, unit = None, None
    if obs.stats:
        statistic = statistic or ("average" if obs.stat("average") else (obs.stats[0].stat if obs.stats else None))
        s = obs.stat(statistic or "")
        if s is None:
            raise ComparisonError(f"Observation/{observation_id} has no '{statistic}' statistic")
        value, unit = s.quantity.value, s.quantity.code
    elif obs.value is not None:
        statistic = None
        value, unit = obs.value.value, obs.value.code
    ind = kn.indicators.get(obs.indicator_key or "")
    loc_id = (obs.subject_ref or "").split("/")[-1] or None
    loc = ds.locations.get(loc_id or "")
    cohort = ds.groups.get(obs.focus_refs[0].split("/")[-1]) if obs.focus_refs else None
    method = " / ".join(x for x in [*obs.performer, obs.device_ref or "", obs.method or ""] if x) or None
    period = obs.effective_period
    if period is None and obs.effective_datetime:
        from datadoctor.domain.models import Period

        period = Period(start=obs.effective_datetime, end=obs.effective_datetime)
    label_parts = [ind.label if ind else (obs.code_text or obs.code or obs.id), loc.name if loc and loc.name else (loc_id or "")]
    if cohort:
        label_parts.append(cohort.label)
    if period and period.year and period.is_annual:
        label_parts.append(str(period.year))
    elif obs.effective_datetime:
        label_parts.append(obs.effective_datetime)
    if statistic:
        label_parts.append(f"annual {statistic}" if period and period.is_annual else statistic)
    return IndicatorDescriptor(
        observation_id=obs.id, statistic=statistic, label=" · ".join(p for p in label_parts if p),
        indicator_key=obs.indicator_key, measure_label=ind.label if ind else None, medium=obs.medium,
        unit=unit, value=value, location_id=loc_id, location_name=loc.name if loc else None, cohort=cohort,
        period=period, aggregation=_aggregation(obs, statistic), method=method,
    )


# ---------------------------------------------------------------------------------------------------
# Dimensions
# ---------------------------------------------------------------------------------------------------


def _measure(a: IndicatorDescriptor, b: IndicatorDescriptor, ds: Dataset, kn: Knowledge) -> DimensionResult:
    rid = "CMP-MEASURE"
    if not a.indicator_key or not b.indicator_key:
        return DimensionResult(dimension="Measure", rule_id=rid, status=FAIL,
                               reason="At least one indicator is not mapped to a known measure; identity cannot be established.")
    oa, ob = ds.observations[a.observation_id], ds.observations[b.observation_id]
    if a.indicator_key == b.indicator_key:
        if (oa.code_system, oa.code) == (ob.code_system, ob.code):
            return DimensionResult(dimension="Measure", rule_id=rid, status=PASS,
                                   reason=f"Same measure and same code ({oa.code}).")
        rel = kn.relation(a.indicator_key, b.indicator_key)
        if rel and rel.relationship == "related":
            return DimensionResult(dimension="Measure", rule_id=rid, status=COND, reason=rel.note,
                                   details={"codes": [oa.code, ob.code], "relationship": "related"})
        return DimensionResult(dimension="Measure", rule_id=rid, status=PASS,
                               reason=f"Different codes ({oa.code} vs {ob.code}) for the same measure. {rel.note if rel else ''}".strip(),
                               details={"codes": [oa.code, ob.code], "relationship": "equivalent"})
    rel = kn.relation(a.indicator_key, b.indicator_key)
    if rel is None:
        return DimensionResult(dimension="Measure", rule_id=rid, status=FAIL,
                               reason=f"'{a.measure_label}' and '{b.measure_label}' are different measures.")
    status = {"equivalent": PASS, "related": COND, "broader": FAIL}.get(rel.relationship, FAIL)
    return DimensionResult(dimension="Measure", rule_id=rid, status=status,
                           reason=f"{a.measure_label} vs {b.measure_label}: {rel.relationship}. {rel.note}",
                           details={"relationship": rel.relationship})


def _unit(a: IndicatorDescriptor, b: IndicatorDescriptor, kn: Knowledge, transforms: list[str]) -> DimensionResult:
    rid = "CMP-UNIT"
    if not a.unit or not b.unit:
        return DimensionResult(dimension="Unit", rule_id=rid, status=FAIL,
                               reason="A value has no machine-readable unit, so it cannot be converted or compared.")
    if a.unit == b.unit:
        return DimensionResult(dimension="Unit", rule_id=rid, status=PASS, reason=f"Same unit ({a.unit}).")
    conv = kn.convert(1.0, a.unit, b.unit)
    if conv is None:
        return DimensionResult(dimension="Unit", rule_id=rid, status=FAIL,
                               reason=f"No explicit conversion from {a.unit} to {b.unit} in the unit table.")
    rec = conv[1]
    if rec.get("affine"):
        transforms.append(f"Convert A from {a.unit} to {b.unit} (offset {rec.get('offset')}; differences convert without offset).")
    else:
        transforms.append(f"Multiply A by {rec['factor']:g} to convert {a.unit} -> {b.unit}.")
    return DimensionResult(dimension="Unit", rule_id=rid, status=COND,
                           reason=f"Units differ ({a.unit} vs {b.unit}) but convert exactly (x{rec['factor']:g}).",
                           details={"factor": rec["factor"], "offset": rec.get("offset", 0)})


def _medium(a: IndicatorDescriptor, b: IndicatorDescriptor) -> DimensionResult:
    if a.medium == b.medium:
        return DimensionResult(dimension="Medium", rule_id="CMP-MEDIUM", status=PASS, reason=f"Both {a.medium.value}.")
    return DimensionResult(dimension="Medium", rule_id="CMP-MEDIUM", status=FAIL,
                           reason=f"Different media: {a.medium.value} vs {b.medium.value}.")


def _age_text(c: Cohort) -> str:
    lo, hi = c.age_interval()
    return f"{lo:g}+" if hi == float("inf") else f"{lo:g}-{hi:g}"


def _population(a: IndicatorDescriptor, b: IndicatorDescriptor) -> DimensionResult:
    rid = "CMP-POPULATION"
    if a.cohort is None and b.cohort is None:
        return DimensionResult(dimension="Population", rule_id=rid, status=NA, reason="Environmental measurements: no human cohort.")
    if (a.cohort is None) != (b.cohort is None):
        return DimensionResult(dimension="Population", rule_id=rid, status=FAIL, reason="Only one indicator describes a human cohort.")
    assert a.cohort is not None and b.cohort is not None
    notes, status = [], PASS
    if a.cohort.sex != b.cohort.sex:
        if a.cohort.sex and b.cohort.sex:
            status = COND
            notes.append(f"Different sexes ({a.cohort.sex} vs {b.cohort.sex}): valid only as a between-sex comparison.")
        else:
            status = COND
            notes.append("One cohort is sex-specific, the other covers both sexes (nested populations).")
    (alo, ahi), (blo, bhi) = a.cohort.age_interval(), b.cohort.age_interval()
    overlap = (max(alo, blo), min(ahi, bhi))
    details: dict[str, Any] = {"age_a": _age_text(a.cohort), "age_b": _age_text(b.cohort)}
    if overlap[0] > overlap[1]:
        return DimensionResult(dimension="Population", rule_id=rid, status=FAIL,
                               reason=f"Age bands do not overlap ({_age_text(a.cohort)} vs {_age_text(b.cohort)} years): "
                                      "these are different people.", details=details)
    if (alo, ahi) != (blo, bhi):
        status = COND
        ov_hi = "+" if overlap[1] == float("inf") else f"-{overlap[1]:g}"
        notes.append(f"Age bands differ ({_age_text(a.cohort)} vs {_age_text(b.cohort)}); they overlap on {overlap[0]:g}{ov_hi} years. "
                     "Prevalence depends strongly on age.")
        details["overlap"] = [overlap[0], None if overlap[1] == float("inf") else overlap[1]]
    return DimensionResult(dimension="Population", rule_id=rid, status=status,
                           reason=" ".join(notes) or f"Same cohort definition ({a.cohort.label}).", details=details)


def _period(a: IndicatorDescriptor, b: IndicatorDescriptor) -> DimensionResult:
    rid = "CMP-PERIOD"
    if not a.period or not b.period:
        return DimensionResult(dimension="Period", rule_id=rid, status=FAIL, reason="A period is missing.")
    if (a.period.start, a.period.end) == (b.period.start, b.period.end):
        return DimensionResult(dimension="Period", rule_id=rid, status=PASS, reason=f"Same period ({a.period.start} to {a.period.end}).")
    return DimensionResult(dimension="Period", rule_id=rid, status=COND,
                           reason=f"Different periods ({a.period.start}..{a.period.end} vs {b.period.start}..{b.period.end}): "
                                  "a comparison over time, not a contemporaneous one.")


def _aggregation_dim(a: IndicatorDescriptor, b: IndicatorDescriptor) -> DimensionResult:
    rid = "CMP-AGGREGATION"
    if a.aggregation == b.aggregation:
        return DimensionResult(dimension="Aggregation", rule_id=rid, status=PASS, reason=f"Same aggregation ({a.aggregation}).")
    ka, kb = a.aggregation.split(":")[0], b.aggregation.split(":")[0]
    if ka == kb:
        return DimensionResult(dimension="Aggregation", rule_id=rid, status=FAIL,
                               reason=f"Different statistics of the data ({a.statistic} vs {b.statistic}): not the same quantity.")
    return DimensionResult(dimension="Aggregation", rule_id=rid, status=FAIL,
                           reason=f"Different kinds of value ({a.aggregation} vs {b.aggregation}): e.g. an annual summary "
                                  "cannot be compared with a single spot measurement.")


def _method(a: IndicatorDescriptor, b: IndicatorDescriptor) -> DimensionResult:
    rid = "CMP-METHOD"
    if not a.method or not b.method:
        return DimensionResult(dimension="Method / performer", rule_id=rid, status=COND,
                               reason="Method or performer is not documented for at least one value.")
    if a.method == b.method:
        return DimensionResult(dimension="Method / performer", rule_id=rid, status=PASS, reason=f"Same performer/method ({a.method}).")
    return DimensionResult(dimension="Method / performer", rule_id=rid, status=COND,
                           reason=f"Different performers/methods ({a.method} vs {b.method}): inter-laboratory differences possible.")


def findings_touching(findings: list[Finding], keys: set[str]) -> list[Finding]:
    out = []
    for f in findings:
        touched = {f.resource.key} | {r.key for r in f.related_resources}
        if touched & keys:
            out.append(f)
    return out


def _integrity(a: IndicatorDescriptor, b: IndicatorDescriptor, findings: list[Finding]) -> tuple[DimensionResult, list[str]]:
    keys = {f"Observation/{a.observation_id}", f"Observation/{b.observation_id}"}
    loc_keys = {f"Location/{x}" for x in (a.location_id, b.location_id) if x}
    touching = findings_touching(findings, keys | loc_keys)
    blocking = [f for f in touching if f.severity in (Severity.ERROR, Severity.CRITICAL) and f.resource.resource_type != "CodeSystem"]
    if blocking:
        return (DimensionResult(dimension="Integrity", rule_id="CMP-INTEGRITY", status=FAIL,
                                reason=f"{len(blocking)} ERROR/CRITICAL finding(s) on the input records "
                                       f"({', '.join(sorted({f.rule_id for f in blocking}))}).",
                                details={"findings": [f.id for f in blocking]}), [f.id for f in blocking])
    if touching:
        return (DimensionResult(dimension="Integrity", rule_id="CMP-INTEGRITY", status=COND,
                                reason=f"{len(touching)} warning(s) on the inputs ({', '.join(sorted({f.rule_id for f in touching}))}); "
                                       "read them before relying on the comparison.",
                                details={"findings": [f.id for f in touching]}), [])
    return DimensionResult(dimension="Integrity", rule_id="CMP-INTEGRITY", status=PASS,
                           reason="No findings on either input record."), []


# ---------------------------------------------------------------------------------------------------
# Alternatives (computed from the dataset, never invented)
# ---------------------------------------------------------------------------------------------------


def _alternatives(a: IndicatorDescriptor, b: IndicatorDescriptor, dims: list[DimensionResult], ds: Dataset,
                  findings: list[Finding], kn: Knowledge) -> list[str]:
    out: list[str] = []
    status = {d.rule_id: d.status for d in dims}
    blocked = {f.resource.key for f in findings if f.severity in (Severity.ERROR, Severity.CRITICAL)} | \
              {r.key for f in findings if f.severity in (Severity.ERROR, Severity.CRITICAL) and f.resource.resource_type != "CodeSystem"
               for r in f.related_resources}
    if status.get("CMP-POPULATION") == FAIL and a.cohort and b.cohort:
        alo, ahi = a.cohort.age_interval()
        cands = []
        for o in ds.observations.values():
            if o.subject_ref != f"Location/{b.location_id}" or not o.focus_refs:
                continue
            g = ds.groups.get(o.focus_refs[0].split("/")[-1])
            if g is None or o.indicator_key not in (b.indicator_key,):
                continue
            glo, ghi = g.age_interval()
            if max(alo, glo) <= min(ahi, ghi) and (g.sex in (None, a.cohort.sex)):
                cands.append((glo, g.label, o.id))
        if cands:
            names = ", ".join(f"{lab} ({oid})" for _, lab, oid in sorted(cands)[:6])
            out.append(f"Compare with {b.location_name or b.location_id} cohorts whose ages overlap {_age_text(a.cohort)} years: {names}. "
                       "Overlap is partial; state the age bands explicitly.")
        else:
            out.append(f"No {b.location_name or 'comparison'} cohort overlaps {_age_text(a.cohort)} years for this measure.")
    if status.get("CMP-AGGREGATION") == FAIL and a.aggregation.split(":")[0] == b.aggregation.split(":")[0] and a.statistic and b.statistic:
        out.append(f"Compare the same statistic on both sides (e.g. annual {a.statistic} vs annual {a.statistic}).")
    if status.get("CMP-INTEGRITY") == FAIL:
        sides = {(s.indicator_key, s.location_id): s for s in (a, b)}.values()  # one suggestion per site x measure
        for side in sides:
            clean = sorted(o.id for o in ds.observations.values()
                           if o.indicator_key == side.indicator_key and o.subject_ref == f"Location/{side.location_id}"
                           and o.key not in blocked and o.id not in (a.observation_id, b.observation_id))
            if clean:
                out.append(f"Records of {side.measure_label} at {side.location_name} with no ERROR/CRITICAL findings: "
                           f"{', '.join(clean[:5])}{' ...' if len(clean) > 5 else ''} (check their own comparability).")
            else:
                out.append(f"Every {side.measure_label} record at {side.location_name} has integrity findings; ask the data owner to review them first.")
    if status.get("CMP-MEASURE") == FAIL and a.indicator_key and b.location_id:
        rel_keys = {r.b if r.a == a.indicator_key else r.a for r in kn.relations
                    if a.indicator_key in (r.a, r.b) and r.relationship in ("equivalent", "related")}
        cands2 = sorted({o.id for o in ds.observations.values() if o.subject_ref == f"Location/{b.location_id}"
                         and (o.indicator_key == a.indicator_key or o.indicator_key in rel_keys)})
        if cands2:
            out.append(f"Records at {b.location_name} measuring {a.measure_label} or a related measure: {', '.join(cands2[:5])}.")
        else:
            out.append(f"No record at {b.location_name} measures {a.measure_label}; the two sites cannot be compared on this measure.")
    return list(dict.fromkeys(out))


def compare(ds: Dataset, kn: Knowledge, findings: list[Finding], a_id: str, b_id: str,
            a_stat: str | None = None, b_stat: str | None = None, comparison_id: str | None = None) -> Comparison:
    a = describe(ds, kn, a_id, a_stat)
    b = describe(ds, kn, b_id, b_stat)
    transforms: list[str] = []
    dims = [_measure(a, b, ds, kn), _unit(a, b, kn, transforms), _medium(a, b), _population(a, b), _period(a, b),
            _aggregation_dim(a, b), _method(a, b)]
    integ, blocking = _integrity(a, b, findings)
    dims.append(integ)
    core = dims[:-1]
    if any(d.status == FAIL for d in core):
        verdict = ComparabilityVerdict.NOT
    elif integ.status == FAIL:
        verdict = ComparabilityVerdict.BLOCKED_BY_INTEGRITY
    elif any(d.status == COND for d in dims):
        verdict = ComparabilityVerdict.CONDITIONAL
    else:
        verdict = ComparabilityVerdict.DIRECT
    failed = [d.dimension for d in core if d.status == FAIL]
    conds = [d.dimension for d in dims if d.status == COND]
    summary = {
        ComparabilityVerdict.NOT: f"Not comparable: {', '.join(failed)} differ in ways no transformation can fix.",
        ComparabilityVerdict.BLOCKED_BY_INTEGRITY: "Comparable in principle, but blocked: the input records fail integrity checks.",
        ComparabilityVerdict.CONDITIONAL: f"Comparable only with caveats on: {', '.join(conds)}.",
        ComparabilityVerdict.DIRECT: "Directly comparable: same measure, unit, population, period, aggregation and method; no integrity findings.",
    }[verdict]
    cid = comparison_id or "cmp-" + hashlib.sha256(f"{a_id}|{a.statistic}|{b_id}|{b.statistic}".encode()).hexdigest()[:10]
    return Comparison(id=cid, a=a, b=b, verdict=verdict, dimensions=dims, blocking_findings=blocking,
                      transformations=transforms, supported_alternatives=_alternatives(a, b, dims, ds, findings, kn),
                      summary=summary)
