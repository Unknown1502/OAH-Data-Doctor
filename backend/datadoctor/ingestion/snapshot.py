"""Snapshots: a dated, hashed, offline copy of everything an audit needs.

Layout, format 2 (docs/05_DATA_AND_SCHEMAS.md §Snapshot):
    data/snapshots/<snapshot_id>/
        manifest.json                     source URL, fetched-at, counts, sha256 of every file
        metadata/capability_statement.json
        metadata/resource_counts.json     server-side $get-resource-counts (includes deleted resources)
        resources/<Type>.ndjson           FHIR Bulk Data style: one resource per line, sorted by id, canonical JSON
                                          (sorted keys; values exactly as served)
        validation/<Type>.ndjson          one {"resource": "Type/id", "outcome": OperationOutcome} per line (optional)

Format 1 (one file per resource) is still readable. It was replaced because long resource ids exceeded the Windows
260-character path limit when the repository is cloned into a deep folder (found by the fresh-clone test).
"""

from __future__ import annotations

import contextlib
import datetime as dt
import hashlib
import json
import shutil
from collections import defaultdict
from pathlib import Path
from typing import Any

from datadoctor import __version__
from datadoctor.ingestion.fhir_client import FhirClient

FORMAT = "oah-data-doctor-snapshot/2 (FHIR bulk-data NDJSON)"
RawResources = dict[str, dict[str, dict[str, Any]]]


class SnapshotError(RuntimeError):
    pass


def utc_now_iso() -> str:
    return dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def canonical_line(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _write_bytes(root: Path, rel: str, data: bytes, files: list[dict[str, Any]]) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    files.append({"path": rel, "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)})


def _write_json(root: Path, rel: str, obj: Any, files: list[dict[str, Any]]) -> None:
    _write_bytes(root, rel, json.dumps(obj, indent=1, ensure_ascii=False, sort_keys=True).encode("utf-8"), files)


def _write_ndjson(root: Path, rel: str, rows: list[Any], files: list[dict[str, Any]]) -> None:
    _write_bytes(root, rel, ("\n".join(canonical_line(r) for r in rows) + "\n").encode("utf-8"), files)


def write_snapshot(root: Path, header: dict[str, Any], metadata: dict[str, Any], raw: RawResources,
                   validation: dict[str, Any]) -> Path:
    """Write a format-2 snapshot directory and its manifest."""
    files: list[dict[str, Any]] = []
    for name, obj in sorted(metadata.items()):
        _write_json(root, f"metadata/{name}.json", obj, files)
    for rtype, by_id in sorted(raw.items()):
        _write_ndjson(root, f"resources/{rtype}.ndjson", [by_id[i] for i in sorted(by_id)], files)
    by_type: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for key in sorted(validation):
        by_type[key.split("/")[0]].append({"resource": key, "outcome": validation[key]})
    for rtype, rows in sorted(by_type.items()):
        _write_ndjson(root, f"validation/{rtype}.ndjson", rows, files)
    manifest = {**header, "format": FORMAT, "resource_counts": {t: len(v) for t, v in raw.items()},
                "server_validations": len(validation), "files": sorted(files, key=lambda f: f["path"])}
    manifest["manifest_sha256"] = manifest_digest(manifest)
    (root / "manifest.json").write_text(json.dumps(manifest, indent=1, ensure_ascii=False), encoding="utf-8")
    return root


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
    metadata: dict[str, Any] = {"capability_statement": await client.capability_statement()}
    with contextlib.suppress(Exception):  # optional operation: some servers do not offer it
        metadata["resource_counts"] = await client.get_json("$get-resource-counts", use_cache=False)
    raw: RawResources = {}
    validation: dict[str, Any] = {}
    for rtype in resource_types:
        raw[rtype] = {}
        for res in await client.search_all(rtype, page_size, use_cache=False):
            raw[rtype][res["id"]] = res
            if validate is not None and validate(rtype, res):
                validation[f"{rtype}/{res['id']}"] = await client.validate_instance(rtype, res["id"])
    cap = metadata["capability_statement"]
    header = {"snapshot_id": snapshot_id, "source_url": client.base_url, "fetched_at": fetched_at, "completed_at": utc_now_iso(),
              "fhir_version": cap.get("fhirVersion"), "server_software": cap.get("software"),
              "ig_source": {"repo": "https://github.com/hl7-eu/oah", "commit": ig_commit},
              "knowledge_version": knowledge_version, "tool": f"oah-data-doctor {__version__}"}
    return write_snapshot(root, header, metadata, raw, validation)


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
                                                  "manifest_sha256", "server_validations", "format")})
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


def load_snapshot(root: Path, *, verify: bool = True) -> tuple[dict[str, Any], RawResources, dict[str, Any]]:
    """Load (manifest, raw resources by type/id, server validation outcomes by 'Type/id'). Reads formats 1 and 2."""
    if not (root / "manifest.json").is_file():
        raise SnapshotError(f"no manifest in {root}")
    if verify:
        problems = verify_snapshot(root)
        if problems:
            raise SnapshotError(f"snapshot {root.name} failed verification: {problems[:5]}")
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    raw: RawResources = {}
    validation: dict[str, Any] = {}
    for f in manifest["files"]:
        path: str = f["path"]
        parts = path.split("/")
        text = (root / path).read_text(encoding="utf-8")
        if parts[0] == "resources" and path.endswith(".ndjson"):
            bucket = raw.setdefault(parts[1][: -len(".ndjson")], {})
            for line in text.splitlines():
                if line.strip():
                    obj = json.loads(line)
                    bucket[obj["id"]] = obj
        elif parts[0] == "validation" and path.endswith(".ndjson"):
            for line in text.splitlines():
                if line.strip():
                    row = json.loads(line)
                    validation[row["resource"]] = row["outcome"]
        elif parts[0] == "resources":  # format 1: one file per resource
            obj = json.loads(text)
            raw.setdefault(parts[1], {})[obj["id"]] = obj
        elif parts[0] == "validation":
            validation[f"{parts[1]}/{parts[2][:-5]}"] = json.loads(text)
    return manifest, raw, validation


def repack_snapshot(root: Path) -> Path:
    """Rewrite a verified format-1 snapshot as format 2. Resource content is unchanged (checked per resource)."""
    manifest, raw, validation = load_snapshot(root)
    if manifest.get("format") == FORMAT:
        return root
    metadata = {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in sorted((root / "metadata").glob("*.json"))}
    header: dict[str, Any] = {k: manifest[k] for k in ("snapshot_id", "source_url", "fetched_at", "completed_at", "fhir_version", "server_software",
                                         "ig_source", "knowledge_version", "tool") if k in manifest}
    header["repacked"] = {"at": utc_now_iso(), "from_format": "oah-data-doctor-snapshot/1 (one file per resource)",
                          "from_manifest_sha256": manifest["manifest_sha256"],
                          "note": "Same fetched content re-serialised as NDJSON; every resource's canonical sha256 is unchanged."}
    tmp = root.with_name(root.name + ".repack")
    if tmp.exists():
        shutil.rmtree(tmp)
    write_snapshot(tmp, header, metadata, raw, validation)
    _, raw2, validation2 = load_snapshot(tmp)
    same = {t: {i: canonical_line(r) for i, r in v.items()} for t, v in raw.items()} == \
           {t: {i: canonical_line(r) for i, r in v.items()} for t, v in raw2.items()}
    if not same or validation2.keys() != validation.keys():
        shutil.rmtree(tmp)
        raise SnapshotError("repack changed the content; aborted")
    backup = root.with_name(root.name + ".format1")
    root.rename(backup)
    tmp.rename(root)
    shutil.rmtree(backup)
    return root
