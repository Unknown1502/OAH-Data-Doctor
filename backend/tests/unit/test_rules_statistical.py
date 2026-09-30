"""SEM-STAT-001..005 and SEM-SCALE-001: positive, negative and edge cases for each rule."""

from datadoctor.domain.enums import Severity
from tests.helpers import dataset, run, stats_obs

# The anchor record, verbatim from the live sandbox (2026-09-30, DISCOVERY.md D6).
ANCHOR = dict(average=198000, maximum=211000, minimum=185000, std_dev=18385, median=19.8)
CLEAN = dict(average=19.8, maximum=21.1, minimum=18.5, std_dev=1.8385, median=19.8)


# --- SEM-STAT-001: median within [min, max] ---------------------------------------------------------

def test_stat001_fires_on_anchor_median_outside_range():
    f = run("SEM-STAT-001", dataset(stats_obs("A", **ANCHOR)))
    assert len(f) == 1
    assert f[0].severity == Severity.CRITICAL  # ~9,343x below the minimum
    assert f[0].root_cause == "unknown"
    labels = {o.label: o.value for o in f[0].evidence.observed}
    assert labels == {"minimum": 185000, "median": 19.8, "maximum": 211000}


def test_stat001_silent_on_clean_record():
    assert run("SEM-STAT-001", dataset(stats_obs("C", **CLEAN))) == []


def test_stat001_edge_median_equal_to_bound_is_consistent():
    assert run("SEM-STAT-001", dataset(stats_obs("E", minimum=5, median=5, maximum=9))) == []


def test_stat001_edge_rounding_tolerance():
    # median 10.05 published vs max 10.0: within half-ulp of both (0.005 + 0.05) -> consistent
    assert run("SEM-STAT-001", dataset(stats_obs("E", minimum=9.0, median=10.05, maximum=10.0))) == []


def test_stat001_small_violation_is_error_not_critical():
    f = run("SEM-STAT-001", dataset(stats_obs("E", minimum=10, median=13, maximum=11)))
    assert len(f) == 1 and f[0].severity == Severity.ERROR


def test_stat001_needs_all_three_statistics():
    assert run("SEM-STAT-001", dataset(stats_obs("E", minimum=10, median=500))) == []


# --- SEM-STAT-002: mean within [min, max] -----------------------------------------------------------

def test_stat002_fires_when_mean_below_min_equal_max():
    # Pattern seen in live Almyros nitrite 2013: min = max = 0.05, mean 0.03
    f = run("SEM-STAT-002", dataset(stats_obs("N", average=0.03, minimum=0.05, maximum=0.05, median=0.05, unit="mg/L")))
    assert len(f) == 1
    assert any("half" in h for h in f[0].hypotheses)  # half-detection-limit pattern is offered as a hypothesis only


def test_stat002_silent_on_anchor_mean_inside_range():
    assert run("SEM-STAT-002", dataset(stats_obs("A", **ANCHOR))) == []


def test_stat002_zero_bounds_use_record_precision_conservatively():
    # min = max = 0 published without decimals, mean 0.01: cannot be proven inconsistent at 2 dp -> silent
    assert run("SEM-STAT-002", dataset(stats_obs("Z", average=0.01, minimum=0, maximum=0, median=0, std_dev=0))) == []


# --- SEM-STAT-003: |mean - median| <= SD ------------------------------------------------------------

def test_stat003_fires_on_anchor():
    f = run("SEM-STAT-003", dataset(stats_obs("A", **ANCHOR)))
    assert len(f) == 1
    assert f[0].evidence.measures["gap"] > f[0].evidence.measures["std_dev"]


def test_stat003_silent_on_skewed_but_valid_record():
    # Benevento01 NO2 2019 (live): mean 24.48, median 19.5, SD 18.2 -> gap 4.98 <= 18.2
    assert run("SEM-STAT-003", dataset(stats_obs("B", average=24.48, median=19.5, std_dev=18.2, minimum=0.5, maximum=109.5, unit="ug/m3"))) == []


def test_stat003_silent_without_sd():
    assert run("SEM-STAT-003", dataset(stats_obs("B", average=100, median=1, minimum=0, maximum=200))) == []


# --- SEM-STAT-004: SD compatible with range --------------------------------------------------------

def test_stat004_fires_when_sd_exceeds_range_over_sqrt2():
    f = run("SEM-STAT-004", dataset(stats_obs("S", minimum=10, maximum=12, std_dev=5, average=11, median=11)))
    assert len(f) == 1


def test_stat004_fires_when_min_equals_max_but_sd_positive():
    f = run("SEM-STAT-004", dataset(stats_obs("S", minimum=7.0, maximum=7.0, std_dev=0.5, average=7.0, median=7.0)))
    assert len(f) == 1


def test_stat004_edge_integer_min_equal_max_is_ambiguous():
    # Published as integers, min = max = 7 may hide a true range up to 1.0 -> SD 0.5 is attainable -> silent
    assert run("SEM-STAT-004", dataset(stats_obs("S", minimum=7, maximum=7, std_dev=0.5, average=7, median=7))) == []


def test_stat004_edge_n2_bound_is_attainable():
    # Two samples 18.5 and 21.1 -> sample SD = 2.6/sqrt(2) = 1.8385: exactly on the bound, not a violation
    assert run("SEM-STAT-004", dataset(stats_obs("S", **CLEAN))) == []


def test_stat004_edge_rounding_false_positive_avoided():
    # Live Almyros nitrite 2019: max 0.008, min 0 (published as 0), SD 0.0057 vs bound 0.005657.
    # With 4-dp record precision the true SD may be 0.00565 -> must NOT fire.
    assert run("SEM-STAT-004", dataset(stats_obs("S", average=0.03, maximum=0.008, minimum=0, std_dev=0.0057, median=0, unit="mg/L"))) == []


# --- SEM-STAT-005: min <= max -----------------------------------------------------------------------

def test_stat005_fires_on_inverted_range():
    assert len(run("SEM-STAT-005", dataset(stats_obs("I", minimum=30, maximum=20)))) == 1


def test_stat005_silent_on_ordered_range():
    assert run("SEM-STAT-005", dataset(stats_obs("I", minimum=20, maximum=30))) == []


# --- SEM-STAT-006: SD >= 0 --------------------------------------------------------------------------
# Found with the what-if lab: no rule flagged a negative SD, which is impossible by definition.

def test_stat006_fires_on_negative_sd_even_without_min_and_max():
    f = run("SEM-STAT-006", dataset(stats_obs("N", average=19.8, median=19.8, std_dev=-5)))
    assert len(f) == 1 and f[0].severity == Severity.CRITICAL and f[0].root_cause == "unknown"
    assert {o.label: o.value for o in f[0].evidence.observed} == {"std-dev": -5}


def test_stat006_silent_on_zero_and_positive_sd():
    assert run("SEM-STAT-006", dataset(stats_obs("Z", minimum=7, maximum=7, std_dev=0, average=7, median=7))) == []
    assert run("SEM-STAT-006", dataset(stats_obs("C", **CLEAN))) == []


def test_stat006_tolerates_negative_zero_at_published_precision():
    assert run("SEM-STAT-006", dataset(stats_obs("R", average=1.0, std_dev=-0.0))) == []


# --- SEM-SCALE-001: power-of-ten divergence ---------------------------------------------------------

def test_scale001_identifies_the_outlying_statistic_on_anchor():
    f = run("SEM-SCALE-001", dataset(stats_obs("A", **ANCHOR)))
    assert len(f) == 1
    m = f[0].evidence.measures
    assert m["outlying_statistics"] == ["median"]
    assert m["exact_power_of_ten"] is True and m["k"] == 4
    assert f[0].confidence >= 0.85
    assert "root cause unknown" in f[0].interpretation


def test_scale001_silent_on_clean_and_on_skewed_air_data():
    assert run("SEM-SCALE-001", dataset(stats_obs("C", **CLEAN))) == []
    assert run("SEM-SCALE-001", dataset(stats_obs("B", average=24.48, median=19.5, minimum=0.5, maximum=109.5, unit="ug/m3"))) == []


def test_scale001_ignores_zero_values_and_std_dev():
    assert run("SEM-SCALE-001", dataset(stats_obs("Z", average=0.02, median=0.02, minimum=0, maximum=0.03, std_dev=0.0001))) == []


def test_scale001_non_power_of_ten_has_lower_confidence():
    f = run("SEM-SCALE-001", dataset(stats_obs("H", average=2500, median=0.5, minimum=0.5, maximum=0.5, unit="ug/L")))
    assert len(f) == 1
    assert f[0].evidence.measures["outlying_statistics"] == ["average"]
    assert f[0].evidence.measures["exact_power_of_ten"] is False
    assert f[0].confidence < 0.85


def test_scale001_regression_pollutant_minimum_near_zero_is_normal():
    # Gate-0 pre-review false positive (live Benevento02 O3 2018): night-time ozone minima near zero are real.
    # Extremes may legitimately sit orders of magnitude from the centre; only mean vs median is compared.
    ds = dataset(stats_obs("O3", average=32.74, median=30.9, minimum=0.1, maximum=160.3, std_dev=21.0, unit="ug/m3"))
    assert run("SEM-SCALE-001", ds) == []


def test_summaries_never_use_scientific_notation_for_large_numbers():
    from datadoctor.rules.base import fmt

    assert fmt(1676332.35) == "1,676,332.35" and fmt(47393364.0) == "47,393,364" and fmt(19.8) == "19.8"
    f = run("SEM-STAT-003", dataset(stats_obs("C", average=1676500, median=167.65, std_dev=89800, minimum=150, maximum=4000000)))
    assert f and "e+" not in f[0].summary and "1,676,332.35" in f[0].summary
