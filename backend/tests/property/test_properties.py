"""Property-based tests (Hypothesis): the statistical rules are mathematical identities, so they must NEVER fire on
statistics computed from any real sample — whatever the rounding — and must fire on scale injections."""

import math
import statistics

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from datadoctor.rules.registry import run_all
from tests.helpers import KN, dataset, stats_obs

IDENTITY_RULES = {"SEM-STAT-001", "SEM-STAT-002", "SEM-STAT-003", "SEM-STAT-004", "SEM-STAT-005"}

samples = st.lists(st.floats(min_value=0.0, max_value=1000.0, allow_nan=False, allow_infinity=False), min_size=2, max_size=40)


def _summary(xs, decimals):
    r = (lambda v: round(v, decimals)) if decimals > 0 else (lambda v: int(round(v)))
    return dict(average=r(statistics.fmean(xs)), median=r(statistics.median(xs)), minimum=r(min(xs)), maximum=r(max(xs)),
                std_dev=r(statistics.stdev(xs)))


@settings(max_examples=300, suppress_health_check=[HealthCheck.too_slow], deadline=None)
@given(xs=samples, decimals=st.integers(min_value=0, max_value=4))
def test_identity_rules_never_fire_on_real_samples(xs, decimals):
    s = _summary(xs, decimals)
    ds = dataset(stats_obs("P", unit="mg/L", system="http://hl7.eu/fhir/ig/oah/CodeSystem/temporarySystem-oah-eu",
                           code="nitrate", text=None, **s))
    fired = {f.rule_id for f in run_all(ds, KN, only=IDENTITY_RULES)}
    assert fired == set(), (xs, s, fired)


@settings(max_examples=150, deadline=None)
@given(xs=st.lists(st.floats(min_value=1.0, max_value=50.0), min_size=3, max_size=30), k=st.integers(min_value=2, max_value=6))
def test_scale_injection_on_the_median_is_always_detected(xs, k):
    s = _summary(xs, 2)
    s["median"] = round(s["median"] * 10**k, 2)
    ds = dataset(stats_obs("P", unit="mg/L", system="http://hl7.eu/fhir/ig/oah/CodeSystem/temporarySystem-oah-eu",
                           code="nitrate", text=None, **s))
    fired = {f.rule_id for f in run_all(ds, KN)}
    # Every injection is caught by at least one identity rule (median outside range / gap > SD).
    assert fired & {"SEM-STAT-001", "SEM-STAT-003"}
    # SEM-SCALE-001 needs mean/median >= 100x. With data spanning <= 50x, mean/median <= 50, so the rule is only
    # guaranteed from x10^4 upward (Hypothesis found xs=[1,1,2], k=2 -> ratio 75: caught by STAT rules instead).
    if k >= 4:
        assert "SEM-SCALE-001" in fired


@settings(max_examples=150, deadline=None)
@given(xs=st.lists(st.floats(min_value=1.0, max_value=99.0), min_size=2, max_size=30))
def test_scale_rule_silent_when_data_span_less_than_100x(xs):
    s = _summary(xs, 3)
    ds = dataset(stats_obs("P", unit="mg/L", system="http://hl7.eu/fhir/ig/oah/CodeSystem/temporarySystem-oah-eu",
                           code="nitrate", text=None, **s))
    assert not [f for f in run_all(ds, KN, only={"SEM-SCALE-001"})]


@settings(max_examples=100, deadline=None)
@given(xs=samples)
def test_findings_are_deterministic(xs):
    s = _summary(xs, 2)
    s["median"] = s["median"] * 1000 + 1
    ds = dataset(stats_obs("P", **s))
    assert [f.id for f in run_all(ds, KN)] == [f.id for f in run_all(ds, KN)]
    assert all(math.isfinite(f.confidence) for f in run_all(ds, KN))
