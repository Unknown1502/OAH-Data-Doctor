"""Application state: the current audit run, its analyses and dependency graph, plus user-run analyses."""

from __future__ import annotations

import asyncio
import datetime as dt
import json
import logging
import sqlite3
from typing import Any

from datadoctor.audit.analyses import AnalysesResult, run_catalog
from datadoctor.audit.service import AuditResult, audit_dataset
from datadoctor.config import Settings
from datadoctor.domain.models import Dataset
from datadoctor.ingestion.source import load_data
from datadoctor.knowledge.loader import Knowledge, load_knowledge
from datadoctor.normalization.normalizer import build_dataset
from datadoctor.trace.graph import DependencyGraph, build_graph

log = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS user_analyses (id TEXT PRIMARY KEY, kind TEXT NOT NULL, spec TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS runs (run_id TEXT PRIMARY KEY, created_at TEXT, source TEXT, summary TEXT);
"""


class AppState:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.kn: Knowledge = load_knowledge(settings.knowledge_dir)
        self.result: AuditResult | None = None
        self.ds: Dataset | None = None
        self.analyses: AnalysesResult | None = None
        self.graph: DependencyGraph | None = None
        self.scan: dict[str, Any] = {"running": False, "mode": None, "started_at": None, "error": None}
        self.lock = asyncio.Lock()
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(settings.db_path), check_same_thread=False)
        self.db.executescript(_SCHEMA)

    # -- user analyses (persisted so the impact trace includes what users actually ran) -------------
    def user_specs(self, kind: str) -> list[dict[str, Any]]:
        rows = self.db.execute("SELECT spec FROM user_analyses WHERE kind = ? ORDER BY created_at", (kind,)).fetchall()
        return [json.loads(r[0]) for r in rows]

    def add_user_spec(self, kind: str, spec: dict[str, Any]) -> None:
        self.db.execute("INSERT OR REPLACE INTO user_analyses (id, kind, spec, created_at) VALUES (?, ?, ?, ?)",
                        (spec["id"], kind, json.dumps(spec), dt.datetime.now(dt.UTC).isoformat()))
        self.db.commit()

    def clear_user_specs(self) -> None:
        self.db.execute("DELETE FROM user_analyses")
        self.db.commit()

    # -- runs --------------------------------------------------------------------------------------------
    def recompute_analyses(self) -> None:
        assert self.ds is not None and self.result is not None
        self.analyses = run_catalog(self.ds, self.kn, self.result.findings, self.user_specs("comparison"), self.user_specs("claim"))
        self.graph = build_graph(self.ds, self.kn, self.analyses.comparisons, self.analyses.claims)

    async def run(self, mode: str | None = None, snapshot_id: str | None = None) -> AuditResult:
        async with self.lock:
            self.scan = {"running": True, "mode": mode or self.settings.source_mode,
                         "started_at": dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ"), "error": None}
            try:
                raw, source, validation = await load_data(self.settings, mode, snapshot_id)
                ds = build_dataset(raw, source, self.kn, validation)
                res = await asyncio.to_thread(audit_dataset, ds, self.kn)
                self.ds, self.result = ds, res
                await asyncio.to_thread(self.recompute_analyses)
                self.db.execute("INSERT OR REPLACE INTO runs VALUES (?, ?, ?, ?)",
                                (res.run_id, res.created_at, res.source.model_dump_json(), res.summary.model_dump_json()))
                self.db.commit()
                self.scan["running"] = False
                return res
            except Exception as exc:
                self.scan.update(running=False, error=f"{type(exc).__name__}: {exc}")
                raise

    def past_runs(self, limit: int = 20) -> list[dict[str, Any]]:
        rows = self.db.execute("SELECT run_id, created_at, source FROM runs ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
        return [{"run_id": r[0], "created_at": r[1], "source": json.loads(r[2])} for r in rows]
