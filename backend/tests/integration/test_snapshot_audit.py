"""End-to-end on the committed snapshot (offline): anchor reproduction, trace, catalog, lineage, determinism."""

import asyncio
from pathlib import Path

import pytest

from datadoctor.audit.analyses import run_catalog
from datadoctor.audit.service import ANCHOR_ID, audit_dataset, run_audit
from datadoctor.config import REPO_ROOT, Settings
from datadoctor.domain.enums import Severity
from datadoctor.ingestion.snapshot import verify_snapshot
from datadoctor.knowledge.loader import load_knowledge
from datadoctor.normalization.normalizer import build_dataset
from datadoctor.trace.graph import build_graph, impact

SNAP_DIR = REPO_ROOT / "data" / "snapshots"
KN = load_knowledge(REPO_ROOT / "knowledge")


def _latest() -> Path:
    snaps = sorted(p for p in SNAP_DIR.iterdir() if (p / "manifest.json").is_file())
    if not snaps:
        pytest.skip("no snapshot committed")
    return snaps[-1]


@pytest.fixture(scope="module")
def audited():
    st = Settings(snapshot_id=_latest().name)
    res, ds = asyncio.run(run_audit(st, "snapshot", _latest().name))
    return res, ds


def test_snapshot_verifies():
    assert verify_snapshot(_latest()) == []


def test_snapshot_is_labelled_as_snapshot_never_live(audited):
    res, _ = audited
    assert res.source.kind.value == "snapshot"
    assert res.source.snapshot_id and res.source.manifest_sha256


def test_anchor_reproduces_with_verbatim_values(audited):
    res, ds = audited
    a = res.summary.anchor
    assert a["present"]
    assert a["values"] == {"average": 198000.0, "maximum": 211000.0, "minimum": 185000.0, "std-dev": 18385.0, "median": 19.8}
    assert {"SEM-STAT-001", "SEM-RANGE-001", "SEM-SCALE-001", "SEM-STAT-003"} <= set(a["rules_fired"])
    # the server's own base-R4 validation found nothing wrong with it
    oo = ds.server_validation[f"Observation/{ANCHOR_ID}"]
    assert oo["issue"][0]["diagnostics"] == "No issues detected during validation"


def test_anchor_lineage_points_to_the_ig_source_row(audited):
    res, _ = audited
    f = next(f for f in res.findings if f.resource.resource_id == ANCHOR_ID and f.rule_id == "SEM-STAT-001")
    assert f.lineage is not None and all(f.lineage.matches.values())
    assert "198000,00" in f.lineage.raw_row and "19,80" in f.lineage.raw_row
    assert "root cause unknown" in f.lineage.statement


def test_clean_controls_produce_no_errors(audited):
    """Oslo cohort data and Benevento libraries are internally consistent: no ERROR/CRITICAL must fire on them."""
    res, _ = audited
    for f in res.findings:
        if f.severity in (Severity.ERROR, Severity.CRITICAL):
            assert not f.resource.resource_id.startswith("Obs-OS-"), f.summary
            assert f.resource.resource_type != "Library", f.summary


def test_audit_is_deterministic(audited):
    res, ds = audited
    again = audit_dataset(build_dataset(ds.raw, ds.source, KN, ds.server_validation), KN)
    assert [f.id for f in again.findings] == [f.id for f in res.findings]


def test_trace_of_anchor_lists_exactly_the_computed_analyses(audited):
    res, ds = audited
    an = run_catalog(ds, KN, res.findings)
    g = build_graph(ds, KN, an.comparisons, an.claims)
    anchor = next(f for f in res.findings if f.resource.resource_id == ANCHOR_ID and f.rule_id == "SEM-STAT-001")
    rep = impact(g, anchor)
    claim_ids = {n.id for n in rep.reachable if n.type == "claim"}
    assert claim_ids == {"claim:clm-almyros-temperature-rising", "claim:clm-almyros-temperature-rising-median"}
    assert {n.id for n in rep.reachable if n.type == "comparison"} == {"comparison:cmp-almyros-temp-lab-2013-vs-2014"}
    assert rep.counts["series"] == 2 and rep.counts["library"] == 1


def test_trace_counts_change_when_data_change(audited):
    res, ds = audited
    raw = {t: dict(v) for t, v in ds.raw.items()}
    raw["Observation"].pop("Obs-Almyros-TemperatureWater-2014")  # the comparison partner disappears
    ds2 = build_dataset(raw, ds.source, KN, ds.server_validation)
    res2 = audit_dataset(ds2, KN)
    an2 = run_catalog(ds2, KN, res2.findings)
    g2 = build_graph(ds2, KN, an2.comparisons, an2.claims)
    anchor = next(f for f in res2.findings if f.resource.resource_id == ANCHOR_ID and f.rule_id == "SEM-STAT-001")
    rep = impact(g2, anchor)
    assert rep.counts["comparison"] == 0
    assert any(e.id == "cmp-almyros-temp-lab-2013-vs-2014" and not e.ok for e in an2.catalog)
    series = [n for n in rep.reachable if n.type == "series"]
    assert all(n.attrs["points"] == 5 for n in series)


def test_catalog_verdicts_on_real_data(audited):
    res, ds = audited
    an = run_catalog(ds, KN, res.findings)
    v = {c.id: c.verdict.value for c in an.comparisons}
    assert v["cmp-obesity-benevento-vs-oslo-18-29"] == "NOT"
    assert v["cmp-almyros-temp-lab-2013-vs-2014"] == "BLOCKED_BY_INTEGRITY"
    assert v["cmp-field-temp-almyros-vs-giofyros"] == "DIRECT"
    cv = {c.id: c.verdict.value for c in an.claims}
    assert cv["clm-almyros-temperature-rising"] == "BLOCKED"
    assert cv["clm-pm25-causes-cvd"] == "UNSUPPORTED"


def test_support_table_covers_every_published_record(audited):
    """Regression: consolidated libraries were skipped wholesale, which dropped the Almyros lab chemistry (only in
    Library-Almyros-FullResults) and all of Oslo (only in Library-Oslo-All)."""
    from datadoctor.reporting.support import support_table

    res, ds = audited
    rows = support_table(ds, KN, res.findings)
    libs = {r.library_id for r in rows}
    assert "Library-Almyros-FullResults" in libs and "Library-Oslo-All" in libs
    assert "Library-Benevento-All" not in libs  # fully covered by the site libraries: no duplicate rows
    lab_temp = next(r for r in rows if r.library_id == "Library-Almyros-FullResults" and r.indicator_key == "water-temperature")
    assert lab_temp.status == "PARTLY_USABLE" and lab_temp.blocked == 6
    assert any(r.status == "NOT_USABLE" for r in rows)
    covered = {m for lib in ds.libraries.values() if lib.id in libs for m in lib.member_refs}
    official = {o.key for o in ds.observations.values() if o.scope.value == "oah-ig" and o.indicator_key}
    assert official <= covered
