"""Natural language -> ClaimIntent -> StructuredClaim.

A convenience layer only. Both the deterministic keyword parser and the optional LLM produce a ClaimIntent
(indicator keys, place names, years, claim type). A deterministic resolver maps the intent onto records that
exist in the dataset. The resulting StructuredClaim is shown to the user, and the verdict is computed from it by
claims/engine.py. Neither parser can invent a record id: unresolvable intents are reported as such.
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field

from datadoctor.domain.enums import ClaimType
from datadoctor.domain.models import Dataset, NormalizedObservation, StructuredClaim
from datadoctor.knowledge.loader import Knowledge


class ClaimIntent(BaseModel):
    type: Literal["COMPARE_HIGHER", "TREND_INCREASE", "EXCEEDS_THRESHOLD", "ASSOCIATION", "CAUSAL"] | None = None
    indicator_key: str | None = None
    outcome_indicator_key: str | None = None
    locations: list[str] = Field(default_factory=list, description="Location resource ids, in the order mentioned")
    year_from: int | None = None
    year_to: int | None = None
    statistic: Literal["average", "median", "maximum", "minimum"] | None = None
    threshold_hint: Literal["who", "eu", "drinking-water"] | None = None


class ParseResult(BaseModel):
    intent: ClaimIntent
    claim: StructuredClaim | None
    method: str
    understood: list[str]
    problems: list[str]


_TYPE_PATTERNS = [
    (ClaimType.CAUSAL, r"\b(causes?|caused|causing|leads? to|drives?|results? in|responsible for)\b"),
    (ClaimType.ASSOCIATION, r"\b(associated|association|correlat\w*|linked|link between|related to)\b"),
    (ClaimType.EXCEEDS_THRESHOLD, r"\b(exceed\w*|above the (?:limit|guideline|threshold)|breach\w*|over the (?:limit|guideline))\b"),
    (ClaimType.TREND_INCREASE, r"\b(increas\w*|ris(?:e|es|ing)|rose|went up|upward|trend\w*|warm(?:ed|ing))\b"),
    (ClaimType.COMPARE_HIGHER, r"\b(higher|greater|more|worse|warmer|larger|bigger)\b.*\bthan\b"),
]

_SYNONYMS = {
    "water temperature": "water-temperature", "temperature": "water-temperature", "warmer": "water-temperature",
    "conductivity": "electrical-conductivity", "ph": "ph", "dissolved oxygen": "dissolved-oxygen", "oxygen": "dissolved-oxygen",
    "nitrate": "nitrate", "nitrite": "nitrite", "ammonium": "ammonium", "chloride": "chloride", "sulphate": "sulphate",
    "sulfate": "sulphate", "no2": "no2", "nitrogen dioxide": "no2", "ozone": "o3", "o3": "o3", "pm10": "pm10",
    "pm2.5": "pm2-5", "pm 2.5": "pm2-5", "pm25": "pm2-5", "fine particulate": "pm2-5", "benzene": "benzene",
    "obesity": "obesity", "bmi": "bmi-above-30", "cardiovascular": "cvd", "cvd": "cvd", "heart disease": "cvd",
    "diabetes": "diabetes", "high blood pressure": "high-blood-pressure", "hypertension": "hypertension-treatment",
    "mental health": "mental-health", "long-term disease": "long-term-disease", "cadmium": "cadmium-dissolved",
    "lead": "lead-dissolved", "arsenic": "arsenic-dissolved", "mercury": "mercury-dissolved",
}


def _locations(text: str, ds: Dataset) -> list[tuple[int, str]]:
    found: list[tuple[int, str]] = []
    t = text.lower()
    for m in re.finditer(r"(?:benevento\s*(?:site\s*)?|site\s*)0?(\d{1,2})\b", t):
        lid = f"Loc-Benevento-{int(m.group(1)):02d}"
        if lid in ds.locations:
            found.append((m.start(), lid))
    names = {"almyros": "Loc-Almyros", "giofyros lower": "Loc-Giofyros-LowerReach", "giofyros": "Loc-Giofyros",
             "oslo": "Loc-Nordre-Aker", "nordre aker": "Loc-Nordre-Aker"}
    for name, lid in names.items():
        for m in re.finditer(rf"\b{name}\b", t):
            if lid in ds.locations and not any(abs(p - m.start()) < 3 for p, _ in found):
                found.append((m.start(), lid))
    if "benevento" in t and not any(lid.startswith("Loc-Benevento") for _, lid in found):
        found.append((t.index("benevento"), "Loc-Benevento-01"))
    return sorted(set(found))


def parse_deterministic(text: str, ds: Dataset, kn: Knowledge) -> ClaimIntent:
    t = " " + text.lower() + " "
    intent = ClaimIntent()
    for ctype, pat in _TYPE_PATTERNS:
        if re.search(pat, t):
            intent.type = ctype.value  # type: ignore[assignment]
            break
    hits: list[tuple[int, str]] = []
    for word, key in sorted(_SYNONYMS.items(), key=lambda kv: -len(kv[0])):
        for m in re.finditer(rf"(?<![a-z0-9]){re.escape(word)}(?![a-z0-9])", t):
            if key in kn.indicators and not any(s <= m.start() < s + 12 for s, _ in hits):
                hits.append((m.start(), key))
    keys = [k for _, k in sorted(hits)]
    keys = list(dict.fromkeys(keys))
    if keys:
        intent.indicator_key = keys[0]
    if len(keys) > 1:
        intent.outcome_indicator_key = keys[1]
    intent.locations = [lid for _, lid in _locations(text, ds)]
    years = [int(y) for y in re.findall(r"\b(19[5-9]\d|20[0-4]\d)\b", t)]
    if years:
        intent.year_from, intent.year_to = min(years), max(years)
    for stat, pat in (("median", r"\bmedian\b"), ("maximum", r"\b(max|maximum|peak)\b"), ("average", r"\b(mean|average)\b")):
        if re.search(pat, t):
            intent.statistic = stat  # type: ignore[assignment]
            break
    if re.search(r"\bwho\b", t):
        intent.threshold_hint = "who"
    elif re.search(r"\b(eu|directive|legal|limit value)\b", t):
        intent.threshold_hint = "eu"
    elif "drinking" in t:
        intent.threshold_hint = "drinking-water"
    return intent


def _pick(ds: Dataset, loc: str, ind: str | None, year: int | None) -> NormalizedObservation | None:
    cands = [o for o in ds.observations.values() if o.subject_ref == f"Location/{loc}" and o.indicator_key == ind
             and (year is None or o.year == year)]
    if not cands:
        return None
    def rank(o: NormalizedObservation) -> tuple[int, int, str]:
        g = ds.groups.get(o.focus_refs[0].split("/")[-1]) if o.focus_refs else None
        return (0 if g is None or (g.sex is None and g.age_low in (None, 0)) else 1, -(o.year or 0), o.id)
    return sorted(cands, key=rank)[0]


def resolve(intent: ClaimIntent, ds: Dataset, kn: Knowledge, text: str | None = None) -> tuple[StructuredClaim | None, list[str], list[str]]:
    understood, problems = [], []
    if intent.type is None:
        return None, understood, ["Could not tell what kind of claim this is (compare, trend, threshold, association or cause)."]
    ctype = ClaimType(intent.type)
    understood.append(f"claim type: {ctype.value}")
    if intent.indicator_key:
        understood.append(f"measure: {kn.indicators[intent.indicator_key].label}")
    if intent.locations:
        understood.append("places: " + ", ".join(ds.locations[x].name or x for x in intent.locations if x in ds.locations))
    year = intent.year_to or intent.year_from
    if ctype in (ClaimType.ASSOCIATION, ClaimType.CAUSAL):
        if not (intent.indicator_key and intent.outcome_indicator_key):
            return None, understood, ["An association/causal claim needs two measures (exposure and outcome)."]
        return StructuredClaim(type=ctype, indicator_key=intent.indicator_key, outcome_indicator_key=intent.outcome_indicator_key,
                               year_from=intent.year_from if ctype == ClaimType.ASSOCIATION and intent.year_from == intent.year_to else None,
                               text=text), understood, problems
    if not intent.indicator_key:
        return None, understood, ["No measure recognised (e.g. water temperature, NO2, PM2.5, obesity)."]
    if not intent.locations:
        return None, understood, ["No place recognised (e.g. Almyros, Giofyros, Benevento site 01, Oslo)."]
    if ctype == ClaimType.TREND_INCREASE:
        return StructuredClaim(type=ctype, location_id=intent.locations[0], indicator_key=intent.indicator_key,
                               statistic=intent.statistic or "average", year_from=intent.year_from, year_to=intent.year_to,
                               text=text), understood, problems
    if ctype == ClaimType.COMPARE_HIGHER:
        if len(intent.locations) < 2:
            return None, understood, ["A comparison needs two places."]
        a = _pick(ds, intent.locations[0], intent.indicator_key, year)
        b = _pick(ds, intent.locations[1], intent.indicator_key, year)
        if b is None:  # the second place may publish a related measure (e.g. Oslo: BMI >= 30 instead of 'obesity')
            for rel in kn.relations:
                if intent.indicator_key in (rel.a, rel.b) and rel.relationship in ("equivalent", "related") and rel.a != rel.b:
                    other = rel.b if rel.a == intent.indicator_key else rel.a
                    b = _pick(ds, intent.locations[1], other, year)
                    if b is not None:
                        understood.append(f"{ds.locations[intent.locations[1]].name} publishes the related measure "
                                          f"'{kn.indicators[other].label}' ({rel.relationship}; see comparability)")
                        break
        if a is None or b is None:
            miss = intent.locations[0] if a is None else intent.locations[1]
            return None, understood, [f"No {kn.indicators[intent.indicator_key].label} record for {miss}{f' in {year}' if year else ''}."]
        stat = intent.statistic or ("average" if a.stats else None)
        return StructuredClaim(type=ctype, subject=a.id, object=b.id, statistic=stat, text=text), understood, problems
    # EXCEEDS_THRESHOLD
    a = _pick(ds, intent.locations[0], intent.indicator_key, year)
    if a is None:
        return None, understood, [f"No {kn.indicators[intent.indicator_key].label} record found for that place/year."]
    cands = [t for t in kn.thresholds.values() if t["indicator"] == intent.indicator_key]
    pref = {"who": "who-", "eu": "eu-2008", "drinking-water": "eu-dwd"}.get(intent.threshold_hint or "", "")
    th = next((t for t in cands if t["id"].startswith(pref)), cands[0] if cands else None)
    if th is None:
        return None, understood, [f"No reference threshold is recorded for {kn.indicators[intent.indicator_key].label}."]
    understood.append(f"threshold: {th['source']}")
    return StructuredClaim(type=ctype, subject=a.id, statistic=intent.statistic or ("average" if a.stats else None),
                           threshold_id=th["id"], text=text), understood, problems


def parse_llm(text: str, ds: Dataset, kn: Knowledge, model: str) -> ClaimIntent:
    """Optional: ask Claude to fill a ClaimIntent. The verdict never depends on this call."""
    import anthropic

    client = anthropic.Anthropic(timeout=20.0, max_retries=1)
    vocab = {"indicator_keys": {k: v.label for k, v in kn.indicators.items()},
             "locations": {lid: loc.name for lid, loc in ds.locations.items() if loc.scope.value == "oah-ig"}}
    resp = client.messages.parse(
        model=model, max_tokens=2048, output_config={"effort": "low"},
        system="Map the research claim onto the given vocabulary. Use only keys and location ids that appear in it; "
               "leave a field null if the claim does not state it. Do not judge whether the claim is true.",
        messages=[{"role": "user", "content": f"Vocabulary: {vocab}\n\nClaim: {text}"}],
        output_format=ClaimIntent,
    )
    if resp.stop_reason == "refusal" or resp.parsed_output is None:
        raise ValueError("LLM did not return a claim intent")
    intent: ClaimIntent = resp.parsed_output
    # Never trust unknown keys from the model.
    if intent.indicator_key not in kn.indicators:
        intent.indicator_key = None
    if intent.outcome_indicator_key not in kn.indicators:
        intent.outcome_indicator_key = None
    intent.locations = [x for x in intent.locations if x in ds.locations]
    return intent


def parse_claim(text: str, ds: Dataset, kn: Knowledge, provider: str = "none", model: str = "claude-opus-5") -> ParseResult:
    method = "deterministic"
    intent = parse_deterministic(text, ds, kn)
    if provider == "anthropic":
        try:
            intent = parse_llm(text, ds, kn, model)
            method = f"llm:{model}"
        except Exception:  # noqa: BLE001 - any failure keeps the deterministic parse
            method = "deterministic (LLM unavailable)"
    claim, understood, problems = resolve(intent, ds, kn, text)
    return ParseResult(intent=intent, claim=claim, method=method, understood=understood, problems=problems)
