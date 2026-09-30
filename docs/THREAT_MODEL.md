# Threat model

| Asset / risk | Threat | Mitigation |
|---|---|---|
| The OAH sandbox (shared, writable) | Accidental writes by the auditor | `FhirClient.check_method` allows only GET, and POST to `$validate`; a unit test covers PUT, DELETE, PATCH and POST. No write code paths exist |
| Credentials | Leaking API keys | No credentials are needed for the sandbox; the LLM key is optional, read from the environment, and never logged; `.env` is git-ignored |
| Data integrity of evidence | Snapshot tampering or line-ending corruption | sha256 per file plus a manifest digest, verified before use and in CI; `.gitattributes` keeps evidence byte-exact |
| Trust in results | Third-party resources in the shared sandbox masquerading as OAH data | Scope by IG example ids, not `meta.profile`; findings carry scope |
| Trust in results | Live data changing between runs | Every run records its fetch time, resource versions and hashes; snapshots are labelled and never presented as live |
| Server-side request forgery / redirect | A paging `next` link pointing elsewhere | The client refuses links to another host and does not follow redirects |
| Denial of service to the sandbox | Aggressive crawling | 0.25 s polite delay, capped retries with backoff, `Retry-After` honoured, response cache |
| LLM hallucination | Invented numbers or causes in explanations | Grounding check on numbers, template fallback, never used for verdicts |
| Prompt injection via data | Resource text steering an LLM | The LLM sees only finding facts (our generated JSON), not raw resources; its output never changes a verdict |
| API abuse | Oversized input | Pydantic validation, claim text ≤ 500 characters, findings limit ≤ 2000, CORS limited to the dev origin |
| UI injection | Malicious strings in resources | React escapes text; the raw JSON is rendered as text; the HTML report escapes every field |
| Misinterpretation | Over-claiming root causes | Root cause is always "unknown"; hypotheses are labelled as unverified; remediation is "review by the data owner" |
