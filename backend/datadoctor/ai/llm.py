"""Provider-neutral access to an OPTIONAL language model. Nothing in Data Doctor's verdicts depends on it.

Providers (DD_LLM_PROVIDER, the server default):
  none               default: no model, deterministic templates only
  ollama             free, local (https://ollama.com). Default model qwen2.5:3b; `ollama pull qwen2.5:3b`
  openai-compatible  any /chat/completions endpoint, e.g. free tiers of Groq, Google Gemini (OpenAI-compatible
                     endpoint) or OpenRouter; set DD_LLM_BASE_URL, DD_LLM_API_KEY and DD_LLM_MODEL
  anthropic          Claude via the official SDK (paid)

Users can also bring their own key from the UI (LLMConfig + PRESETS below). Such a key travels with that user's request
only; it is never stored on the server, never logged, and redacted from any error message.

Every client offers `complete` (free text) and `complete_json` (validated against a Pydantic model). Callers treat any
LLMError as "use the deterministic fallback".
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from typing import Any, Protocol, TypeVar

import httpx
from pydantic import BaseModel, Field, SecretStr, ValidationError

from datadoctor.config import Settings

M = TypeVar("M", bound=BaseModel)

DEFAULT_MODELS = {"ollama": "qwen2.5:3b", "anthropic": "claude-opus-5"}
_THINK = re.compile(r"<think>.*?</think>", re.S)
_MODEL_ID = re.compile(r"^[\w.:/@+-]{1,200}$")


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


def _redact(text: str, secret: str | None) -> str:
    """Providers sometimes echo the key they rejected; never let it reach a log line or the UI."""
    if secret and len(secret) >= 4:
        text = text.replace(secret, "***")
    return text


def _http_error(r: httpx.Response, key: str | None) -> LLMError:
    """A readable, key-free message from a provider's error response (OpenAI style, or Gemini's list form)."""
    detail: Any = r.text[:200]
    try:
        body = r.json()
        body = body[0] if isinstance(body, list) and body else body
        if isinstance(body, dict):
            err = body.get("error")
            detail = (err.get("message") if isinstance(err, dict) else err) or body.get("message") or detail
    except ValueError:
        pass
    hint = {401: " Check the API key.", 403: " Check the API key and its permissions.",
            404: " Check the model name.", 429: " Rate limit reached; try again shortly."}.get(r.status_code, "")
    return LLMError(_redact(f"HTTP {r.status_code} from the provider: {str(detail).strip()[:200]}.{hint}", key))


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

    def list_models(self) -> list[str]:
        try:
            r = self._http.get("/api/tags")
            return sorted(m["name"] for m in r.json().get("models", [])) if r.status_code == 200 else []
        except (httpx.HTTPError, ValueError, KeyError):
            return []

    def close(self) -> None:
        self._http.close()


class OpenAICompatibleClient:
    """Any OpenAI-style /chat/completions endpoint (Groq, Gemini's OpenAI-compatible API, OpenRouter, Mistral, OpenAI,
    LM Studio, vLLM...)."""

    def __init__(self, model: str, base_url: str, api_key: str | None, timeout_s: float = 60.0,
                 transport: httpx.BaseTransport | None = None, name: str | None = None) -> None:
        if not base_url:
            raise LLMError("DD_LLM_BASE_URL is required for the openai-compatible provider")
        self.model = model
        self.name = name or f"{httpx.URL(base_url).host}:{model}"
        self._key = api_key
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self._http = httpx.Client(base_url=base_url.rstrip("/") + "/", timeout=timeout_s, headers=headers, transport=transport)

    def _post(self, body: dict[str, Any]) -> httpx.Response:
        try:
            return self._http.post("chat/completions", json=body)
        except httpx.HTTPError as exc:
            raise LLMError(f"LLM endpoint not reachable ({type(exc).__name__})") from exc

    def _chat(self, system: str, user: str, *, max_tokens: int, json_mode: bool) -> str:
        body: dict[str, Any] = {"model": self.model, "temperature": 0, "max_tokens": max_tokens,
                                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        r = self._post(body)
        if r.status_code == 400:
            # Not every endpoint or model takes every parameter (e.g. reasoning models reject temperature and
            # max_tokens). Drop what the error names and try once more.
            err = r.text.lower()
            retry = dict(body)
            if "temperature" in err:
                retry.pop("temperature", None)
            if "max_tokens" in err:
                retry["max_completion_tokens"] = retry.pop("max_tokens")
            if "response_format" in err:
                retry.pop("response_format", None)
            if retry != body:
                r = self._post(retry)
        if r.status_code != 200:
            raise _http_error(r, self._key)
        try:
            choices = r.json().get("choices") or [{}]
        except ValueError as exc:
            raise LLMError("LLM endpoint returned a non-JSON response") from exc
        return str((choices[0].get("message") or {}).get("content") or "")

    def complete(self, system: str, user: str, *, max_tokens: int = 1024) -> str:
        return _clean(self._chat(system, user, max_tokens=max_tokens, json_mode=False))

    def complete_json(self, system: str, user: str, model_cls: type[M]) -> M:
        return _validate(self._chat(_schema_prompt(system, model_cls), user, max_tokens=1024, json_mode=True), model_cls)

    def list_models(self) -> list[str]:
        try:
            r = self._http.get("models")
            return sorted(str(m["id"]) for m in r.json().get("data", [])) if r.status_code == 200 else []
        except (httpx.HTTPError, ValueError, KeyError, TypeError):
            return []

    def close(self) -> None:
        self._http.close()


class AnthropicClient:
    """Claude through the official SDK (optional dependency: pip install ".[ai]")."""

    def __init__(self, model: str, timeout_s: float = 20.0, api_key: str | None = None) -> None:
        try:
            import anthropic
        except ImportError as exc:
            raise LLMError('Claude needs the optional SDK on the server: pip install ".[ai]"') from exc

        self._anthropic = anthropic
        kwargs: dict[str, Any] = {"timeout": timeout_s, "max_retries": 1}
        if api_key:
            kwargs["api_key"] = api_key
        self._client = anthropic.Anthropic(**kwargs)
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

    def list_models(self) -> list[str]:
        try:
            return sorted(m.id for m in self._client.models.list(limit=100))
        except Exception:  # noqa: BLE001 - listing is a convenience only
            return []

    def close(self) -> None:
        self._client.close()


def get_llm(settings: Settings) -> LLMClient | None:
    """The server's configured client, or None when no model is configured or it cannot be constructed."""
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


# --- Bring your own key --------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Preset:
    id: str
    label: str
    kind: str  # ollama | openai-compatible | anthropic
    base_url: str | None
    default_model: str
    needs_key: bool
    free_tier: bool
    key_url: str | None
    note: str


# Fixed endpoints: a user picks a provider, never a URL (a free-form URL would let any visitor of a hosted instance make
# the server call arbitrary addresses). "custom" is offered only when the operator sets DD_LLM_ALLOW_CUSTOM_URL=true.
PRESETS: dict[str, Preset] = {p.id: p for p in (
    Preset("ollama", "Ollama (local)", "ollama", None, "qwen2.5:3b", False, True, None,
           "Free. Runs on the machine that runs Data Doctor, so nothing leaves it. Needs Ollama and `ollama pull qwen2.5:3b`."),
    Preset("groq", "Groq", "openai-compatible", "https://api.groq.com/openai/v1", "llama-3.1-8b-instant", True, True,
           "https://console.groq.com/keys", "Free tier with rate limits. Very fast."),
    Preset("gemini", "Google Gemini", "openai-compatible", "https://generativelanguage.googleapis.com/v1beta/openai",
           "gemini-3.5-flash-lite", True, True, "https://aistudio.google.com/apikey", "Free tier with rate limits."),
    Preset("openrouter", "OpenRouter", "openai-compatible", "https://openrouter.ai/api/v1", "openrouter/free", True, True,
           "https://openrouter.ai/keys", "One key for many models; `openrouter/free` picks a free one."),
    Preset("mistral", "Mistral", "openai-compatible", "https://api.mistral.ai/v1", "mistral-small-latest", True, True,
           "https://console.mistral.ai/api-keys", "Free experiment tier with rate limits."),
    Preset("openai", "OpenAI", "openai-compatible", "https://api.openai.com/v1", "gpt-4.1-mini", True, False,
           "https://platform.openai.com/api-keys", "Paid."),
    Preset("anthropic", "Anthropic Claude", "anthropic", None, DEFAULT_MODELS["anthropic"], True, False,
           "https://console.anthropic.com/settings/keys", "Paid. Needs the optional SDK on the server (pip install \".[ai]\")."),
    Preset("custom", "Other OpenAI-compatible endpoint", "openai-compatible", None, "", False, False, None,
           "Any /chat/completions endpoint, such as LM Studio or vLLM."),
)}


class LLMConfig(BaseModel):
    """A user's own model settings, sent with that user's request. The key is a SecretStr: it never appears in reprs."""

    provider: str = Field(max_length=40)
    model: str = Field(default="", max_length=200)
    api_key: SecretStr | None = None
    base_url: str | None = Field(default=None, max_length=300)


def presets_for(settings: Settings) -> list[dict[str, Any]]:
    return [asdict(p) for p in PRESETS.values() if p.id != "custom" or settings.llm_allow_custom_url]


def client_from_config(cfg: LLMConfig, settings: Settings, transport: httpx.BaseTransport | None = None) -> LLMClient:
    """Build a client for one request from a user's settings. Raises LLMError with a user-facing reason."""
    if not settings.llm_allow_user_keys:
        raise LLMError("This server does not accept user-supplied model settings (DD_LLM_ALLOW_USER_KEYS=false).")
    preset = PRESETS.get(cfg.provider)
    if preset is None:
        raise LLMError(f"Unknown provider {cfg.provider[:40]!r}.")
    if preset.id == "custom" and not settings.llm_allow_custom_url:
        raise LLMError("Custom endpoints are switched off on this server (DD_LLM_ALLOW_CUSTOM_URL=false).")
    model = cfg.model.strip() or preset.default_model
    if not _MODEL_ID.match(model):
        raise LLMError("Enter a model name (letters, digits and . : / @ + - _ only).")
    key = cfg.api_key.get_secret_value().strip() if cfg.api_key else ""
    if len(key) > 500 or any(c.isspace() for c in key):
        raise LLMError("That does not look like an API key (it is too long or contains spaces).")
    if preset.needs_key and not key:
        raise LLMError(f"{preset.label} needs an API key.")
    timeout = settings.llm_timeout_s
    if preset.kind == "ollama":
        base = settings.llm_base_url if settings.llm_provider == "ollama" and settings.llm_base_url else "http://localhost:11434"
        return OllamaClient(model, base, timeout, transport=transport)
    if preset.kind == "anthropic":
        return AnthropicClient(model, api_key=key)
    base_url = preset.base_url
    if preset.id == "custom":
        try:
            url = httpx.URL((cfg.base_url or "").strip())
        except httpx.InvalidURL as exc:
            raise LLMError("Enter the endpoint's base URL, for example http://localhost:1234/v1.") from exc
        if url.scheme not in ("http", "https") or not url.host:
            raise LLMError("Enter the endpoint's base URL, for example http://localhost:1234/v1.")
        base_url = str(url)
    assert base_url
    return OpenAICompatibleClient(model, base_url, key or None, timeout, transport=transport, name=f"{preset.id}:{model}")


def close_client(client: object) -> None:
    close = getattr(client, "close", None)
    if callable(close):
        close()
