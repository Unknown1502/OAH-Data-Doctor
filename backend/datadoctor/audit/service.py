"""Audit orchestration: data source -> normalisation -> rules -> lineage -> summary."""

from __future__ import annotations

import asyncio
import datetime as dt
import hashlib
import logging
from collections import Counter
from typing import Any

from pydantic import BaseModel, Field

from datadoctor import __version__
from datadoctor.config import Settings
from datadoctor.domain.enums import Scope, Severity
from datadoctor.domain.models import Dataset, Finding, SourceInfo
from datadoctor.ingestion.cache import HttpCache
from datadoctor.ingestion.fhir_client import FhirClient
from datadoctor.ingestion.source import load_data
from datadoctor.knowledge.loader import Knowledge, load_knowledge
from datadoctor.normalization.normalizer import build_dataset
from datadoctor.provenance.lineage import almyros_lineage
from datadoctor.rules.base import rules_version
from datadoctor.rules.registry import load_rules, run_all

log = logging.getLogger(__name__)
ANCHOR_ID = "Obs-Almyros-TemperatureWater-2013"
BLOCKING = (Severity.ERROR, Severity.CRITICAL)


class AuditSummary(BaseModel):
    resources_by_type: dict[str, int]
    resources_by_scope: dict[str, int]
    observations_checked: int
    findings_total: int
    findings_by_severity: dict[str, int]
    findings_by_rule: dict[str, int]
    findings_by_scope: dict[str, int]
    affected_resources: int
    oah_observations: int
    oah_observations_with_blocking: int
    integrity_pass_rate: float | None = Field(description="share of OAH IG observations with no ERROR/CRITICAL finding")
    server_validation: dict[str, int] = Field(default_factory=dict,
                                              description="server $validate outcomes for flagged OAH observations (snapshot runs)")
    anchor: dict[str, Any]


class AuditResult(BaseModel):
    run_id: str
    created_at: str
    tool_version: str
    rules_version: str
    knowledge_version: str
    ig_commit: str
    source: SourceInfo
    summary: AuditSummary
    findings: list[Finding]


def _run_id(source: SourceInfo, rules_v: str, kn_v: str) -> str:
    stamp = dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%SZ")
    h = hashlib.sha256(f"{source.kind}|{source.fetched_at}|{source.snapshot_id}|{rules_v}|{kn_v}".encode()).hexdigest()[:6]
    return f"run-{stamp}-{h}"


def blocking_keys(findings: list[Finding]) -> dict[str, list[Finding]]:
    """resource key -> ERROR/CRITICAL findings that touch it (as primary or related resource)."""
    out: dict[str, list[Finding]] = {}
    for f in findings:
        if f.severity not in BLOCKING:
            continue
        keys = {f.resource.key} | ({r.key for r in f.related_resources} if f.resource.resource_type != "CodeSystem" else set())
        for k in keys:
            out.setdefault(k, []).append(f)
    return out


def summarise(ds: Dataset, findings: list[Finding], kn: Knowledge) -> AuditSummary:
    sev = Counter(f.severity.value for f in findings)
    affected = {f.resource.key for f in findings}
    oah_obs = [o for o in ds.observations.values() if o.scope is Scope.OAH_IG]
    blocked = blocking_keys(findings)
    oah_blocked = [o for o in oah_obs if o.key in blocked]
    anchor = ds.observations.get(ANCHOR_ID)
    anchor_findings = [f for f in findings if f.resource.key == f"Observation/{ANCHOR_ID}"]
    anchor_info: dict[str, Any] = {"id": ANCHOR_ID, "present": anchor is not None,
                                   "rules_fired": sorted({f.rule_id for f in anchor_findings})}
    if anchor is not None:
        anchor_info["values"] = {s.stat: s.quantity.value for s in anchor.stats}
        anchor_info["unit"] = next((s.quantity.code for s in anchor.stats if s.quantity.code), None)
        anchor_info["server_validation"] = ds.server_validation.get(f"Observation/{ANCHOR_ID}")
    scope_counts: Counter[str] = Counter()
    for rs in ds.raw.values():
        for rid in rs:
            scope_counts[Scope.OAH_IG.value if rid in kn.ig_instances else Scope.THIRD_PARTY.value] += 1
    sv: dict[str, int] = {}
    if ds.server_validation:
        flagged_validated = [o for o in oah_blocked if o.key in ds.server_validation]
        no_errors = [o for o in flagged_validated
                     if not any(i.get("severity") in ("error", "fatal") for i in ds.server_validation[o.key].get("issue", []))]
        sv = {"validated_total": len(ds.server_validation),
              "validated_with_errors": sum(1 for oo in ds.server_validation.values()
                                           if any(i.get("severity") in ("error", "fatal") for i in oo.get("issue", []))),
              "flagged_observations_validated": len(flagged_validated),
              "flagged_observations_passing_server_validation": len(no_errors)}
    return AuditSummary(
        resources_by_type=ds.counts(),
        resources_by_scope=dict(scope_counts),
        observations_checked=len(ds.observations),
        findings_total=len(findings),
        findings_by_severity={s.value: sev.get(s.value, 0) for s in reversed(Severity)},
        findings_by_rule=dict(sorted(Counter(f.rule_id for f in findings).items())),
        findings_by_scope=dict(Counter(f.scope.value for f in findings)),
        affected_resources=len(affected),
        oah_observations=len(oah_obs),
        oah_observations_with_blocking=len(oah_blocked),
        integrity_pass_rate=round(1 - len(oah_blocked) / len(oah_obs), 4) if oah_obs else None,
        server_validation=sv,
        anchor=anchor_info,
    )


def audit_dataset(ds: Dataset, kn: Knowledge) -> AuditResult:
    load_rules()
    findings = run_all(ds, kn)
    for f in findings:
        if f.resource.resource_type == "Observation":
            obs = ds.observations.get(f.resource.resource_id)
            if obs is not None:
                f.lineage = almyros_lineage(obs, ds, kn.ig_commit)
    rv = rules_version()
    return AuditResult(
        run_id=_run_id(ds.source, rv, kn.version),
        created_at=dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        tool_version=__version__, rules_version=rv, knowledge_version=kn.version, ig_commit=kn.ig_commit,
        source=ds.source, summary=summarise(ds, findings, kn), findings=findings,
    )


async def validate_flagged_on_server(settings: Settings, ds: Dataset, findings: list[Finding], *,
                                     concurrency: int = 4) -> dict[str, Any]:
    """Ask the FHIR server's own `$validate` (read-only GET) about every official observation Data Doctor flags.

    Snapshots store these verdicts; a live run fetches them so the "server says valid / Data Doctor says impossible"
    comparison is available for live data too. Requests are rate-limited by the client's polite delay and cached.
    """
    keys = sorted(k for k in blocking_keys(findings)
                  if k.startswith("Observation/") and (o := ds.observations.get(k.split("/", 1)[1])) is not None
                  and o.scope is Scope.OAH_IG)
    out: dict[str, Any] = {}
    cache = HttpCache(settings.db_path, settings.cache_ttl_s)
    try:
        async with FhirClient(settings.fhir_base, cache, delay_s=settings.http_delay_s, timeout_s=settings.http_timeout_s,
                              retries=1) as client:
            sem = asyncio.Semaphore(concurrency)

            async def one(key: str) -> None:
                async with sem:
                    rtype, rid = key.split("/", 1)
                    out[key] = await client.validate_instance(rtype, rid)

            await asyncio.gather(*(one(k) for k in keys))
    finally:
        cache.close()
    return out


async def complete_live_validation(settings: Settings, ds: Dataset, res: AuditResult, kn: Knowledge) -> AuditResult:
    """For live runs without stored server verdicts, fetch them and recompute the summary. Never fails the audit."""
    from datadoctor.domain.enums import SourceKind

    if ds.source.kind is not SourceKind.LIVE or ds.server_validation:
        return res
    try:
        ds.server_validation = await validate_flagged_on_server(settings, ds, res.findings)
    except Exception as exc:  # noqa: BLE001 - the audit stands without server verdicts; the UI says "not checked"
        log.warning("server $validate of flagged records failed: %s", exc)
        return res
    return res.model_copy(update={"summary": summarise(ds, res.findings, kn)})


async def run_audit(settings: Settings, mode: str | None = None, snapshot_id: str | None = None) -> tuple[AuditResult, Dataset]:
    kn = load_knowledge(settings.knowledge_dir)
    raw, source, validation = await load_data(settings, mode, snapshot_id)
    ds = build_dataset(raw, source, kn, validation)
    res = await complete_live_validation(settings, ds, audit_dataset(ds, kn), kn)
    return res, ds
