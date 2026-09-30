# AI policy

## In the product

- **No model decides anything.** Detection, comparability and claim verdicts are deterministic code, tested without any LLM.
  `DD_LLM_PROVIDER=none` is the default and the product is complete without it.
- **Allowed uses (optional, `DD_LLM_PROVIDER=anthropic`):**
  1. Rephrasing an already computed finding for a non-specialist (`ai/explainer.py`). The model receives only the finding's facts
     (JSON), never raw data. Output is **rejected** if it contains any number not present in those facts, and the deterministic
     template is shown instead with the reason. Refusals, timeouts and errors also fall back to the template.
  2. Reading a typed claim into a `ClaimIntent` (`claims/parser.py`, structured output). Unknown indicator keys or location ids are
     dropped. The resolver maps the intent onto real records, and the resulting structured claim is shown to the user. The verdict
     is computed from that structure by the rules.
- **Model:** `claude-opus-5` by default (configurable with `DD_LLM_MODEL`), low effort, 20 s timeout, one retry.
- **Tests:** `backend/tests/unit/test_ai_policy.py` uses a mock and proves that ungrounded numbers are rejected.
- **Data:** only finding facts or the user's claim text are sent. No credentials are stored in the repository (`.env.example` only).

## In the making

This project was built with an AI coding assistant (Claude, by Anthropic) that drafted code, tests and documentation under human
direction. Discovery, Gate 0 evidence and every published number come from real runs against the sandbox, recorded with
timestamps. The Gate 0 sample requires a human reviewer's sign-off (docs/GATE0_REPORT.md).
