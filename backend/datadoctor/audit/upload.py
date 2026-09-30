"""Check data a user brings: FHIR JSON (one resource, a Bundle or a JSON array) or NDJSON, through the same rules.

The uploaded resources join the current dataset for one request only: references to published Locations and Groups
still resolve, series rules see the other years, and an uploaded resource with the id of a published one replaces it
for that check. Findings are reported for the uploaded resources only. Nothing is stored and nothing is sent anywhere.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from typing import Any

from datadoctor.config import INGEST_TYPES
from datadoctor.domain.models import Dataset, Finding, canonical_sha256
from datadoctor.knowledge.loader import Knowledge
from datadoctor.normalization.normalizer import (
    normalize_group,
    normalize_library,
    normalize_location,
    normalize_observation,
)
from datadoctor.rules.base import RuleContext, rules_version
from datadoctor.rules.registry import run_all

MAX_CHARS = 5_000_000
MAX_RESOURCES = 2_000
_ID = re.compile(r"^[A-Za-z0-9\-.]{1,64}$")
_SEVERITY_RANK = {"CRITICAL": 0, "ERROR": 1, "WARNING": 2, "INFO": 3}


class UploadError(ValueError):
    pass


def parse_upload(text: str) -> tuple[list[dict[str, Any]], list[str]]:
    """Resources to check, and notes about anything skipped. Accepts a resource, a Bundle, a JSON array or NDJSON."""
    text = text.strip().lstrip("﻿")
    if not text:
        raise UploadError("Nothing to check: paste FHIR JSON or choose a file.")
    if len(text) > MAX_CHARS:
        raise UploadError(f"That is more than {MAX_CHARS // 1_000_000} MB; split it into smaller files.")
    try:
        doc: Any = json.loads(text)
        items = doc if isinstance(doc, list) else [doc]
    except json.JSONDecodeError:
        items = []
        for n, line in enumerate(text.splitlines(), 1):
            if not line.strip():
                continue
            try:
                items.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise UploadError(f"Line {n} is not valid JSON ({exc.msg}). Paste a FHIR resource, a Bundle, or NDJSON "
                                  "(one resource per line).") from exc
    resources: list[dict[str, Any]] = []
    notes: list[str] = []
    for item in items:
        if isinstance(item, dict) and item.get("resourceType") == "Bundle":
            entries = [e.get("resource") for e in item.get("entry", []) if isinstance(e, dict)]
            resources.extend(r for r in entries if isinstance(r, dict))
            if not entries:
                notes.append("A Bundle had no entries.")
        elif isinstance(item, dict) and isinstance(item.get("resourceType"), str):
            resources.append(item)
        else:
            notes.append("Skipped an item that is not a FHIR resource (no resourceType).")
    if len(resources) > MAX_RESOURCES:
        raise UploadError(f"{len(resources)} resources; at most {MAX_RESOURCES} per check.")
    kept: list[dict[str, Any]] = []
    skipped = Counter[str]()
    for i, r in enumerate(resources, 1):
        rtype = r["resourceType"]
        if rtype not in INGEST_TYPES:
            skipped[rtype] += 1
            continue
        r = dict(r)
        if not isinstance(r.get("id"), str) or not _ID.match(r["id"]):
            r["id"] = f"upload-{i}"
        kept.append(r)
    for rtype, n in sorted(skipped.items()):
        notes.append(f"Skipped {n} {rtype} resource{'s' if n > 1 else ''}: Data Doctor checks {', '.join(INGEST_TYPES)}.")
    if not kept:
        raise UploadError("No resource Data Doctor can check was found. " + " ".join(notes))
    return kept, notes


def check_upload(ds: Dataset, kn: Knowledge, resources: list[dict[str, Any]]) -> dict[str, Any]:
    raw = {t: dict(v) for t, v in ds.raw.items()}
    replaced: set[str] = set()  # same id as a published record, different content
    identical: set[str] = set()  # an unchanged copy of a published record
    for r in resources:
        key = f"{r['resourceType']}/{r['id']}"
        published = raw.get(r["resourceType"], {}).get(r["id"])
        if published is not None:
            (identical if canonical_sha256(published) == canonical_sha256(r) else replaced).add(key)
        raw.setdefault(r["resourceType"], {})[r["id"]] = r
    by_type: dict[str, dict[str, dict[str, Any]]] = {}
    for r in resources:
        by_type.setdefault(r["resourceType"], {})[r["id"]] = r
    whatif = ds.model_copy(update={
        "raw": raw,
        "observations": {**ds.observations, **{i: normalize_observation(r, kn) for i, r in by_type.get("Observation", {}).items()}},
        "locations": {**ds.locations, **{i: normalize_location(r, kn) for i, r in by_type.get("Location", {}).items()}},
        "groups": {**ds.groups, **{i: normalize_group(r) for i, r in by_type.get("Group", {}).items()}},
        "libraries": {**ds.libraries, **{i: normalize_library(r, kn) for i, r in by_type.get("Library", {}).items()}},
        "resource_sha256": {**ds.resource_sha256, **{f"{r['resourceType']}/{r['id']}": canonical_sha256(r) for r in resources}},
    })
    keys = [f"{r['resourceType']}/{r['id']}" for r in resources]
    mine = set(keys)
    findings: list[Finding] = [f for f in run_all(whatif, kn) if f.resource.key in mine]
    per: dict[str, list[Finding]] = {k: [] for k in keys}
    for f in findings:
        per[f.resource.key].append(f)
    sev = Counter(f.severity.value for f in findings)
    ctx = RuleContext(ds=whatif, kn=kn, rules_version=rules_version())
    rows = []
    for r, key in zip(resources, keys, strict=True):
        fs = per[key]
        obs = whatif.observations.get(r["id"]) if r["resourceType"] == "Observation" else None
        rows.append({"key": key, "resource_type": r["resourceType"], "id": r["id"],
                     "display": ctx.display(obs) if obs is not None else str(r.get("name") or r.get("title") or r["id"]),
                     "replaces_published": key in replaced, "identical_to_published": key in identical, "findings": len(fs),
                     "worst": min((f.severity.value for f in fs), key=_SEVERITY_RANK.__getitem__, default=None)})
    out_findings = []
    for f in sorted(findings, key=lambda f: (_SEVERITY_RANK[f.severity.value], f.resource.key, f.rule_id)):
        d = f.model_dump(mode="json", exclude={"provenance", "lineage"})
        d["resource"]["key"] = f.resource.key
        out_findings.append(d)
    return {
        "resources": rows,
        "findings": out_findings,
        "summary": {"checked": len(resources), "with_findings": sum(1 for k in keys if per[k]),
                    "findings_total": len(findings), "by_severity": {k: sev.get(k, 0) for k in _SEVERITY_RANK},
                    "replaced_published": len(replaced), "identical_to_published": len(identical),
                    "context": ds.source.model_dump()},
    }
