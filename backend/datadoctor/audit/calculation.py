"""The arithmetic behind a finding, written out so anyone can check it by hand.

Presentation only. Every result shown is a measure the rule already computed (`Finding.evidence.measures`), every operand
is a published value or another measure, and numbers are shown with every digit the rule kept (`exact`).
Nothing here decides anything, changes a value, or names a cause; a finding whose rule does no arithmetic has no
calculation. Tested in `tests/integration/test_calculation.py`.
"""

from __future__ import annotations

import math
import re
from typing import Any, Literal

from pydantic import BaseModel, Field

from datadoctor.domain.models import Finding

Operation = Literal["ratio", "difference", "relative_excess", "sum", "log10", "count"]
_SUPERSCRIPT = str.maketrans("0123456789-", "⁰¹²³⁴⁵⁶⁷⁸⁹⁻")


# Display names for UCUM codes, the same as the UI's UNIT_DISPLAY (frontend/src/lib/format.ts).
_UNIT_DISPLAY = {"Cel": "°C", "ug/m3": "µg/m³", "ug/L": "µg/L", "uS/cm": "µS/cm", "[pH]": "pH"}


def exact(v: float | int | None) -> str:
    """Every digit the rule kept, with thousands separators and never in scientific notation, so the arithmetic can be
    redone by hand (198,000 − 19.8 shows as 197,980.2, not a rounded 197,980)."""
    if v is None:
        return "—"
    if isinstance(v, bool) or not isinstance(v, int | float) or not math.isfinite(v):
        return str(v)
    if float(v).is_integer() and abs(v) < 1e15:
        return f"{int(v):,}"
    if 0 < abs(v) < 1e-6:
        return repr(float(v))
    return f"{v:,.10f}".rstrip("0").rstrip(".")


def _unit(u: str) -> str:
    return _UNIT_DISPLAY.get(u, u)


class CalcStep(BaseModel):
    label: str  # what is computed, in words
    expression: str  # e.g. "average / median = 198,000 / 19.8"
    result: str  # the rule's own value, every digit it kept
    value: float | None = None  # that value, unformatted
    measure: str | None = None  # the key in evidence.measures the result comes from
    operation: Operation | None = None
    operands: list[float] = Field(default_factory=list)


class ConstraintCheck(BaseModel):
    constraint: str  # the rule's constraint, verbatim
    evaluated: str  # the constraint with the published numbers in it, e.g. "10,000 ≥ 100"
    holds: bool  # always False for a finding: it exists because the constraint does not hold


class Calculation(BaseModel):
    steps: list[CalcStep]
    result: str  # the derived result in one sentence, e.g. "The average is 10,000 times the median: exactly 10⁴."
    check: ConstraintCheck | None


def _num(f: Finding, label: str) -> float | None:
    for o in f.evidence.observed:
        if o.label == label and isinstance(o.value, int | float) and not isinstance(o.value, bool):
            return float(o.value)
    return None


def _power_of_ten(value: float | None, m: dict[str, Any]) -> str:
    """"exactly 10⁴" only when the value is 10^k; "within 5 % of 10⁴" when the rule's power-of-ten signature
    (|log10 - k| < 0.02, i.e. within about 4.7 %) holds but the value is not exact."""
    if value is None or not m.get("exact_power_of_ten") or m.get("k") is None:
        return ""
    k = int(m["k"])
    sup = f"10{str(k).translate(_SUPERSCRIPT)}"
    return f"exactly {sup}" if math.isclose(value, 10.0**k, rel_tol=1e-9) else f"within 5 % of {sup}"


def _central_outside(f: Finding, centre: str) -> Calculation | None:
    m = f.evidence.measures
    v, lo, hi = _num(f, centre), _num(f, "minimum"), _num(f, "maximum")
    if v is None or lo is None or hi is None:
        return None
    below = m.get("violated_bound") == "minimum"
    bound_name, bound = ("minimum", lo) if below else ("maximum", hi)
    check = ConstraintCheck(constraint=f.evidence.constraint, holds=False,
                            evaluated=f"{exact(v)} < {exact(lo)}" if below else f"{exact(v)} > {exact(hi)}")
    factor = m.get("factor")
    if not isinstance(factor, int | float):
        return Calculation(steps=[], check=check,
                           result=f"The {centre} lies {'below the minimum' if below else 'above the maximum'}.")
    big, small = (bound_name, bound), (centre, v)
    if v > bound:
        big, small = small, big
    step = CalcStep(label=f"How far the {centre} is from the {bound_name}",
                    expression=f"{big[0]} / {small[0]} = {exact(big[1])} / {exact(small[1])}",
                    result=exact(factor), value=float(factor), measure="factor", operation="ratio",
                    operands=[big[1], small[1]])
    pow10 = _power_of_ten(float(factor), m)
    where = "smaller than the minimum" if below else "larger than the maximum"
    return Calculation(steps=[step], check=check,
                       result=f"The {centre} is {exact(factor)} times {where}{': ' + pow10 if pow10 else ''}.")


def _scale(f: Finding) -> Calculation | None:
    m = f.evidence.measures
    a, med = _num(f, "average"), _num(f, "median")
    ratio, factor = m.get("mean_median_ratio"), m.get("factor")
    if a is None or med is None or not isinstance(ratio, int | float) or not isinstance(factor, int | float):
        return None
    if a >= med:
        step = CalcStep(label="Ratio of the average to the median", expression=f"average / median = {exact(a)} / {exact(med)}",
                        result=exact(ratio), value=float(ratio), measure="mean_median_ratio", operation="ratio",
                        operands=[a, med])
        shown, sentence = float(ratio), f"The average is {exact(ratio)} times the median"
    else:
        step = CalcStep(label="Ratio of the median to the average", expression=f"median / average = {exact(med)} / {exact(a)}",
                        result=exact(factor), value=float(factor), measure="factor", operation="ratio",
                        operands=[med, a])
        shown, sentence = float(factor), f"The median is {exact(factor)} times the average"
    steps = [step]
    if isinstance(m.get("log10_factor"), int | float):
        steps.append(CalcStep(label="Orders of magnitude", expression=f"log10({exact(shown)})", result=exact(m["log10_factor"]),
                              value=float(m["log10_factor"]), measure="log10_factor", operation="log10",
                              operands=[shown]))
    pow10 = _power_of_ten(shown, m)
    check = ConstraintCheck(constraint=f.evidence.constraint, holds=False,
                            evaluated=f"{exact(ratio)} ≥ 100" if ratio >= 100 else f"{exact(ratio)} ≤ 1/100")
    return Calculation(steps=steps, check=check, result=f"{sentence}{': ' + pow10 if pow10 else ''}.")


def _gap(f: Finding) -> Calculation | None:
    m = f.evidence.measures
    a, med, sd = _num(f, "average"), _num(f, "median"), _num(f, "std-dev")
    gap, ratio = m.get("gap"), m.get("ratio_gap_to_sd")
    if a is None or med is None or sd is None or not isinstance(gap, int | float):
        return None
    steps = [CalcStep(label="Gap between the average and the median", expression=f"|average − median| = |{exact(a)} − {exact(med)}|",
                      result=exact(gap), value=float(gap), measure="gap", operation="difference", operands=[a, med])]
    if isinstance(ratio, int | float):
        steps.append(CalcStep(label="The gap in standard deviations",
                              expression=f"gap / standard deviation = {exact(gap)} / {exact(sd)}", result=exact(ratio),
                              value=float(ratio), measure="ratio_gap_to_sd", operation="ratio", operands=[float(gap), sd]))
    check = ConstraintCheck(constraint=f.evidence.constraint, holds=False, evaluated=f"{exact(gap)} > {exact(sd)}")
    result = (f"The average and the median are {exact(ratio)} standard deviations apart; at most 1 is possible."
              if isinstance(ratio, int | float) else "The average and the median are further apart than the standard deviation allows.")
    return Calculation(steps=steps, check=check, result=result)


def _sd_range(f: Finding) -> Calculation | None:
    m = f.evidence.measures
    lo, hi, sd = _num(f, "minimum"), _num(f, "maximum"), _num(f, "std-dev")
    rng, bound = m.get("range"), m.get("sd_upper_bound")
    if lo is None or hi is None or sd is None or not isinstance(rng, int | float) or not isinstance(bound, int | float):
        return None
    steps = [CalcStep(label="Range of the data", expression=f"maximum − minimum = {exact(hi)} − {exact(lo)}", result=exact(rng),
                      value=float(rng), measure="range", operation="difference", operands=[hi, lo]),
             CalcStep(label="Largest standard deviation this range allows", expression="range / √2, plus the rounding allowance",
                      result=exact(bound), value=float(bound), measure="sd_upper_bound")]
    check = ConstraintCheck(constraint=f.evidence.constraint, holds=False, evaluated=f"{exact(sd)} > {exact(bound)}")
    return Calculation(steps=steps, check=check,
                       result=f"The standard deviation ({exact(sd)}) is larger than any data with this range can have.")


def _range(f: Finding, hard: bool) -> Calculation | None:
    bounds = f.evidence.measures.get("bounds") or {}
    unit = _unit(f.evidence.measures.get("canonical_unit") or "")
    parts = []
    for o in f.evidence.observed:
        if not isinstance(o.value, int | float) or isinstance(o.value, bool):
            continue
        if "max" in bounds and o.value > bounds["max"]:
            parts.append(f"{o.label} {exact(o.value)} > {exact(bounds['max'])} {unit}".strip())
        elif "min" in bounds and o.value < bounds["min"]:
            parts.append(f"{o.label} {exact(o.value)} < {exact(bounds['min'])} {unit}".strip())
    if not parts:
        return None
    kind = "possible" if hard else "typical"
    n = len(parts)
    result = (f"{n} published value{'s' if n > 1 else ''} {'lie' if n > 1 else 'lies'} outside the {kind} range"
              + ("." if hard else " (unusual, not impossible)."))
    return Calculation(steps=[], result=result,
                       check=ConstraintCheck(constraint=f.evidence.constraint, holds=False, evaluated="; ".join(parts)))


_PAIR = re.compile(r"^\s*(-?[\d,]*\.?\d+)\s+vs\s+(-?[\d,]*\.?\d+)\s*$")


def _subset(f: Finding) -> Calculation | None:
    mre = f.evidence.measures.get("max_relative_excess")
    pairs = []
    for o in f.evidence.observed:
        hit = _PAIR.match(str(o.value))
        if hit:
            a, b = (float(x.replace(",", "")) for x in hit.groups())
            pairs.append((o.label.split(":")[0], hit.group(1), hit.group(2), a, b))
    if not pairs or not isinstance(mre, int | float):
        return None
    stat, sa, sb, a, b = max(pairs, key=lambda p: (p[3] - p[4]) / p[4] if p[4] > 0 else math.inf)
    step = CalcStep(label=f"How much the PM2.5 {stat} exceeds the PM10 {stat}", expression=f"(PM2.5 − PM10) / PM10 = ({sa} − {sb}) / {sb}",
                    result=exact(mre), value=float(mre), measure="max_relative_excess", operation="relative_excess",
                    operands=[a, b])
    check = ConstraintCheck(constraint=f.evidence.constraint, holds=False,
                            evaluated="; ".join(f"{s}: {x} > {y}" for s, x, y, _, _ in pairs))
    return Calculation(steps=[step], check=check, result=f"PM2.5 exceeds PM10 by {exact(round(mre * 100, 1))} % ({stat}).")


def _complements(f: Finding) -> Calculation | None:
    total = f.evidence.measures.get("sum")
    vals = [float(o.value) for o in f.evidence.observed if isinstance(o.value, int | float) and not isinstance(o.value, bool)]
    if not isinstance(total, int | float) or not vals:
        return None
    step = CalcStep(label="Sum of the complementary shares", expression=" + ".join(exact(v) for v in vals), result=exact(total),
                    value=float(total), measure="sum", operation="sum", operands=vals)
    return Calculation(steps=[step], result=f"The complementary shares add up to {exact(total)} %, not 100 %.",
                       check=ConstraintCheck(constraint=f.evidence.constraint, holds=False, evaluated=f"{exact(total)} ≠ 100"))


def _synonyms(f: Finding) -> Calculation | None:
    m = f.evidence.measures
    d, p = m.get("divergent_pairs"), m.get("matched_pairs")
    if not isinstance(d, int) or not isinstance(p, int):
        return None
    return Calculation(steps=[], result=f"{d} of {p} pairs of indicators with the same definition report different values.",
                       check=ConstraintCheck(constraint=f.evidence.constraint, holds=False, evaluated=f"{d} of {p} pairs differ"))


def _same_position(f: Finding) -> Calculation | None:
    m = f.evidence.measures
    if not isinstance(m.get("sites"), int):
        return None
    return Calculation(steps=[], result=f"{m['sites']} distinct monitoring sites share one position.",
                       check=ConstraintCheck(constraint=f.evidence.constraint, holds=False,
                                             evaluated=f"{m['sites']} sites at {m.get('latitude')}, {m.get('longitude')}"))


def _min_max(f: Finding) -> Calculation | None:
    lo, hi = _num(f, "minimum"), _num(f, "maximum")
    if lo is None or hi is None:
        return None
    return Calculation(steps=[], result="The minimum is larger than the maximum.",
                       check=ConstraintCheck(constraint=f.evidence.constraint, holds=False, evaluated=f"{exact(lo)} > {exact(hi)}"))


def _negative_sd(f: Finding) -> Calculation | None:
    sd = _num(f, "std-dev")
    if sd is None:
        return None
    return Calculation(steps=[], result="The standard deviation is negative.",
                       check=ConstraintCheck(constraint=f.evidence.constraint, holds=False, evaluated=f"{exact(sd)} < 0"))


def calculation(f: Finding) -> Calculation | None:
    """The finding's own evidence as checkable arithmetic, or None when its rule does no arithmetic."""
    match f.rule_id:
        case "SEM-STAT-001":
            return _central_outside(f, "median")
        case "SEM-STAT-002":
            return _central_outside(f, "average")
        case "SEM-STAT-003":
            return _gap(f)
        case "SEM-STAT-004":
            return _sd_range(f)
        case "SEM-STAT-005":
            return _min_max(f)
        case "SEM-STAT-006":
            return _negative_sd(f)
        case "SEM-SCALE-001":
            return _scale(f)
        case "SEM-RANGE-001":
            return _range(f, hard=True)
        case "SEM-RANGE-002":
            return _range(f, hard=False)
        case "SEM-XREC-001":
            return _subset(f)
        case "SEM-COHORT-002":
            return _complements(f)
        case "SEM-CODE-001":
            return _synonyms(f)
        case "SEM-SPATIAL-001":
            return _same_position(f)
        case _:
            return None
