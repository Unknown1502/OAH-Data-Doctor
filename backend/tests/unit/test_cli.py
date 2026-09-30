"""The command line reports expected failures as one clear line (no traceback) and writes UTF-8 even when redirected."""

import io
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
