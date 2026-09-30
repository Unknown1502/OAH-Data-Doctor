"""REST API. The UI talks only to this API; only the backend talks to the FHIR server (read-only)."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
from collections import Counter
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from datadoctor import __version__
from datadoctor.ai.explainer import get_explainer
from datadoctor.api.state import AppState
from datadoctor.audit.service import blocking_keys
from datadoctor.claims.engine import ClaimError, evaluate_claim
from datadoctor.claims.parser import parse_claim
from datadoctor.comparability.engine import ComparisonError, compare
from datadoctor.config import REPO_ROOT, get_settings
from datadoctor.domain.enums import Scope, Severity
from datadoctor.domain.models import Finding, StructuredClaim
from datadoctor.ingestion.snapshot import list_snapshots
from datadoctor.reporting.operation_outcome import operation_outcome_bundle
from datadoctor.reporting.report import build_model, render_html, render_markdown
from datadoctor.reporting.support import support_table
from datadoctor.rules.registry import load_rules
from datadoctor.trace.graph import impact

log = logging.getLogger("datadoctor.api")
STATE: AppState | None = None


def state() -> AppState:
    if STATE is None or STATE.result is None:
        raise HTTPException(503, "No audit run available yet")
    return STATE


@asynccontextmanager
async def lifespan(app: FastAPI):  # noqa: ANN201
    global STATE
    st = get_settings()
    STATE = AppState(st)
    try:
        await STATE.run("snapshot", st.snapshot_id)  # instant, offline-safe first view (labelled SNAPSHOT)
    except Exception as exc:  # noqa: BLE001
        log.warning("no snapshot available at startup: %s", exc)
    if st.source_mode in ("auto", "live") and os.environ.get("DD_STARTUP_LIVE", "1") == "1":
        asyncio.create_task(_background_live(st.source_mode))
    yield


async def _background_live(mode: str) -> None:
    assert STATE is not None
    try:
        await STATE.run(mode)
    except Exception as exc:  # noqa: BLE001 - the snapshot view stays; the UI shows the error
        log.warning("live refresh failed: %s", exc)


app = FastAPI(title="OAH Data Doctor API", version=__version__, lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
                   allow_methods=["GET", "POST"], allow_headers=["*"])


# ---------------------------------------------------------------------------------------------------
# Views
# ---------------------------------------------------------------------------------------------------


def _compact(f: Finding) -> dict[str, Any]:
    return {"id": f.id, "rule_id": f.rule_id, "title": f.title, "category": f.category.value, "severity": f.severity.value,
            "confidence": f.confidence, "confidence_label": f.confidence_label, "scope": f.scope.value,
            "resource": f.resource.model_dump(), "summary": f.summary, "related_count": len(f.related_resources),
            "has_lineage": f.lineage is not None}


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {"status": "ok", "version": __version__}


@app.get("/api/status")
def status() -> dict[str, Any]:
    s = STATE
    return {"version": __version__, "has_run": bool(s and s.result),
            "run_id": s.result.run_id if s and s.result else None,
            "source": s.result.source.model_dump() if s and s.result else None,
            "scan": s.scan if s else None, "mode": s.settings.source_mode if s else None,
            "fhir_base": s.settings.fhir_base if s else None,
            "llm": s.settings.llm_provider if s else "none",
            "snapshots": list_snapshots(s.settings.snapshots_dir) if s else []}


class AuditRequest(BaseModel):
    source: str = "auto"
    snapshot_id: str | None = None


@app.post("/api/audit")
async def run_audit_endpoint(req: AuditRequest) -> dict[str, Any]:
    assert STATE is not None
    if req.source not in ("live", "snapshot", "auto"):
        raise HTTPException(400, "source must be live, snapshot or auto")
    try:
        res = await STATE.run(req.source, req.snapshot_id)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, f"Audit failed: {exc}") from exc
    return {"run_id": res.run_id, "source": res.source.model_dump(), "summary": res.summary.model_dump()}


@app.get("/api/overview")
def overview() -> dict[str, Any]:
    s = state()
    res, an = s.result, s.analyses
    assert res is not None and an is not None and s.ds is not None
    oah = [f for f in res.findings if f.scope is Scope.OAH_IG]
    by_cat = Counter(f.category.value for f in res.findings)
    anchor = next((f for f in res.findings if f.resource.resource_id == res.summary.anchor["id"] and f.rule_id == "SEM-STAT-001"), None)
    hero = anchor or next(iter(res.findings), None)
    sites = Counter()
    for f in oah:
        if f.severity in (Severity.ERROR, Severity.CRITICAL) and f.resource.resource_type == "Observation":
            o = s.ds.observations.get(f.resource.resource_id)
            if o and o.subject_ref:
                loc = s.ds.locations.get(o.subject_ref.split("/")[-1])
                sites[loc.name if loc and loc.name else o.subject_ref] += 1
    return {
        "run_id": res.run_id, "created_at": res.created_at, "source": res.source.model_dump(), "summary": res.summary.model_dump(),
        "rules_version": res.rules_version, "knowledge_version": res.knowledge_version, "ig_commit": res.ig_commit,
        "findings_by_category": dict(by_cat),
        "hero_finding": _compact(hero) if hero else None,
        "top_findings": [_compact(f) for f in res.findings[:6]],
        "blocking_by_site": dict(sites.most_common()),
        "comparisons": [{"id": c.id, "a": c.a.label, "b": c.b.label, "verdict": c.verdict.value} for c in an.comparisons],
        "claims": [{"id": c.id, "text": c.claim_rendered, "verdict": c.verdict.value} for c in an.claims],
        "graph": s.graph.stats() if s.graph else {},
    }


@app.get("/api/findings")
def findings(severity: str | None = None, rule: str | None = None, scope: str | None = None, category: str | None = None,
             q: str | None = None, resource: str | None = None, limit: int = Query(500, le=2000)) -> dict[str, Any]:
    s = state()
    assert s.result is not None
    out = []
    for f in s.result.findings:
        if severity and f.severity.value not in severity.split(","):
            continue
        if rule and f.rule_id not in rule.split(","):
            continue
        if scope and f.scope.value != scope:
            continue
        if category and f.category.value not in category.split(","):
            continue
        if resource and resource not in ({f.resource.key} | {r.key for r in f.related_resources}):
            continue
        if q and q.lower() not in (f.summary + f.resource.key + f.rule_id + f.title).lower():
            continue
        out.append(_compact(f))
    return {"total": len(out), "items": out[:limit],
            "facets": {"severity": dict(Counter(f.severity.value for f in s.result.findings)),
                       "rule": dict(Counter(f.rule_id for f in s.result.findings)),
                       "category": dict(Counter(f.category.value for f in s.result.findings)),
                       "scope": dict(Counter(f.scope.value for f in s.result.findings))}}


def _finding(fid: str) -> Finding:
    s = state()
    assert s.result is not None
    f = next((x for x in s.result.findings if x.id == fid), None)
    if f is None:
        raise HTTPException(404, f"finding {fid} not in the current run")
    return f


@app.get("/api/findings/{fid}")
def finding_detail(fid: str) -> dict[str, Any]:
    s = state()
    assert s.ds is not None and s.result is not None and s.graph is not None
    f = _finding(fid)
    raw = s.ds.raw.get(f.resource.resource_type, {}).get(f.resource.resource_id)
    same = [_compact(x) for x in s.result.findings if x.id != f.id and x.resource.key == f.resource.key]
    record: dict[str, Any] | None = None
    obs = s.ds.observations.get(f.resource.resource_id) if f.resource.resource_type == "Observation" else None
    if obs is not None:
        ind = s.kn.indicators.get(obs.indicator_key or "")
        record = {"indicator_key": obs.indicator_key, "indicator": ind.label if ind else (obs.code_text or obs.code),
                  "canonical_unit": ind.canonical_unit if ind else None,
                  "hard": s.kn.hard_bounds(ind) if ind else None, "typical": s.kn.typical_bounds(ind) if ind else None,
                  "year": obs.year, "location": loc.name if (loc := s.ds.locations.get((obs.subject_ref or "").split("/")[-1])) else None,
                  "stats": [{"stat": x.stat, "value": x.quantity.value, "unit": x.quantity.code} for x in obs.stats],
                  "value": obs.value.model_dump() if obs.value else None}
    return {"finding": f.model_dump(), "raw": raw, "record": record,
            "server_validation": s.ds.server_validation.get(f.resource.key),
            "impact": impact(s.graph, f).model_dump(),
            "explanation": get_explainer("none", s.settings.llm_model).explain(f).model_dump(),
            "same_resource": same, "rule": load_rules()[f.rule_id].spec.as_dict()}


@app.post("/api/findings/{fid}/explain")
def explain(fid: str) -> dict[str, Any]:
    s = state()
    f = _finding(fid)
    return get_explainer(s.settings.llm_provider, s.settings.llm_model).explain(f).model_dump()


@app.post("/api/validate/{rtype}/{rid}")
async def validate_live(rtype: str, rid: str) -> dict[str, Any]:
    """Ask the FHIR server's own validator about one record now (GET $validate: read-only)."""
    from datadoctor.ingestion.fhir_client import FhirClient

    s = state()
    if rtype not in s.settings.ingest_types:
        raise HTTPException(400, "unsupported resource type")
    try:
        async with FhirClient(s.settings.fhir_base, None, delay_s=0, timeout_s=30, retries=1) as client:
            oo = await client.validate_instance(rtype, rid)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, f"The FHIR server could not be reached: {exc}") from exc
    import datetime as _dt

    return {"outcome": oo, "checked_at": _dt.datetime.now(_dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ"), "server": s.settings.fhir_base}


@app.get("/api/resources/{rtype}/{rid}")
def resource(rtype: str, rid: str) -> dict[str, Any]:
    s = state()
    assert s.ds is not None
    raw = s.ds.raw.get(rtype, {}).get(rid)
    if raw is None:
        raise HTTPException(404, f"{rtype}/{rid} not in the current dataset")
    return {"resource": raw, "sha256": s.ds.resource_sha256.get(f"{rtype}/{rid}"),
            "server_validation": s.ds.server_validation.get(f"{rtype}/{rid}"), "source": s.ds.source.model_dump()}


@app.get("/api/trace/resource/{rtype}/{rid}")
def trace_resource(rtype: str, rid: str) -> dict[str, Any]:
    s = state()
    assert s.graph is not None
    return impact(s.graph, start=[f"{rtype}/{rid}"]).model_dump()


@app.get("/api/observations")
def observations(include_third_party: bool = False) -> dict[str, Any]:
    s = state()
    assert s.ds is not None and s.result is not None
    blocked = blocking_keys(s.result.findings)
    counts = Counter(k for f in s.result.findings for k in {f.resource.key} | {r.key for r in f.related_resources})
    out = []
    for o in sorted(s.ds.observations.values(), key=lambda x: x.id):
        if o.scope is not Scope.OAH_IG and not include_third_party:
            continue
        loc = s.ds.locations.get((o.subject_ref or "").split("/")[-1])
        g = s.ds.groups.get(o.focus_refs[0].split("/")[-1]) if o.focus_refs else None
        ind = s.kn.indicators.get(o.indicator_key or "")
        out.append({"id": o.id, "indicator_key": o.indicator_key, "indicator": ind.label if ind else (o.code_text or o.code),
                    "medium": o.medium.value, "location_id": loc.id if loc else None, "location": loc.name if loc else None,
                    "cohort": g.label if g else None, "year": o.year, "date": o.effective_datetime,
                    "statistics": [x.stat for x in o.stats], "value": o.value.value if o.value else None,
                    "unit": (o.value.code if o.value else next((x.quantity.code for x in o.stats if x.quantity.code), None)),
                    "blocking": o.key in blocked, "findings": counts.get(o.key, 0), "scope": o.scope.value})
    return {"total": len(out), "items": out}


class Side(BaseModel):
    observation: str
    statistic: str | None = None


class CompareRequest(BaseModel):
    a: Side
    b: Side


@app.post("/api/compare")
def compare_endpoint(req: CompareRequest) -> dict[str, Any]:
    s = state()
    assert s.ds is not None and s.result is not None
    try:
        c = compare(s.ds, s.kn, s.result.findings, req.a.observation, req.b.observation, req.a.statistic, req.b.statistic)
    except ComparisonError as exc:
        raise HTTPException(400, str(exc)) from exc
    s.add_user_spec("comparison", {"id": c.id, "title": f"User comparison {c.id}",
                                   "a": {"observation": req.a.observation, "statistic": c.a.statistic},
                                   "b": {"observation": req.b.observation, "statistic": c.b.statistic}})
    s.recompute_analyses()
    return c.model_dump()


class ClaimRequest(BaseModel):
    claim: StructuredClaim


@app.post("/api/claims")
def claim_endpoint(req: ClaimRequest) -> dict[str, Any]:
    s = state()
    assert s.ds is not None and s.result is not None
    try:
        r = evaluate_claim(req.claim, s.ds, s.kn, s.result.findings)
    except (ClaimError, ComparisonError) as exc:
        raise HTTPException(400, str(exc)) from exc
    cid = "user-" + hashlib.sha256(req.claim.model_dump_json(exclude={"text"}).encode()).hexdigest()[:10]
    s.add_user_spec("claim", {"id": cid, "title": r.claim_rendered, "claim": req.claim.model_dump(mode="json", exclude_none=True)})
    s.recompute_analyses()
    return r.model_copy(update={"id": cid}).model_dump()


class ParseRequest(BaseModel):
    text: str


@app.post("/api/claims/parse")
def parse_endpoint(req: ParseRequest) -> dict[str, Any]:
    s = state()
    assert s.ds is not None
    if not req.text.strip() or len(req.text) > 500:
        raise HTTPException(400, "claim text must be 1-500 characters")
    return parse_claim(req.text, s.ds, s.kn, s.settings.llm_provider, s.settings.llm_model).model_dump()


@app.get("/api/analyses")
def analyses() -> dict[str, Any]:
    s = state()
    assert s.analyses is not None
    return s.analyses.model_dump()


@app.post("/api/analyses/reset")
def reset_user_analyses() -> dict[str, Any]:
    s = state()
    s.clear_user_specs()
    s.recompute_analyses()
    return {"ok": True}


@app.get("/api/knowledge")
def knowledge() -> dict[str, Any]:
    s = state()
    kn = s.kn
    return {"version": kn.version, "ig_commit": kn.ig_commit,
            "indicators": {k: {"label": v.label, "medium": v.medium.value, "kind": v.kind, "unit": v.canonical_unit}
                           for k, v in kn.indicators.items()},
            "thresholds": kn.thresholds, "plausibility": kn.plausibility}


@app.get("/api/rules")
def rules() -> list[dict[str, Any]]:
    s = STATE
    counts = Counter(f.rule_id for f in s.result.findings) if s and s.result else Counter()
    return [{**r.spec.as_dict(), "findings": counts.get(rid, 0)} for rid, r in sorted(load_rules().items())]


@app.get("/api/support")
def support() -> list[dict[str, Any]]:
    s = state()
    assert s.ds is not None and s.result is not None
    return [r.model_dump() for r in support_table(s.ds, s.kn, s.result.findings)]


@app.get("/api/runs")
def runs() -> list[dict[str, Any]]:
    assert STATE is not None
    return STATE.past_runs()


@app.get("/api/reports/{name}")
def report(name: str) -> Response:
    s = state()
    assert s.result is not None and s.ds is not None and s.analyses is not None
    res = s.result
    fname = f"oah-data-doctor-{res.run_id}"
    if name == "findings.json":
        return JSONResponse(res.model_dump(mode="json"), headers={"Content-Disposition": f'attachment; filename="{fname}-findings.json"'})
    if name == "operation-outcome.json":
        return JSONResponse(operation_outcome_bundle(res.findings, res.run_id, res.created_at), media_type="application/fhir+json",
                            headers={"Content-Disposition": f'attachment; filename="{fname}-operation-outcome.json"'})
    sup = support_table(s.ds, s.kn, res.findings)
    model = build_model(res, s.analyses, sup)
    if name == "report.md":
        return PlainTextResponse(render_markdown(model), media_type="text/markdown",
                                 headers={"Content-Disposition": f'attachment; filename="{fname}-report.md"'})
    if name == "report.html":
        return HTMLResponse(render_html(model))
    if name == "support.json":
        return JSONResponse([r.model_dump() for r in sup])
    raise HTTPException(404, "unknown report")


# ---------------------------------------------------------------------------------------------------
# Static UI (built frontend) — single port for `python tasks.py run`
# ---------------------------------------------------------------------------------------------------
DIST = REPO_ROOT / "frontend" / "dist"
if (DIST / "index.html").is_file():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str) -> Response:
        if path.startswith("api/"):
            raise HTTPException(404)
        target = (DIST / path).resolve()
        if path and target.is_file() and Path(DIST.resolve()) in target.parents:
            return FileResponse(target)
        return FileResponse(DIST / "index.html")
