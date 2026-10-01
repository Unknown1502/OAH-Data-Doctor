"""Published documents must agree with a fresh audit (master prompt rule 1: no hand-typed numbers)."""

import asyncio
import json

import pytest

from datadoctor.audit.service import run_audit
from datadoctor.config import REPO_ROOT, Settings
from datadoctor.rules.registry import load_rules

NUMBERS = REPO_ROOT / "docs" / "numbers.json"


@pytest.fixture(scope="module")
def fresh():
    if not NUMBERS.exists():
        pytest.skip("docs not rendered yet (python scripts/render_docs.py)")
    res, _ = asyncio.run(run_audit(Settings(), "snapshot"))
    return res.summary, json.loads(NUMBERS.read_text(encoding="utf-8"))


def test_rendered_numbers_match_a_fresh_audit(fresh):
    s, n = fresh
    assert n["N_FINDINGS"] == str(s.findings_total)
    assert n["N_CRITICAL"] == str(s.findings_by_severity["CRITICAL"])
    assert n["N_FLAGGED_OBS"] == str(s.oah_observations_with_blocking)
    assert n["N_OAH_OBS"] == str(s.oah_observations)
    assert n["N_FLAGGED_PASS_SERVER"] == str(s.server_validation["flagged_observations_passing_server_validation"])
    assert n["N_MEDIAN_OUTSIDE"] == str(s.findings_by_rule.get("SEM-STAT-001", 0))
    # the per-medium split behind "Expected impact on ecosystem and human health" adds up to the headline numbers
    assert int(n["N_WATER_OBS"]) + int(n["N_AIR_OBS"]) + int(n["N_HEALTH_OBS"]) == s.oah_observations
    assert int(n["N_WATER_FLAGGED"]) + int(n["N_AIR_FLAGGED"]) + int(n["N_HEALTH_FLAGGED"]) == s.oah_observations_with_blocking


def test_documents_have_no_unfilled_placeholders():
    for p in (REPO_ROOT / "README.md", REPO_ROOT / "docs" / "SUBMISSION.md"):
        text = p.read_text(encoding="utf-8")
        assert "{{" not in text, f"unrendered placeholder in {p.name}"


def test_rules_catalog_documents_every_rule():
    text = (REPO_ROOT / "docs" / "04_RULES_CATALOG.md").read_text(encoding="utf-8")
    for rid, rule in load_rules().items():
        assert f"## {rid}" in text and f"v{rule.spec.version}" in text, f"{rid} missing or stale in the rules catalog"


def test_gate0_human_verdicts_are_never_prefilled():
    """Gate 0 needs a human verdict per sample: the report offers TRUE POSITIVE / FALSE POSITIVE / UNCERTAIN with a reason,
    and no box may be ticked by a tool."""
    report = (REPO_ROOT / "docs" / "GATE0_REPORT.md").read_text(encoding="utf-8")
    samples = report.count("**Independent re-derivation:**")
    assert samples == 20
    assert report.count("**Human verdict:** [ ] TRUE POSITIVE  [ ] FALSE POSITIVE  [ ] UNCERTAIN") == samples
    assert report.count("**Reason:** ______") == samples
    assert "[x]" not in report.lower()

