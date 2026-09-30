"""'What this data can / cannot support': one row per published data set x indicator (Library profile)."""

from __future__ import annotations

from collections import defaultdict

from pydantic import BaseModel

from datadoctor.audit.service import blocking_keys
from datadoctor.domain.enums import Scope
from datadoctor.domain.models import Dataset, Finding
from datadoctor.knowledge.loader import Knowledge


class SupportRow(BaseModel):
    library_id: str
    library_title: str
    indicator_key: str
    indicator_label: str
    medium: str
    observations: int
    years: list[int]
    blocked: int
    warned: int
    status: str  # USABLE | USABLE_WITH_CAVEATS | PARTLY_USABLE | NOT_USABLE
    can_support: list[str]
    cannot_support: list[str]
    rules: list[str]


def support_table(ds: Dataset, kn: Knowledge, findings: list[Finding]) -> list[SupportRow]:
    blocked = blocking_keys(findings)
    touched: dict[str, set[str]] = defaultdict(set)
    for f in findings:
        for k in {f.resource.key} | {r.key for r in f.related_resources}:
            touched[k].add(f.rule_id)
    rows: list[SupportRow] = []
    for lib in sorted(ds.libraries.values(), key=lambda x: x.id):
        if lib.scope is not Scope.OAH_IG or lib.id.endswith("-All") or lib.id.endswith("FullResults"):
            continue  # consolidated collections duplicate their parts; report the site-level collections
        groups: dict[str, list[str]] = defaultdict(list)
        for m in lib.member_refs:
            o = ds.observations.get(m.split("/")[-1])
            if o and o.indicator_key:
                groups[o.indicator_key].append(o.key)
        for ind, keys in sorted(groups.items()):
            d = kn.indicators[ind]
            n = len(keys)
            nb = sum(1 for k in keys if k in blocked)
            nw = sum(1 for k in keys if k not in blocked and touched.get(k))
            years = sorted({o.year for k in keys if (o := ds.observations[k.split('/')[-1]]).year})
            can, cannot = [], []
            if nb == n:
                status = "NOT_USABLE"
                cannot += ["any quantitative statement (every record fails integrity checks)"]
            elif nb:
                status = "PARTLY_USABLE"
                can.append(f"statements restricted to the {n - nb} record(s) without integrity findings")
                cannot.append(f"trends or summaries spanning the {nb} flagged record(s)")
            elif nw:
                status = "USABLE_WITH_CAVEATS"
                can.append("descriptive statements, with the listed caveats stated")
            else:
                status = "USABLE"
                can.append("descriptive statements for the published period(s)")
            if status in ("USABLE", "USABLE_WITH_CAVEATS"):
                if len(years) >= 3:
                    can.append(f"trend testing ({len(years)} annual points)")
                else:
                    cannot.append(f"trend claims (only {len(years)} year(s) published)")
            if d.kind == "prevalence":
                cannot.append("significance testing between cohorts (cohort sizes are not published)")
            cannot.append("causal claims")
            rules = sorted({r for k in keys for r in touched.get(k, set())})
            rows.append(SupportRow(library_id=lib.id, library_title=lib.title or lib.id, indicator_key=ind, indicator_label=d.label,
                                   medium=d.medium.value, observations=n, years=years, blocked=nb, warned=nw, status=status,
                                   can_support=can, cannot_support=cannot, rules=rules))
    return rows
