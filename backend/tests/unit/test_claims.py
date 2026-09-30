"""Claim guardrail: every claim type, every verdict path (CLM-*)."""

import pytest

from datadoctor.claims.engine import ClaimError, evaluate_claim
from datadoctor.claims.stats import mann_kendall, spearman, theil_sen
from datadoctor.domain.enums import ClaimType as T
from datadoctor.domain.enums import ClaimVerdict as V
from datadoctor.domain.models import StructuredClaim
from datadoctor.rules.registry import run_all
from tests.helpers import AIR, KN, OAH, dataset, group, location, stats_obs, value_obs


def _eval(ds, **kw):
    return evaluate_claim(StructuredClaim(**kw), ds, KN, run_all(ds, KN))


def _no2(oid, avg, lo, hi, loc="Loc-T", year=2019):
    return stats_obs(oid, average=avg, median=avg, minimum=lo, maximum=hi, std_dev=round((hi - lo) / 4, 2),
                     unit="ug/m3", system=AIR, code="no2", location=loc, year=year, text=None)


def _two_sites(a, b):
    ds = dataset(location("S1", 41.1, 14.7), location("S2", 41.2, 14.8), a, b)
    for o in ds.observations.values():
        o.performer = ["ARPAC"]
    return ds


def _assert_complete(r):
    assert r.reasons, "every verdict explains itself"
    assert r.rule_trace
    if r.verdict == V.BLOCKED:
        assert r.blocking_findings
    if r.verdict in (V.UNSUPPORTED, V.BLOCKED, V.CONDITIONAL, V.SUPPORTED):
        assert r.safe_alternatives or r.verdict == V.UNSUPPORTED


# --- COMPARE_HIGHER --------------------------------------------------------------------------------

def test_compare_higher_supported_when_ranges_separate():
    ds = _two_sites(_no2("A", 60, 50, 70, "S1"), _no2("B", 20, 10, 30, "S2"))
    r = _eval(ds, type=T.COMPARE_HIGHER, subject="A", object="B", statistic="average")
    assert r.verdict == V.SUPPORTED
    _assert_complete(r)


def test_compare_higher_conditional_when_ranges_overlap():
    ds = _two_sites(_no2("A", 25, 1, 110, "S1"), _no2("B", 24, 1, 120, "S2"))
    r = _eval(ds, type=T.COMPARE_HIGHER, subject="A", object="B", statistic="average")
    assert r.verdict == V.CONDITIONAL
    assert any("descriptive" in s for s in r.safe_alternatives)


def test_compare_higher_unsupported_when_data_show_opposite():
    ds = _two_sites(_no2("A", 24.48, 0.5, 109.5, "S1"), _no2("B", 24.89, 1.4, 124.7, "S2"))
    r = _eval(ds, type=T.COMPARE_HIGHER, subject="A", object="B", statistic="average")
    assert r.verdict == V.UNSUPPORTED and "opposite" in r.reasons[0]


def test_compare_higher_unsupported_when_not_comparable():
    ds = dataset(location("Loc-BN"), location("Loc-OS", 59.9, 10.7), group("GF", "female", 35, 74), group("G18", None, 18, 29),
                 value_obs("BN", 29, code="obesity", location="Loc-BN", group="GF"),
                 value_obs("OS", 3, code="bmi-above-30", location="Loc-OS", group="G18"))
    r = _eval(ds, type=T.COMPARE_HIGHER, subject="BN", object="OS")
    assert r.verdict == V.UNSUPPORTED and r.comparison is not None


def test_compare_higher_blocked_by_integrity():
    ds = _two_sites(stats_obs("A", average=198000, maximum=211000, minimum=185000, median=19.8, location="S1"),
                    stats_obs("B", average=15.0, maximum=16.0, minimum=14.0, median=15.0, location="S2"))
    r = _eval(ds, type=T.COMPARE_HIGHER, subject="A", object="B", statistic="average")
    assert r.verdict == V.BLOCKED
    _assert_complete(r)


# --- TREND_INCREASE --------------------------------------------------------------------------------

def _series(values, broken_year=None, start=2013):
    res = []
    for i, v in enumerate(values):
        y = start + i
        if y == broken_year:
            res.append(stats_obs(f"T{y}", average=v * 10000, median=v, minimum=v * 10000 - 1, maximum=v * 10000 + 1,
                                 system=OAH, code="nitrate", unit="mg/L", year=y, text=None))
        else:
            res.append(stats_obs(f"T{y}", average=v, median=v, minimum=v - 0.5, maximum=v + 0.5, system=OAH, code="nitrate",
                                 unit="mg/L", year=y, text=None))
    return dataset(*res)


def _trend(ds, stat="average"):
    return _eval(ds, type=T.TREND_INCREASE, location_id="Loc-T", indicator_key="nitrate", statistic=stat, year_from=2000, year_to=2030)


def test_trend_supported_with_exact_mann_kendall():
    r = _trend(_series([1, 2, 3, 4, 5, 6]))
    assert r.verdict == V.SUPPORTED
    assert r.statistics["mann_kendall"]["method"] == "exact permutation"
    assert r.statistics["mann_kendall"]["p_one_sided"] == pytest.approx(1 / 720, abs=1e-6)


def test_trend_conditional_when_too_few_points_for_significance():
    r = _trend(_series([1, 2, 3]))
    assert r.verdict == V.CONDITIONAL and r.statistics["mann_kendall"]["p_one_sided"] == pytest.approx(1 / 6, abs=1e-6)


def test_trend_unsupported_when_decreasing():
    assert _trend(_series([6, 5, 4, 3])).verdict == V.UNSUPPORTED


def test_trend_unsupported_with_fewer_than_three_points():
    assert _trend(_series([1, 2])).verdict == V.UNSUPPORTED


def test_trend_blocked_when_a_point_has_integrity_findings():
    r = _trend(_series([1, 2, 3, 4, 5], broken_year=2015))
    assert r.verdict == V.BLOCKED
    _assert_complete(r)


# --- EXCEEDS_THRESHOLD ------------------------------------------------------------------------------

def _pm10(avg):
    return dataset(stats_obs("P", average=avg, median=avg - 2, minimum=0, maximum=avg * 4, std_dev=avg / 2, unit="ug/m3",
                             system=AIR, code="pm10", year=2018, text=None))


def test_threshold_supported_above_who_guideline():
    r = _eval(_pm10(27.97), type=T.EXCEEDS_THRESHOLD, subject="P", statistic="average", threshold_id="who-2021-pm10-annual")
    assert r.verdict == V.SUPPORTED and r.statistics["ratio"] == pytest.approx(27.97 / 15, rel=1e-3)


def test_threshold_unsupported_below_limit():
    r = _eval(_pm10(20.26), type=T.EXCEEDS_THRESHOLD, subject="P", statistic="average", threshold_id="eu-2008-50-pm10-annual")
    assert r.verdict == V.UNSUPPORTED


def test_threshold_wrong_indicator():
    r = _eval(_pm10(50), type=T.EXCEEDS_THRESHOLD, subject="P", statistic="average", threshold_id="who-2021-no2-annual")
    assert r.verdict == V.UNSUPPORTED


def test_threshold_on_8h_target_cannot_use_annual_mean():
    ds = dataset(stats_obs("O3", average=130, median=120, minimum=1, maximum=200, std_dev=40, unit="ug/m3", system=AIR,
                           code="o3", text=None))
    r = _eval(ds, type=T.EXCEEDS_THRESHOLD, subject="O3", statistic="average", threshold_id="eu-2008-50-o3-target")
    assert r.verdict == V.UNSUPPORTED and "8-hour" in r.reasons[0]


def test_threshold_drinking_water_standard_on_surface_water_is_conditional():
    ds = dataset(stats_obs("N", average=60, median=60, minimum=55, maximum=65, unit="mg/L", system=OAH, code="nitrate", text=None))
    r = _eval(ds, type=T.EXCEEDS_THRESHOLD, subject="N", statistic="average", threshold_id="eu-dwd-nitrate")
    assert r.verdict == V.CONDITIONAL


def test_threshold_unknown_id_raises():
    with pytest.raises(ClaimError):
        _eval(_pm10(20), type=T.EXCEEDS_THRESHOLD, subject="P", statistic="average", threshold_id="nope")


# --- ASSOCIATION / CAUSAL ----------------------------------------------------------------------------

def _paired(n):
    res = [group("G", None, 0)]
    for i in range(n):
        res.append(location(f"L{i}", 41 + i / 100, 14 + i / 100))
        res.append(stats_obs(f"E{i}", average=10.0 + i, median=10.0 + i, minimum=1, maximum=50, unit="ug/m3", system=AIR,
                             code="pm2-5", location=f"L{i}", year=2024, text=None))
        res.append(value_obs(f"O{i}", 2 + i, code="cvd", location=f"L{i}", group="G"))
    return dataset(*res)


def test_association_unsupported_with_too_few_units():
    r = _eval(_paired(3), type=T.ASSOCIATION, indicator_key="pm2-5", outcome_indicator_key="cvd")
    assert r.verdict == V.UNSUPPORTED and "at least 8" in r.reasons[0]


def test_association_conditional_with_enough_units_and_monotonic_relation():
    r = _eval(_paired(8), type=T.ASSOCIATION, indicator_key="pm2-5", outcome_indicator_key="cvd")
    assert r.verdict == V.CONDITIONAL  # never SUPPORTED: ecological design
    assert r.statistics["spearman"]["rho"] == 1.0


def test_causal_is_always_unsupported_even_with_strong_association():
    r = _eval(_paired(8), type=T.CAUSAL, indicator_key="pm2-5", outcome_indicator_key="cvd")
    assert r.verdict == V.UNSUPPORTED
    assert "causation" in r.reasons[0]


# --- statistics ------------------------------------------------------------------------------------

def test_mann_kendall_exact_and_ties():
    assert mann_kendall([1, 2, 3, 4])["p_one_sided"] == pytest.approx(1 / 24, abs=1e-6)
    assert mann_kendall([1, 1, 1])["p_one_sided"] == 1.0
    assert mann_kendall(list(range(12)))["method"] == "normal approximation"


def test_theil_sen_and_spearman():
    assert theil_sen([0, 1, 2, 3, 4], [0, 2, 4, 6, 100]) == 2.0  # robust to the outlier
    s = spearman([1, 2, 3, 4], [4, 3, 2, 1])
    assert s["rho"] == -1.0 and s["p_two_sided"] == pytest.approx(2 / 24, abs=1e-6)


# --- The evidence ladder: the verdict restated per rung ------------------------------------------------------------------

def _rungs(r):
    return {x["level"]: x["status"] for x in r.ladder}


def test_ladder_for_a_supported_threshold_claim():
    r = _eval(_pm10(27.97), type=T.EXCEEDS_THRESHOLD, subject="P", statistic="average", threshold_id="who-2021-pm10-annual")
    assert _rungs(r) == {"observation": "supported", "description": "supported", "comparison": "supported",
                         "association": "not_claimed", "causation": "not_claimed"}
    assert r.supported_up_to == "Comparison" and [x["claimed"] for x in r.ladder] == [False, False, True, False, False]


def test_ladder_when_integrity_blocks_even_describing_the_values():
    r = _trend(_series([1, 2, 3, 4, 5], broken_year=2015))
    assert r.verdict == V.BLOCKED
    assert _rungs(r)["observation"] == "blocked" and _rungs(r)["comparison"] == "blocked" and r.supported_up_to is None


def test_ladder_for_an_association_with_too_few_sites_stops_at_description():
    r = _eval(_paired(3), type=T.ASSOCIATION, indicator_key="pm2-5", outcome_indicator_key="cvd")
    assert _rungs(r)["association"] == "unsupported" and _rungs(r)["comparison"] == "not_claimed"
    assert r.supported_up_to == "Description"


def test_ladder_for_a_causal_claim_never_reaches_causation():
    r = _eval(_paired(8), type=T.CAUSAL, indicator_key="pm2-5", outcome_indicator_key="cvd")
    assert _rungs(r)["causation"] == "unsupported" and r.ladder[-1]["claimed"]
    assert _rungs(r)["association"] == "conditional"  # the weaker claim, with caveats (ecological design)
    assert r.supported_up_to == "Association"
