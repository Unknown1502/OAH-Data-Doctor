"""Plain-language explanations of ALREADY-COMPUTED findings (the only place a language model may write prose).

Contract (docs/AI_POLICY.md):
- the explainer receives a finding and returns prose; the model never sees raw data and never decides anything;
- the deterministic TemplateExplainer is the default and the fallback;
- model output is rejected (-> template) if it contains any number that does not occur in the finding's evidence,
  or if the call fails, times out, or is refused;
- any provider works (ai/llm.py): a free local model through Ollama, a free OpenAI-compatible endpoint, or Claude;
- tests use MockExplainer / fake clients; the product works fully with DD_LLM_PROVIDER=none.
"""

from __future__ import annotations

import contextlib
import json
import logging
import re
from typing import Protocol

from pydantic import BaseModel

from datadoctor.ai.llm import LLMClient, LLMError
from datadoctor.domain.models import Finding

log = logging.getLogger(__name__)


class Explanation(BaseModel):
    text: str
    method: str  # template | llm:<provider:model> | mock
    fallback_reason: str | None = None


class Explainer(Protocol):
    def explain(self, finding: Finding) -> Explanation: ...


def _facts(f: Finding) -> dict:
    return {
        "rule": f.rule_id, "title": f.title, "severity": f.severity.value, "confidence": f.confidence_label,
        "record": f.resource.display or f.resource.key, "summary": f.summary,
        "constraint": f.evidence.constraint, "expected": f.evidence.expected,
        "observed": [{"label": o.label, "value": o.value, "unit": o.unit} for o in f.evidence.observed[:10]],
        "interpretation": f.interpretation, "hypotheses": f.hypotheses, "remediation": f.remediation,
        "lineage": f.lineage.statement if f.lineage else None,
    }


class TemplateExplainer:
    """Deterministic plain-language rendering. Always available; used whenever a model is off or fails."""

    def explain(self, finding: Finding) -> Explanation:
        f = finding
        parts = [f"What we saw: {f.summary}",
                 f"Why it matters: {f.evidence.expected} Here that does not hold ({f.evidence.constraint}).",
                 f"What it means: {f.interpretation} Confidence is {f.confidence_label} ({f.confidence})."]
        if f.lineage:
            parts.append(f"Where it comes from: {f.lineage.statement}")
        if f.hypotheses:
            parts.append("Possible explanations (not verified): " + " ".join(f.hypotheses))
        parts.append(f"What to do: {f.remediation}")
        return Explanation(text="\n\n".join(parts), method="template")


_NUM = re.compile(r"-?\d[\d,]*\.?\d*")


def _numbers(text: str) -> set[float]:
    out = set()
    for m in _NUM.findall(text):
        with contextlib.suppress(ValueError):
            out.add(round(float(m.replace(",", "")), 6))
    return out


_CAUSE = re.compile(r"\b(because|due to|caused by|as a result of|the reason|typo|mistyped|entered wrong\w*|"
                    r"data[- ]entry error|correction needed|must be corrected|should be corrected|needs? (?:to be )?correct\w*)\b",
                    re.I)


_CONNECTIVE = {"because", "due to", "caused by", "as a result of"}
_HEDGE = re.compile(r"\b(could|might|may|possibly|perhaps|potentially)\b(?:\s+(?:also\s+)?be)?\s*$", re.I)


def adds_cause_or_correction(text: str, finding: Finding) -> bool:
    """True if the text asserts a cause or a correction that the finding's facts do not contain (policy: root cause
    unknown; never auto-correct). A deterministic safety net for small models that drift in meaning.

    A hedged cause ("this could be due to ...") is tolerated only when the finding itself lists unverified hypotheses;
    a flat assertion ("this is due to ...") or an accusation or correction ("typo", "correction needed") never is."""
    facts = json.dumps(_facts(finding), ensure_ascii=False).lower()
    for m in _CAUSE.finditer(text):
        phrase = m.group(0).lower()
        if phrase in facts:
            continue
        if phrase in _CONNECTIVE and finding.hypotheses and _HEDGE.search(text[max(0, m.start() - 30):m.start()]):
            continue
        return True
    return False


def numbers_are_grounded(text: str, finding: Finding) -> bool:
    allowed = _numbers(json.dumps(_facts(finding), ensure_ascii=False)) | {round(x, 6) for x in range(0, 11)}
    allowed |= {round(float(o.value), 6) for o in finding.evidence.observed if isinstance(o.value, int | float)}
    return _numbers(text) <= allowed


SYSTEM = ("You rewrite a data-quality finding for an environmental-health researcher in plain language. "
          "Use only the facts provided. Do not add numbers, causes, or recommendations that are not in the facts. "
          "Never state why a value is wrong: root cause is unknown unless the facts say otherwise. Do not write \"because\", "
          "\"due to\" or \"caused by\"; mention a possible explanation only as unverified. "
          "Write at most 120 words, no headings, no lists.")


class LLMExplainer:
    """Rephrases a finding with any configured model; falls back to the template on any problem."""

    def __init__(self, client: LLMClient) -> None:
        self._client = client
        self._fallback = TemplateExplainer()

    def explain(self, finding: Finding) -> Explanation:
        try:
            text = self._client.complete(SYSTEM, "Facts (JSON):\n" + json.dumps(_facts(finding), ensure_ascii=False), max_tokens=400)
        except LLMError as exc:
            log.warning("LLM explanation failed: %s", exc)
            return self._fallback.explain(finding).model_copy(update={"fallback_reason": str(exc)[:200]})
        if not text:
            return self._fallback.explain(finding).model_copy(update={"fallback_reason": "LLM returned no text"})
        reason = ("LLM output contained ungrounded numbers" if not numbers_are_grounded(text, finding)
                  else "LLM output asserted a cause or correction" if adds_cause_or_correction(text, finding) else None)
        if reason:
            log.info("Rephrasing of %s discarded (%s): %s", finding.id, reason, text[:400])
            return self._fallback.explain(finding).model_copy(update={"fallback_reason": reason})
        return Explanation(text=text, method=f"llm:{self._client.name}")


class MockExplainer:
    def __init__(self, text: str) -> None:
        self.text = text

    def explain(self, finding: Finding) -> Explanation:
        if not numbers_are_grounded(self.text, finding):
            return TemplateExplainer().explain(finding).model_copy(update={"fallback_reason": "LLM output contained ungrounded numbers"})
        return Explanation(text=self.text, method="mock")


def get_explainer(client: LLMClient | None) -> Explainer:
    return LLMExplainer(client) if client is not None else TemplateExplainer()
