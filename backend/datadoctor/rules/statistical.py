"""Internal consistency of published summary statistics (one record at a time).

These rules test mathematical facts that hold for ANY dataset, whatever its distribution:
  min <= median <= max,  min <= mean <= max,  |mean - median| <= SD,  SD <= range/sqrt(2),  min <= max.
A violation therefore proves the published numbers cannot all be describing the same data. It never
proves which number is wrong, or why — root cause stays "unknown".
"""

from __future__ import annotations

import math
from collections.abc import Iterator

from datadoctor.domain.enums import Category, Severity
from datadoctor.domain.models import Evidence, Finding, NormalizedObservation
from datadoctor.rules.base import (
    RuleContext,
    RuleSpec,
    fmt,
    obs_ref,
    observed,
    order_factor,
    power_of_ten_signature,
    record_decimals,
    rule,
    stat_tol,
    stats_excerpt,
)

SCALE_HYPOTHESIS = ("The values differ by an exact power of ten (x10^{k}), a pattern consistent with a unit-scale or "
                    "decimal-separator error somewhere upstream (hypothesis — not verified).")


def _central_outside(ctx: RuleContext, spec: RuleSpec, stat_name: str, label: str) -> Iterator[Finding]:
    for obs in ctx.observations(only_stats=True):
        c, lo, hi = obs.stat(stat_name), obs.stat("minimum"), obs.stat("maximum")
        if not (c and lo and hi) or None in (c.quantity.value, lo.quantity.value, hi.quantity.value):
            continue
        rd = record_decimals(obs)
        v, vlo, vhi = c.quantity.value, lo.quantity.value, hi.quantity.value
        assert v is not None and vlo is not None and vhi is not None
        if vlo > vhi:
            continue  # inverted range is SEM-STAT-005's finding; do not double-report
        below = vlo - v - (stat_tol(c, rd) + stat_tol(lo, rd))
        above = v - vhi - (stat_tol(c, rd) + stat_tol(hi, rd))
        if below <= 0 and above <= 0:
            continue
        bound, bound_name = (vlo, "minimum") if below > 0 else (vhi, "maximum")
        factor = order_factor(v, bound)
        sig = power_of_ten_signature(factor)
        severity = Severity.CRITICAL if factor is not None and factor >= 10 else Severity.ERROR
        hyps = [SCALE_HYPOTHESIS.format(k=sig["k"])] if sig.get("exact_power_of_ten") else []
        if stat_name == "average" and abs(vhi - vlo) <= stat_tol(hi, rd) + stat_tol(lo, rd):
            half = vlo / 2
            if abs(v - half) <= stat_tol(c, rd) + stat_tol(lo, rd) / 2:
                hyps.append("Every value equals the reported min/max, yet the mean is half of it: consistent with the "
                            "mean being computed with half the detection limit substituted for censored values while "
                            "min/max report the limit itself (hypothesis — not verified).")
        interp = ("Likely scale inconsistency between statistics of the same record (root cause unknown)."
                  if sig.get("exact_power_of_ten") else
                  "The summary statistics are internally inconsistent (root cause unknown).")
        where = "below the minimum" if below > 0 else "above the maximum"
        factor_txt = f" — about {fmt(round(factor, 1))}x {'smaller' if below > 0 else 'larger'}" if factor and factor >= 2 else ""
        yield ctx.make(
            spec,
            resource=obs_ref(obs, c.fhir_path, ctx.display(obs)),
            severity=severity,
            confidence=0.95,
            summary=(f"{ctx.display(obs)}: the published {label} ({fmt(v)}) lies {where} ({fmt(bound)}){factor_txt}. "
                     f"A {label} can never fall outside the range of the data it summarises."),
            evidence=Evidence(
                observed=[observed(lo), observed(c), observed(hi)],
                constraint=f"minimum <= {label} <= maximum",
                expected=f"The {label} must lie between the minimum and the maximum of the same data.",
                measures={"violated_bound": bound_name, "distance": round(max(below, above), 10),
                          "factor": round(factor, 4) if factor else None, **sig,
                          "tolerance_applied": round(stat_tol(c, rd) + stat_tol(lo if below > 0 else hi, rd), 10)},
                raw_excerpt=stats_excerpt(obs),
            ),
            interpretation=interp,
            hypotheses=hyps,
        )


SPEC_001 = RuleSpec(
    id="SEM-STAT-001", version="1.0", title="Median outside the reported [minimum, maximum]",
    category=Category.STATISTICAL,
    severity="ERROR; CRITICAL when the median is >= 10x away from the violated bound",
    confidence="0.95 — a mathematical identity; residual uncertainty only in statistic labelling",
    applies_to="Observations with observation-statistics components median, minimum and maximum",
    constraint="minimum <= median <= maximum (within half a unit of the last published decimal)",
    rationale="The median is an order statistic of the data; it is bounded by the smallest and largest value.",
)
SPEC_002 = RuleSpec(
    id="SEM-STAT-002", version="1.0", title="Mean outside the reported [minimum, maximum]",
    category=Category.STATISTICAL,
    severity="ERROR; CRITICAL when the mean is >= 10x away from the violated bound",
    confidence="0.95 — a mathematical identity",
    applies_to="Observations with observation-statistics components average, minimum and maximum",
    constraint="minimum <= mean <= maximum (within published precision)",
    rationale="An arithmetic mean is a convex combination of the data, so it lies within their range.",
)


@rule(SPEC_001)
def median_outside_range(ctx: RuleContext) -> Iterator[Finding]:
    yield from _central_outside(ctx, SPEC_001, "median", "median")


@rule(SPEC_002)
def mean_outside_range(ctx: RuleContext) -> Iterator[Finding]:
    yield from _central_outside(ctx, SPEC_002, "average", "mean")


SPEC_003 = RuleSpec(
    id="SEM-STAT-003", version="1.0", title="Mean–median gap exceeds the standard deviation",
    category=Category.STATISTICAL,
    severity="ERROR",
    confidence="0.9 — holds for every distribution with finite variance, for population and sample SD",
    applies_to="Observations publishing average, median and std-dev",
    constraint="|mean - median| <= SD",
    rationale="Hotelling & Solomons (1932): |mu - m| <= sigma. The sample SD (Bessel) is >= the population SD, "
              "so the bound also holds with the sample SD.",
    references=("Hotelling H, Solomons LM. The limits of a measure of skewness. Ann Math Stat 1932;3:141-142.",),
)


@rule(SPEC_003)
def mean_median_gap(ctx: RuleContext) -> Iterator[Finding]:
    for obs in ctx.observations(only_stats=True):
        a, m, s = obs.stat("average"), obs.stat("median"), obs.stat("std-dev")
        if not (a and m and s) or None in (a.quantity.value, m.quantity.value, s.quantity.value):
            continue
        rd = record_decimals(obs)
        va, vm, vs = a.quantity.value, m.quantity.value, s.quantity.value
        assert va is not None and vm is not None and vs is not None
        if vs < 0:
            continue
        gap = abs(va - vm)
        slack = stat_tol(a, rd) + stat_tol(m, rd) + stat_tol(s, rd)
        if gap - slack <= vs:
            continue
        yield ctx.make(
            SPEC_003,
            resource=obs_ref(obs, m.fhir_path, ctx.display(obs)),
            severity=Severity.ERROR,
            confidence=0.9,
            summary=(f"{ctx.display(obs)}: mean ({fmt(va)}) and median ({fmt(vm)}) differ by {fmt(round(gap, 6))}, "
                     f"more than the standard deviation ({fmt(vs)}). No real dataset can have that shape."),
            evidence=Evidence(
                observed=[observed(a), observed(m), observed(s)],
                constraint="|mean - median| <= standard deviation",
                expected="The distance between mean and median is at most one standard deviation.",
                measures={"gap": round(gap, 10), "std_dev": vs, "ratio_gap_to_sd": round(gap / vs, 4) if vs else None,
                          "tolerance_applied": round(slack, 10)},
                raw_excerpt=stats_excerpt(obs),
            ),
            interpretation="The mean, median and standard deviation cannot describe the same data (root cause unknown).",
        )


SPEC_004 = RuleSpec(
    id="SEM-STAT-004", version="1.0", title="Standard deviation incompatible with the reported range",
    category=Category.STATISTICAL,
    severity="ERROR",
    confidence="0.9 — the bound is attained only by n = 2 samples at the extremes",
    applies_to="Observations publishing std-dev, minimum and maximum",
    constraint="SD <= (max - min)/sqrt(2); and SD = 0 when min = max",
    rationale="For data inside [min, max] the sample SD is maximised by two points at the extremes, giving "
              "range/sqrt(2); if every value is equal the SD must be zero.",
)


@rule(SPEC_004)
def sd_vs_range(ctx: RuleContext) -> Iterator[Finding]:
    for obs in ctx.observations(only_stats=True):
        s, lo, hi = obs.stat("std-dev"), obs.stat("minimum"), obs.stat("maximum")
        if not (s and lo and hi) or None in (s.quantity.value, lo.quantity.value, hi.quantity.value):
            continue
        rd = record_decimals(obs)
        vs, vlo, vhi = s.quantity.value, lo.quantity.value, hi.quantity.value
        assert vs is not None and vlo is not None and vhi is not None
        if vlo > vhi:
            continue
        rng_max = (vhi - vlo) + stat_tol(hi, rd) + stat_tol(lo, rd)
        bound = rng_max / math.sqrt(2)
        if vs - stat_tol(s, rd) <= bound:  # also covers min = max: the bound shrinks to the rounding slack
            continue
        yield ctx.make(
            SPEC_004,
            resource=obs_ref(obs, s.fhir_path, ctx.display(obs)),
            severity=Severity.ERROR,
            confidence=0.9,
            summary=(f"{ctx.display(obs)}: the standard deviation ({fmt(vs)}) is larger than any dataset with range "
                     f"[{fmt(vlo)}, {fmt(vhi)}] can produce (max {fmt(round((vhi - vlo) / math.sqrt(2), 6))})."),
            evidence=Evidence(
                observed=[observed(lo), observed(hi), observed(s)],
                constraint="SD <= (maximum - minimum) / sqrt(2)",
                expected="The spread of the data cannot exceed what its own range allows.",
                measures={"sd_upper_bound": round(bound, 10), "range": vhi - vlo},
                raw_excerpt=stats_excerpt(obs),
            ),
            interpretation="The standard deviation and range cannot describe the same data (root cause unknown).",
        )


SPEC_005 = RuleSpec(
    id="SEM-STAT-005", version="1.0", title="Minimum greater than maximum",
    category=Category.STATISTICAL, severity="ERROR", confidence="0.95",
    applies_to="Observations publishing minimum and maximum",
    constraint="minimum <= maximum", rationale="By definition.",
)


@rule(SPEC_005)
def inverted_range(ctx: RuleContext) -> Iterator[Finding]:
    for obs in ctx.observations(only_stats=True):
        lo, hi = obs.stat("minimum"), obs.stat("maximum")
        if not (lo and hi) or lo.quantity.value is None or hi.quantity.value is None:
            continue
        rd = record_decimals(obs)
        if lo.quantity.value - hi.quantity.value <= stat_tol(lo, rd) + stat_tol(hi, rd):
            continue
        yield ctx.make(
            SPEC_005, resource=obs_ref(obs, lo.fhir_path, ctx.display(obs)), severity=Severity.ERROR, confidence=0.95,
            summary=f"{ctx.display(obs)}: minimum ({fmt(lo.quantity.value)}) exceeds maximum ({fmt(hi.quantity.value)}).",
            evidence=Evidence(observed=[observed(lo), observed(hi)], constraint="minimum <= maximum",
                              expected="The minimum is never larger than the maximum.", raw_excerpt=stats_excerpt(obs)),
            interpretation="Minimum and maximum are swapped or mislabelled (root cause unknown).",
        )


SPEC_006 = RuleSpec(
    id="SEM-STAT-006", version="1.0", title="Negative standard deviation",
    category=Category.STATISTICAL, severity="CRITICAL", confidence="0.99",
    applies_to="Observations publishing std-dev",
    constraint="SD >= 0",
    rationale="A standard deviation is the square root of a variance, so it can never be negative. Checked on its own, "
              "because a record may publish a standard deviation without a minimum and maximum (added after the "
              "what-if lab showed that no rule caught it).",
)


@rule(SPEC_006)
def negative_sd(ctx: RuleContext) -> Iterator[Finding]:
    for obs in ctx.observations(only_stats=True):
        s = obs.stat("std-dev")
        if not s or s.quantity.value is None:
            continue
        rd = record_decimals(obs)
        if s.quantity.value + stat_tol(s, rd) >= 0:  # -0.0, or a negative value within rounding, is not negative
            continue
        yield ctx.make(
            SPEC_006, resource=obs_ref(obs, s.fhir_path, ctx.display(obs)), severity=Severity.CRITICAL, confidence=0.99,
            summary=f"{ctx.display(obs)}: the standard deviation is negative ({fmt(s.quantity.value)}), which is impossible.",
            evidence=Evidence(observed=[observed(s)], constraint="SD >= 0",
                              expected="A standard deviation is never negative.", raw_excerpt=stats_excerpt(obs)),
            interpretation="The standard deviation cannot be correct as published (root cause unknown).",
        )


SPEC_SCALE = RuleSpec(
    id="SEM-SCALE-001", version="1.1", title="Mean and median differ by orders of magnitude",
    category=Category.STATISTICAL,
    severity="ERROR",
    confidence="0.9 when the ratio is an exact power of ten (a scale signature); 0.75 otherwise",
    applies_to="Observations publishing a positive average and median",
    constraint="1/100 < mean/median < 100",
    rationale="Mean and median are both measures of the centre of the same data; a ratio >= 100 is essentially "
              "never produced by real environmental data and an exact power of ten is the signature of a scale "
              "mix-up. Extremes (min/max) are NOT compared with each other or with the centre: a pollutant minimum "
              "near zero is normal (v1.1, after Gate-0 pre-review). Min/max are only used to say which of the two "
              "central values sits with the rest of the record.",
)


@rule(SPEC_SCALE)
def scale_divergence(ctx: RuleContext) -> Iterator[Finding]:
    for obs in ctx.observations(only_stats=True):
        a, m = obs.stat("average"), obs.stat("median")
        if not (a and m) or not a.quantity.value or not m.quantity.value or a.quantity.value <= 0 or m.quantity.value <= 0:
            continue
        factor = order_factor(a.quantity.value, m.quantity.value)
        if factor is None or factor < 100:
            continue
        sig = power_of_ten_signature(factor)
        exact = bool(sig.get("exact_power_of_ten"))
        # Which central value sits with the extremes? (geometric centre of positive min/max)
        ext = [s.quantity.value for s in (obs.stat("minimum"), obs.stat("maximum")) if s and s.quantity.value and s.quantity.value > 0]
        outlying: list[str] = []
        if ext:
            centre = sum(math.log10(v) for v in ext) / len(ext)
            da, dm = abs(math.log10(a.quantity.value) - centre), abs(math.log10(m.quantity.value) - centre)
            if abs(da - dm) >= 1:
                outlying = ["average" if da > dm else "median"]
        odd = obs.stat(outlying[0]) if outlying else m
        assert odd is not None
        other = a if odd is m else m
        who = f"the {'mean' if odd is a else 'median'} ({fmt(odd.quantity.value)})" if outlying else               f"mean ({fmt(a.quantity.value)}) and median ({fmt(m.quantity.value)})"
        rest = f" is on a different scale from the rest of the record (~{fmt(other.quantity.value)})" if outlying else " differ"
        yield ctx.make(
            SPEC_SCALE,
            resource=obs_ref(obs, odd.fhir_path, ctx.display(obs)),
            severity=Severity.ERROR,
            confidence=0.9 if exact else 0.75,
            summary=f"{ctx.display(obs)}: {who}{rest} — a factor of about {fmt(round(factor, 1))}.",
            evidence=Evidence(
                observed=[observed(s) for s in obs.stats if s.stat in ("minimum", "maximum", "average", "median")],
                constraint="1/100 < mean / median < 100",
                expected="The mean and the median of the same data lie on the same scale.",
                measures={"outlying_statistics": outlying, "mean_median_ratio": round(a.quantity.value / m.quantity.value, 6),
                          "factor": round(factor, 4), **sig},
                raw_excerpt=stats_excerpt(obs),
            ),
            interpretation=("Likely scale inconsistency (root cause unknown)." if exact else
                            "Mean and median of this record are on different scales (root cause unknown)."),
            hypotheses=[SCALE_HYPOTHESIS.format(k=sig["k"])] if exact else [],
        )


def stat_rule_ids() -> list[str]:
    return [SPEC_001.id, SPEC_002.id, SPEC_003.id, SPEC_004.id, SPEC_005.id, SPEC_SCALE.id]


__all__ = ["stat_rule_ids", "NormalizedObservation"]
