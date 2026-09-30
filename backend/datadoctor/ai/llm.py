"""Provider-neutral access to an OPTIONAL language model. Nothing in Data Doctor's verdicts depends on it.

Providers (DD_LLM_PROVIDER):
  none               default: no model, deterministic templates only
  ollama             free, local (https://ollama.com). Default model qwen2.5:3b; `ollama pull qwen2.5:3b`
  openai-compatible  any /chat/completions endpoint, e.g. free tiers of Groq, Google Gemini (OpenAI-compatible
                     endpoint) or OpenRouter; set DD_LLM_BASE_URL, DD_LLM_API_KEY and DD_LLM_MODEL
  anthropic          Claude via the official SDK (paid)

Every client offers `complete` (free text) and `complete_json` (validated against a Pydantic model). Callers treat any
LLMError as "use the deterministic fallback".
"""

from __future__ import annotations

import json
import re
from typing import Any, Protocol, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from datadoctor.config import Settings

M = TypeVar("M", bound=BaseModel)

DEFAULT_MODELS = {"ollama": "qwen2.5:3b", "anthropic": "claude-opus-5"}
_THINK = re.compile(r"<think>.*?</think>", re.S)


class LLMError(RuntimeError):
    pass


class LLMClient(Protocol):
    name: str

    def complete(self, system: str, user: str, *, max_tokens: int = 1024) -> str: ...

    def complete_json(self, system: str, user: str, model_cls: type[M]) -> M: ...


def _clean(text: str) -> str:
    """Drop reasoning traces some local models emit, and markdown fences around JSON."""
    text = _THINK.sub("", text).strip()
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.S)
    return fence.group(1).strip() if fence else text


def _validate(raw: str, model_cls: type[M]) -> M:
    try:
        return model_cls.model_validate(json.loads(_clean(raw)))
    except (json.JSONDecodeError, ValidationError) as exc:
        raise LLMError(f"model output is not valid {model_cls.__name__} JSON: {str(exc)[:160]}") from exc


def _schema_prompt(system: str, model_cls: type[BaseModel]) -> str:
    return (f"{system}\n\nReply with a single JSON object only, no prose, matching this JSON Schema:\n"
            f"{json.dumps(model_cls.model_json_schema())}")


class OllamaClient:
    """Ollama's native chat API. `format` constrains output to the JSON Schema (Ollama >= 0.5)."""

    def __init__(self, model: str, base_url: str = "http://localhost:11434", timeout_s: float = 120.0,
                 transport: httpx.BaseTransport | None = None) -> None:
        self.model = model
        self.name = f"ollama:{model}"
        self._http = httpx.Client(base_url=base_url.rstrip("/"), timeout=timeout_s, transport=transport)

    def _chat(self, system: str, user: str, *, max_tokens: int, fmt: dict[str, Any] | None = None) -> str:
        body: dict[str, Any] = {"model": self.model, "stream": False, "keep_alive": "30m",  # stay loaded: cold start ~45 s
                                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                                "options": {"temperature": 0, "seed": 7, "num_predict": max_tokens}}  # repeatable
        if fmt is not None:
            body["format"] = fmt
        try:
            r = self._http.post("/api/chat", json=body)
        except httpx.HTTPError as exc:
            raise LLMError(f"Ollama is not reachable at {self._http.base_url} ({type(exc).__name__}); start it with `ollama serve`") from exc
        if r.status_code != 200:
            detail = r.json().get("error", r.text) if r.headers.get("content-type", "").startswith("application/json") else r.text
            hint = f"; run `ollama pull {self.model}`" if "not found" in str(detail) else ""
            raise LLMError(f"Ollama error: {str(detail)[:160]}{hint}")
        return str(r.json().get("message", {}).get("content", ""))

    def complete(self, system: str, user: str, *, max_tokens: int = 1024) -> str:
        return _clean(self._chat(system, user, max_tokens=max_tokens))

    def complete_json(self, system: str, user: str, model_cls: type[M]) -> M:
        return _validate(self._chat(_schema_prompt(system, model_cls), user, max_tokens=1024,
                                    fmt=model_cls.model_json_schema()), model_cls)


class OpenAICompatibleClient:
    """Any OpenAI-style /chat/completions endpoint (Groq, Gemini's OpenAI-compatible API, OpenRouter, vLLM, LM Studio...)."""

    def __init__(self, model: str, base_url: str, api_key: str | None, timeout_s: float = 60.0,
                 transport: httpx.BaseTransport | None = None) -> None:
        if not base_url:
            raise LLMError("DD_LLM_BASE_URL is required for the openai-compatible provider")
        self.model = model
        self.name = f"{httpx.URL(base_url).host}:{model}"
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self._http = httpx.Client(base_url=base_url.rstrip("/"), timeout=timeout_s, headers=headers, transport=transport)

    def _chat(self, system: str, user: str, *, max_tokens: int, json_mode: bool) -> str:
        body: dict[str, Any] = {"model": self.model, "temperature": 0, "max_tokens": max_tokens,
                                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        try:
            r = self._http.post("/chat/completions", json=body)
        except httpx.HTTPError as exc:
            raise LLMError(f"LLM endpoint not reachable ({type(exc).__name__})") from exc
        if r.status_code != 200:
            raise LLMError(f"LLM endpoint returned HTTP {r.status_code}: {r.text[:160]}")
        choices = r.json().get("choices") or [{}]
        return str((choices[0].get("message") or {}).get("content") or "")

    def complete(self, system: str, user: str, *, max_tokens: int = 1024) -> str:
        return _clean(self._chat(system, user, max_tokens=max_tokens, json_mode=False))

    def complete_json(self, system: str, user: str, model_cls: type[M]) -> M:
        return _validate(self._chat(_schema_prompt(system, model_cls), user, max_tokens=1024, json_mode=True), model_cls)


class AnthropicClient:
    """Claude through the official SDK (optional dependency: pip install ".[ai]")."""

    def __init__(self, model: str, timeout_s: float = 20.0) -> None:
        import anthropic

        self._anthropic = anthropic
        self._client = anthropic.Anthropic(timeout=timeout_s, max_retries=1)
        self.model = model
        self.name = f"anthropic:{model}"

    def complete(self, system: str, user: str, *, max_tokens: int = 2048) -> str:
        a = self._anthropic
        try:
            resp = self._client.messages.create(model=self.model, max_tokens=max_tokens, system=system,
                                                output_config={"effort": "low"}, messages=[{"role": "user", "content": user}])
        except (a.APIStatusError, a.APIConnectionError, a.APITimeoutError) as exc:
            raise LLMError(f"Claude call failed: {type(exc).__name__}") from exc
        if resp.stop_reason == "refusal":
            raise LLMError("LLM declined")
        return "".join(b.text for b in resp.content if b.type == "text").strip()

    def complete_json(self, system: str, user: str, model_cls: type[M]) -> M:
        a = self._anthropic
        try:
            resp = self._client.messages.parse(model=self.model, max_tokens=2048, system=system, output_config={"effort": "low"},
                                               messages=[{"role": "user", "content": user}], output_format=model_cls)
        except (a.APIStatusError, a.APIConnectionError, a.APITimeoutError) as exc:
            raise LLMError(f"Claude call failed: {type(exc).__name__}") from exc
        if resp.stop_reason == "refusal" or resp.parsed_output is None:
            raise LLMError("LLM declined")
        return resp.parsed_output


def get_llm(settings: Settings) -> LLMClient | None:
    """The configured client, or None when no model is configured or it cannot be constructed."""
    provider = settings.llm_provider
    model = settings.llm_model or DEFAULT_MODELS.get(provider, "")
    try:
        if provider == "ollama":
            return OllamaClient(model, settings.llm_base_url or "http://localhost:11434", settings.llm_timeout_s)
        if provider == "openai-compatible":
            return OpenAICompatibleClient(model, settings.llm_base_url or "", settings.llm_api_key, settings.llm_timeout_s)
        if provider == "anthropic":
            return AnthropicClient(model)
    except Exception:  # noqa: BLE001 - misconfiguration or missing package: stay deterministic
        return None
    return None
