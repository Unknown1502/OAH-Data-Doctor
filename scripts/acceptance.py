"""Acceptance check against a RUNNING Data Doctor: every API endpoint, with expected outcomes.

    python scripts/acceptance.py [base_url]        (default http://127.0.0.1:8321)

Three kinds of checks:
- fixed facts about the published data (the anchor record, the verdicts of the catalog analyses and example claims,
  each reasoned from the values and the official limits; see docs/CLAIM_SAFETY_SPEC.md and docs/COMPARABILITY_SPEC.md);
- consistency: every count agrees across the overview, the findings list, the filters, the reports and the rendered docs;
- behaviour: errors are reported and never leak submitted secrets, nothing changes a verdict but the rules.

It only calls this Data Doctor's own API (which itself only reads the sandbox). Checking a claim saves it as a user
analysis, so, like the e2e tests, it clears user-added analyses before and after the run (POST /api/analyses/reset).
Exit status 0 when every check passes.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parents[1]
ANCHOR = "Obs-Almyros-TemperatureWater-2013"
ANCHOR_RULES = {"SEM-RANGE-001", "SEM-SCALE-001", "SEM-STAT-001", "SEM-STAT-003"}

# Expected verdicts, each reasoned from the published values (checked against the raw FHIR resources) and the
# official limits: WHO 2021 annual AQG PM2.5 5 ug/m3 and PM10 15 ug/m3; EU Directive 2008/50/EC annual PM10 40 ug/m3.
EXPECTED_COMPARISONS = {
    "cmp-field-temp-almyros-vs-giofyros": "DIRECT",  # same measure, method, unit and day
    "cmp-benevento-no2-site01-vs-site02-2019": "CONDITIONAL",
    "cmp-benevento-no2-2018-vs-2019": "CONDITIONAL",
    "cmp-obesity-benevento-vs-oslo-18-29": "NOT",  # different populations
    "cmp-obesity-benevento-vs-oslo-female": "CONDITIONAL",
    "cmp-almyros-temp-lab-2013-vs-2014": "BLOCKED_BY_INTEGRITY",  # the 2013 anchor record is broken
    "cmp-almyros-ec-lab-vs-field": "NOT",
}
EXPECTED_CLAIMS = {
    "clm-almyros-temperature-rising": "BLOCKED",  # every point of the series has integrity findings
    "clm-almyros-temperature-rising-median": "BLOCKED",
    "clm-benevento-no2-site01-higher": "UNSUPPORTED",  # 24.48 < 24.89
    "clm-benevento-pm25-exceeds-who": "CONDITIONAL",  # 21.59 > 5, but a warning touches the record
    "clm-benevento04-pm10-exceeds-who-2018": "SUPPORTED",  # 27.97 > 15
    "clm-giofyros-warmer-than-almyros": "CONDITIONAL",  # 18.6 > 16.1, no uncertainty published
    "clm-benevento-pm10-exceeds-eu": "UNSUPPORTED",  # 20.26 < 40
    "clm-obesity-benevento-higher-than-oslo": "UNSUPPORTED",  # age bands do not overlap
    "clm-pm25-associated-with-cvd": "UNSUPPORTED",  # 3 paired sites, ecological design
    "clm-pm25-causes-cvd": "UNSUPPORTED",  # aggregates cannot establish causation
}
# The example claims offered in the UI, typed as free text.
EXPECTED_TYPED = {
    "Water temperature at Almyros increased from 2013 to 2020": {"BLOCKED"},
    "NO2 was higher at Benevento site 01 than site 02 in 2019": {"UNSUPPORTED"},
    "PM10 at Benevento site 04 exceeded the WHO guideline in 2018": {"SUPPORTED"},
    "Obesity is higher in Benevento than in Oslo": {"CONDITIONAL", "UNSUPPORTED"},  # never SUPPORTED: cohorts differ
    "PM2.5 causes cardiovascular disease in Benevento": {"UNSUPPORTED"},
}
REPORTS = {"findings.json": "json", "operation-outcome.json": "fhir+json", "report.md": "markdown", "report.html": "html",
           "support.json": "json"}

results: list[tuple[bool, str, str]] = []


def check(ok: bool, name: str, detail: Any = "") -> bool:
    results.append((bool(ok), name, str(detail)[:220]))
    return bool(ok)


def main(base: str) -> int:
    c = httpx.Client(base_url=base, timeout=180)
    get = lambda p: c.get(p)  # noqa: E731
    post = lambda p, b: c.post(p, json=b)  # noqa: E731
    print("Clearing user-added analyses so the checks see the catalog state (as the e2e tests do).")
    c.post("/api/analyses/reset")
    try:
        return _checks(get, post, base)
    finally:
        c.post("/api/analyses/reset")


def _checks(get: Any, post: Any, base: str) -> int:
    # --- status ------------------------------------------------------------------------------------------------------
    check(get("/api/health").json().get("status") == "ok", "health")
    st = get("/api/status").json()
    check(st["has_run"] and st["source"]["kind"] in ("live", "snapshot"), "a run is loaded and labelled live/snapshot",
          f"{st['source']['kind']} {st['source'].get('fetched_at')} fallback={st['source'].get('fallback_reason')}")
    rules = get("/api/rules").json()
    check(st["rule_count"] == len(rules), "rule count in status equals the rule registry", f"{st['rule_count']} vs {len(rules)}")

    # --- counts agree everywhere --------------------------------------------------------------------------------------
    ov = get("/api/overview").json()
    sm = ov["summary"]
    total = sm["findings_total"]
    check(total == sum(sm["findings_by_severity"].values()) == sum(sm["findings_by_rule"].values()),
          "findings total = sum by severity = sum by rule", total)
    items = get("/api/findings?limit=2000").json()["items"]
    check(len(items) == total, "findings list length = total", f"{len(items)} vs {total}")
    for sev, n in sm["findings_by_severity"].items():
        got = len(get(f"/api/findings?severity={sev}&limit=2000").json()["items"])
        check(got == n, f"filter severity={sev}", f"{got} vs {n}")
    for rid, n in sm["findings_by_rule"].items():
        got = len(get(f"/api/findings?rule={rid}&limit=2000").json()["items"])
        check(got == n, f"filter rule={rid}", f"{got} vs {n}")
    check(all(f["scope"] == "oah-ig" for f in items), "only official (IG) records are flagged, never third-party uploads")
    check(len({f["id"] for f in items}) == total, "finding ids are unique")

    # --- the anchor record -------------------------------------------------------------------------------------------
    check(ov["hero_finding"]["resource"]["resource_id"] == ANCHOR, "hero finding is the anchor record", ov["hero_finding"]["id"])
    res = get(f"/api/resources/Observation/{ANCHOR}").json()["resource"]
    comps = {x["code"]["coding"][0]["code"]: x["valueQuantity"]["value"] for x in res["component"] if "valueQuantity" in x}
    check(comps.get("average") == 198000 and comps.get("median") == 19.8, "anchor published values (198000 vs 19.8)", comps)
    anchor_f = [f for f in items if f["resource"]["resource_id"] == ANCHOR]
    check({f["rule_id"] for f in anchor_f} == ANCHOR_RULES, "anchor flagged by the expected rules", sorted(f["rule_id"] for f in anchor_f))
    hero = get(f"/api/findings/{ov['hero_finding']['id']}").json()
    sv = hero["server_validation"] or {}
    sv_issues = sv.get("issue", [])
    check(sv.get("resourceType") == "OperationOutcome" and sv_issues
          and not [i for i in sv_issues if i.get("severity") in ("error", "fatal")],
          "server $validate had no errors on the anchor (the gap Data Doctor fills)", [i.get("diagnostics") for i in sv_issues][:2])
    check(hero["finding"]["lineage"] and ".csv" in hero["finding"]["lineage"]["statement"], "anchor lineage traced to the IG source CSV",
          (hero["finding"]["lineage"] or {}).get("statement", "")[:120])
    check("root cause unknown" in hero["finding"]["interpretation"].lower(), "root cause is not guessed", hero["finding"]["interpretation"])
    trace = get(f"/api/trace/resource/Observation/{ANCHOR}").json()
    check(trace["statement"].startswith("Within the analyses"), "impact trace for the anchor", trace["statement"])

    # --- every finding opens, with evidence ---------------------------------------------------------------------------
    bad = []
    for f in items:
        r = get(f"/api/findings/{f['id']}")
        d = r.json() if r.status_code == 200 else {}
        fd = d.get("finding", {})
        if r.status_code != 200 or not fd.get("evidence") or not d.get("rule") or not d.get("explanation", {}).get("text") \
                or not 0 <= fd.get("confidence", -1) <= 1:
            bad.append(f["id"])
    check(not bad, f"all {total} finding pages open with evidence, rule, explanation, confidence", bad[:5])

    # --- analyses: expected verdicts -------------------------------------------------------------------------------------
    an = get("/api/analyses").json()
    cmp_v = {x["id"]: x["verdict"] for x in an["comparisons"]}
    for cid, want in EXPECTED_COMPARISONS.items():
        check(cmp_v.get(cid) == want, f"comparison {cid}", f"{cmp_v.get(cid)} (expected {want})")
    clm = {x["id"]: x for x in an["claims"]}
    for cid, want in EXPECTED_CLAIMS.items():
        got = clm.get(cid, {}).get("verdict")
        check(got == want, f"claim {cid}", f"{got} (expected {want}); {(clm.get(cid, {}).get('reasons') or [''])[0][:100]}")
    check(all(x["reasons"] for x in an["claims"]), "every claim verdict gives reasons")
    check(all(x["blocking_findings"] for x in an["claims"] if x["verdict"] == "BLOCKED"), "every BLOCKED claim names its blocking findings")
    check(not any(x["claim"]["type"] == "CAUSAL" and x["verdict"] == "SUPPORTED" for x in an["claims"]), "no causal claim is ever SUPPORTED")

    # --- typed claims through the parser --------------------------------------------------------------------------------
    for text, want in EXPECTED_TYPED.items():
        p = post("/api/claims/parse", {"text": text}).json()
        if not check(p["claim"] is not None, f"typed claim understood: {text}", p.get("problems")):
            continue
        v = post("/api/claims", {"claim": p["claim"]}).json()
        check(v["verdict"] in want, f"typed claim verdict: {text}", f"{v['verdict']} (expected {sorted(want)}) read by {p['method']}")
    p = post("/api/claims/parse", {"text": "hello world"}).json()
    check(p["claim"] is None and p["problems"], "nonsense is not turned into a claim", p["problems"])

    # --- reports ---------------------------------------------------------------------------------------------------------------
    for name, ctype in REPORTS.items():
        r = get(f"/api/reports/{name}")
        check(r.status_code == 200 and ctype in r.headers.get("content-type", ""), f"report {name}", r.headers.get("content-type"))
    fj = get("/api/reports/findings.json").json()
    n = len(fj["findings"]) if isinstance(fj, dict) and "findings" in fj else len(fj)
    check(n == total, "findings.json has every finding", f"{n} vs {total}")
    oo = get("/api/reports/operation-outcome.json").json()
    issues = sum(len(e["resource"].get("issue", [])) for e in oo.get("entry", []))
    check(oo.get("resourceType") == "Bundle" and issues >= total, "OperationOutcome bundle carries every finding", f"{issues} issues")
    md = get("/api/reports/report.md").text
    check(f"{total:,}" in md or str(total) in md, "Markdown report states the same findings total", total)
    support = get("/api/support").json()
    check(any("Almyros" in json.dumps(r) for r in support) and any("Oslo" in json.dumps(r) for r in support),
          "support table covers Almyros lab chemistry and Oslo", len(support))

    # --- rendered docs match the data ------------------------------------------------------------------------------------
    numbers = json.loads((ROOT / "docs" / "numbers.json").read_text(encoding="utf-8"))
    if st["source"].get("manifest_sha256") or st["source"]["kind"] == "live":
        want_total = numbers.get("FINDINGS_TOTAL") or numbers.get("N_FINDINGS")
        if want_total is not None:
            check(str(want_total).replace(",", "") == str(total), "README/SUBMISSION findings total = this run", f"{want_total} vs {total}")
    check(numbers.get("ANCHOR_IMPACT") == trace["statement"], "README impact sentence = this run", numbers.get("ANCHOR_IMPACT"))

    # --- the published data, exactly as published ---------------------------------------------------------------------
    obs_items = get("/api/observations").json()["items"]
    anchor_item = next((o for o in obs_items if o["id"] == ANCHOR), None)
    check(anchor_item is not None and anchor_item["stats"] == comps, "data page: the anchor's values exactly as published",
          anchor_item["stats"] if anchor_item else None)
    locs = get("/api/locations").json()["items"]
    check(sum(x["observations"] for x in locs) == sum(1 for o in obs_items if o["location_id"]), "data page: place counts add up to the records")
    check(sum(1 for o in obs_items if o["blocking"]) == sum(x["with_problems"] for x in locs), "data page: records with problems add up")

    # --- what-if lab and checking your own data ------------------------------------------------------------------------
    lab = post("/api/lab/observation", {"observation_id": ANCHOR, "values": {}}).json()
    check({c["rule_id"] for c in lab["checks"] if c["fired"]} == ANCHOR_RULES and not lab["changed"],
          "lab: the published record reproduces its findings")
    idea = post("/api/lab/observation", {"observation_id": ANCHOR,
                                         "values": {"average": 19.8, "minimum": 18.5, "maximum": 21.1, "std-dev": 1.8385}}).json()
    fired_idea = {c["rule_id"] for c in idea["checks"] if c["fired"]}
    check(not fired_idea & ANCHOR_RULES and "SEM-TEMP-001" in fired_idea,
          "lab: the scale-error hypothesis clears the record but not its series", sorted(fired_idea))
    up = post("/api/check", {"content": json.dumps({"resourceType": "Bundle", "entry": [{"resource": res}]})}).json()
    check({f["rule_id"] for f in up["findings"]} == ANCHOR_RULES and up["resources"][0]["identical_to_published"],
          "check: an uploaded copy of the anchor gets the same findings")
    check(get(f"/api/resources/Observation/{ANCHOR}").json()["resource"] == res, "the lab and the check never change the published record")
    check(get("/api/overview").json()["summary"]["findings_total"] == total, "the lab and the check never change the audit")

    # --- errors ------------------------------------------------------------------------------------------------------------
    check(get("/api/findings/F-nope").status_code == 404, "unknown finding -> 404")
    check(post("/api/claims/parse", {"text": " "}).status_code == 400, "empty claim -> 400")
    check(post("/api/claims/parse", {"text": "x" * 501}).status_code == 400, "over-long claim -> 400")
    check(post("/api/validate/Patient/x", {}).status_code == 400, "unsupported resource type -> 400")
    check(post("/api/compare", {"a": {"observation": "nope"}, "b": {"observation": "nope2"}}).status_code == 400, "bad comparison -> 400")
    check(get("/api/reports/nope.txt").status_code == 404, "unknown report -> 404")

    # --- language model settings never leak a key --------------------------------------------------------------------------
    secret = "gsk_acceptance_Secret_0001"
    prov = get("/api/llm/providers").json()
    check(not prov["allow_user_keys"] or {"groq", "gemini", "ollama"} <= {p["id"] for p in prov["providers"]}, "provider presets listed")
    r = post("/api/claims/parse", {"text": "NO2 at site 01", "llm": {"api_key": secret}})
    check(r.status_code == 422 and secret not in r.text, "validation errors never echo a key")
    t = post("/api/llm/test", {"provider": "gemini"}).json()
    check(t["ok"] is False and "needs an API key" in t["error"], "a key is required where the provider needs one")

    # --- live $validate (read-only) when the run is live ----------------------------------------------------------------
    if st["source"]["kind"] == "live":
        v = post(f"/api/validate/Observation/{ANCHOR}", {})
        body = v.json() if v.status_code == 200 else {}
        oc = body.get("outcome", {})
        errs = [i for i in oc.get("issue", []) if i.get("severity") in ("error", "fatal")]
        check(v.status_code == 200 and not errs, "live server $validate on the anchor: no errors", [i.get("diagnostics") for i in oc.get("issue", [])][:2])

    # --- report --------------------------------------------------------------------------------------------------------------
    failed = [r for r in results if not r[0]]
    for ok, name, detail in results:
        if not ok or "-v" in sys.argv:
            print(f"{'PASS' if ok else 'FAIL'}  {name}  {detail}")
    print(f"\n{len(results) - len(failed)}/{len(results)} checks passed against {base} "
          f"({st['source']['kind']}, run {st['run_id']}, {total} findings)")
    return 1 if failed else 0


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):  # readable output when redirected on Windows
        stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    sys.exit(main(args[0] if args else "http://127.0.0.1:8321"))
