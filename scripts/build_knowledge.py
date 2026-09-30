"""Regenerate knowledge/oah/* from the OAH FHIR IG source at a pinned commit.

Why: the published IG site (build.fhir.org/ig/hl7-eu/oah) returned 404 during discovery (2026-09-30) and the
sandbox hosts no StructureDefinitions/CodeSystems. The FSH source on GitHub is the authoritative, citable
definition, so we derive our knowledge from it reproducibly and record the commit + sha256 of every input.

Usage:  python scripts/build_knowledge.py [--commit <sha>]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import urllib.parse
import urllib.request
from pathlib import Path

REPO = "hl7-eu/oah"
DEFAULT_COMMIT = "b907cf0869b59d82d9138b3d147fca66f333d911"
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "knowledge" / "oah"

FSH_EXAMPLES = [
    "almyros_gov_chem.fsh", "benevento_libraries.fsh", *[f"benevento_pollutant_{i:02d}.fsh" for i in range(1, 13)],
    "bn_disease_prevalence_groups.fsh", "bn_disease_prevalence_observations.fsh", "ec_tmp.fsh", "library_tmp.fsh",
    "loc_benevento.fsh", "loc_nordre_aker.fsh", "organization_arpac.fsh", "os_disease_prevalence_groups.fsh",
    "os_disease_prevalence_observations.fsh", "oslo_libraries.fsh", "water_tmp.fsh",
]
CODESYSTEM_FSH = "input/fsh/terminologies/oah-codeSystem.fsh"
UPSTREAM_FILES = ["_samples/crete/Almyros_gov_chem_analysis.csv"]


def fetch(commit: str, path: str) -> bytes:
    url = f"https://raw.githubusercontent.com/{REPO}/{commit}/{urllib.parse.quote(path)}"
    with urllib.request.urlopen(url, timeout=60) as r:  # noqa: S310 - fixed https host
        return r.read()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--commit", default=DEFAULT_COMMIT)
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    sources: list[dict[str, str]] = []

    # 1. IG example instance ids (official content) -------------------------------------------------
    instances: list[dict[str, str]] = []
    for name in FSH_EXAMPLES:
        path = f"input/fsh/examples/{name}"
        text = fetch(args.commit, path).decode("utf-8")
        sources.append({"path": path, "sha256": hashlib.sha256(text.encode()).hexdigest()})
        current: dict[str, str] | None = None
        for line in text.splitlines():
            m = re.match(r"^Instance:\s*(\S+)", line)
            if m:
                current = {"id": m.group(1), "file": path}
                instances.append(current)
                continue
            m = re.match(r"^InstanceOf:\s*(\S+)", line)
            if m and current is not None:
                current["instance_of"] = m.group(1)
    (OUT / "ig_instances.json").write_text(json.dumps(
        {"repo": REPO, "commit": args.commit, "count": len(instances), "instances": instances}, indent=1), "utf-8")

    # 2. Temporary OAH CodeSystem concepts (code, display, definition) --------------------------------
    text = fetch(args.commit, CODESYSTEM_FSH).decode("utf-8")
    sources.append({"path": CODESYSTEM_FSH, "sha256": hashlib.sha256(text.encode()).hexdigest()})
    concepts = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        m = re.match(r'^\*\s+#(\S+)\s+"([^"]*)"(?:\s+"([^"]*)")?', line)
        if m:
            concepts.append({"code": m.group(1), "display": m.group(2), "definition": m.group(3) or "",
                             "fsh_line": lineno})
    (OUT / "codesystem_temporarySystem-oah-eu.json").write_text(json.dumps(
        {"url": "http://hl7.eu/fhir/ig/oah/CodeSystem/temporarySystem-oah-eu", "repo": REPO,
         "commit": args.commit, "source": CODESYSTEM_FSH, "concepts": concepts}, indent=1, ensure_ascii=False), "utf-8")

    # 3. Upstream sample files used for lineage evidence ----------------------------------------------
    up = OUT / "upstream"
    up.mkdir(exist_ok=True)
    for path in UPSTREAM_FILES:
        data = fetch(args.commit, path)
        (up / Path(path).name).write_bytes(data)
        sources.append({"path": path, "sha256": hashlib.sha256(data).hexdigest()})

    (OUT / "sources.json").write_text(json.dumps({"repo": f"https://github.com/{REPO}", "commit": args.commit,
                                                  "files": sources}, indent=1), "utf-8")
    print(f"instances={len(instances)} concepts={len(concepts)} upstream={len(UPSTREAM_FILES)} -> {OUT}")


if __name__ == "__main__":
    main()
