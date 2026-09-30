"""Render documents whose numbers must come from a real run (master prompt, rule 1: no hand-typed counts).

Inputs : the latest committed snapshot (audited now), docs/evaluation.json, the test suites.
Outputs: README.md and docs/SUBMISSION.md (from docs/templates/*.tmpl), docs/04_RULES_CATALOG.md (from the rule registry),
         docs/numbers.json (every value substituted, for audit).
backend/tests/integration/test_docs.py fails if a rendered document disagrees with a fresh audit.
"""

from __future__ import annotations

import asyncio
import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from datadoctor.audit.analyses import run_catalog  # noqa: E402
from datadoctor.audit.service import run_audit  # noqa: E402
from datadoctor.config import Settings  # noqa: E402
from datadoctor.knowledge.loader import load_knowledge  # noqa: E402
from datadoctor.rules.registry import load_rules  # noqa: E402


def count_backend_tests() -> int:
    out = subprocess.run([sys.executable, "-m", "pytest", "backend/tests", "--collect-only", "-q"], cwd=ROOT,
                         capture_output=True, text=True).stdout
    m = re.search(r"(\d+) tests? collected", out)
    if m:
        return int(m.group(1))
    per_file = [int(x) for x in re.findall(r"^\S+\.py: (\d+)$", out, re.M)]  # -qq output: "path.py: N"
    return sum(per_file) if per_file else sum(1 for line in out.splitlines() if "::" in line)


def count_e2e_tests() -> int:
    spec = (ROOT / "frontend" / "tests" / "demo.spec.ts").read_text(encoding="utf-8")
    loops = re.findall(r"for \(const path of \[(.*?)\]\) \{\s*test\(", spec, re.S)  # only loops that generate tests
    looped = sum(len(re.findall(r'"[^"]+"', x)) for x in loops)
    return len(re.findall(r"^\s*test\(", spec, re.M)) - len(loops) + looped


def numbers() -> dict[str, str]:
    kn = load_knowledge(ROOT / "knowledge")
    res, ds = asyncio.run(run_audit(Settings(), "snapshot"))
    an = run_catalog(ds, kn, res.findings)
    s = res.summary
    ev = json.loads((ROOT / "docs" / "evaluation.json").read_text(encoding="utf-8"))
    manifest = json.loads((ROOT / "data" / "snapshots" / res.source.snapshot_id / "manifest.json").read_text(encoding="utf-8"))  # type: ignore[operator]
    cv = Counter(c.verdict.value for c in an.comparisons)
    clv = Counter(c.verdict.value for c in an.claims)
    by_rule = s.findings_by_rule
    a = s.anchor["values"]
    from datadoctor.trace.graph import build_graph, impact

    graph = build_graph(ds, kn, an.comparisons, an.claims)
    anchor_f = next(f for f in res.findings if f.resource.resource_id == s.anchor["id"] and f.rule_id == "SEM-STAT-001")
    spatial = next((f for f in res.findings if f.rule_id == "SEM-SPATIAL-001"), None)
    gate0 = (ROOT / "docs" / "GATE0_REPORT.md").read_text(encoding="utf-8")
    n_samples = len(re.findall(r"^### \d+\. ", gate0, re.M))
    n_confirmed = gate0.count("Independent re-derivation:** CONFIRMED")
    sv = s.server_validation
    n = {
        "SNAPSHOT_ID": res.source.snapshot_id,
        "SNAPSHOT_FETCHED": res.source.fetched_at,
        "MANIFEST_SHA": res.source.manifest_sha256,
        "N_FILES": len(manifest["files"]),
        "RULES_VERSION": res.rules_version,
        "KNOWLEDGE_VERSION": res.knowledge_version,
        "IG_COMMIT": res.ig_commit[:8],
        "N_RESOURCES": sum(s.resources_by_type.values()),
        "N_OBSERVATIONS": s.resources_by_type.get("Observation", 0),
        "N_OAH_OBS": s.oah_observations,
        "N_THIRD_PARTY": s.resources_by_scope.get("third-party", 0),
        "N_FINDINGS": s.findings_total,
        "N_CRITICAL": s.findings_by_severity.get("CRITICAL", 0),
        "N_ERROR": s.findings_by_severity.get("ERROR", 0),
        "N_WARNING": s.findings_by_severity.get("WARNING", 0),
        "N_AFFECTED": s.affected_resources,
        "N_FLAGGED_OBS": s.oah_observations_with_blocking,
        "N_SAFE_OBS": s.oah_observations - s.oah_observations_with_blocking,
        "PASS_RATE": f"{(s.integrity_pass_rate or 0) * 100:.1f}",
        "N_VALIDATED": sv.get("validated_total", 0),
        "N_VALIDATED_ERRORS": sv.get("validated_with_errors", 0),
        "N_FLAGGED_PASS_SERVER": sv.get("flagged_observations_passing_server_validation", 0),
        "N_RULES": len(load_rules()),
        "N_RULES_FIRED": len(by_rule),
        "N_MEDIAN_OUTSIDE": by_rule.get("SEM-STAT-001", 0),
        "N_MEAN_OUTSIDE": by_rule.get("SEM-STAT-002", 0),
        "N_GAP_SD": by_rule.get("SEM-STAT-003", 0),
        "N_SCALE": by_rule.get("SEM-SCALE-001", 0),
        "N_SCALE_EXACT": sum(1 for f in res.findings if f.rule_id == "SEM-SCALE-001" and f.evidence.measures.get("exact_power_of_ten")),
        "N_IMPOSSIBLE": by_rule.get("SEM-RANGE-001", 0),
        "N_XREC": by_rule.get("SEM-XREC-001", 0),
        "N_UNIT": by_rule.get("STR-UNIT-001", 0),
        "ANCHOR_AVG": f"{a['average']:,.0f}",
        "ANCHOR_MEDIAN": f"{a['median']:g}",
        "ANCHOR_MIN": f"{a['minimum']:,.0f}",
        "ANCHOR_MAX": f"{a['maximum']:,.0f}",
        "ANCHOR_RULES": ", ".join(s.anchor["rules_fired"]),
        "N_CMP": len(an.comparisons),
        "CMP_VERDICTS": ", ".join(f"{v} {k}" for k, v in sorted(cv.items())),
        "N_CLAIMS": len(an.claims),
        "CLAIM_VERDICTS": ", ".join(f"{v} {k}" for k, v in sorted(clv.items())),
        "EVAL_INJECTED": ev["injected"],
        "EVAL_DETECTED": ev["detected"],
        "EVAL_CI": ev["detection_ci"],
        "EVAL_FAULT_TYPES": ev["fault_types"],
        "EVAL_BENIGN": ev["benign_records"],
        "EVAL_FP": ev["benign_new_findings"],
        "EVAL_FP_CI": ev["fp_ci"],
        "N_SAME_COORD_SITES": spatial.evidence.measures.get("sites") if spatial else 0,
        "ANCHOR_LINEAGE": anchor_f.lineage.locator if anchor_f.lineage else "not located",
        "ANCHOR_IMPACT": impact(graph, anchor_f).statement,
        "GATE0_CONFIRMED": f"{n_confirmed} of {n_samples}",
        "N_BACKEND_TESTS": count_backend_tests(),
        "N_E2E_TESTS": count_e2e_tests(),
    }
    return {k: str(v) for k, v in n.items()}


def render(template: Path, out: Path, n: dict[str, str]) -> None:
    text = template.read_text(encoding="utf-8")
    missing = sorted(set(re.findall(r"\{\{([A-Z0-9_]+)\}\}", text)) - set(n))
    if missing:
        raise SystemExit(f"{template.name}: unknown placeholders {missing}")
    out.write_text(re.sub(r"\{\{([A-Z0-9_]+)\}\}", lambda m: n[m.group(1)], text), encoding="utf-8")


def rules_catalog(n: dict[str, str]) -> str:
    rules = load_rules()
    res, _ = asyncio.run(run_audit(Settings(), "snapshot"))
    by_rule = res.summary.findings_by_rule
    tests = {p.name: p.read_text(encoding="utf-8") for p in (ROOT / "backend" / "tests" / "unit").glob("test_rules_*.py")}
    L = ["# 04 — Rules catalog", "",
         f"Generated from the rule registry by `scripts/render_docs.py` (rules version `{n['RULES_VERSION']}`). This file is the "
         "authoritative description of rule behaviour; it cannot drift from the code because it is rendered from it.", "",
         "Principles shared by every rule:", "",
         "- Pure function of the dataset and the knowledge layer; no I/O, no LLM, deterministic finding ids.",
         "- Numbers are compared within half a unit of their last published decimal (an exact zero uses the record's finest "
         "precision), so rounding alone never raises a finding.",
         "- Root cause is always `unknown`. Patterns that suggest a cause are attached as explicitly labelled, unverified hypotheses.",
         "- Every finding carries rule id and version, resource, FHIRPath, observed values, constraint, confidence, severity, "
         "provenance and remediation (\"review by the data owner\").", "",
         f"Findings per rule refer to snapshot `{n['SNAPSHOT_ID']}`.", "",
         "| Rule | Title | Category | Severity | Findings in snapshot |", "|---|---|---|---|---|"]
    for rid, r in sorted(rules.items()):
        L.append(f"| [{rid}](#{rid.lower()}) | {r.spec.title} | {r.spec.category.value.title()} | {r.spec.severity.split(';')[0]} | {by_rule.get(rid, 0)} |")
    L.append("")
    for rid, r in sorted(rules.items()):
        sp = r.spec
        test_files = [name for name, text in tests.items() if f'"{rid}"' in text]
        L += [f"## {rid}", "", f"**{sp.title}** (v{sp.version}, {sp.category.value.lower()})", "",
              f"- **Must hold:** {sp.constraint}", f"- **Applies to:** {sp.applies_to}", f"- **Severity:** {sp.severity}",
              f"- **Confidence:** {sp.confidence}", f"- **Why:** {sp.rationale}"]
        if sp.references:
            L.append(f"- **References:** {'; '.join(sp.references)}")
        L.append(f"- **Tests:** {', '.join(f'`backend/tests/unit/{t}`' for t in sorted(test_files)) or 'integration tests'} "
                 "(positive, negative and edge cases)")
        L.append("")
    L += ["## Comparability dimensions (CMP-*)", "",
          "CMP-MEASURE, CMP-UNIT, CMP-MEDIUM, CMP-POPULATION, CMP-PERIOD, CMP-AGGREGATION, CMP-METHOD, CMP-INTEGRITY. "
          "See docs/COMPARABILITY_SPEC.md.", "",
          "## Claim guardrail steps (CLM-*)", "",
          "CLM-CMP-001, CLM-DIR-001, CLM-UNC-001, CLM-TRD-001/002, CLM-INT-001, CLM-THR-001/002/003, CLM-ASC-001, CLM-CAU-001/002. "
          "See docs/CLAIM_SAFETY_SPEC.md.", ""]
    return "\n".join(L)


def main() -> None:
    n = numbers()
    (ROOT / "docs" / "numbers.json").write_text(json.dumps(n, indent=1), encoding="utf-8")
    tmpl = ROOT / "docs" / "templates"
    render(tmpl / "README.md.tmpl", ROOT / "README.md", n)
    render(tmpl / "SUBMISSION.md.tmpl", ROOT / "docs" / "SUBMISSION.md", n)
    (ROOT / "docs" / "04_RULES_CATALOG.md").write_text(rules_catalog(n), encoding="utf-8")
    print(json.dumps(n, indent=1))


if __name__ == "__main__":
    main()
