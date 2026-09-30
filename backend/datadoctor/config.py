"""Runtime configuration. Environment variables only (see .env.example); no secrets have defaults."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_FHIR_BASE = "https://sandbox.hl7europe.eu/oneaquahealth/fhir"
# Resource types the auditor ingests. Chosen from $get-resource-counts on the live sandbox (DISCOVERY.md D4).
INGEST_TYPES = ("Observation", "Location", "Group", "Library", "Organization", "Device", "Provenance")


def _load_dotenv(path: Path) -> None:
    """Minimal .env reader (KEY=VALUE lines) so no extra dependency is needed. Never overrides real env vars."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


@dataclass(frozen=True)
class Settings:
    fhir_base: str = DEFAULT_FHIR_BASE
    data_dir: Path = REPO_ROOT / "data"
    knowledge_dir: Path = REPO_ROOT / "knowledge"
    source_mode: str = "auto"  # auto (live, fall back to latest snapshot) | live | snapshot
    snapshot_id: str | None = None
    http_delay_s: float = 0.25
    http_timeout_s: float = 60.0
    http_retries: int = 4
    page_size: int = 200
    cache_ttl_s: int = 900
    llm_provider: str = "none"  # none | ollama | openai-compatible | anthropic (see ai/llm.py)
    llm_model: str = ""  # empty = provider default (ollama: qwen2.5:3b)
    llm_base_url: str | None = None  # ollama: http://localhost:11434; openai-compatible: e.g. https://api.groq.com/openai/v1
    llm_api_key: str | None = None  # only for hosted openai-compatible endpoints; never logged
    llm_timeout_s: float = 120.0
    ingest_types: tuple[str, ...] = field(default=INGEST_TYPES)

    @property
    def db_path(self) -> Path:
        return self.data_dir / "datadoctor.sqlite"

    @property
    def snapshots_dir(self) -> Path:
        return self.data_dir / "snapshots"

    @property
    def reports_dir(self) -> Path:
        return self.data_dir / "reports"


def get_settings() -> Settings:
    _load_dotenv(REPO_ROOT / ".env")
    env = os.environ
    return Settings(
        fhir_base=env.get("DD_FHIR_BASE", DEFAULT_FHIR_BASE).rstrip("/"),
        data_dir=Path(env.get("DD_DATA_DIR", str(REPO_ROOT / "data"))),
        knowledge_dir=Path(env.get("DD_KNOWLEDGE_DIR", str(REPO_ROOT / "knowledge"))),
        source_mode=env.get("DD_SOURCE", "auto"),
        snapshot_id=env.get("DD_SNAPSHOT_ID") or None,
        http_delay_s=float(env.get("DD_HTTP_DELAY_S", "0.25")),
        http_timeout_s=float(env.get("DD_HTTP_TIMEOUT_S", "60")),
        llm_provider=env.get("DD_LLM_PROVIDER", "none"),
        llm_model=env.get("DD_LLM_MODEL", ""),
        llm_base_url=env.get("DD_LLM_BASE_URL") or None,
        llm_api_key=env.get("DD_LLM_API_KEY") or None,
        llm_timeout_s=float(env.get("DD_LLM_TIMEOUT_S", "120")),
    )
