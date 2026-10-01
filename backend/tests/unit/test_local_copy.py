"""Saving the data on this computer: an IG source file is kept only if it matches the sha256 recorded for it."""

import asyncio
import hashlib

import httpx
import pytest

from datadoctor.ingestion.local_copy import LocalCopyError, fetch_ig_files

BODY = b"Year;Parameter;Average;Median\n2013;Temperature (water);198000;19.8\n"
NAME = "Almyros_gov_chem_analysis.csv"
FILES = [{"path": f"_samples/crete/{NAME}", "sha256": hashlib.sha256(BODY).hexdigest()}]


def _fetch(dest, body: bytes, status: int = 200, calls: list[str] | None = None) -> list[tuple]:
    def handler(req: httpx.Request) -> httpx.Response:
        if calls is not None:
            calls.append(str(req.url))
        return httpx.Response(status, content=body)

    stages: list[tuple] = []
    asyncio.run(fetch_ig_files(FILES, "abc1234def", dest, progress=lambda *s: stages.append(s),
                               transport=httpx.MockTransport(handler)))
    return stages


def test_a_matching_file_is_saved_from_the_pinned_commit(tmp_path):
    calls: list[str] = []
    stages = _fetch(tmp_path, BODY, calls=calls)
    assert (tmp_path / NAME).read_bytes() == BODY
    assert calls == [f"https://raw.githubusercontent.com/hl7-eu/oah/abc1234def/_samples/crete/{NAME}"]
    assert stages[-1][2] == "done" and "matches" in stages[-1][3]


def test_a_file_that_does_not_match_its_sha256_is_never_saved(tmp_path):
    with pytest.raises(LocalCopyError, match="sha256"):
        _fetch(tmp_path, BODY.replace(b"19.8", b"198"))
    assert list(tmp_path.iterdir()) == []  # neither the file nor a partial download


def test_a_failed_download_is_reported_and_nothing_is_saved(tmp_path):
    with pytest.raises(LocalCopyError, match="HTTP 404"):
        _fetch(tmp_path, b"Not Found", status=404)
    assert list(tmp_path.iterdir()) == []


def test_a_file_already_on_this_computer_is_not_downloaded_again(tmp_path):
    (tmp_path / NAME).write_bytes(BODY)
    calls: list[str] = []
    stages = _fetch(tmp_path, b"unused", calls=calls)
    assert calls == [] and "already on this computer" in stages[0][3]
