"""The optional language-model layer: free providers (Ollama, OpenAI-compatible) through mock transports, the honesty
guards on rephrased text, and the rules-first claim reading. No network, no model, no cost."""

import json
from dataclasses import replace

import httpx
import pytest

from datadoctor.ai.explainer import LLMExplainer, adds_cause_or_correction, get_explainer
from datadoctor.ai.llm import LLMError, OllamaClient, OpenAICompatibleClient, _clean, get_llm
from datadoctor.claims.parser import ClaimIntent, parse_claim, parse_deterministic
from datadoctor.config import Settings
from datadoctor.rules.registry import run_rule
from tests.helpers import KN, dataset, location, stats_obs

SENT: list[httpx.Request] = []


def _transport(status: int, payload: dict) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        SENT.append(request)
        return httpx.Response(status, json=payload)

    SENT.clear()
    return httpx.MockTransport(handler)


def _finding():
    ds = dataset(stats_obs("A", average=198000, maximum=211000, minimum=185000, std_dev=18385, median=19.8))
    return run_rule("SEM-STAT-001", ds, KN)[0]


class FakeClient:
    name = "fake:model"

    def __init__(self, text: str = "", intent: dict | None = None, error: str | None = None) -> None:
        self.text, self.intent, self.error = text, intent or {}, error

    def complete(self, system: str, user: str, *, max_tokens: int = 1024) -> str:
        if self.error:
            raise LLMError(self.error)
        return self.text

    def complete_json(self, system, user, model_cls):
        if self.error:
            raise LLMError(self.error)
        return model_cls.model_validate(self.intent)


# --- providers -------------------------------------------------------------------------------------------------


def test_clean_strips_reasoning_and_fences():
    assert _clean("<think>hmm, 42?</think>\nPlain answer.") == "Plain answer."
    assert _clean('```json\n{"a": 1}\n```') == '{"a": 1}'


def test_ollama_request_is_local_deterministic_and_schema_constrained():
    reply = {"message": {"role": "assistant", "content": json.dumps({"type": "TREND_INCREASE", "indicator_key": "o3"})}}
    c = OllamaClient("qwen2.5:3b", transport=_transport(200, reply))
    got = c.complete_json("sys", "claim", ClaimIntent)
    assert got.type == "TREND_INCREASE" and c.name == "ollama:qwen2.5:3b"
    req = SENT[0]
    body = json.loads(req.content)
    assert req.url.path == "/api/chat" and str(req.url).startswith("http://localhost:11434")
    assert body["stream"] is False and body["options"]["temperature"] == 0 and "seed" in body["options"]
    assert body["format"] == ClaimIntent.model_json_schema()  # output constrained to the schema
    assert "Authorization" not in req.headers  # local: no key


def test_ollama_missing_model_says_how_to_fix():
    c = OllamaClient("qwen2.5:3b", transport=_transport(404, {"error": "model 'qwen2.5:3b' not found"}))
    with pytest.raises(LLMError, match="ollama pull qwen2.5:3b"):
        c.complete("sys", "hi")


def test_ollama_not_running_is_an_llm_error():
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    with pytest.raises(LLMError, match="ollama serve"):
        OllamaClient("m", transport=httpx.MockTransport(refuse)).complete("sys", "hi")


def test_openai_compatible_request_shape():
    reply = {"choices": [{"message": {"role": "assistant", "content": "Plain text."}}]}
    c = OpenAICompatibleClient("llama-3.1-8b-instant", "https://api.groq.com/openai/v1", "k-test", transport=_transport(200, reply))
    assert c.complete("sys", "hi") == "Plain text."
    assert c.name == "api.groq.com:llama-3.1-8b-instant"
    req = SENT[0]
    assert req.url.path == "/openai/v1/chat/completions" and req.headers["Authorization"] == "Bearer k-test"
    body = json.loads(req.content)
    assert body["temperature"] == 0 and "response_format" not in body


def test_openai_compatible_json_mode_and_errors():
    good = {"choices": [{"message": {"content": '```json\n{"type": "CAUSAL"}\n```'}}]}
    c = OpenAICompatibleClient("m", "http://localhost:1234/v1", None, transport=_transport(200, good))
    assert c.complete_json("sys", "claim", ClaimIntent).type == "CAUSAL"
    assert json.loads(SENT[0].content)["response_format"] == {"type": "json_object"}
    assert "Authorization" not in SENT[0].headers
    with pytest.raises(LLMError, match="HTTP 429"):
        OpenAICompatibleClient("m", "http://x/v1", "k", transport=_transport(429, {"error": "rate limited"})).complete("s", "u")
    bad = {"choices": [{"message": {"content": "Sure! The claim is a trend."}}]}
    with pytest.raises(LLMError, match="not valid ClaimIntent"):
        OpenAICompatibleClient("m", "http://x/v1", "k", transport=_transport(200, bad)).complete_json("s", "u", ClaimIntent)


def test_get_llm_selects_provider_and_never_raises():
    base = Settings()
    assert get_llm(base) is None
    ollama = get_llm(replace(base, llm_provider="ollama"))
    assert isinstance(ollama, OllamaClient) and ollama.name == "ollama:qwen2.5:3b"
    assert get_llm(replace(base, llm_provider="ollama", llm_model="llama3.2:3b")).name == "ollama:llama3.2:3b"
    assert get_llm(replace(base, llm_provider="openai-compatible")) is None  # no base URL: misconfigured -> deterministic
    hosted = get_llm(replace(base, llm_provider="openai-compatible", llm_model="m", llm_base_url="https://api.groq.com/openai/v1"))
    assert isinstance(hosted, OpenAICompatibleClient) and hosted.name == "groq:m"  # a known endpoint is named after its provider
    other = get_llm(replace(base, llm_provider="openai-compatible", llm_model="m", llm_base_url="http://localhost:1234/v1"))
    assert other is not None and other.name == "localhost:m"
    assert get_llm(replace(base, llm_provider="something-else")) is None


# --- explanations ----------------------------------------------------------------------------------------------


def test_llm_explainer_accepts_grounded_faithful_text():
    out = LLMExplainer(FakeClient("The median, 19.8, lies below the minimum, 185,000, so these values cannot all be right.")).explain(_finding())
    assert out.method == "llm:fake:model" and out.fallback_reason is None


@pytest.mark.parametrize("text", [
    "The minimum of 185,000 is wrong because the unit was entered as mK instead of Cel.",
    "This is probably a typo in the median.",
    "Correction needed: the median should read 198,000.",
    "The values must be corrected before use.",
])
def test_llm_explainer_rejects_invented_causes_and_corrections(text):
    f = _finding()
    assert adds_cause_or_correction(text, f)
    out = LLMExplainer(FakeClient(text)).explain(f)
    assert out.method == "template" and out.fallback_reason


def test_cause_guard_does_not_block_neutral_wording():
    assert not adds_cause_or_correction("The median, 19.8, lies below the minimum, 185,000. Ask the data owner.", _finding())


def test_hedged_cause_is_tolerated_only_when_the_finding_lists_hypotheses():
    # Shaped like the real Almyros aluminium record: an exact power-of-ten gap comes with an unverified hypothesis.
    ds = dataset(stats_obs("Al", average=150000, maximum=200000, minimum=100000, median=10))
    f = run_rule("SEM-STAT-001", ds, KN)[0]
    assert f.hypotheses
    assert not adds_cause_or_correction("This could be due to a unit or decimal separator error somewhere upstream.", f)
    assert not adds_cause_or_correction("It might be because of a unit mix-up.", f)
    assert adds_cause_or_correction("This is due to a unit error.", f)  # flat assertion
    assert adds_cause_or_correction("This could be a typo.", f)  # accusation, hedged or not
    assert adds_cause_or_correction("This could be due to a unit error.", f.model_copy(update={"hypotheses": []}))


def test_llm_failure_or_silence_falls_back_to_template():
    f = _finding()
    down = LLMExplainer(FakeClient(error="Ollama is not reachable")).explain(f)
    assert down.method == "template" and "not reachable" in (down.fallback_reason or "")
    assert LLMExplainer(FakeClient("")).explain(f).fallback_reason == "LLM returned no text"
    assert get_explainer(None).explain(f).method == "template"


# --- claim reading ---------------------------------------------------------------------------------------------


def _claim_ds():
    return dataset(location("Loc-Almyros"), location("Loc-Benevento-01"), location("Loc-Benevento-02"),
                   stats_obs("T13", average=19.8, median=19.8, location="Loc-Almyros", year=2013))


@pytest.mark.parametrize(("text", "ctype"), [
    ("Almyros water got warmer between 2013 and 2020", "TREND_INCREASE"),
    ("Water temperature at Almyros became hotter since 2013", "TREND_INCREASE"),
    ("Water at Almyros is warmer than at Benevento site 02", "COMPARE_HIGHER"),
    ("Fine particles make people in Benevento sick with heart disease", "CAUSAL"),
    ("Ozone harms the heart", "CAUSAL"),
    ("PM10 at site 04 was above the WHO annual guideline", "EXCEEDS_THRESHOLD"),
    ("Obesity is linked to NO2", "ASSOCIATION"),
])
def test_deterministic_claim_types(text, ctype):
    assert parse_deterministic(text, _claim_ds(), KN).type == ctype


def test_fine_particles_means_pm2_5():
    it = parse_deterministic("Fine particles make people in Benevento sick with heart disease", _claim_ds(), KN)
    assert (it.indicator_key, it.outcome_indicator_key) == ("pm2-5", "cvd")


def test_rules_win_and_model_only_fills_gaps():
    ds = _claim_ds()
    # The model misreads the type and proposes an invented location; the rules' reading stands.
    wrong = FakeClient(intent={"type": "COMPARE_HIGHER", "indicator_key": None, "locations": ["Loc-Atlantis"], "statistic": "median"})
    res = parse_claim("Almyros water got warmer between 2013 and 2020", ds, KN, wrong)
    assert res.intent.type == "TREND_INCREASE" and res.intent.locations == ["Loc-Almyros"]
    assert res.intent.statistic == "median"  # a field the rules did not find is taken from the model
    assert res.method in ("llm:fake:model", "deterministic (model reading did not resolve)")
    # The rules cannot tell the claim type here; the model can.
    fill = FakeClient(intent={"type": "ASSOCIATION", "indicator_key": "o3", "outcome_indicator_key": "diabetes"})
    res = parse_claim("Ozone and diabetes in Benevento", ds, KN, fill)
    assert parse_deterministic("Ozone and diabetes in Benevento", ds, KN).type is None
    assert res.intent.type == "ASSOCIATION"


def test_model_unavailable_means_deterministic_reading():
    res = parse_claim("Almyros water got warmer between 2013 and 2020", _claim_ds(), KN, FakeClient(error="Ollama is not reachable"))
    assert res.method.startswith("deterministic (language model unavailable")
    assert res.intent.type == "TREND_INCREASE"


# --- bring your own key -----------------------------------------------------------------------------------------

KEY = "gsk_live_abcdef123456"


def _cfg(**kw):
    from datadoctor.ai.llm import LLMConfig

    return LLMConfig(**kw)


def test_user_config_builds_the_preset_client_with_the_users_key():
    from datadoctor.ai.llm import client_from_config

    reply = {"choices": [{"message": {"content": "OK"}}]}
    c = client_from_config(_cfg(provider="groq", api_key=KEY), Settings(), transport=_transport(200, reply))
    assert c.name == "groq:llama-3.1-8b-instant"  # the preset's default model
    assert c.complete("s", "u") == "OK"
    assert str(SENT[0].url) == "https://api.groq.com/openai/v1/chat/completions"
    assert SENT[0].headers["Authorization"] == f"Bearer {KEY}"
    assert KEY not in repr(_cfg(provider="groq", api_key=KEY))  # SecretStr


@pytest.mark.parametrize(("cfg", "settings", "msg"), [
    ({"provider": "nope"}, {}, "Unknown provider"),
    ({"provider": "gemini"}, {}, "needs an API key"),
    ({"provider": "groq", "api_key": "has space"}, {}, "does not look like an API key"),
    ({"provider": "groq", "api_key": KEY, "model": "bad model!"}, {}, "model name"),
    ({"provider": "custom", "base_url": "http://169.254.169.254/latest"}, {}, "switched off"),
    ({"provider": "custom", "model": "m", "base_url": "file:///etc/passwd"}, {"llm_allow_custom_url": True}, "base URL"),
    ({"provider": "groq", "api_key": KEY}, {"llm_allow_user_keys": False}, "does not accept"),
])
def test_user_config_is_validated(cfg, settings, msg):
    from datadoctor.ai.llm import client_from_config

    with pytest.raises(LLMError, match=msg):
        client_from_config(_cfg(**cfg), replace(Settings(), **settings))


def test_custom_endpoint_when_the_operator_allows_it():
    from datadoctor.ai.llm import client_from_config, presets_for

    assert "custom" not in [p["id"] for p in presets_for(Settings())]
    allowed = replace(Settings(), llm_allow_custom_url=True)
    assert "custom" in [p["id"] for p in presets_for(allowed)]
    c = client_from_config(_cfg(provider="custom", model="local-model", base_url="http://localhost:1234/v1"), allowed,
                           transport=_transport(200, {"choices": [{"message": {"content": "OK"}}]}))
    c.complete("s", "u")
    assert str(SENT[0].url) == "http://localhost:1234/v1/chat/completions" and "Authorization" not in SENT[0].headers


def test_rejected_key_is_redacted_from_errors():
    c = OpenAICompatibleClient("m", "https://api.example.org/v1", KEY,
                               transport=_transport(401, {"error": {"message": f"Invalid API Key: {KEY}"}}))
    with pytest.raises(LLMError) as exc:
        c.complete("s", "u")
    assert "HTTP 401" in str(exc.value) and KEY not in str(exc.value) and "***" in str(exc.value)


def test_retries_without_parameters_the_model_rejects():
    calls: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        calls.append(body)
        if "temperature" in body:
            return httpx.Response(400, json={"error": {"message": "Unsupported value: 'temperature' does not support 0"}})
        return httpx.Response(200, json={"choices": [{"message": {"content": "OK"}}]})

    c = OpenAICompatibleClient("reasoning-model", "https://api.example.org/v1", "k", transport=httpx.MockTransport(handler))
    assert c.complete("s", "u") == "OK"
    assert len(calls) == 2 and "temperature" not in calls[1]


def test_model_listing_is_best_effort():
    listing = {"data": [{"id": "b-model"}, {"id": "a-model"}]}
    assert OpenAICompatibleClient("m", "https://x.org/v1", "k", transport=_transport(200, listing)).list_models() == ["a-model", "b-model"]
    assert OpenAICompatibleClient("m", "https://x.org/v1", "k", transport=_transport(403, {})).list_models() == []
    tags = {"models": [{"name": "qwen2.5:3b"}]}
    assert OllamaClient("m", transport=_transport(200, tags)).list_models() == ["qwen2.5:3b"]
