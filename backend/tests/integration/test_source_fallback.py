"""When the sandbox is unreachable, `auto` serves the latest verified snapshot and says so; `live` fails loudly."""

import asyncio
from dataclasses import replace

import pytest

from datadoctor.config import Settings
from datadoctor.domain.enums import SourceKind
from datadoctor.ingestion.source import NoDataAvailable, load_data

UNREACHABLE = Settings(fhir_base="http://127.0.0.1:9/fhir", http_timeout_s=2.0, http_retries=0, http_delay_s=0.0)


def test_auto_falls_back_to_the_verified_snapshot_with_a_reason():
    raw, source, validation = asyncio.run(load_data(UNREACHABLE, "auto"))
    assert source.kind is SourceKind.SNAPSHOT
    assert source.fallback_reason and "Live sandbox unavailable" in source.fallback_reason
    assert source.manifest_sha256
    assert len(raw["Observation"]) > 0 and validation


def test_live_mode_never_silently_substitutes_a_snapshot():
    with pytest.raises(NoDataAvailable):
        asyncio.run(load_data(UNREACHABLE, "live"))


def test_auto_without_any_snapshot_reports_both_failures(tmp_path):
    empty = replace(UNREACHABLE, data_dir=tmp_path)
    with pytest.raises(NoDataAvailable) as exc:
        asyncio.run(load_data(empty, "auto"))
    assert "no snapshot" in str(exc.value)
