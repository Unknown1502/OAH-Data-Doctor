"""Cross-record rules: consistency between records that must agree with one another.

Each record can look fine on its own; these rules check facts that link records together
(time series, cohort partitions, complementary shares, physical subset relations).
"""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Iterator

from datadoctor.domain.enums import Category, Severity
from datadoctor.domain.models import (
    Cohort,
    Evidence,
    Finding,
    NormalizedObservation,
    ObservedValue,
    StatComponent,
)
from datadoctor.rules.base import (
    RuleContext,
    RuleSpec,
    fmt,
    obs_ref,
    record_decimals,
    rule,
    stat_tol,
    tolerance,
)


def canonical(ctx: RuleContext, obs: NormalizedObservation, s: StatComponent | None, record_dec: int) -> tuple[float, float] | None:
    """(value, rounding tolerance) of a statistic in its indicator's canonical unit, via the explicit conversion table.

    Returns None when the statistic is missing or its unit cannot be converted: cross-record rules never compare
    raw numbers published in different units (regression found by the fault-injection evaluation).
    """
    if s is None or s.quantity.value is None or not obs.indicator_key:
        return None
    ind = ctx.kn.indicators.get(obs.indicator_key)
    unit = s.quantity.code
    if ind is None or unit is None:
        return None
    conv = ctx.kn.convert(s.quantity.value, unit, ind.canonical_unit)
    if conv is None:
        return None
    return conv[0], stat_tol(s, record_dec) * abs(conv[1].get("factor", 1))

SPEC_TEMP = RuleSpec(
    id="SEM-TEMP-001", version="1.1", title="Scale break within a time series",
    category=Category.SEMANTIC, severity="ERROR",
    confidence="0.8 — the other years agree within 10x while this one is >= 100x away",
    applies_to="Annual summary statistics for the same site and indicator with >= 3 years",
    constraint="within a series whose other points agree within 10x, no point is >= 100x from their median",
    rationale="Environmental levels do not jump by orders of magnitude for one year and return; a scale/unit slip is far likelier.",
)


@rule(SPEC_TEMP)
def series_scale_break(ctx: RuleContext) -> Iterator[Finding]:
    series: dict[tuple[str, str], list[NormalizedObservation]] = defaultdict(list)
    for o in ctx.observations(only_stats=True):
        if o.indicator_key and o.effective_period and o.effective_period.is_annual:
            series[(o.subject_ref or "", o.indicator_key)].append(o)
    for (_subj, _ind), obs_list in sorted(series.items()):
        if len(obs_list) < 3:
            continue
        flagged: dict[str, list[tuple[str, float, float]]] = defaultdict(list)
        for stat in ("average", "median", "minimum", "maximum"):
            vals = [(o, cv[0]) for o in obs_list
                    if (cv := canonical(ctx, o, o.stat(stat), record_decimals(o))) is not None and cv[0] > 0]
            if len(vals) < 3:
                continue
            for i, (o, v) in enumerate(vals):
                others = [math.log10(x) for j, (_, x) in enumerate(vals) if j != i]
                others.sort()
                if others[-1] - others[0] > 1:
                    continue  # the rest of the series does not agree within 10x: no stable reference
                mid = len(others) // 2
                centre = others[mid] if len(others) % 2 else (others[mid - 1] + others[mid]) / 2
                if abs(math.log10(v) - centre) >= 2:
                    flagged[o.id].append((stat, v, 10 ** centre))
        for oid, items in sorted(flagged.items()):
            o = ctx.ds.observations[oid]
            first = o.stat(items[0][0])
            siblings = sorted((x for x in obs_list if x.id != oid), key=lambda x: x.year or 0)
            yield ctx.make(
                SPEC_TEMP,
                resource=obs_ref(o, first.fhir_path if first else None, ctx.display(o)),
                related=[obs_ref(x) for x in siblings],
                severity=Severity.ERROR, confidence=0.8,
                summary=(f"{ctx.display(o)}: the {items[0][0]} ({fmt(items[0][1])}) is about "
                         f"{fmt(round(max(items[0][1], items[0][2]) / min(items[0][1], items[0][2])))}x away from the same "
                         f"statistic in the other {len(siblings)} years (~{fmt(round(items[0][2], 6))})."),
                evidence=Evidence(
                    observed=[ObservedValue(label=f"{s} {o.year}", value=v) for s, v, _ in items]
                    + [ObservedValue(label=f"{items[0][0]} {x.year}", value=(st.quantity.value if (st := x.stat(items[0][0])) else None))
                       for x in siblings],
                    constraint="a series point lies within 100x of the other points' median",
                    expected="Year-to-year values of one statistic at one site stay on one scale.",
                    measures={"statistics": [s for s, _, _ in items], "series_length": len(obs_list)},
                ),
                interpretation="Likely scale inconsistency in one year of the series (root cause unknown).",
            )


def _interval(c: Cohort) -> tuple[float, float]:
    return c.age_interval()


def _tiles(parts: list[Cohort], whole: tuple[float, float]) -> bool:
    ivs = sorted(_interval(p) for p in parts)
    if not ivs or ivs[0][0] != whole[0] or ivs[-1][1] != whole[1]:
        return False
    return all(nxt[0] in (prev[1], prev[1] + 1) for prev, nxt in zip(ivs, ivs[1:], strict=False))


SPEC_C1 = RuleSpec(
    id="SEM-COHORT-001", version="1.0", title="Pooled value outside the range of its subgroups",
    category=Category.SEMANTIC, severity="ERROR",
    confidence="0.9 — any pooled proportion is a weighted average of the proportions of a partition",
    applies_to="Prevalence observations with the same site, indicator and period whose cohorts form a partition "
               "(male + female of the same ages, or age bands exactly tiling the pooled age range)",
    constraint="min(subgroups) <= pooled <= max(subgroups) (within published precision)",
    rationale="A weighted average of numbers cannot lie outside them, whatever the (unpublished) group sizes.",
)


@rule(SPEC_C1)
def pooled_within_partition(ctx: RuleContext) -> Iterator[Finding]:
    buckets: dict[tuple[str, str, int | None], list[tuple[Cohort, NormalizedObservation]]] = defaultdict(list)
    for o in ctx.observations():
        if o.value is None or o.value.value is None or not o.focus_refs or o.indicator_key is None:
            continue
        g = ctx.ds.groups.get(o.focus_refs[0].split("/")[-1])
        if g:
            buckets[(o.subject_ref or "", o.indicator_key, o.year)].append((g, o))
    for _key, members in sorted(buckets.items()):
        for pooled_g, pooled in members:
            if pooled_g.sex is not None:
                continue
            whole = _interval(pooled_g)
            partitions = []
            sexes = [(g, o) for g, o in members if g.sex in ("male", "female") and _interval(g) == whole]
            if {g.sex for g, _ in sexes} == {"male", "female"}:
                partitions.append(("sex", sexes))
            bands = [(g, o) for g, o in members if g.sex is None and g.group_id != pooled_g.group_id]
            if len(bands) >= 2 and _tiles([g for g, _ in bands], whole):
                partitions.append(("age", bands))
            for kind, part in partitions:
                vals = [(o.value.value, tolerance(o.value.value, o.value.decimals), o) for _, o in part if o.value and o.value.value is not None]
                if len(vals) < 2 or pooled.value is None or pooled.value.value is None:
                    continue
                pv, pt = pooled.value.value, tolerance(pooled.value.value, pooled.value.decimals)
                lo = min(vals, key=lambda x: x[0])
                hi = max(vals, key=lambda x: x[0])
                if lo[0] - pv > pt + lo[1] or pv - hi[0] > pt + hi[1]:
                    yield ctx.make(
                        SPEC_C1,
                        resource=obs_ref(pooled, "Observation.valueQuantity", ctx.display(pooled)),
                        related=[obs_ref(o) for _, _, o in vals], discriminator=kind,
                        severity=Severity.ERROR, confidence=0.9,
                        summary=(f"{ctx.display(pooled)}: pooled value {fmt(pv)}% lies outside its {kind} subgroups "
                                 f"({fmt(lo[0])}%–{fmt(hi[0])}%). A pooled share must lie between its subgroups."),
                        evidence=Evidence(
                            observed=[ObservedValue(label=f"pooled ({pooled_g.label})", value=pv, unit="%")]
                            + [ObservedValue(label=ctx.ds.groups[o.focus_refs[0].split('/')[-1]].label, value=v, unit="%")
                               for v, _, o in vals],
                            constraint="min(subgroups) <= pooled <= max(subgroups)",
                            expected="A population share is a weighted average of the shares of its subgroups.",
                            measures={"partition": kind, "subgroups": len(vals)},
                        ),
                        interpretation="Cohort values are mutually inconsistent (root cause unknown).",
                    )


SPEC_C2 = RuleSpec(
    id="SEM-COHORT-002", version="1.0", title="Complementary shares do not add up to 100 %",
    category=Category.SEMANTIC, severity="ERROR",
    confidence="0.9 — complements are exhaustive and exclusive by definition (knowledge/indicators/registry.yaml)",
    applies_to="Complement sets (e.g. long-term disease / no long-term disease; the four BMI bands) observed for the same site, cohort and period",
    constraint="|sum - 100| <= sum of rounding half-units",
    rationale="Mutually exclusive, exhaustive categories partition a population.",
)


@rule(SPEC_C2)
def complements_sum(ctx: RuleContext) -> Iterator[Finding]:
    idx: dict[tuple[str, str, tuple[str, ...], int | None], NormalizedObservation] = {}
    for o in ctx.observations():
        if o.indicator_key and o.value is not None and o.value.value is not None:
            idx[(o.indicator_key, o.subject_ref or "", tuple(o.focus_refs), o.year)] = o
    contexts = sorted({k[1:] for k in idx})
    for cset in ctx.kn.complements:
        for subj, focus, year in contexts:
            obs = [idx.get((m, subj, focus, year)) for m in cset["members"]]
            if any(o is None for o in obs):
                continue
            present = [o for o in obs if o is not None and o.value is not None and o.value.value is not None]
            total = sum(o.value.value for o in present if o.value and o.value.value is not None)
            slack = sum(tolerance(o.value.value, o.value.decimals) for o in present if o.value)
            if abs(total - 100) <= slack + 1e-9:
                continue
            first = present[0]
            yield ctx.make(
                SPEC_C2,
                resource=obs_ref(first, "Observation.valueQuantity", ctx.display(first)),
                related=[obs_ref(o) for o in present[1:]], discriminator=cset["id"],
                severity=Severity.ERROR, confidence=0.9,
                summary=(f"{ctx.display(first)}: the {len(present)} complementary shares ({cset['id']}) add up to "
                         f"{fmt(round(total, 6))}%, not 100%."),
                evidence=Evidence(
                    observed=[ObservedValue(label=o.indicator_key or o.id, value=o.value.value if o.value else None, unit="%") for o in present],
                    constraint="sum of complementary shares = 100 %",
                    expected="Exhaustive, mutually exclusive categories cover the whole population.",
                    measures={"sum": total, "slack": slack, "set": cset["id"]},
                ),
                interpretation="Complementary indicators are mutually inconsistent (root cause unknown).",
            )


SPEC_X = RuleSpec(
    id="SEM-XREC-001", version="1.1", title="Sub-fraction exceeds its super-fraction (PM2.5 > PM10)",
    category=Category.SEMANTIC,
    severity="ERROR when any statistic exceeds by > 10 % (relative); WARNING otherwise",
    confidence="0.7 — impossible for co-located measurements on the same days; different data coverage could explain it",
    applies_to="Annual summaries of a subset/superset pair (knowledge: PM2.5 within PM10) at the same site and year",
    constraint="for each published statistic: stat(PM2.5) <= stat(PM10)",
    rationale="If PM2.5_d <= PM10_d every day, every order statistic and the mean preserve the inequality.",
)


@rule(SPEC_X)
def subset_exceeds_superset(ctx: RuleContext) -> Iterator[Finding]:
    by_key: dict[tuple[str, str, int | None], NormalizedObservation] = {}
    for o in ctx.observations(only_stats=True):
        if o.indicator_key and o.effective_period and o.effective_period.is_annual:
            by_key[(o.indicator_key, o.subject_ref or "", o.year)] = o
    for rel in ctx.kn.subsets:
        for (ind, subj, year), sub in sorted(by_key.items()):
            if ind != rel["sub"]:
                continue
            sup = by_key.get((rel["super"], subj, year))
            if sup is None:
                continue
            rs, rp = record_decimals(sub), record_decimals(sup)
            viol = []
            for stat in ("average", "median", "maximum", "minimum"):
                ca, cb = canonical(ctx, sub, sub.stat(stat), rs), canonical(ctx, sup, sup.stat(stat), rp)
                if ca is None or cb is None:
                    continue  # missing, or no explicit unit conversion: never compare raw numbers across units
                if ca[0] - cb[0] > ca[1] + cb[1]:
                    viol.append((stat, ca[0], cb[0]))
            if not viol:
                continue
            worst = max((va - vb) / vb if vb > 0 else math.inf for _, va, vb in viol)
            yield ctx.make(
                SPEC_X,
                resource=obs_ref(sub, None, ctx.display(sub)), related=[obs_ref(sup)],
                severity=Severity.ERROR if worst > 0.10 else Severity.WARNING, confidence=0.7,
                summary=(f"{ctx.display(sub)}: PM2.5 exceeds PM10 at the same site and year for "
                         f"{', '.join(s for s, _, _ in viol)} (e.g. {viol[0][0]} {fmt(viol[0][1])} vs {fmt(viol[0][2])} ug/m3). "
                         "PM2.5 is a subset of PM10."),
                evidence=Evidence(
                    observed=[ObservedValue(label=f"{s}: PM2.5 vs PM10", value=f"{fmt(va)} vs {fmt(vb)}", unit="ug/m3") for s, va, vb in viol],
                    constraint="statistic(PM2.5) <= statistic(PM10)",
                    expected=rel["rationale"],
                    measures={"violating_statistics": [s for s, _, _ in viol],
                              "max_relative_excess": round(worst, 4) if math.isfinite(worst) else None},
                ),
                interpretation="Physically inconsistent pair unless the two series cover different days (root cause unknown).",
                hypotheses=["The PM2.5 and PM10 annual summaries may be computed over different sets of valid days "
                            "(hypothesis — data coverage is not published)."],
            )
