"""Save the data on this computer, downloaded from the source.

A public copy of this repository may carry no OneAquaHealth data (its licence is unverified, docs/07). A user then downloads
it here, directly from OneAquaHealth's own servers, so nothing is redistributed:

- the IG's source files used for lineage, from the IG repository on GitHub at the pinned commit, each saved only if it matches
  the sha256 recorded in knowledge/oah/sources.json;
- a new verified snapshot of the sandbox (GET and the server's own $validate only), exactly as `python tasks.py snapshot`.
"""

from __future__ import annotations

import hashlib
import urllib.parse
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx

from datadoctor.config import Settings
from datadoctor.ingestion.cache import HttpCache
from datadoctor.ingestion.fhir_client import FhirClient
from datadoctor.ingestion.snapshot import create_snapshot
from datadoctor.knowledge.loader import Knowledge

IG_REPO = "hl7-eu/oah"
OAH_PROFILE = "http://hl7.eu/fhir/ig/oah/StructureDefinition/"
Progress = Callable[[str, str, str, str | None], None]


class LocalCopyError(RuntimeError):
    pass


def ig_sample_files(kn: Knowledge) -> list[dict[str, str]]:
    """The IG source files lineage reads (sources.json records each one's path and sha256)."""
    return [f for f in kn.sources.get("files", []) if f["path"].startswith("_samples/")]


def missing_ig_files(kn: Knowledge) -> list[str]:
    return [Path(f["path"]).name for f in ig_sample_files(kn) if not (kn.upstream_dir / Path(f["path"]).name).is_file()]


def official_records(kn: Knowledge) -> Callable[[str, dict[str, Any]], bool]:
    """Which resources a snapshot asks the server's $validate about: the IG's own example observations."""

    def pick(rtype: str, res: dict[str, Any]) -> bool:
        return rtype == "Observation" and res["id"] in kn.ig_instances and any(
            p.startswith(OAH_PROFILE) for p in res.get("meta", {}).get("profile", []))

    return pick


async def fetch_ig_files(files: list[dict[str, str]], commit: str, dest: Path, *, progress: Progress,
                         transport: httpx.AsyncBaseTransport | None = None) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    async with httpx.AsyncClient(timeout=60.0, transport=transport) as http:
        for f in files:
            name = Path(f["path"]).name
            target, stage = dest / name, f"ig:{name}"
            label = f"Downloading {name} from the IG repository"
            if target.is_file() and hashlib.sha256(target.read_bytes()).hexdigest() == f["sha256"]:
                progress(stage, label, "done", "already on this computer, sha256 matches")
                continue
            progress(stage, label, "running", f"github.com/{IG_REPO} at {commit[:7]}")
            r = await http.get(f"https://raw.githubusercontent.com/{IG_REPO}/{commit}/{urllib.parse.quote(f['path'])}")
            digest = hashlib.sha256(r.content).hexdigest()
            if r.status_code != 200 or digest != f["sha256"]:
                why = f"HTTP {r.status_code}" if r.status_code != 200 else "it does not match the sha256 in knowledge/oah/sources.json"
                progress(stage, label, "failed", why)
                raise LocalCopyError(f"{name} was not saved: {why}")
            part = target.with_name(name + ".part")
            part.write_bytes(r.content)
            part.replace(target)
            progress(stage, label, "done", f"sha256 {digest[:12]}… matches")


async def capture_snapshot(settings: Settings, kn: Knowledge, *, progress: Progress,
                           transport: httpx.AsyncBaseTransport | None = None) -> Path:
    cache = HttpCache(settings.db_path, settings.cache_ttl_s)
    try:
        async with FhirClient(settings.fhir_base, cache, delay_s=settings.http_delay_s, timeout_s=settings.http_timeout_s,
                              transport=transport) as client:
            return await create_snapshot(client, settings.snapshots_dir, settings.ingest_types, page_size=settings.page_size,
                                         validate=official_records(kn), ig_commit=kn.ig_commit,
                                         knowledge_version=kn.version, progress=progress)
    finally:
        cache.close()
