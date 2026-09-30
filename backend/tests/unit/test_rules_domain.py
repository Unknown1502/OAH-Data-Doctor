"""Domain-knowledge rules: SEM-RANGE-001/002, SEM-DEF-001, SEM-CODE-001, SEM-SPATIAL-001."""

from datadoctor.domain.enums import Severity
from tests.helpers import OAH, dataset, group, location, run, stats_obs, value_obs

# --- SEM-RANGE-001 (impossible) / SEM-RANGE-002 (unusual) -------------------------------------------

def test_range001_water_temperature_above_boiling_is_critical():
    f = run("SEM-RANGE-001", dataset(stats_obs("A", average=198000, maximum=211000, minimum=185000, median=19.8)))
    assert len(f) == 1 and f[0].severity == Severity.CRITICAL
    flagged = {o.label for o in f[0].evidence.observed}
    assert flagged == {"average", "maximum", "minimum"}  # the median 19.8 is plausible and not flagged


def test_range001_silent_on_plausible_temperature():
    assert run("SEM-RANGE-001", dataset(stats_obs("C", average=19.8, maximum=21.1, minimum=18.5, median=19.8))) == []


def test_range001_converts_units_before_checking():
    # 9,040 mS/cm = 9,040,000 uS/cm > physical ceiling 300,000 uS/cm
    ds = dataset(stats_obs("E", average=9040, maximum=9040, minimum=9040, median=9040, unit="mS/cm",
                           system=OAH, code="electrical-conductivity", text=None))
    assert len(run("SEM-RANGE-001", ds)) == 1


def test_range001_prevalence_over_100_percent():
    assert len(run("SEM-RANGE-001", dataset(value_obs("P", 104.0)))) == 1
    assert run("SEM-RANGE-001", dataset(value_obs("P", 99.0))) == []


def test_range001_ph_without_unit_is_checked_on_the_ph_scale():
    ds = dataset(stats_obs("PH", average=76800, maximum=82000, minimum=71600, unit=None, system=OAH, code="ph", text="pH"))
    f = run("SEM-RANGE-001", ds)
    assert len(f) == 1 and "assumed" in f[0].evidence.measures["unit_note"]


def test_range002_unusual_but_possible_is_only_a_warning():
    # Live Almyros field EC 18.4 mS/cm: unusual for freshwater, normal for brackish water
    ds = dataset(value_obs("EC", 18.4, unit="mS/cm", code="conductivity", profile="observation-indicators-oah", date="2024-11-21"))
    f = run("SEM-RANGE-002", ds)
    assert len(f) == 1 and f[0].severity == Severity.WARNING
    assert run("SEM-RANGE-001", ds) == []


def test_range002_not_reported_when_range001_already_fires():
    assert run("SEM-RANGE-002", dataset(stats_obs("A", average=198000, maximum=211000, minimum=185000, median=19.8))) == []


# --- SEM-DEF-001: indicator definition contradicts the published unit ---------------------------------

def test_def001_per_100000_definition_with_percent_unit():
    # The OAH CodeSystem defines #obesity as "... per 100.000 inhabitants" while data are published in %
    f = run("SEM-DEF-001", dataset(value_obs("O1", 29.0), value_obs("O2", 31.0)))
    assert len(f) == 1
    assert f[0].severity == Severity.WARNING
    assert {r.resource_id for r in f[0].related_resources} == {"O1", "O2"}


def test_def001_silent_for_codes_without_rate_definition():
    assert run("SEM-DEF-001", dataset(stats_obs("C", average=19.8, maximum=21.1, minimum=18.5, median=19.8))) == []


# --- SEM-CODE-001: near-synonymous definitions with divergent values --------------------------------

def _hbp(oid: str, code: str, v: float) -> dict:
    return value_obs(oid, v, code=code, group="G-F")


def test_code001_hypertension_vs_high_blood_pressure_treatment_diverge():
    ds = dataset(group("G-F", sex="female", low=35, high=74),
                 _hbp("H1", "hypertension", 23.0), _hbp("H2", "high-blood-pression-treatment", 33.0))
    f = run("SEM-CODE-001", ds)
    assert len(f) == 1
    assert f[0].evidence.measures["divergent_pairs"] == 1


def test_code001_silent_when_values_agree_within_rounding():
    ds = dataset(group("G-F", sex="female", low=35, high=74),
                 _hbp("H1", "hypertension", 23.0), _hbp("H2", "high-blood-pression-treatment", 23.0))
    assert run("SEM-CODE-001", ds) == []


def test_code001_silent_for_genuinely_different_constructs():
    # prevalence of high blood pressure vs share under treatment: different definitions -> not synonyms
    ds = dataset(group("G-F", sex="female"), _hbp("H1", "high-blood-pression", 20.0),
                 _hbp("H2", "high-blood-pression-treatment", 33.0))
    assert run("SEM-CODE-001", ds) == []


# --- SEM-SPATIAL-001: distinct sites share identical coordinates -------------------------------------

def test_spatial001_identical_coordinates_for_distinct_sites():
    ds = dataset(location("S1", 41.129, 14.781), location("S2", 41.129, 14.781), location("S3", 41.129, 14.781),
                 with_default_location=False)
    f = run("SEM-SPATIAL-001", ds)
    assert len(f) == 1 and len(f[0].related_resources) == 3


def test_spatial001_silent_for_distinct_positions_and_missing_positions():
    ds = dataset(location("S1", 41.129, 14.781), location("S2", 41.2, 14.9), location("S3", None, None),
                 with_default_location=False)
    assert run("SEM-SPATIAL-001", ds) == []


def test_code001_regression_thresholds_in_parentheses_are_definitional():
    # Gate-0 pre-review false positive: '(>=190 mg/dl)' vs '(>=240 mg/dl)' are different indicators.
    ds = dataset(group("G-F", sex="female", low=35, high=74),
                 _hbp("C1", "cholesterolemia-190", 64.0), _hbp("C2", "cholesterolemia-240", 31.0))
    assert run("SEM-CODE-001", ds) == []
