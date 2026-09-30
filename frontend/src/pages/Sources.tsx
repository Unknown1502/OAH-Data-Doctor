import { ModelBadge, useLlm } from "../components/ModelSettings";
import { useRun } from "../components/Shell";
import { Button, Loading, SourceBadge, useDocumentTitle } from "../components/ui";
import { useState } from "react";
import { post, useApi } from "../lib/api";
import { when } from "../lib/format";
import type { RuleSpec } from "../lib/types";

const CATEGORY_TEXT: Record<string, string> = {
  STRUCTURAL: "Structure (what FHIR validation on the server cannot check)",
  STATISTICAL: "Statistics that must hold for any real data",
  SEMANTIC: "Domain knowledge: physics, definitions, terminology, cross-record logic",
};

export default function Sources() {
  useDocumentTitle("Sources and rules");
  const { status, runId, scan, scanning } = useRun();
  const llm = useLlm();
  const rules = useApi<RuleSpec[]>("/rules", [runId]);
  const [cleared, setCleared] = useState(false);
  const src = status?.source;
  const cats = Array.from(new Set((rules.data ?? []).map((r) => r.category)));

  return (
    <article>
      <h1 className="m-0 text-4xl font-bold tracking-tight">Sources and rules</h1>

      <section aria-labelledby="src-h" className="mt-8">
        <h2 id="src-h" className="m-0 text-2xl font-bold tracking-tight">Where the data comes from</h2>
        <div className="mt-3 rounded-xl border border-line bg-panel p-5">
          <div className="flex flex-wrap items-center gap-3">
            <SourceBadge source={src} />
            <span className="text-ink-2">{src?.base_url}</span>
          </div>
          <p className="mt-3 max-w-[75ch] text-ink-2">
            Data Doctor only reads from the OneAquaHealth FHIR sandbox: every request is a GET, or the server's own $validate, which never
            stores anything. Live results can change because the sandbox is shared and writable. Snapshots are dated copies with a sha256
            for every file, so a result can always be reproduced and is never presented as live.
          </p>
          <div className="mt-4 flex flex-wrap gap-3">
            <Button kind="primary" onClick={() => scan("live")} disabled={scanning}>Scan live sandbox</Button>
            <Button onClick={() => scan("snapshot")} disabled={scanning}>Use the latest snapshot</Button>
            <Button kind="quiet" onClick={async () => { await post("/analyses/reset", {}); setCleared(true); }}>
              {cleared ? "Cleared the comparisons and claims you ran" : "Clear the comparisons and claims I ran"}
            </Button>
          </div>
        </div>

        <h3 className="mb-2 mt-6 text-lg font-semibold">Verified snapshots</h3>
        {status?.snapshots.length ? (
          <div className="overflow-x-auto rounded-xl border border-line bg-panel">
            <table className="data">
              <caption className="sr-only">Snapshots available offline</caption>
              <thead>
                <tr>
                  <th scope="col">Taken</th>
                  <th scope="col">Resources</th>
                  <th scope="col">Server validations stored</th>
                  <th scope="col">Manifest sha256</th>
                </tr>
              </thead>
              <tbody>
                {status.snapshots.map((s) => (
                  <tr key={s.snapshot_id}>
                    <td className="whitespace-nowrap">{when(s.fetched_at)}</td>
                    <td>{Object.entries(s.resource_counts).map(([k, v]) => `${v} ${k}`).join(", ")}</td>
                    <td className="readout">{s.server_validations}</td>
                    <td className="code break-all text-sm">{s.manifest_sha256}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="text-ink-2">No snapshot yet. Run <code className="code">python tasks.py snapshot</code> while online to create one.</p>
        )}
      </section>

      <section aria-labelledby="rules-h" className="mt-12">
        <h2 id="rules-h" className="m-0 text-2xl font-bold tracking-tight">The rules</h2>
        <p className="mt-1 max-w-[75ch] text-ink-2">
          {rules.data ? `${rules.data.length} deterministic checks` : "Deterministic checks"}, each with tests that prove it fires on broken data and stays silent on clean data. Values are compared
          within half a unit of their last published decimal, so rounding alone never raises a finding.
        </p>
        {!rules.data && <Loading what="rules" />}
        {cats.map((cat) => (
          <div key={cat} className="mt-6">
            <h3 className="m-0 text-lg font-semibold">{CATEGORY_TEXT[cat] ?? cat}</h3>
            <dl className="m-0 mt-2 divide-y divide-line rounded-xl border border-line bg-panel">
              {(rules.data ?? []).filter((r) => r.category === cat).map((r) => (
                <div key={r.id} className="grid gap-1 p-4 md:grid-cols-[13rem_1fr]">
                  <dt>
                    <span className="code font-semibold">{r.id}</span>
                    <span className="block text-sm text-ink-3">{r.findings ? `${r.findings} findings this run` : "No findings this run"}</span>
                  </dt>
                  <dd className="m-0">
                    <p className="m-0 font-semibold">{r.title}</p>
                    <p className="m-0 mt-1 text-ink-2">Must hold: {r.constraint}</p>
                    <p className="m-0 mt-1 text-ink-2">{r.rationale}</p>
                    <p className="m-0 mt-1 text-sm text-ink-3">Severity: {r.severity}. Confidence: {r.confidence}.</p>
                  </dd>
                </div>
              ))}
            </dl>
          </div>
        ))}
      </section>

      <section aria-labelledby="ai-h" className="mt-12">
        <h2 id="ai-h" className="m-0 text-2xl font-bold tracking-tight">Where AI is and is not used</h2>
        <p className="mt-2 max-w-[75ch] text-ink-2">
          No language model detects a finding, decides comparability or judges a claim. Optionally, a language model can rephrase an already
          computed finding, and fill gaps when the keyword rules read a typed claim. Any model works: a free local one through Ollama, a free
          hosted endpoint, or Claude. A rephrasing is thrown away and the fixed template is used instead if it contains a number that is not in
          the evidence, or if it states a cause or a correction the finding does not. The language model is currently{" "}
          {llm.activeName ? (
            <>
              enabled: <ModelBadge name={llm.activeName} source={llm.config ? "yours" : "server"} /> ({llm.config ? "your key" : "this server's setting"})
            </>
          ) : (
            "switched off"
          )}
          .
          {status?.llm_user_keys && (
            <>
              {" "}You can use your own provider and key, including free tiers: choose{" "}
              <button type="button" onClick={llm.open} className="text-karst underline underline-offset-2">Language model</button> at the top of
              any page. Your key stays in your browser and is sent only with your own requests; the server never stores or logs it.
            </>
          )}
        </p>
      </section>
    </article>
  );
}
