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
    libs = [lib for lib in ds.libraries.values() if lib.scope is Scope.OAH_IG]
    by_lib: dict[str, dict[str, list[str]]] = {}
    for lib in libs:
        groups: dict[str, list[str]] = defaultdict(list)
        for m in lib.member_refs:
            o = ds.observations.get(m.split("/")[-1])
            if o and o.indicator_key:
                groups[o.indicator_key].append(o.key)
        by_lib[lib.id] = groups
    size = {lib.id: len(lib.member_refs) for lib in libs}

    def duplicated(lib_id: str, ind: str, keys: list[str]) -> bool:
        """A consolidated collection's row is redundant only if smaller collections already contain all its records."""
        smaller = set().union(*[set(by_lib[o].get(ind, [])) for o in by_lib if o != lib_id and size[o] < size[lib_id]])
        return set(keys) <= smaller

    for lib in sorted(libs, key=lambda x: x.id):
        for ind, keys in sorted(by_lib[lib.id].items()):
            if duplicated(lib.id, ind, keys):
                continue
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
