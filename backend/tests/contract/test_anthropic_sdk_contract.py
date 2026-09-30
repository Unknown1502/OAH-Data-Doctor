"""Contract test for the optional (paid) Claude provider: our calls go through the real Anthropic SDK request builder
into a mock transport. No network, no credentials, no cost. Skipped when the SDK is not installed.
The free providers (Ollama, OpenAI-compatible) are covered in tests/unit/test_llm.py."""

import json

import pytest

anthropic = pytest.importorskip("anthropic")
httpx2 = pytest.importorskip("httpx2")

from datadoctor.ai.explainer import LLMExplainer  # noqa: E402
from datadoctor.ai.llm import AnthropicClient, LLMError  # noqa: E402
from datadoctor.claims import parser as claim_parser  # noqa: E402
from datadoctor.rules.registry import run_rule  # noqa: E402
from tests.helpers import KN, dataset, location, stats_obs  # noqa: E402

SENT: list[dict] = []


def _message(text: str, stop: str = "end_turn") -> dict:
    return {"id": "msg_test", "type": "message", "role": "assistant", "model": "claude-opus-5",
            "content": [{"type": "text", "text": text}] if text else [], "stop_reason": stop, "stop_sequence": None,
            "usage": {"input_tokens": 10, "output_tokens": 20}}


def _client(reply: dict) -> "anthropic.Anthropic":
    def handler(request):
        SENT.append(json.loads(request.content))
        return httpx2.Response(200, json=reply)

    return anthropic.Anthropic(api_key="test-key", max_retries=0,
                               http_client=anthropic.DefaultHttpxClient(transport=httpx2.MockTransport(handler)))


def _finding():
    ds = dataset(stats_obs("A", average=198000, maximum=211000, minimum=185000, std_dev=18385, median=19.8))
    return run_rule("SEM-STAT-001", ds, KN)[0]


def _claude(reply: dict, monkeypatch) -> AnthropicClient:
    SENT.clear()
    sdk_client = _client(reply)
    monkeypatch.setattr(anthropic, "Anthropic", lambda **kw: sdk_client)
    return AnthropicClient("claude-opus-5")


def _explainer(reply: dict, monkeypatch) -> LLMExplainer:
    return LLMExplainer(_claude(reply, monkeypatch))


def test_request_shape_and_grounded_answer_is_used(monkeypatch):
    ex = _explainer(_message("The median, 19.8, lies below the minimum, 185,000, so these values cannot all be right."), monkeypatch)
    out = ex.explain(_finding())
    assert out.method == "llm:anthropic:claude-opus-5"
    body = SENT[0]
    assert body["model"] == "claude-opus-5" and body["output_config"] == {"effort": "low"}
    assert "Never state why a value is wrong" in body["system"]
    facts = json.loads(body["messages"][0]["content"].split("\n", 1)[1])
    assert facts["rule"] == "SEM-STAT-001"  # only the finding's facts are sent, not raw FHIR


def test_invented_number_is_discarded(monkeypatch):
    out = _explainer(_message("The true temperature was probably 21.3 C."), monkeypatch).explain(_finding())
    assert out.method == "template" and "ungrounded" in (out.fallback_reason or "")


def test_refusal_falls_back_to_template(monkeypatch):
    out = _explainer(_message("", stop="refusal"), monkeypatch).explain(_finding())
    assert out.method == "template" and out.fallback_reason == "LLM declined"


def test_structured_claim_parse_through_sdk(monkeypatch):
    intent = {"type": "TREND_INCREASE", "indicator_key": "water-temperature", "outcome_indicator_key": None,
              "locations": ["Loc-Almyros", "Loc-invented"], "year_from": 2013, "year_to": 2020, "statistic": None,
              "threshold_hint": None}
    client = _claude(_message(json.dumps(intent)), monkeypatch)
    ds = dataset(location("Loc-Almyros"), stats_obs("T13", average=19.8, maximum=21.1, minimum=18.5, median=19.8, location="Loc-Almyros"))
    got = claim_parser.parse_llm("Almyros water got warmer from 2013 to 2020", ds, KN, client)
    assert got.type == "TREND_INCREASE" and got.indicator_key == "water-temperature"
    assert got.locations == ["Loc-Almyros"]  # unknown ids proposed by the model are dropped
    assert SENT[0]["output_config"]["effort"] == "low" and "format" in SENT[0]["output_config"]


def test_model_without_effort_setting_is_retried_without_it(monkeypatch):
    SENT.clear()
    calls = {"n": 0}

    def handler(request):
        SENT.append(json.loads(request.content))
        calls["n"] += 1
        if "output_config" in SENT[-1]:
            return httpx2.Response(400, json={"type": "error", "error": {"type": "invalid_request_error",
                                                                          "message": "output_config.effort: not supported by this model"}})
        return httpx2.Response(200, json=_message("OK"))

    sdk = anthropic.Anthropic(api_key="test-key", max_retries=0,
                              http_client=anthropic.DefaultHttpxClient(transport=httpx2.MockTransport(handler)))
    monkeypatch.setattr(anthropic, "Anthropic", lambda **kw: sdk)
    assert AnthropicClient("claude-haiku-4-5").complete("s", "u") == "OK"
    assert calls["n"] == 2 and "output_config" not in SENT[1]


def test_rejected_key_gives_a_readable_error(monkeypatch):
    def handler(request):
        return httpx2.Response(401, json={"type": "error", "error": {"type": "authentication_error", "message": "invalid x-api-key"}})

    sdk = anthropic.Anthropic(api_key="test-key", max_retries=0,
                              http_client=anthropic.DefaultHttpxClient(transport=httpx2.MockTransport(handler)))
    monkeypatch.setattr(anthropic, "Anthropic", lambda **kw: sdk)
    with pytest.raises(LLMError, match="Check the API key"):
        AnthropicClient("claude-opus-5").complete("s", "u")
