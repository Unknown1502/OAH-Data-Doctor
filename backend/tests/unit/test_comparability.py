"""Golden comparability tests (docs/06_TEST_PLAN.md §Comparability)."""

import pytest

from datadoctor.comparability.engine import ComparisonError, compare
from datadoctor.domain.enums import ComparabilityVerdict as V
from datadoctor.domain.enums import DimensionStatus as D
from datadoctor.rules.registry import run_all
from tests.helpers import KN, OAH, dataset, group, location, stats_obs, value_obs


def _cmp(ds, a, b, sa=None, sb=None):
    return compare(ds, KN, run_all(ds, KN), a, b, sa, sb)


def _dim(c, rule_id):
    return next(d for d in c.dimensions if d.rule_id == rule_id)


def test_golden_benevento_35_74_vs_oslo_non_overlapping_band_is_not():
    ds = dataset(location("Loc-BN"), location("Loc-OS", 59.9, 10.7), group("G-BN-F", "female", 35, 74), group("G-OS-18", None, 18, 29),
                 value_obs("BN", 29, code="obesity", location="Loc-BN", group="G-BN-F"),
                 value_obs("OS", 3, code="bmi-above-30", location="Loc-OS", group="G-OS-18"))
    c = _cmp(ds, "BN", "OS")
    assert c.verdict == V.NOT
    assert _dim(c, "CMP-POPULATION").status == D.FAIL
    assert _dim(c, "CMP-MEASURE").status == D.CONDITIONAL  # obesity vs BMI>=30: related, definition unverified


def test_golden_identical_measure_unit_cohort_period_is_direct():
    ds = dataset(location("L1", 35.1, 25.0), location("L2", 35.2, 25.1),
                 value_obs("A", 16.1, unit="Cel", code="waterTemperature", location="L1", profile="observation-indicators-oah", date="2024-11-21"),
                 value_obs("B", 18.6, unit="Cel", code="waterTemperature", location="L2", profile="observation-indicators-oah", date="2024-11-21"))
    for r in ("A", "B"):
        ds.raw["Observation"][r]["performer"] = [{"display": "Lab"}]
        ds.observations[r].performer = ["Lab"]
    c = _cmp(ds, "A", "B")
    assert c.verdict == V.DIRECT, [(d.rule_id, d.status, d.reason) for d in c.dimensions]


def test_golden_unit_convertible_is_conditional_with_transformation():
    ds = dataset(location("L1", 35.1, 25.0), location("L2", 35.2, 25.1),
                 value_obs("A", 1.2, unit="mS/cm", code="conductivity", location="L1", profile="observation-indicators-oah", date="2024-11-21"),
                 value_obs("B", 1500, unit="uS/cm", code="conductivity", location="L2", profile="observation-indicators-oah", date="2024-11-21"))
    for r in ("A", "B"):
        ds.raw["Observation"][r]["performer"] = [{"display": "Lab"}]
        ds.observations[r].performer = ["Lab"]
    c = _cmp(ds, "A", "B")
    assert c.verdict == V.CONDITIONAL
    assert _dim(c, "CMP-UNIT").status == D.CONDITIONAL
    assert any("1000" in t for t in c.transformations)


def test_integrity_findings_block_otherwise_comparable_values():
    ds = dataset(stats_obs("Y13", average=198000, maximum=211000, minimum=185000, median=19.8, year=2013),
                 stats_obs("Y14", average=22.5, maximum=24.0, minimum=21.0, median=22.5, year=2014))
    c = _cmp(ds, "Y13", "Y14", "average", "average")
    assert c.verdict == V.BLOCKED_BY_INTEGRITY
    assert c.blocking_findings


def test_not_outranks_blocked():
    # mean vs median is not the same quantity: NOT even though the record is also broken
    ds = dataset(stats_obs("Y13", average=198000, maximum=211000, minimum=185000, median=19.8, year=2013),
                 stats_obs("Y14", average=22.5, maximum=24.0, minimum=21.0, median=22.5, year=2014))
    c = _cmp(ds, "Y13", "Y14", "average", "median")
    assert c.verdict == V.NOT
    assert _dim(c, "CMP-AGGREGATION").status == D.FAIL


def test_broader_measure_is_not_comparable():
    ds = dataset(group("G", None, 0), value_obs("CVD", 5, code="cvd", group="G"), value_obs("DCC", 11, code="diabate-copd-cvd", group="G"))
    assert _cmp(ds, "CVD", "DCC").verdict == V.NOT


def test_different_media_are_not_comparable():
    ds = dataset(value_obs("W", 16.1, unit="Cel", code="waterTemperature", profile="observation-indicators-oah", date="2024-11-21"),
                 stats_obs("AIR", average=20.0, median=19.0, minimum=1.0, maximum=80.0, unit="ug/m3",
                           system="https://oneaquahealth.eu/air-parameters", code="no2", text=None))
    assert _cmp(ds, "W", "AIR", None, "average").verdict == V.NOT


def test_unknown_observation_raises():
    with pytest.raises(ComparisonError):
        _cmp(dataset(value_obs("A", 1)), "A", "missing")


def test_alternatives_are_computed_from_existing_records():
    ds = dataset(location("Loc-BN"), location("Loc-OS", 59.9, 10.7), group("G-BN-F", "female", 35, 74),
                 group("G-OS-18", None, 18, 29), group("G-OS-40", None, 40, 49),
                 value_obs("BN", 29, code="obesity", location="Loc-BN", group="G-BN-F"),
                 value_obs("OS18", 3, code="bmi-above-30", location="Loc-OS", group="G-OS-18"),
                 value_obs("OS40", 7, code="bmi-above-30", location="Loc-OS", group="G-OS-40"))
    c = _cmp(ds, "BN", "OS18")
    assert any("OS40" in a for a in c.supported_alternatives)
    assert not any("OS18" in a for a in c.supported_alternatives)


def test_codes_differ_but_same_measure_is_equivalent():
    ds = dataset(stats_obs("LAB", average=19.8, maximum=21.1, minimum=18.5, median=19.8),
                 stats_obs("LAB2", average=20.1, maximum=21.0, minimum=19.0, median=20.1, system=OAH, code="waterTemperature", text=None))
    assert _dim(_cmp(ds, "LAB", "LAB2", "average", "average"), "CMP-MEASURE").status == D.PASS
