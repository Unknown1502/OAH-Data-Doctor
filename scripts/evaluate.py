"""Fault-injection evaluation (docs/06_TEST_PLAN.md §Evaluation) -> docs/EVALUATION.md.

Method
1. Load the committed snapshot and audit it.
2. Pick CONTROL records: official observations/locations/libraries that currently have zero findings.
3. Faults: for each fault type, copy the dataset, inject ONE fault into ONE control record, re-run every rule,
   and record whether the rule(s) designed for that fault fire on that record. Sensitivity = detected / injected.
4. Benign transformations: apply realistic changes that keep the data scientifically valid (unit conversion,
   rounding, re-ordering, proportional jitter, dropping an optional statistic) and count NEW findings on the
   transformed record. Every new finding is a false positive.

Caveat (printed in the report): injected faults measure rule SENSITIVITY on known patterns. They do not measure
real-world accuracy, which depends on which faults actually occur in data, and on human review (Gate 0).
"""

from __future__ import annotations

import asyncio
import copy
import datetime as dt
import math
import random
import sys
import time
from collections import defaultdict
from collections.abc import Callable
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from datadoctor.audit.service import run_audit  # noqa: E402
from datadoctor.config import Settings  # noqa: E402
from datadoctor.domain.enums import Scope  # noqa: E402
from datadoctor.knowledge.loader import load_knowledge  # noqa: E402
from datadoctor.normalization.normalizer import build_dataset  # noqa: E402
from datadoctor.rules.registry import run_all  # noqa: E402

STATS = "http://terminology.hl7.org/CodeSystem/observation-statistics"
SEED = 20260930
PER_FAULT = 20
Raw = dict[str, dict[str, dict[str, Any]]]


def stat_comp(res: dict[str, Any], name: str) -> dict[str, Any] | None:
    for c in res.get("component", []):
        if any(cc.get("system") == STATS and cc.get("code") == name for cc in c["code"].get("coding", [])):
            return c.get("valueQuantity")
    return None


def main() -> None:
    kn = load_knowledge(ROOT / "knowledge")
    snaps = sorted(p.name for p in (ROOT / "data" / "snapshots").iterdir() if (p / "manifest.json").exists())
    res, ds = asyncio.run(run_audit(Settings(), "snapshot", snaps[-1]))
    # Records touched by a record-level finding. Terminology-level findings (SEM-DEF-001 / SEM-CODE-001 on the
    # CodeSystem) list every observation using a code; they say nothing about the record's values, so they do not
    # disqualify a record as a control.
    record_level = [f for f in res.findings if f.resource.resource_type != "CodeSystem"]
    touched = {f.resource.key for f in record_level} | {r.key for f in record_level for r in f.related_resources}
    base_raw: Raw = ds.raw
    rng = random.Random(SEED)

    obs = {k: v for k, v in ds.observations.items() if v.scope is Scope.OAH_IG and v.key not in touched}
    full_stats = [o.id for o in obs.values() if all(o.stat(s) for s in ("average", "median", "minimum", "maximum", "std-dev"))
                  and all((o.stat(s).quantity.value or 0) > 0 for s in ("average", "median", "maximum"))]
    with_value = [o.id for o in obs.values() if o.value is not None and o.value.value is not None]
    temps = [o.id for o in obs.values() if o.indicator_key == "water-temperature" and o.value is not None]
    prev = [o.id for o in obs.values() if o.indicator_key and kn.indicators[o.indicator_key].kind == "prevalence"]
    groups = ds.groups

    def audit(raw: Raw) -> list[Any]:
        return run_all(build_dataset(raw, ds.source, kn), kn)

    def fired_on(findings: list[Any], key: str) -> set[str]:
        return {f.rule_id for f in findings if f.resource.resource_type != "CodeSystem"
                and (f.resource.key == key or key in {r.key for r in f.related_resources})}

    # ---- fault definitions: (name, expected rules, candidates, mutate(raw, id) -> key checked) ----------------
    def scale(stat: str, k: int) -> Callable[[Raw, str], str]:
        def m(raw: Raw, oid: str) -> str:
            q = stat_comp(raw["Observation"][oid], stat)
            assert q is not None
            q["value"] = q["value"] * 10**k
            return f"Observation/{oid}"
        return m

    def swap_minmax(raw: Raw, oid: str) -> str:
        r = raw["Observation"][oid]
        lo, hi = stat_comp(r, "minimum"), stat_comp(r, "maximum")
        assert lo and hi
        lo["value"], hi["value"] = hi["value"] + 1, lo["value"]
        return f"Observation/{oid}"

    def median_above(raw: Raw, oid: str) -> str:
        r = raw["Observation"][oid]
        q, hi = stat_comp(r, "median"), stat_comp(r, "maximum")
        assert q and hi
        q["value"] = round(hi["value"] * 1.5 + 1, 2)
        return f"Observation/{oid}"

    def inflate_sd(raw: Raw, oid: str) -> str:
        r = raw["Observation"][oid]
        sd, lo, hi = stat_comp(r, "std-dev"), stat_comp(r, "minimum"), stat_comp(r, "maximum")
        assert sd and lo and hi
        sd["value"] = round((hi["value"] - lo["value"]) * 1.2 + 1, 2)
        return f"Observation/{oid}"

    def boil(raw: Raw, oid: str) -> str:
        raw["Observation"][oid]["valueQuantity"]["value"] = 150.0
        return f"Observation/{oid}"

    def over_100(raw: Raw, oid: str) -> str:
        raw["Observation"][oid]["valueQuantity"]["value"] = 120.0
        return f"Observation/{oid}"

    def drop_unit(raw: Raw, oid: str) -> str:
        r = raw["Observation"][oid]
        q = r.get("valueQuantity") or next(c["valueQuantity"] for c in r["component"] if "valueQuantity" in c)
        q.pop("code", None)
        return f"Observation/{oid}"

    def dangle(raw: Raw, oid: str) -> str:
        raw["Observation"][oid]["subject"] = {"reference": "Location/Loc-does-not-exist"}
        return f"Observation/{oid}"

    # pooled-outside candidates: Oslo 'All' records whose Male/Female partners exist
    pooled: list[tuple[str, str, str]] = []
    for o in obs.values():
        if o.focus_refs and o.focus_refs[0] == "Group/Group-OS-All":
            m = next((x for x in ds.observations.values() if x.indicator_key == o.indicator_key and x.focus_refs == ["Group/Group-OS-Male"]), None)
            f = next((x for x in ds.observations.values() if x.indicator_key == o.indicator_key and x.focus_refs == ["Group/Group-OS-Female"]), None)
            if m and f:
                pooled.append((o.id, m.id, f.id))

    def pooled_out(raw: Raw, oid: str) -> str:
        _, mid, fid = next(p for p in pooled if p[0] == oid)
        hi = max(raw["Observation"][mid]["valueQuantity"]["value"], raw["Observation"][fid]["valueQuantity"]["value"])
        raw["Observation"][oid]["valueQuantity"]["value"] = hi + 5
        return f"Observation/{oid}"

    comps = [o.id for o in obs.values() if o.indicator_key in ("no-long-term-disease", "no-diabetes-copd-cvd") and o.focus_refs]

    def complement(raw: Raw, oid: str) -> str:
        raw["Observation"][oid]["valueQuantity"]["value"] += 10
        return f"Observation/{oid}"

    pm_pairs = []
    for o in ds.observations.values():
        if o.indicator_key == "pm2-5" and o.key not in touched:
            sup = next((x for x in ds.observations.values() if x.indicator_key == "pm10" and x.subject_ref == o.subject_ref and x.year == o.year), None)
            if sup and sup.key not in touched:
                pm_pairs.append(o.id)

    def pm25_up(raw: Raw, oid: str) -> str:
        o = ds.observations[oid]
        sup = next(x for x in ds.observations.values() if x.indicator_key == "pm10" and x.subject_ref == o.subject_ref and x.year == o.year)
        for st in ("average", "median", "maximum"):
            q, qs = stat_comp(raw["Observation"][oid], st), stat_comp(base_raw["Observation"][sup.id], st)
            if q and qs:
                q["value"] = round(qs["value"] * 1.3 + 0.5, 2)
        return f"Observation/{oid}"

    clean_locs = [lid for lid, loc in ds.locations.items() if loc.scope is Scope.OAH_IG and loc.latitude is not None and f"Location/{lid}" not in touched]

    def same_coords(raw: Raw, lid: str) -> str:
        other = next(x for x in clean_locs if x != lid and raw["Location"][x].get("partOf", {}).get("reference") != f"Location/{lid}"
                     and raw["Location"][lid].get("partOf", {}).get("reference") != f"Location/{x}")
        raw["Location"][lid]["position"] = copy.deepcopy(raw["Location"][other]["position"])
        return f"Location/{lid}"

    libs = [lid for lid, lib in ds.libraries.items() if lib.scope is Scope.OAH_IG and lib.member_refs]

    def lib_count(raw: Raw, lid: str) -> str:
        for e in raw["Library"][lid]["extension"]:
            if e["url"].endswith("library-numberOfRecords"):
                e["valueInteger"] += 1
        return f"Library/{lid}"

    faults: list[tuple[str, set[str], list[str], Callable[[Raw, str], str]]] = [
        ("Median scaled x100", {"SEM-STAT-001", "SEM-STAT-003", "SEM-SCALE-001"}, full_stats, scale("median", 2)),
        ("Median scaled x10,000", {"SEM-STAT-001", "SEM-SCALE-001"}, full_stats, scale("median", 4)),
        ("Mean scaled x1,000", {"SEM-STAT-002", "SEM-STAT-003", "SEM-SCALE-001"}, full_stats, scale("average", 3)),
        ("Minimum and maximum swapped", {"SEM-STAT-005"}, full_stats, swap_minmax),
        ("Median above maximum (x1.5)", {"SEM-STAT-001"}, full_stats, median_above),
        ("SD larger than the range allows", {"SEM-STAT-004"}, full_stats, inflate_sd),
        ("Water temperature 150 C", {"SEM-RANGE-001"}, temps, boil),
        ("Prevalence 120 %", {"SEM-RANGE-001"}, prev, over_100),
        ("UCUM unit code removed", {"STR-UNIT-001"}, with_value + full_stats, drop_unit),
        ("Subject reference dangling", {"STR-REF-001"}, with_value + full_stats, dangle),
        ("Pooled share above both subgroups", {"SEM-COHORT-001"}, [p[0] for p in pooled], pooled_out),
        ("Complementary shares +10 points", {"SEM-COHORT-002"}, comps, complement),
        ("PM2.5 set 30 % above PM10", {"SEM-XREC-001"}, pm_pairs, pm25_up),
        ("Two sites given identical coordinates", {"SEM-SPATIAL-001"}, clean_locs, same_coords),
        ("Library record count off by one", {"STR-LIB-001"}, libs, lib_count),
    ]

    t0 = time.time()
    fault_rows = []
    for name, expected, cands, mutate in faults:
        cands = sorted(set(cands))
        sample = rng.sample(cands, min(PER_FAULT, len(cands)))
        detected = 0
        fired_count: dict[str, int] = defaultdict(int)
        collateral = 0
        for cid in sample:
            raw = copy.deepcopy(base_raw)
            key = mutate(raw, cid)
            findings = audit(raw)
            fired = fired_on(findings, key)
            for r in fired:
                fired_count[r] += 1
            if fired & expected:
                detected += 1
            # collateral false positives: new findings on OTHER control records
            collateral += sum(1 for f in findings if f.resource.resource_type != "CodeSystem" and f.resource.key != key
                              and f.resource.key not in touched and key not in {r.key for r in f.related_resources})
        fault_rows.append((name, sorted(expected), len(cands), len(sample), detected, dict(fired_count), collateral))
        print(f"{name}: {detected}/{len(sample)}", flush=True)

    # ---- benign transformations ----------------------------------------------------------------------------
    def to_mg_m3(raw: Raw, oid: str) -> str:
        r = raw["Observation"][oid]
        for c in r["component"]:
            q = c.get("valueQuantity")
            if q and q.get("code") == "ug/m3":
                q["value"] = q["value"] / 1000
                q["code"] = q["unit"] = "mg/m3"
        return f"Observation/{oid}"

    def round_1dp(raw: Raw, oid: str) -> str:
        for c in raw["Observation"][oid].get("component", []):
            q = c.get("valueQuantity")
            if q and isinstance(q.get("value"), float):
                q["value"] = round(q["value"], 1)
        return f"Observation/{oid}"

    def reorder(raw: Raw, oid: str) -> str:
        raw["Observation"][oid]["component"].reverse()
        return f"Observation/{oid}"

    def jitter(raw: Raw, oid: str) -> str:
        f = 1 + rng.uniform(-0.05, 0.05)
        for c in raw["Observation"][oid].get("component", []):
            q = c.get("valueQuantity")
            if q and q.get("value") is not None:
                q["value"] = round(q["value"] * f, 4)
        return f"Observation/{oid}"

    def drop_sd(raw: Raw, oid: str) -> str:
        r = raw["Observation"][oid]
        r["component"] = [c for c in r["component"] if not any(cc.get("code") == "std-dev" for cc in c["code"].get("coding", []))]
        return f"Observation/{oid}"

    air = [i for i in full_stats if ds.observations[i].medium.value == "air"]
    benign = [("Unit converted ug/m3 -> mg/m3 (values /1000)", air, to_mg_m3), ("All statistics rounded to 1 decimal", full_stats, round_1dp),
              ("Components re-ordered", full_stats, reorder), ("All statistics scaled by the same +-5 %", full_stats, jitter),
              ("Optional std-dev removed", full_stats, drop_sd)]
    benign_rows = []
    for name, cands, mutate in benign:
        sample = rng.sample(sorted(set(cands)), min(PER_FAULT, len(set(cands))))
        new = 0
        rules: dict[str, int] = defaultdict(int)
        for cid in sample:
            raw = copy.deepcopy(base_raw)
            key = mutate(raw, cid)
            for r in fired_on(audit(raw), key):
                new += 1
                rules[r] += 1
        benign_rows.append((name, len(sample), new, dict(rules)))
        print(f"benign {name}: {new} new findings", flush=True)

    elapsed = time.time() - t0
    total_inj = sum(r[3] for r in fault_rows)
    total_det = sum(r[4] for r in fault_rows)
    total_benign = sum(r[1] for r in benign_rows)
    total_fp = sum(r[2] for r in benign_rows)
    collateral_total = sum(r[6] for r in fault_rows)

    def wilson(k: int, n: int) -> str:
        if n == 0:
            return "—"
        z = 1.96
        p = k / n
        d = 1 + z * z / n
        c = (p + z * z / (2 * n)) / d
        h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
        return f"{max(0, c - h) * 100:.1f}–{min(1, c + h) * 100:.1f} %"

    L = ["# Evaluation: fault injection", "",
         f"Generated by `python tasks.py evaluate` on {dt.datetime.now(dt.UTC).strftime('%Y-%m-%d %H:%M UTC')} from snapshot "
         f"`{res.source.snapshot_id}` (seed {SEED}, up to {PER_FAULT} records per fault type, {elapsed:.0f} s).", "",
         "> **Caveat.** Injected faults measure the *sensitivity of the rules to known fault patterns*. They do not measure "
         "real-world accuracy, which depends on which faults actually occur in published data and is assessed by human review "
         "of real findings (docs/GATE0_REPORT.md).", "",
         "## Headline", "",
         f"- Injected faults detected by the rule designed for them: **{total_det} of {total_inj}** "
         f"({total_det / total_inj * 100:.1f} %, 95 % CI {wilson(total_det, total_inj)}).",
         f"- Benign, scientifically valid transformations: **{total_fp} new findings on {total_benign} transformed records** "
         f"(false-positive rate {total_fp / total_benign * 100:.1f} %, 95 % CI {wilson(total_fp, total_benign)}).",
         f"- Collateral findings on untouched control records during fault runs: **{collateral_total}**.", "",
         "Control records are official OAH records with no finding in the unmodified snapshot "
         f"({len(obs)} observations, {len(clean_locs)} locations, {len(libs)} libraries).", "",
         "## Faults", "", "| Fault injected | Expected rule(s) | Candidates | Injected | Detected | Rate | Rules that fired |", "|---|---|---|---|---|---|---|"]
    for name, exp, nc, ns, det, fired, _ in fault_rows:
        L.append(f"| {name} | {', '.join(exp)} | {nc} | {ns} | {det} | {det / ns * 100:.0f} % | "
                 f"{', '.join(f'{k} ({v})' for k, v in sorted(fired.items()))} |" if ns else f"| {name} | {', '.join(exp)} | 0 | 0 | — | — | — |")
    L += ["", "## Benign transformations (must not raise findings)", "",
          "| Transformation | Records | New findings | Rules |", "|---|---|---|---|"]
    for name, n, new, rules in benign_rows:
        L.append(f"| {name} | {n} | {new} | {', '.join(f'{k} ({v})' for k, v in rules.items()) or '—'} |")
    L += ["", "## What this evaluation changed", "",
          "The first run (same seed) produced **4 false positives** under the benign unit conversion (ug/m3 -> mg/m3): "
          "SEM-XREC-001 compared PM2.5 and PM10 as raw numbers across units. Both cross-record rules now convert to the "
          "indicator's canonical unit with the explicit conversion table and never compare across units they cannot convert "
          "(SEM-XREC-001 and SEM-TEMP-001 v1.1, regression tests in `backend/tests/unit/test_rules_crossrecord.py`). "
          "Three fault types first had no control records because a terminology-level finding (SEM-DEF-001) lists every "
          "health record; controls are now selected on record-level findings only.", ""]
    L += ["", "## Not evaluated here", "",
          "- SEM-TEMP-001 (scale break in a time series): the snapshot has no clean multi-year series to inject into (every "
          "Almyros series already has findings; Benevento has two years). It is covered by unit tests.",
          "- SEM-DEF-001 and SEM-CODE-001 are knowledge-driven checks on the terminology, not on record values.",
          "- SEM-RANGE-002 (unusual values) is advisory by design.", "",
          "The property-based tests (`backend/tests/property`) complement this: 300 randomly generated real samples, summarised "
          "and rounded at 0 to 4 decimals, never trigger an identity rule.", ""]
    (ROOT / "docs" / "EVALUATION.md").write_text("\n".join(L), encoding="utf-8")
    print("\n".join(L[:14]))


if __name__ == "__main__":
    main()
