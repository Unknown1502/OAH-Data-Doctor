"""Cross-record rules: SEM-TEMP-001, SEM-COHORT-001, SEM-COHORT-002, SEM-XREC-001."""

from tests.helpers import AIR, OAH, dataset, group, run, stats_obs, value_obs


# --- SEM-TEMP-001: scale break inside a time series ------------------------------------------------

def _cd(year: int, mean: float) -> dict:
    return stats_obs(f"Cd-{year}", average=mean, minimum=0.5, maximum=0.5, median=0.5, unit="ug/L",
                     system=OAH, code="cadmium-dissolved", year=year, text=None)


def test_temp001_flags_the_single_year_on_a_different_scale():
    # Live Almyros cadmium: mean 0.25 every year except 2018 (2500)
    ds = dataset(_cd(2013, 0.25), _cd(2014, 0.25), _cd(2018, 2500), _cd(2019, 0.25), _cd(2020, 0.25))
    f = run("SEM-TEMP-001", ds)
    assert [x.resource.resource_id for x in f] == ["Cd-2018"]


def test_temp001_silent_on_consistently_scaled_series():
    ds = dataset(_cd(2013, 0.25), _cd(2014, 0.3), _cd(2018, 0.2), _cd(2019, 0.25))
    assert run("SEM-TEMP-001", ds) == []


def test_temp001_needs_three_points():
    assert run("SEM-TEMP-001", dataset(_cd(2013, 0.25), _cd(2018, 2500))) == []


# --- SEM-COHORT-001: pooled value outside its partition ---------------------------------------------

def _cohort_ds(all_v: float, m: float, f: float):  # noqa: D103
    return dataset(group("G-All", low=0), group("G-M", sex="male"), group("G-F", sex="female"),
                   value_obs("A", all_v, code="mental-health", group="G-All"),
                   value_obs("M", m, code="mental-health", group="G-M"),
                   value_obs("F", f, code="mental-health", group="G-F"))


def test_cohort001_pooled_outside_male_female_range():
    f = run("SEM-COHORT-001", _cohort_ds(25, 17, 20))
    assert len(f) == 1


def test_cohort001_silent_when_pooled_between_subgroups():
    # Live Oslo mental-health: All 19, Male 17, Female 20
    assert run("SEM-COHORT-001", _cohort_ds(19, 17, 20)) == []


def test_cohort001_edge_rounding_at_bound():
    # integer-published shares: 21 vs 20 may be 20.5 vs 20.49 under rounding -> not provable -> silent
    assert run("SEM-COHORT-001", _cohort_ds(21, 17, 20)) == []


def test_cohort001_one_decimal_precision_is_stricter():
    assert len(run("SEM-COHORT-001", _cohort_ds(20.4, 17.0, 20.0))) == 1


# --- SEM-COHORT-002: complements must sum to 100 % ------------------------------------------------

def _ltd(a: int, b: int):
    return dataset(group("G-All", low=0), value_obs("L1", a, code="long-term-disease", group="G-All"),
                   value_obs("L2", b, code="no-long-term-disease", group="G-All"))


def test_cohort002_complements_not_summing_to_100():
    f = run("SEM-COHORT-002", _ltd(42, 68))
    assert len(f) == 1 and f[0].evidence.measures["sum"] == 110.0


def test_cohort002_silent_within_rounding():
    assert run("SEM-COHORT-002", _ltd(42, 58)) == []
    assert run("SEM-COHORT-002", _ltd(42, 59)) == []  # 101: two integer-rounded shares -> within +-1


def test_cohort002_needs_every_member():
    ds = dataset(group("G-All", low=0), value_obs("L1", 42, code="long-term-disease", group="G-All"))
    assert run("SEM-COHORT-002", ds) == []


# --- SEM-XREC-001: PM2.5 must not exceed PM10 -----------------------------------------------------

def _pm(code: str, oid: str, **kw) -> dict:
    return stats_obs(oid, unit="ug/m3", system=AIR, code=code, year=2019, text=None, **kw)


def test_xrec001_pm25_greater_than_pm10_same_site_and_year():
    ds = dataset(_pm("pm2-5", "P25", average=21.59, median=18.1, maximum=89.2, minimum=0),
                 _pm("pm10", "P10", average=20.26, median=17.1, maximum=113, minimum=0))
    f = run("SEM-XREC-001", ds)
    assert len(f) == 1
    assert set(f[0].evidence.measures["violating_statistics"]) == {"average", "median"}


def test_xrec001_silent_when_pm25_below_pm10():
    ds = dataset(_pm("pm2-5", "P25", average=18.51, median=18, maximum=57.5),
                 _pm("pm10", "P10", average=19.68, median=13.1, maximum=129.2))
    # median 18 > 13.1 would violate; keep only consistent stats in this negative control
    ds.observations["P25"].stats = [s for s in ds.observations["P25"].stats if s.stat != "median"]
    assert run("SEM-XREC-001", ds) == []


def test_xrec001_different_years_are_not_compared():
    a = _pm("pm2-5", "P25", average=30.0)
    b = _pm("pm10", "P10", average=20.0)
    b["effectivePeriod"] = {"start": "2018-01-01", "end": "2018-12-31"}
    assert run("SEM-XREC-001", dataset(a, b)) == []
