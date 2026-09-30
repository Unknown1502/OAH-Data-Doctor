# AI policy

## In the product

- **No model decides anything.** Detection, comparability and claim verdicts are deterministic code, tested without any LLM.
  `DD_LLM_PROVIDER=none` is the default and the product is complete without it.
- **Any model, free by default.** `ai/llm.py` is provider-neutral (`DD_LLM_PROVIDER`):

  | Provider | Cost | Notes |
  |---|---|---|
  | `ollama` | free, local, offline | default model `qwen2.5:3b` (about 2 GB); JSON output constrained to the schema |
  | `openai-compatible` | free tiers exist | any `/chat/completions` endpoint: Groq, Gemini, OpenRouter, LM Studio, vLLM |
  | `anthropic` | paid | Claude through the official SDK (`pip install ".[ai]"`) |

  All calls use temperature 0. Small free models are less reliable, so correctness never depends on model quality: every
  output passes the deterministic guards below, or it is discarded.
- **Allowed uses:**
  1. Rephrasing an already computed finding for a non-specialist (`ai/explainer.py`). The model receives only the finding's facts
     (JSON), never raw data. Output is **rejected** if it contains any number not present in those facts, or if it states a cause
     or a correction ("because", "due to", "typo", "correction needed", ...) that the facts do not contain (a hedged "this could be due to ..." is
     tolerated only when the finding itself lists unverified hypotheses). The deterministic template is then shown instead, with the
     reason. Refusals, timeouts, errors and empty answers also fall back to the template.
  2. Filling gaps when reading a typed claim into a `ClaimIntent` (`claims/parser.py`). **The keyword rules come first:** every
     field they recognise is kept, and the model only supplies fields they missed. Unknown indicator keys or location ids from the
     model are dropped. If the combined reading does not resolve but the rules' reading does, the rules' reading is used. The
     resolver maps the intent onto real records, the resulting structured claim is shown to the user, and the verdict is computed
     from that structure by the rules.
- **Tests:** `backend/tests/unit/test_llm.py` (Ollama and OpenAI-compatible requests through mock transports, the cause and number
  guards, rules-first merging), `test_ai_policy.py` (grounding) and `contract/test_anthropic_sdk_contract.py` (Claude request
  shape through the real SDK). No test needs a model, a network or a key.
- **Data:** only finding facts or the user's claim text are sent. No credentials are stored in the repository (`.env.example` only).

## In the making

This project was built with an AI coding assistant (Claude, by Anthropic) that drafted code, tests and documentation under human
direction. Discovery, Gate 0 evidence and every published number come from real runs against the sandbox, recorded with
timestamps. The Gate 0 sample requires a human reviewer's sign-off (docs/GATE0_REPORT.md).
