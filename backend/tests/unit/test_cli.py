"""The command line reports expected failures as one clear line (no traceback) and writes UTF-8 even when redirected."""

import io
import json
import sys

import datadoctor.cli as cli
from datadoctor.ingestion.snapshot import SnapshotError
from datadoctor.ingestion.source import NoDataAvailable


def _failing(exc):
    async def run_audit(*args, **kwargs):
        raise exc

    return run_audit


def test_unreachable_sandbox_is_one_clear_error(monkeypatch, capsys):
    monkeypatch.setattr(cli, "run_audit", _failing(NoDataAvailable("live sandbox unavailable: getaddrinfo failed")))
    assert cli.main(["audit", "--source", "live"]) == 1
    err = capsys.readouterr().err
    assert err.startswith("error: live sandbox unavailable") and "hint: " in err and "--source auto" in err
    assert "Traceback" not in err


def test_tampered_snapshot_is_one_clear_error(monkeypatch, capsys):
    monkeypatch.setattr(cli, "run_audit", _failing(SnapshotError("snapshot X failed verification: ['sha256 mismatch']")))
    assert cli.main(["audit", "--source", "snapshot"]) == 1
    err = capsys.readouterr().err
    assert "failed verification" in err and "take a fresh one" in err


def test_redirected_output_is_utf8(monkeypatch):
    raw = io.BytesIO()
    legacy = io.TextIOWrapper(raw, encoding="cp1252", newline="\n")  # what Windows gives a redirected stdout
    monkeypatch.setattr(sys, "stdout", legacy)
    cli.utf8_output()
    print("OAH Data Doctor — median → minimum")
    sys.stdout.flush()
    assert raw.getvalue().decode("utf-8") == "OAH Data Doctor — median → minimum\n"


def test_check_command_exit_status_gates_a_pipeline(tmp_path, capsys):
    from tests.helpers import location, stats_obs

    bad = tmp_path / "bad.ndjson"
    bad.write_text(json.dumps(stats_obs("x1", average=198000, maximum=211000, minimum=185000, std_dev=18385, median=19.8)))
    ok = tmp_path / "ok.json"
    # A new site uploaded with its observation, so the reference resolves and there is no series to disagree with.
    ok.write_text(json.dumps({"resourceType": "Bundle", "entry": [
        {"resource": location("Loc-New-Site")},
        {"resource": stats_obs("x2", average=19.8, maximum=21.1, minimum=18.5, std_dev=1.8385, median=19.8, location="Loc-New-Site")}]}))
    assert cli.main(["check", str(bad)]) == 1
    assert "SEM-STAT-001" in capsys.readouterr().out
    assert cli.main(["check", str(ok)]) == 0
    missing = cli.main(["check", str(tmp_path / "nope.json")])
    assert missing == 1 and "Check the file path" in capsys.readouterr().err
