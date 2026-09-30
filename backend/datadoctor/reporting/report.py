"""Researcher report (Markdown + self-contained HTML). Every number is read from the run; nothing is typed in."""

from __future__ import annotations

import html
from collections import Counter
from typing import Any

from datadoctor.audit.analyses import AnalysesResult
from datadoctor.audit.service import AuditResult
from datadoctor.domain.enums import Severity
from datadoctor.reporting.support import SupportRow

STATUS_TEXT = {"USABLE": "Usable", "USABLE_WITH_CAVEATS": "Usable with caveats", "PARTLY_USABLE": "Partly usable",
               "NOT_USABLE": "Do not use until reviewed"}


def build_model(res: AuditResult, an: AnalysesResult, support: list[SupportRow]) -> dict[str, Any]:
    s = res.summary
    by_rule: dict[str, list[Any]] = {}
    for f in res.findings:
        by_rule.setdefault(f.rule_id, []).append(f)
    return {"res": res, "an": an, "support": support, "s": s, "by_rule": by_rule,
            "status_counts": Counter(r.status for r in support)}


def _src(res: AuditResult) -> str:
    src = res.source
    if src.kind.value == "live":
        return f"LIVE — fetched {src.fetched_at} from {src.base_url}"
    return (f"SNAPSHOT {src.snapshot_id} — fetched {src.fetched_at} from {src.base_url}; manifest sha256 "
            f"{src.manifest_sha256}" + (f" (fallback: {src.fallback_reason})" if src.fallback_reason else ""))


def render_markdown(m: dict[str, Any]) -> str:
    res: AuditResult = m["res"]
    s = m["s"]
    an: AnalysesResult = m["an"]
    L = [
        "# OAH Data Doctor — researcher report", "",
        f"*Run `{res.run_id}` · generated {res.created_at} · Data Doctor {res.tool_version} · rules `{res.rules_version}` · "
        f"knowledge `{res.knowledge_version}` · IG source `hl7-eu/oah@{res.ig_commit[:12]}`*", "",
        f"**Data source:** {_src(res)}", "",
        "## Headline", "",
        f"- {s.observations_checked} observations checked ({s.oah_observations} official OAH IG examples).",
        f"- {s.findings_total} findings: " + ", ".join(f"{v} {k}" for k, v in s.findings_by_severity.items() if v) + ".",
        f"- {s.oah_observations - s.oah_observations_with_blocking} of {s.oah_observations} official observations "
        f"({(s.integrity_pass_rate or 0) * 100:.1f} %) have no ERROR/CRITICAL finding.",
    ]
    sv = s.server_validation
    if sv:
        L.append(f"- The FHIR server's own `$validate` was run on {sv['validated_total']} observations: "
                 f"{sv['validated_with_errors']} reported an error. All {sv['flagged_observations_passing_server_validation']} "
                 f"of the {sv['flagged_observations_validated']} observations Data Doctor flags passed it.")
    a = s.anchor
    if a.get("present"):
        L.append(f"- Anchor record `{a['id']}`: values {a.get('values')} {a.get('unit')}; rules fired: {', '.join(a['rules_fired'])}.")
    L += ["", "## What this data can and cannot support", "",
          "| Data set | Indicator | Records | Years | Flagged | Status | Can support | Cannot support |",
          "|---|---|---|---|---|---|---|---|"]
    for r in m["support"]:
        L.append(f"| {r.library_title} | {r.indicator_label} | {r.observations} | {', '.join(map(str, r.years))} | "
                 f"{r.blocked} blocking, {r.warned} warning | **{STATUS_TEXT[r.status]}** | {'; '.join(r.can_support)} | {'; '.join(r.cannot_support)} |")
    L += ["", "## Findings by rule", ""]
    for rid, fs in sorted(m["by_rule"].items()):
        sev = Counter(f.severity.value for f in fs)
        ex = fs[0]
        L += [f"### {rid} — {ex.title}", "",
              f"{len(fs)} finding(s): " + ", ".join(f"{v} {k}" for k, v in sev.items()) + f". Constraint: `{ex.evidence.constraint}`.", "",
              f"Example: {ex.summary}", ""]
        if ex.lineage:
            L += [f"Upstream: {ex.lineage.statement}", ""]
    L += ["## Comparisons computed", "", "| Comparison | Verdict | Why |", "|---|---|---|"]
    for c in an.comparisons:
        L.append(f"| {c.a.label} vs {c.b.label} | **{c.verdict.value}** | {c.summary} |")
    L += ["", "## Claims checked", "", "| Claim | Verdict | Reason | Safe wording |", "|---|---|---|---|"]
    for cl in an.claims:
        L.append(f"| {cl.claim_rendered} | **{cl.verdict.value}** | {cl.reasons[0]} | {cl.safe_alternatives[0] if cl.safe_alternatives else '—'} |")
    L += ["", "## Method and limitations", "",
          "- Detection, comparability and claim verdicts are deterministic rules (docs/04_RULES_CATALOG.md); no LLM decides anything.",
          "- A finding shows that published values cannot all be correct. It never shows *which* value is wrong or *why*: root cause is "
          "reported as unknown unless proven. Upstream lineage only locates where values first appear.",
          "- Typical-range warnings (SEM-RANGE-002) flag unusual, not impossible, values.",
          "- Cohort sizes, sample counts and data coverage are not published, so statistical significance between cohorts cannot be tested.",
          "- Data Doctor never modifies source data. Every finding recommends review by the data owner.", "",
          "## Attribution", "",
          "Data: OneAquaHealth FHIR sandbox operated by HL7 Europe. Definitions: OneAquaHealth FHIR IG (hl7-eu/oah). "
          "Independent hackathon project, not endorsed by OneAquaHealth, HL7 Europe or IEEE.", ""]
    return "\n".join(L)


_CSS = """
:root{--bg:#0b1216;--panel:#111b21;--ink:#e6eef2;--mute:#8aa0ab;--line:#22323b;--crit:#ff5a4e;--err:#ff9f43;--warn:#f5d547;--ok:#4cd6a4}
@media (prefers-color-scheme: light){:root{--bg:#f6f8f7;--panel:#fff;--ink:#11201c;--mute:#5a6b66;--line:#dde5e2}}
body{background:var(--bg);color:var(--ink);font:15px/1.55 system-ui,-apple-system,Segoe UI,sans-serif;margin:0;padding:32px 16px}
main{max-width:1100px;margin:0 auto}h1{font-size:28px;margin:0 0 4px}h2{margin-top:36px;border-bottom:1px solid var(--line);padding-bottom:6px}
.meta{color:var(--mute);font-size:13px}.src{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:12px 14px;margin:16px 0}
table{border-collapse:collapse;width:100%;font-size:13.5px;background:var(--panel)}th,td{border:1px solid var(--line);padding:7px 9px;text-align:left;vertical-align:top}
th{color:var(--mute);font-weight:600}.pill{display:inline-block;border-radius:99px;padding:1px 9px;font-size:12px;font-weight:700}
.USABLE{background:#1f7a55;color:#fff}.USABLE_WITH_CAVEATS{background:#8a7a12;color:#fff}.PARTLY_USABLE{background:#9a5a12;color:#fff}.NOT_USABLE{background:#9d2a22;color:#fff}
.v-DIRECT,.v-SUPPORTED{background:#1f7a55;color:#fff}.v-CONDITIONAL{background:#8a7a12;color:#fff}.v-NOT,.v-UNSUPPORTED{background:#555;color:#fff}.v-BLOCKED_BY_INTEGRITY,.v-BLOCKED{background:#9d2a22;color:#fff}
code{font-family:ui-monospace,Consolas,monospace;font-size:12.5px}ul{padding-left:20px}
"""


def render_html(m: dict[str, Any]) -> str:
    res: AuditResult = m["res"]
    s = m["s"]
    an: AnalysesResult = m["an"]
    e = html.escape
    sup_rows = "".join(
        f"<tr><td>{e(r.library_title)}</td><td>{e(r.indicator_label)}</td><td>{r.observations}</td><td>{e(', '.join(map(str, r.years)))}</td>"
        f"<td>{r.blocked} / {r.warned}</td><td><span class='pill {r.status}'>{e(STATUS_TEXT[r.status])}</span></td>"
        f"<td>{e('; '.join(r.can_support))}</td><td>{e('; '.join(r.cannot_support))}</td></tr>" for r in m["support"])
    rule_rows = "".join(
        f"<tr><td><code>{e(rid)}</code></td><td>{e(fs[0].title)}</td><td>{len(fs)}</td>"
        f"<td>{e(', '.join(f'{v} {k}' for k, v in Counter(f.severity.value for f in fs).items()))}</td><td>{e(fs[0].summary)}</td></tr>"
        for rid, fs in sorted(m["by_rule"].items()))
    cmp_rows = "".join(f"<tr><td>{e(c.a.label)}<br><span class='meta'>vs</span> {e(c.b.label)}</td>"
                       f"<td><span class='pill v-{c.verdict.value}'>{c.verdict.value}</span></td><td>{e(c.summary)}</td></tr>" for c in an.comparisons)
    clm_rows = "".join(f"<tr><td>{e(c.claim_rendered)}</td><td><span class='pill v-{c.verdict.value}'>{c.verdict.value}</span></td>"
                       f"<td>{e(c.reasons[0])}</td><td>{e(c.safe_alternatives[0]) if c.safe_alternatives else '—'}</td></tr>" for c in an.claims)
    sv = s.server_validation
    sv_li = (f"<li>The server's own <code>$validate</code> ran on {sv['validated_total']} observations and reported "
             f"{sv['validated_with_errors']} errors; all {sv['flagged_observations_passing_server_validation']} observations "
             "flagged here passed it.</li>") if sv else ""
    sev = ", ".join(f"{v} {k}" for k, v in s.findings_by_severity.items() if v)
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>OAH Data Doctor report</title><style>{_CSS}</style></head><body><main>
<h1>OAH Data Doctor — researcher report</h1>
<div class="meta">Run <code>{e(res.run_id)}</code> · {e(res.created_at)} · rules <code>{e(res.rules_version)}</code> · knowledge <code>{e(res.knowledge_version)}</code> · IG source hl7-eu/oah@{e(res.ig_commit[:12])}</div>
<div class="src"><b>Data source:</b> {e(_src(res))}</div>
<h2>Headline</h2><ul>
<li>{s.observations_checked} observations checked ({s.oah_observations} official OAH IG examples).</li>
<li>{s.findings_total} findings: {e(sev)}.</li>
<li>{s.oah_observations - s.oah_observations_with_blocking} of {s.oah_observations} official observations ({(s.integrity_pass_rate or 0) * 100:.1f} %) have no ERROR/CRITICAL finding.</li>
{sv_li}</ul>
<h2>What this data can and cannot support</h2>
<table><tr><th>Data set</th><th>Indicator</th><th>Records</th><th>Years</th><th>Blocking / warning</th><th>Status</th><th>Can support</th><th>Cannot support</th></tr>{sup_rows}</table>
<h2>Findings by rule</h2><table><tr><th>Rule</th><th>Title</th><th>Findings</th><th>Severity</th><th>Example</th></tr>{rule_rows}</table>
<h2>Comparisons computed</h2><table><tr><th>Comparison</th><th>Verdict</th><th>Why</th></tr>{cmp_rows}</table>
<h2>Claims checked</h2><table><tr><th>Claim</th><th>Verdict</th><th>Reason</th><th>Safe wording</th></tr>{clm_rows}</table>
<h2>Method and limitations</h2><ul>
<li>Detection, comparability and claim verdicts are deterministic rules; no LLM decides anything.</li>
<li>A finding shows that published values cannot all be correct. It never shows which value is wrong or why; root cause is reported as unknown unless proven.</li>
<li>Cohort sizes, sample counts and data coverage are not published, so significance between cohorts cannot be tested.</li>
<li>Data Doctor never modifies source data; every finding recommends review by the data owner.</li></ul>
<p class="meta">Data: OneAquaHealth FHIR sandbox (HL7 Europe). Definitions: OneAquaHealth FHIR IG (hl7-eu/oah). Independent hackathon project, not endorsed by OneAquaHealth, HL7 Europe or IEEE.</p>
</main></body></html>"""
