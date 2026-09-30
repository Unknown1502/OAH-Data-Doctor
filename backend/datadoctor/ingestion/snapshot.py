"""Snapshots: a dated, hashed, offline copy of everything an audit needs.

Layout (docs/05_DATA_AND_SCHEMAS.md §Snapshot):
    data/snapshots/<snapshot_id>/
        manifest.json                  source URL, fetched-at, counts, sha256 of every file
        metadata/capability_statement.json
        metadata/resource_counts.json  server-side $get-resource-counts (includes deleted resources)
        resources/<Type>/<id>.json     raw FHIR JSON as served (re-serialised with sorted keys; values unchanged)
        validation/<Type>/<id>.json    server $validate OperationOutcome (optional)
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from pathlib import Path
from typing import Any

from datadoctor import __version__
from datadoctor.ingestion.fhir_client import FhirClient


class SnapshotError(RuntimeError):
    pass


def utc_now_iso() -> str:
    return dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _write_json(path: Path, obj: Any) -> tuple[str, int]:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(obj, indent=1, ensure_ascii=False, sort_keys=True).encode("utf-8")
    path.write_bytes(data)
    return hashlib.sha256(data).hexdigest(), len(data)


async def create_snapshot(
    client: FhirClient,
    snapshots_dir: Path,
    resource_types: tuple[str, ...],
    *,
    page_size: int = 200,
    validate: Any = None,  # callable(resource_type, raw) -> bool : which resources to $validate server-side
    ig_commit: str | None = None,
    knowledge_version: str | None = None,
) -> Path:
    fetched_at = utc_now_iso()
    snapshot_id = fetched_at.replace(":", "-")
    root = snapshots_dir / snapshot_id
    if root.exists():
        raise SnapshotError(f"snapshot {snapshot_id} already exists")
    files: list[dict[str, Any]] = []

    def record(rel: str, obj: Any) -> None:
        sha, size = _write_json(root / rel, obj)
        files.append({"path": rel, "sha256": sha, "bytes": size})

    cap = await client.capability_statement()
    record("metadata/capability_statement.json", cap)
    try:
        counts = await client.get_json("$get-resource-counts", use_cache=False)
        record("metadata/resource_counts.json", counts)
    except Exception:  # noqa: BLE001 - optional operation
        pass

    resource_counts: dict[str, int] = {}
    validated = 0
    for rtype in resource_types:
        resources = await client.search_all(rtype, page_size, use_cache=False)
        resource_counts[rtype] = len(resources)
        for res in resources:
            record(f"resources/{rtype}/{res['id']}.json", res)
            if validate is not None and validate(rtype, res):
                oo = await client.validate_instance(rtype, res["id"])
                record(f"validation/{rtype}/{res['id']}.json", oo)
                validated += 1

    manifest = {
        "snapshot_id": snapshot_id,
        "source_url": client.base_url,
        "fetched_at": fetched_at,
        "completed_at": utc_now_iso(),
        "fhir_version": cap.get("fhirVersion"),
        "server_software": cap.get("software"),
        "resource_counts": resource_counts,
        "server_validations": validated,
        "ig_source": {"repo": "https://github.com/hl7-eu/oah", "commit": ig_commit},
        "knowledge_version": knowledge_version,
        "tool": f"oah-data-doctor {__version__}",
        "files": sorted(files, key=lambda f: f["path"]),
    }
    manifest["manifest_sha256"] = manifest_digest(manifest)
    (root / "manifest.json").write_text(json.dumps(manifest, indent=1, ensure_ascii=False), encoding="utf-8")
    return root


def manifest_digest(manifest: dict[str, Any]) -> str:
    body = {k: v for k, v in manifest.items() if k != "manifest_sha256"}
    return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def list_snapshots(snapshots_dir: Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if not snapshots_dir.exists():
        return out
    for d in sorted(snapshots_dir.iterdir(), reverse=True):
        m = d / "manifest.json"
        if m.is_file():
            man = json.loads(m.read_text(encoding="utf-8"))
            out.append({k: man.get(k) for k in ("snapshot_id", "source_url", "fetched_at", "resource_counts",
                                                  "manifest_sha256", "server_validations")})
    return out


def verify_snapshot(root: Path) -> list[str]:
    """Return a list of integrity problems (empty list = snapshot verified)."""
    problems = []
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    if manifest_digest(manifest) != manifest.get("manifest_sha256"):
        problems.append("manifest digest mismatch")
    for f in manifest["files"]:
        p = root / f["path"]
        if not p.is_file():
            problems.append(f"missing {f['path']}")
        elif hashlib.sha256(p.read_bytes()).hexdigest() != f["sha256"]:
            problems.append(f"sha256 mismatch {f['path']}")
    return problems


def load_snapshot(root: Path, *, verify: bool = True) -> tuple[dict[str, Any], dict[str, dict[str, dict[str, Any]]], dict[str, Any]]:
    """Load (manifest, raw resources by type/id, server validation outcomes by 'Type/id')."""
    if not (root / "manifest.json").is_file():
        raise SnapshotError(f"no manifest in {root}")
    if verify:
        problems = verify_snapshot(root)
        if problems:
            raise SnapshotError(f"snapshot {root.name} failed verification: {problems[:5]}")
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    raw: dict[str, dict[str, dict[str, Any]]] = {}
    validation: dict[str, Any] = {}
    for f in manifest["files"]:
        parts = f["path"].split("/")
        if parts[0] == "resources":
            obj = json.loads((root / f["path"]).read_text(encoding="utf-8"))
            raw.setdefault(parts[1], {})[obj["id"]] = obj
        elif parts[0] == "validation":
            validation[f"{parts[1]}/{parts[2][:-5]}"] = json.loads((root / f["path"]).read_text(encoding="utf-8"))
    return manifest, raw, validation
