"""Dependency graph and impact trace.

Nodes are records and the analyses Data Doctor actually computes in the current run:
  observation, location, group        (records)
  library                             (published data-set collections containing the record)
  series                              (annual time series per site x indicator x statistic, >= 3 points; used by trend claims)
  profile                             (per-library per-indicator summary shown in the researcher report)
  comparison, claim                   (catalog analyses + analyses a user ran)
Edges point downstream ("is consumed by"). The impact of a finding is exactly the set of nodes reachable from
the records it touches — nothing is estimated or extrapolated (docs/IMPACT_TRACE_SPEC.md).
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel

from datadoctor.domain.models import ClaimResult, Comparison, Dataset, Finding
from datadoctor.knowledge.loader import Knowledge

SERIES_STATS = ("average", "median")
MIN_SERIES = 3


@dataclass
class Node:
    id: str
    type: str
    label: str
    attrs: dict[str, Any] = field(default_factory=dict)


class ImpactNode(BaseModel):
    id: str
    type: str
    label: str
    depth: int
    via: str | None
    attrs: dict[str, Any] = {}


class ImpactReport(BaseModel):
    finding_id: str | None
    start: list[str]
    reachable: list[ImpactNode]
    counts: dict[str, int]
    edges: list[tuple[str, str, str]]
    statement: str


class DependencyGraph:
    def __init__(self) -> None:
        self.nodes: dict[str, Node] = {}
        self.out: dict[str, set[tuple[str, str]]] = defaultdict(set)

    def add(self, node_id: str, type_: str, label: str, **attrs: Any) -> None:
        if node_id not in self.nodes:
            self.nodes[node_id] = Node(node_id, type_, label, attrs)

    def link(self, src: str, dst: str, kind: str) -> None:
        if src in self.nodes and dst in self.nodes and src != dst:
            self.out[src].add((dst, kind))

    def downstream(self, starts: list[str]) -> tuple[dict[str, tuple[int, str | None]], list[tuple[str, str, str]]]:
        seen: dict[str, tuple[int, str | None]] = {}
        edges: list[tuple[str, str, str]] = []
        q = deque((s, 0) for s in starts if s in self.nodes)
        for s in starts:
            if s in self.nodes:
                seen[s] = (0, None)
        while q:
            cur, d = q.popleft()
            for nxt, kind in sorted(self.out.get(cur, ())):
                edges.append((cur, nxt, kind))
                if nxt not in seen:
                    seen[nxt] = (d + 1, cur)
                    q.append((nxt, d + 1))
        return seen, edges

    def stats(self) -> dict[str, int]:
        c: dict[str, int] = defaultdict(int)
        for n in self.nodes.values():
            c[n.type] += 1
        return dict(c)


def build_graph(ds: Dataset, kn: Knowledge, comparisons: list[Comparison], claims: list[ClaimResult]) -> DependencyGraph:
    g = DependencyGraph()
    for o in ds.observations.values():
        g.add(o.key, "observation", o.id, scope=o.scope.value)
    for loc in ds.locations.values():
        g.add(f"Location/{loc.id}", "location", loc.name or loc.id)
    for gid, c in ds.groups.items():
        g.add(f"Group/{gid}", "group", c.label)
    for o in ds.observations.values():
        if o.subject_ref:
            g.link(o.subject_ref, o.key, "context-of")
        for f in o.focus_refs:
            g.link(f, o.key, "context-of")

    # Libraries and per-library indicator profiles
    for lib in ds.libraries.values():
        lid = f"Library/{lib.id}"
        g.add(lid, "library", lib.title or lib.id, declared=lib.declared_records)
        for m in lib.member_refs:
            g.link(m, lid, "member-of")
            obs = ds.observations.get(m.split("/")[-1]) if m.startswith("Observation/") else None
            if obs and obs.indicator_key:
                pid = f"profile:{lib.id}:{obs.indicator_key}"
                g.add(pid, "profile", f"{lib.title or lib.id} · {kn.indicators[obs.indicator_key].label} profile",
                      library=lib.id, indicator=obs.indicator_key)
                g.link(m, pid, "summarised-in")

    # Annual series per site x indicator x statistic
    series: dict[tuple[str, str, str], list[str]] = defaultdict(list)
    for o in ds.observations.values():
        if o.indicator_key and o.effective_period and o.effective_period.is_annual and o.subject_ref:
            for st in SERIES_STATS:
                if o.stat(st):
                    series[(o.subject_ref, o.indicator_key, st)].append(o.key)
    for (loc, ind, st), members in series.items():
        if len(members) < MIN_SERIES:
            continue
        sid = f"series:{loc.split('/')[-1]}:{ind}:{st}"
        locname = ds.locations.get(loc.split("/")[-1])
        g.add(sid, "series", f"{kn.indicators[ind].label} at {locname.name if locname else loc} · annual {st} series",
              location=loc, indicator=ind, statistic=st, points=len(members))
        g.link(loc, sid, "context-of")
        for m in members:
            g.link(m, sid, "point-of")

    for c in comparisons:
        cid = f"comparison:{c.id}"
        g.add(cid, "comparison", f"{c.a.label}  vs  {c.b.label}", verdict=c.verdict.value)
        for side in (c.a, c.b):
            g.link(f"Observation/{side.observation_id}", cid, "input-to")
            if side.location_id:
                g.link(f"Location/{side.location_id}", cid, "context-of")
            if side.cohort:
                g.link(f"Group/{side.cohort.group_id}", cid, "context-of")

    for cl in claims:
        nid = f"claim:{cl.id}"
        g.add(nid, "claim", cl.claim_rendered, verdict=cl.verdict.value, type=cl.claim.type.value)
        for key in cl.inputs:
            g.link(key, nid, "evidence-for")
        if cl.comparison is not None:
            cmp_id = f"comparison:{cl.comparison.id}"
            g.add(cmp_id, "comparison", f"{cl.comparison.a.label}  vs  {cl.comparison.b.label}", verdict=cl.comparison.verdict.value)
            g.link(cmp_id, nid, "basis-of")
            for side in (cl.comparison.a, cl.comparison.b):
                g.link(f"Observation/{side.observation_id}", cmp_id, "input-to")
        if cl.claim.type.value == "TREND_INCREASE" and cl.claim.location_id and cl.claim.indicator_key:
            sid = f"series:{cl.claim.location_id}:{cl.claim.indicator_key}:{cl.claim.statistic or 'average'}"
            g.link(sid, nid, "basis-of")
    return g


DOWNSTREAM_TYPES = ("library", "profile", "series", "comparison", "claim")


def impact(g: DependencyGraph, finding: Finding | None = None, start: list[str] | None = None) -> ImpactReport:
    if finding is not None:
        starts = [finding.resource.key] if finding.resource.resource_type != "CodeSystem" else []
        starts += [r.key for r in finding.related_resources]
    else:
        starts = start or []
    seen, edges = g.downstream(starts)
    reach = [ImpactNode(id=n, type=g.nodes[n].type, label=g.nodes[n].label, depth=d, via=v, attrs=g.nodes[n].attrs)
             for n, (d, v) in seen.items() if g.nodes[n].type in DOWNSTREAM_TYPES]
    reach.sort(key=lambda x: (DOWNSTREAM_TYPES.index(x.type), x.depth, x.label))
    counts = {t: sum(1 for r in reach if r.type == t) for t in DOWNSTREAM_TYPES}
    plural = {"library": "libraries", "series": "series"}
    parts = [f"{counts[t]} {t if counts[t] == 1 else plural.get(t, t + 's')}" for t in DOWNSTREAM_TYPES if counts[t]]
    statement = ("Within the analyses Data Doctor computes, this record feeds " + ", ".join(parts) + "."
                 if parts else "No analysis computed by Data Doctor consumes this record.")
    keep = {n.id for n in reach} | set(starts)
    return ImpactReport(finding_id=finding.id if finding else None, start=starts, reachable=reach, counts=counts,
                        edges=[e for e in edges if e[0] in keep and e[1] in keep], statement=statement)
