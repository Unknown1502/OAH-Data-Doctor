"""Tests are hermetic: a developer's local .env (for example DD_LLM_PROVIDER=ollama) must not change what they see.
Real environment variables win over .env, so pinning them here is enough."""

import os

os.environ["DD_LLM_PROVIDER"] = "none"
os.environ.pop("DD_LLM_MODEL", None)
os.environ.pop("DD_LLM_BASE_URL", None)
os.environ.pop("DD_LLM_API_KEY", None)
