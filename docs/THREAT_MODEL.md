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
| User-supplied API keys | A key leaking through storage, logs, error messages or echoed request bodies | Kept in the user's browser only (session storage unless they choose to remember it); sent per request in the body, not a URL; held as a `SecretStr`; never stored or logged; redacted from provider errors; 422 responses omit submitted values (tested) |
| Server-side request forgery via model settings | A visitor making the server call internal addresses (for example cloud metadata) | Users choose among fixed provider presets; a free-form URL requires `DD_LLM_ALLOW_CUSTOM_URL=true` (off by default) and must be http(s) |
| Data uploaded for checking | Oversized input, data retained on the server, writes to the sandbox | At most 5 MB and 2,000 resources; parsed as JSON only; checked in memory for one request and never stored or forwarded |
| What-if server check | Using the lab to load or write to the public sandbox | Only `POST Observation/$validate` (validates, stores nothing), at most one request every 2 s for all users together, values limited to finite numbers of at most 1e12 |
| LLM hallucination | Invented numbers, causes or corrections in explanations; misread claims | Numbers must occur in the evidence and causes or corrections must occur in the facts, else template fallback; claim reading is rules-first and model keys or ids that do not exist are dropped; never used for verdicts |
| Prompt injection via data | Resource text steering an LLM | The LLM sees only finding facts (our generated JSON) or the claim the user typed, not raw resources; its output never changes a verdict. With the default free provider (Ollama) nothing leaves the machine |
| API abuse | Oversized input | Pydantic validation, claim text ≤ 500 characters, findings limit ≤ 2000, CORS limited to the dev origin |
| UI injection | Malicious strings in resources | React escapes text; the raw JSON is rendered as text; the HTML report escapes every field |
| Misinterpretation | Over-claiming root causes | Root cause is always "unknown"; hypotheses are labelled as unverified; remediation is "review by the data owner" |
