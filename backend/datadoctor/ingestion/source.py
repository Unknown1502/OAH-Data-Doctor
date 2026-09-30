"""Chooses where an audit's data comes from and labels it honestly.

Modes:
  live      fetch now; fail loudly if the sandbox is unreachable
  snapshot  read a dated snapshot (latest unless an id is given)
  auto      try live; if the sandbox is unreachable, serve the latest snapshot with fallback_reason set
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any

from datadoctor.config import Settings
from datadoctor.domain.enums import SourceKind
from datadoctor.domain.models import SourceInfo
from datadoctor.ingestion.cache import HttpCache
from datadoctor.ingestion.fhir_client import FhirClient, SandboxUnavailable
from datadoctor.ingestion.snapshot import SnapshotError, list_snapshots, load_snapshot

RawResources = dict[str, dict[str, dict[str, Any]]]


class NoDataAvailable(RuntimeError):
    pass


def latest_snapshot_dir(settings: Settings, snapshot_id: str | None = None) -> Path:
    if snapshot_id:
        p = settings.snapshots_dir / snapshot_id
        if not (p / "manifest.json").is_file():
            raise SnapshotError(f"unknown snapshot {snapshot_id}")
        return p
    snaps = list_snapshots(settings.snapshots_dir)
    if not snaps:
        raise SnapshotError("no snapshots available — run `python tasks.py snapshot` while online")
    return settings.snapshots_dir / snaps[0]["snapshot_id"]


def load_from_snapshot(settings: Settings, snapshot_id: str | None = None, fallback_reason: str | None = None
                       ) -> tuple[RawResources, SourceInfo, dict[str, Any]]:
    root = latest_snapshot_dir(settings, snapshot_id)
    manifest, raw, validation = load_snapshot(root)
    info = SourceInfo(kind=SourceKind.SNAPSHOT, base_url=manifest["source_url"], fetched_at=manifest["fetched_at"],
                      snapshot_id=manifest["snapshot_id"], manifest_sha256=manifest["manifest_sha256"],
                      fallback_reason=fallback_reason)
    return raw, info, validation


async def load_live(settings: Settings, *, use_cache: bool = False) -> tuple[RawResources, SourceInfo, dict[str, Any]]:
    cache = HttpCache(settings.db_path, settings.cache_ttl_s)
    fetched_at = dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        async with FhirClient(settings.fhir_base, cache, delay_s=settings.http_delay_s,
                              timeout_s=settings.http_timeout_s, retries=settings.http_retries) as client:
            await client.capability_statement()
            raw: RawResources = {}
            for rtype in settings.ingest_types:
                raw[rtype] = {r["id"]: r for r in await client.search_all(rtype, settings.page_size, use_cache=use_cache)}
    finally:
        cache.close()
    info = SourceInfo(kind=SourceKind.LIVE, base_url=settings.fhir_base, fetched_at=fetched_at)
    return raw, info, {}


async def load_data(settings: Settings, mode: str | None = None, snapshot_id: str | None = None
                    ) -> tuple[RawResources, SourceInfo, dict[str, Any]]:
    mode = mode or settings.source_mode
    if mode == "snapshot":
        return load_from_snapshot(settings, snapshot_id or settings.snapshot_id)
    try:
        return await load_live(settings)
    except (SandboxUnavailable, OSError, Exception) as exc:  # noqa: BLE001 - any live failure triggers fallback
        if mode == "live":
            raise NoDataAvailable(f"live sandbox unavailable: {exc}") from exc
        try:
            return load_from_snapshot(settings, snapshot_id or settings.snapshot_id,
                                      fallback_reason=f"Live sandbox unavailable ({type(exc).__name__}: {str(exc)[:160]}). "
                                                      "Showing the latest verified snapshot instead.")
        except SnapshotError as snap_exc:
            raise NoDataAvailable(f"live failed ({exc}) and no snapshot available ({snap_exc})") from snap_exc
