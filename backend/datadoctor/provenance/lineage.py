"""Upstream lineage: locate the IG source-file row a FHIR record was generated from and compare values.

This proves *where* a value first appears (before FHIR conversion). It does not prove *why* it is wrong:
root cause remains unknown and the statement says so.
"""

from __future__ import annotations

import re

from datadoctor.domain.models import Dataset, LineageRecord, NormalizedObservation

ALMYROS_FILE = "Almyros_gov_chem_analysis.csv"
_COLUMNS = {"AVERAGE": "average", "MAX": "maximum", "MIN": "minimum", "STDEV": "std-dev", "MEDIAN": "median"}


def _num(text: str) -> float | None:
    t = text.strip()
    if not t:
        return None
    try:
        return float(t.replace(",", "."))  # the file mixes decimal comma ("19,80") and decimal point ("0.9899")
    except ValueError:
        return None


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def almyros_lineage(obs: NormalizedObservation, ds: Dataset, ig_commit: str) -> LineageRecord | None:
    text = ds.upstream_files.get(ALMYROS_FILE)
    if not text or not obs.id.startswith("Obs-Almyros-") or obs.year is None:
        return None
    param = _norm(obs.code_text or obs.code_display or "")
    lines = text.splitlines()
    header = [h.strip() for h in lines[0].split(";")]
    for lineno, line in enumerate(lines[1:], start=2):
        cells = line.split(";")
        if len(cells) != len(header):
            continue
        row = dict(zip(header, cells, strict=True))
        if row.get("Year", "").strip() != str(obs.year) or _norm(row.get("Parameter", "")) != param:
            continue
        matches: dict[str, bool] = {}
        for col, stat in _COLUMNS.items():
            s = obs.stat(stat)
            src = _num(row.get(col, ""))
            if s is None or s.quantity.value is None or src is None:
                continue
            matches[stat] = abs(s.quantity.value - src) <= 1e-9 * max(1.0, abs(src))
        if not matches:
            return None
        all_match = all(matches.values())
        loc = f"_samples/crete/{ALMYROS_FILE}, line {lineno}"
        stmt = (f"The same values appear in the IG source file ({loc}) at commit {ig_commit[:8]}: the inconsistency "
                "was already present before FHIR conversion. This locates where the values first appear; it does "
                "not establish why (root cause unknown)."
                if all_match else
                f"The FHIR values differ from the IG source row ({loc}) for "
                f"{', '.join(k for k, v in matches.items() if not v)}: a change was introduced during or after conversion.")
        return LineageRecord(source=f"https://github.com/hl7-eu/oah/blob/{ig_commit}/_samples/crete/{ALMYROS_FILE}",
                             locator=loc, raw_row=line.strip(), matches=matches, statement=stmt)
    return None
