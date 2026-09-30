"""Loads every rule module (populating REGISTRY) and runs rules deterministically."""

from __future__ import annotations

import importlib

from datadoctor.domain.models import Dataset, Finding
from datadoctor.knowledge.loader import Knowledge
from datadoctor.rules.base import REGISTRY, Rule, RuleContext, rules_version

RULE_MODULES = (
    "datadoctor.rules.structural",
    "datadoctor.rules.statistical",
    "datadoctor.rules.domain",
    "datadoctor.rules.crossrecord",
)


def load_rules() -> dict[str, Rule]:
    for m in RULE_MODULES:
        importlib.import_module(m)
    return REGISTRY


def _sort_key(f: Finding) -> tuple[int, str, str]:
    return (-f.severity.rank, f.rule_id, f.resource.key)


def run_rule(rule_id: str, ds: Dataset, kn: Knowledge) -> list[Finding]:
    rules = load_rules()
    ctx = RuleContext(ds=ds, kn=kn, rules_version=rules_version())
    return sorted(rules[rule_id].evaluate(ctx), key=_sort_key)


def run_all(ds: Dataset, kn: Knowledge, *, only: set[str] | None = None) -> list[Finding]:
    rules = load_rules()
    ctx = RuleContext(ds=ds, kn=kn, rules_version=rules_version())
    out: dict[str, Finding] = {}
    for rid in sorted(rules):
        if only and rid not in only:
            continue
        for f in rules[rid].evaluate(ctx):
            out[f.id] = f  # ids are deterministic; duplicates collapse
    return sorted(out.values(), key=_sort_key)
