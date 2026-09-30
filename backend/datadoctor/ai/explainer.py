"""Plain-language explanations of ALREADY-COMPUTED findings (the only place an LLM may be used).

Contract (docs/AI_POLICY.md):
- the explainer receives a finding and returns prose; it never sees raw data and never decides anything;
- the deterministic TemplateExplainer is the default and the fallback;
- LLM output is rejected (-> template) if it contains any number that does not occur in the finding's evidence,
  or if the call fails, times out, or is refused;
- tests use MockExplainer; the product works fully with DD_LLM_PROVIDER=none.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Protocol

from pydantic import BaseModel

from datadoctor.domain.models import Finding

log = logging.getLogger(__name__)


class Explanation(BaseModel):
    text: str
    method: str  # template | llm:<model> | mock
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
    """Deterministic plain-language rendering. Always available; used whenever an LLM is off or fails."""

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
        try:
            out.add(round(float(m.replace(",", "")), 6))
        except ValueError:
            pass
    return out


def numbers_are_grounded(text: str, finding: Finding) -> bool:
    allowed = _numbers(json.dumps(_facts(finding), ensure_ascii=False)) | {round(x, 6) for x in range(0, 11)}
    allowed |= {round(float(o.value), 6) for o in finding.evidence.observed if isinstance(o.value, int | float)}
    return _numbers(text) <= allowed


class AnthropicExplainer:
    SYSTEM = ("You rewrite a data-quality finding for an environmental-health researcher in plain language. "
              "Use only the facts provided. Do not add numbers, causes, or recommendations that are not in the facts. "
              "Never state why a value is wrong: root cause is unknown unless the facts say otherwise. "
              "Write at most 120 words, no headings.")

    def __init__(self, model: str, timeout_s: float = 20.0) -> None:
        import anthropic  # optional dependency: pip install ".[ai]"

        self._anthropic = anthropic
        self._client = anthropic.Anthropic(timeout=timeout_s, max_retries=1)
        self._model = model
        self._fallback = TemplateExplainer()

    def explain(self, finding: Finding) -> Explanation:
        a = self._anthropic
        try:
            resp = self._client.messages.create(
                model=self._model, max_tokens=2048, system=self.SYSTEM, output_config={"effort": "low"},
                messages=[{"role": "user", "content": "Facts (JSON):\n" + json.dumps(_facts(finding), ensure_ascii=False)}],
            )
        except (a.APIStatusError, a.APIConnectionError, a.APITimeoutError) as exc:
            log.warning("LLM explanation failed: %s", exc)
            return self._fallback.explain(finding).model_copy(update={"fallback_reason": f"LLM call failed: {type(exc).__name__}"})
        if resp.stop_reason == "refusal":
            return self._fallback.explain(finding).model_copy(update={"fallback_reason": "LLM declined"})
        text = "".join(b.text for b in resp.content if b.type == "text").strip()
        if not text or not numbers_are_grounded(text, finding):
            return self._fallback.explain(finding).model_copy(update={"fallback_reason": "LLM output contained ungrounded numbers"})
        return Explanation(text=text, method=f"llm:{self._model}")


class MockExplainer:
    def __init__(self, text: str) -> None:
        self.text = text

    def explain(self, finding: Finding) -> Explanation:
        if not numbers_are_grounded(self.text, finding):
            return TemplateExplainer().explain(finding).model_copy(update={"fallback_reason": "LLM output contained ungrounded numbers"})
        return Explanation(text=self.text, method="mock")


def get_explainer(provider: str, model: str) -> Explainer:
    if provider == "anthropic":
        try:
            return AnthropicExplainer(model)
        except Exception as exc:  # noqa: BLE001 - missing package or credentials: stay deterministic
            log.warning("LLM explainer unavailable (%s); using templates", exc)
    return TemplateExplainer()
