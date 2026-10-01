"""The evidence chain: a finding's calculation only writes out the backend's own evidence, so anyone can check it by hand.

Every result shown is a measure the rule computed; every operand is a published value or another measure; redoing the
arithmetic from the operands gives the shown result. Nothing here may claim a cause or a corrected value.
"""

import asyncio
import math
import re
from pathlib import Path

import pytest

from datadoctor.audit.calculation import calculation, exact
from datadoctor.audit.service import ANCHOR_ID, run_audit
from datadoctor.config import REPO_ROOT, Settings
from datadoctor.domain.models import Finding

SNAP_DIR = REPO_ROOT / "data" / "snapshots"


def _latest() -> Path:
    snaps = sorted(p for p in SNAP_DIR.iterdir() if (p / "manifest.json").is_file())
    if not snaps:
        pytest.skip("no snapshot committed")
    return snaps[-1]


@pytest.fixture(scope="module")
def findings() -> list[Finding]:
    res, _ = asyncio.run(run_audit(Settings(snapshot_id=_latest().name), "snapshot", _latest().name))
    return res.findings


def _anchor(findings: list[Finding], rule_id: str) -> Finding:
    return next(f for f in findings if f.rule_id == rule_id and f.resource.resource_id == ANCHOR_ID)


def test_anchor_mean_median_ratio_is_written_out(findings):
    f = _anchor(findings, "SEM-SCALE-001")
    c = calculation(f)
    assert c is not None
    step = c.steps[0]
    assert step.expression == "average / median = 198,000 / 19.8"
    assert step.result == "10,000"
    assert step.measure == "mean_median_ratio" and step.value == f.evidence.measures["mean_median_ratio"]
    assert c.result == "The average is 10,000 times the median: exactly 10⁴."
    assert c.check is not None and c.check.evaluated == "10,000 ≥ 100" and c.check.holds is False
    assert c.check.constraint == f.evidence.constraint


def test_anchor_median_below_minimum_is_written_out(findings):
    f = _anchor(findings, "SEM-STAT-001")
    c = calculation(f)
    assert c is not None
    assert c.check is not None and c.check.evaluated == "19.8 < 185,000" and c.check.holds is False
    step = c.steps[0]
    assert step.expression == "minimum / median = 185,000 / 19.8"
    assert step.result == exact(f.evidence.measures["factor"])
    assert c.result.startswith("The median is ") and "times smaller than the minimum" in c.result


def test_anchor_mean_median_gap_is_written_out(findings):
    f = _anchor(findings, "SEM-STAT-003")
    c = calculation(f)
    assert c is not None
    assert c.steps[0].expression == "|average − median| = |198,000 − 19.8|"
    assert c.steps[0].result == exact(f.evidence.measures["gap"]) == "197,980.2"
    assert c.steps[1].measure == "ratio_gap_to_sd"


def _redo(operation: str, a: list[float]) -> float:
    """The arithmetic a step names, redone from its operands."""
    if operation == "ratio":
        return a[0] / a[1]
    if operation == "difference":
        return abs(a[0] - a[1])
    if operation == "relative_excess":
        return (a[0] - a[1]) / a[1]
    return sum(a)


def test_every_calculation_restates_the_backend_evidence(findings):
    checked = 0
    for f in findings:
        c = calculation(f)
        if c is None:
            continue
        m = f.evidence.measures
        published = {float(o.value) for o in f.evidence.observed if isinstance(o.value, int | float)}
        for step in c.steps:
            if step.measure is not None:
                # The shown result is the rule's own measure, with every digit it kept.
                assert step.value == m[step.measure], (f.id, step)
                assert step.result == exact(m[step.measure]), (f.id, step)
            if step.operation in ("ratio", "difference", "relative_excess", "sum"):
                a = step.operands
                redone = _redo(step.operation, a)
                assert step.value is not None
                assert math.isclose(redone, step.value, rel_tol=1e-3, abs_tol=1e-9), (f.id, step, redone)
                # Operands are published values or other measures, never numbers from elsewhere.
                allowed = published | {float(v) for v in m.values() if isinstance(v, int | float) and not isinstance(v, bool)}
                if step.operation != "relative_excess":  # those operands are parsed from the "a vs b" evidence text
                    assert all(any(math.isclose(x, p, rel_tol=1e-9) for p in allowed) for x in a), (f.id, step)
            checked += 1
        if c.check is not None:
            assert c.check.holds is False, f.id  # a finding exists because its constraint does not hold
    assert checked > 300  # the snapshot has hundreds of findings with arithmetic


def test_calculations_never_state_a_cause_or_a_corrected_value(findings):
    banned = re.compile(r"\b(correct(ed|ion)?|should be|actual(ly)?|real value|corrupt\w*|typo|because|due to)\b", re.I)
    for f in findings:
        c = calculation(f)
        if c is None:
            continue
        text = " ".join([c.result, *(s.label + " " + s.expression for s in c.steps), c.check.evaluated if c.check else ""])
        assert not banned.search(text), (f.id, text)


def test_exact_shows_every_digit_and_never_scientific_notation():
    assert exact(198000.0) == "198,000"
    assert exact(197980.2) == "197,980.2"
    assert exact(9343.4343) == "9,343.4343"
    assert exact(0.374) == "0.374"
    assert exact(4.0) == "4"
    assert exact(-5.0) == "-5"
    assert "e" not in exact(1234567890.5)


def test_range_check_shows_readable_units(findings):
    c = calculation(_anchor(findings, "SEM-RANGE-001"))
    assert c is not None and c.check is not None
    assert c.check.evaluated == "average 198,000 > 100 °C; maximum 211,000 > 100 °C; minimum 185,000 > 100 °C"


def test_findings_without_arithmetic_have_no_calculation(findings):
    for rule_id in ("STR-UNIT-001", "SEM-DEF-001", "SEM-TEMP-001"):
        f = next(x for x in findings if x.rule_id == rule_id)
        assert calculation(f) is None, rule_id
