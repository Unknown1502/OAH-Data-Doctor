"""Structural rules: what a base-R4 validator on the sandbox cannot check (OAH profiles, UCUM, references).

The sandbox's own `$validate` cannot load the OAH profiles (DISCOVERY.md D3), so these checks run locally
against constraints transcribed from the IG's FSH at a pinned commit (knowledge/oah/profile_constraints.yaml).
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from datadoctor.config import INGEST_TYPES
from datadoctor.domain.enums import Category, Severity
from datadoctor.domain.models import Evidence, Finding, ObservedValue, ResourceRef
from datadoctor.rules.base import RuleContext, RuleSpec, rule

# ---------------------------------------------------------------------------------------------------
# A minimal FHIR path evaluator (dotted element paths; `name[x]` matches any choice type)
# ---------------------------------------------------------------------------------------------------


def values_at(node: Any, path: str) -> list[Any]:
    current = [node]
    for part in path.split("."):
        nxt: list[Any] = []
        for c in current:
            if not isinstance(c, dict):
                continue
            if part.endswith("[x]"):
                base = part[:-3]
                items = [v for k, v in c.items() if k.startswith(base) and len(k) > len(base) and k[len(base)].isupper()]
            else:
                items = [c[part]] if part in c else []
            for v in items:
                nxt.extend(v if isinstance(v, list) else [v])
        current = nxt
    return current


def _check(resource: dict[str, Any], chk: dict[str, Any]) -> str | None:
    path, kind = chk["path"], chk["type"]
    want: Any = chk.get("value")
    if kind == "min":
        n = len(values_at(resource, path))
        return f"{path}: found {n}, profile requires at least {want}" if n < int(want) else None
    if kind == "max":
        n = len(values_at(resource, path))
        return f"{path}: found {n}, profile allows at most {want}" if n > int(want) else None
    if kind == "fixed":
        bad = [v for v in values_at(resource, path) if v != want]
        return f"{path}: found {bad[0]!r}, profile fixes it to {want!r}" if bad else None
    if kind == "ref_type":
        bad = [v.get("reference") for v in values_at(resource, path) if isinstance(v, dict) and v.get("reference")
               and not str(v["reference"]).startswith(f"{want}/")]
        return f"{path}: references {bad[0]}, profile requires a {want}" if bad else None
    if kind == "per_item_min":
        parent = chk["parent"]
        rel = path[len(parent) + 1:]
        for i, item in enumerate(values_at(resource, parent)):
            if len(values_at(item, rel)) < int(want):
                return f"{parent}[{i}].{rel}: missing, profile requires at least {want}"
        return None
    raise ValueError(f"unknown check type {kind}")


def _profile_checks(kn_constraints: dict[str, Any], profile_id: str) -> tuple[str, list[dict[str, Any]]]:
    prof = kn_constraints["profiles"][profile_id]
    checks = list(prof["checks"])
    parent = prof.get("parent")
    while parent:
        checks = list(kn_constraints["profiles"][parent]["checks"]) + checks
        parent = kn_constraints["profiles"][parent].get("parent")
    return prof["source"], checks


SPEC_PROF = RuleSpec(
    id="STR-PROF-001", version="1.0", title="Resource violates its declared OAH profile",
    category=Category.STRUCTURAL, severity="ERROR", confidence="0.9 — constraints hand-transcribed from FSH",
    applies_to="Resources whose meta.profile names an OAH profile (Observation, Group, Library, Location)",
    constraint="cardinality, fixed values and reference targets from the OAH FSH at the pinned commit",
    rationale="The sandbox cannot validate OAH profiles itself (profiles not loaded on the server).",
)


@rule(SPEC_PROF)
def profile_conformance(ctx: RuleContext) -> Iterator[Finding]:
    pc = ctx.kn.profile_constraints
    base = pc["base"]
    for rtype in sorted(ctx.ds.raw):
        for rid, res in sorted(ctx.ds.raw[rtype].items()):
            for prof_url in res.get("meta", {}).get("profile", []):
                if not prof_url.startswith(base) or prof_url[len(base):] not in pc["profiles"]:
                    continue
                pid = prof_url[len(base):]
                source, checks = _profile_checks(pc, pid)
                problems = [p for p in (_check(res, c) for c in checks) if p]
                if not problems:
                    continue
                yield ctx.make(
                    SPEC_PROF,
                    resource=ResourceRef(resource_type=rtype, resource_id=rid, display=res.get("name") or rid),
                    severity=Severity.ERROR, confidence=0.9, discriminator=pid,
                    summary=f"{rtype}/{rid} declares profile {pid} but violates {len(problems)} of its constraints.",
                    evidence=Evidence(
                        observed=[ObservedValue(label=p.split(":")[0], value=p.split(": ", 1)[1]) for p in problems],
                        constraint=f"conformance to {prof_url}",
                        expected=f"All constraints of {pid} ({source}) hold.",
                        measures={"profile": prof_url, "fsh_source": source, "violations": problems},
                    ),
                    interpretation="Structural non-conformance with the OAH implementation guide.",
                    remediation="Ask the data owner to correct the resource so it conforms to the declared profile.",
                )


SPEC_UNIT = RuleSpec(
    id="STR-UNIT-001", version="1.0", title="Quantity without a valid UCUM unit code",
    category=Category.STRUCTURAL,
    severity="ERROR if the code is missing or known-invalid; WARNING if merely unrecognised by our curated table",
    confidence="0.95 for missing/known-invalid; 0.6 for unrecognised (curated table, not a full UCUM parser)",
    applies_to="Every Quantity with a value (Observation.value and components); one finding per Observation",
    constraint="Quantity.system = UCUM and Quantity.code is a valid UCUM expression",
    rationale="Without a machine-readable unit, a value cannot be compared, converted or range-checked.",
)


@rule(SPEC_UNIT)
def ucum_units(ctx: RuleContext) -> Iterator[Finding]:
    for obs in ctx.observations():
        issues: list[tuple[str, str, str | None, str]] = []  # (kind, path, code, suggestion)
        quantities: list[tuple[str, dict[str, Any]]] = []
        if isinstance(obs.raw.get("valueQuantity"), dict):
            quantities.append(("Observation.valueQuantity", obs.raw["valueQuantity"]))
        for i, comp in enumerate(obs.raw.get("component", [])):
            if isinstance(comp.get("valueQuantity"), dict):
                quantities.append((f"Observation.component[{i}].valueQuantity", comp["valueQuantity"]))
        for path, q in quantities:
            if q.get("value") is None:
                continue
            code = q.get("code")
            if not code:
                issues.append(("missing", path, None, ""))
            elif code in ctx.kn.units_invalid:
                issues.append(("invalid", path, code, ctx.kn.units_invalid[code]["suggest"]))
            elif code not in ctx.kn.units_valid:
                issues.append(("unrecognised", path, code, ""))
        if not issues:
            continue
        order = {"missing": 0, "invalid": 1, "unrecognised": 2}
        worst = min(issues, key=lambda x: order[x[0]])
        severity = Severity.WARNING if worst[0] == "unrecognised" else Severity.ERROR
        what = {"missing": "has no unit code", "invalid": f"uses '{worst[2]}', which is not valid UCUM (use '{worst[3]}')",
                "unrecognised": f"uses unit code '{worst[2]}', not recognised by our curated UCUM table"}[worst[0]]
        yield ctx.make(
            SPEC_UNIT,
            resource=ResourceRef(resource_type="Observation", resource_id=obs.id, fhir_path=worst[1], display=ctx.display(obs)),
            severity=severity, confidence=0.6 if worst[0] == "unrecognised" else 0.95,
            summary=f"{ctx.display(obs)}: {len(issues)} value(s) {what}.",
            evidence=Evidence(
                observed=[ObservedValue(label=p.split(".")[-2] if "component" in p else "value", value=c or "(none)",
                                        fhir_path=p) for _, p, c, _ in issues],
                constraint="Quantity.code is a valid UCUM code",
                expected="Each numeric value carries a machine-readable UCUM unit.",
                measures={"problem": worst[0], "suggest": worst[3] or None, "count": len(issues)},
                raw_excerpt=[q for _, q in quantities][:3],
            ),
            interpretation="The unit of these values cannot be interpreted by software.",
            remediation="Ask the data owner to add or correct the UCUM unit code.",
        )


SPEC_REF = RuleSpec(
    id="STR-REF-001", version="1.0", title="Reference does not resolve",
    category=Category.STRUCTURAL, severity="ERROR", confidence="0.9 (resolution is checked within the ingested snapshot)",
    applies_to="Relative references to ingested resource types (" + ", ".join(INGEST_TYPES) + "); Library.content is covered by STR-LIB-001",
    constraint="every relative reference points to a resource present on the server",
    rationale="A dangling reference silently drops context (site, cohort, device) from any analysis.",
)
_REF_PATHS = {
    "Observation": ["subject", "focus", "device", "performer", "specimen", "derivedFrom", "hasMember"],
    "Location": ["partOf"],
    "Provenance": ["target", "agent.who"],
    "Group": [],
}


@rule(SPEC_REF)
def references_resolve(ctx: RuleContext) -> Iterator[Finding]:
    for rtype, paths in _REF_PATHS.items():
        for rid, res in sorted(ctx.ds.raw.get(rtype, {}).items()):
            missing = []
            for p in paths:
                for v in values_at(res, p):
                    ref = v.get("reference") if isinstance(v, dict) else None
                    if not ref or ref.startswith(("http", "#", "urn:")) or "/" not in ref:
                        continue
                    t = ref.split("/")[0]
                    if t in INGEST_TYPES and ctx.ds.resolve(ref) is None:
                        missing.append((p, ref))
            if not missing:
                continue
            yield ctx.make(
                SPEC_REF,
                resource=ResourceRef(resource_type=rtype, resource_id=rid, fhir_path=f"{rtype}.{missing[0][0]}"),
                severity=Severity.ERROR, confidence=0.9,
                summary=f"{rtype}/{rid} references {', '.join(r for _, r in missing)}, which does not exist on the server.",
                evidence=Evidence(observed=[ObservedValue(label=p, value=r, fhir_path=f"{rtype}.{p}") for p, r in missing],
                                  constraint="reference resolves", expected="Referenced resources exist.",
                                  measures={"unresolved": [r for _, r in missing]}),
                interpretation="Dangling reference (root cause unknown).",
                remediation="Ask the data owner to publish the referenced resource or fix the reference.",
            )


SPEC_LIB = RuleSpec(
    id="STR-LIB-001", version="1.0", title="Data-set Library inconsistent with its declared contents",
    category=Category.STRUCTURAL, severity="ERROR", confidence="0.9",
    applies_to="Library resources listing FHIR members in Library.content (asset collections)",
    constraint="declared numberOfRecords = number of listed members, and every member resolves",
    rationale="Researchers select data through these collections; a wrong count or missing member silently changes a study population.",
)


@rule(SPEC_LIB)
def library_consistency(ctx: RuleContext) -> Iterator[Finding]:
    for lib in sorted(ctx.ds.libraries.values(), key=lambda x: x.id):
        listed = lib.member_refs
        if not listed:
            continue  # members are external links only: count is not verifiable
        declared = lib.declared_records if lib.declared_records is not None else lib.declared_size
        unresolved = [m for m in listed if m.split("/")[0] in INGEST_TYPES and ctx.ds.resolve(m) is None]
        dup = len(listed) - len(set(listed))
        count_bad = declared is not None and int(declared) != len(listed)
        if not (count_bad or unresolved or dup):
            continue
        yield ctx.make(
            SPEC_LIB,
            resource=ResourceRef(resource_type="Library", resource_id=lib.id, fhir_path="Library.content", display=lib.title),
            severity=Severity.ERROR, confidence=0.9,
            summary=(f"Library {lib.title or lib.id}: declares {declared} records, lists {len(listed)}"
                     f"{f', {len(unresolved)} do not resolve' if unresolved else ''}{f', {dup} duplicated' if dup else ''}."),
            evidence=Evidence(
                observed=[ObservedValue(label="declared numberOfRecords", value=declared),
                          ObservedValue(label="listed members", value=len(listed))],
                constraint="numberOfRecords = |content| and all members resolve",
                expected="The collection contains exactly the records it declares.",
                measures={"declared": declared, "listed": len(listed), "unresolved": unresolved, "duplicates": dup},
            ),
            interpretation="The data-set definition does not match its contents (root cause unknown).",
            remediation="Ask the data owner to reconcile the Library with its members.",
        )
