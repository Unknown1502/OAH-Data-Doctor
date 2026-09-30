"""Checking data a user brings: every accepted format, clear errors, and findings for the uploaded records only."""

import json

import pytest

from datadoctor.audit.upload import MAX_RESOURCES, UploadError, check_upload, parse_upload
from tests.helpers import KN, dataset, location, stats_obs

ANCHOR = dict(average=198000, maximum=211000, minimum=185000, std_dev=18385, median=19.8)
CLEAN = dict(average=19.8, maximum=21.1, minimum=18.5, std_dev=1.8385, median=19.8)


def test_accepts_a_resource_a_bundle_an_array_and_ndjson():
    a, b = stats_obs("A", **ANCHOR), stats_obs("B", **CLEAN)
    bundle = {"resourceType": "Bundle", "type": "collection", "entry": [{"resource": a}, {"resource": b}]}
    for text in (json.dumps(a), json.dumps(bundle), json.dumps([a, b]), json.dumps(a) + "\n\n" + json.dumps(b) + "\n"):
        got, notes = parse_upload(text)
        assert [r["id"] for r in got] in (["A"], ["A", "B"]) and notes == []


def test_skips_what_it_cannot_check_and_says_so():
    got, notes = parse_upload(json.dumps([stats_obs("A", **CLEAN), {"resourceType": "Patient", "id": "p"}, {"x": 1}]))
    assert [r["id"] for r in got] == ["A"]
    assert any("Patient" in n for n in notes) and any("not a FHIR resource" in n for n in notes)


def test_missing_or_invalid_ids_get_a_stable_placeholder():
    r = stats_obs("A", **CLEAN)
    del r["id"]
    got, _ = parse_upload(json.dumps([stats_obs("ok", **CLEAN), r, {**stats_obs("x", **CLEAN), "id": "bad id!"}]))
    assert [x["id"] for x in got] == ["ok", "upload-2", "upload-3"]


@pytest.mark.parametrize(("text", "msg"), [
    ("", "Nothing to check"),
    ("   ", "Nothing to check"),
    ('{"resourceType": "Observation"\nnot json', "Line 1 is not valid JSON"),
    (json.dumps({"resourceType": "Patient", "id": "p"}), "No resource Data Doctor can check"),
])
def test_clear_errors(text, msg):
    with pytest.raises(UploadError, match=msg):
        parse_upload(text)


def test_size_limits():
    many = json.dumps([stats_obs(f"o{i}", **CLEAN) for i in range(MAX_RESOURCES + 1)])
    with pytest.raises(UploadError, match=f"at most {MAX_RESOURCES}"):
        parse_upload(many)


def test_findings_are_reported_for_uploaded_records_only():
    ds = dataset(location("Loc-T"), location("Loc-U"), stats_obs("published-bad", **ANCHOR))
    # mine-ok is at another site: at Loc-T it would sit in the same series as the broken records and rightly be flagged
    res = check_upload(ds, KN, [stats_obs("mine-bad", **ANCHOR), stats_obs("mine-ok", **CLEAN, location="Loc-U")])
    keys = {f["resource"]["key"] for f in res["findings"]}
    assert keys == {"Observation/mine-bad"}  # the published bad record is context, not reported
    rows = {r["id"]: r for r in res["resources"]}
    assert rows["mine-ok"]["findings"] == 0 and rows["mine-bad"]["worst"] == "CRITICAL"
    assert res["summary"]["with_findings"] == 1 and res["findings"][0]["severity"] in ("CRITICAL", "ERROR")


def test_same_id_as_a_published_record_replaces_it_for_this_check_only():
    ds = dataset(location("Loc-T"), stats_obs("P", **ANCHOR))
    res = check_upload(ds, KN, [stats_obs("P", **CLEAN)])
    assert res["resources"][0]["replaces_published"] and res["findings"] == []
    same = check_upload(ds, KN, [stats_obs("P", **ANCHOR)])
    assert same["resources"][0]["identical_to_published"] and same["findings"]
    assert ds.raw["Observation"]["P"]["component"][0]["valueQuantity"]["value"] == 198000  # context untouched
