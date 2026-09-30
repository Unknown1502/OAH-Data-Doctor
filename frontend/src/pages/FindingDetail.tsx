import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import Lineage from "../components/Lineage";
import MagnitudeRuler from "../components/MagnitudeRuler";
import RawResourceDrawer from "../components/RawResourceDrawer";
import TraceGraph from "../components/TraceGraph";
import TwoVerdicts from "../components/TwoVerdicts";
import WhatIfLab from "../components/WhatIfLab";
import { ModelBadge, ProviderIcon, describeModel, useLlm } from "../components/ModelSettings";
import { useRun } from "../components/Shell";
import { Button, ErrorNote, FindingLink, Loading, SeverityBadge, SourceBadge, useDocumentTitle } from "../components/ui";
import { download, post, useApi } from "../lib/api";
import { num, pretty, sentence, unit, when } from "../lib/format";
import { rulerFor } from "../lib/ruler";
import type { FindingDetail as Detail, OperationOutcome } from "../lib/types";

function Section({ id, title, children }: { id: string; title: string; children: React.ReactNode }) {
  return (
    <section aria-labelledby={id} className="min-w-0 border-t border-line pt-6">
      <h2 id={id} className="m-0 mb-3 text-xl font-bold tracking-tight">
        {title}
      </h2>
      {children}
    </section>
  );
}

/** What may safely be concluded from a finding, from its severity alone: the same rule the support table uses. */
function safeConclusion(severity: string, record: string): string {
  if (severity === "CRITICAL" || severity === "ERROR")
    return `Do not use “${record}” as published in an analysis, comparison or claim until the publisher has reviewed it. What caused the problem is unknown.`;
  if (severity === "WARNING")
    return `“${record}” can be used, with the caveat above stated wherever it is used.`;
  return `Nothing changes in how “${record}” can be used; this is noted for completeness.`;
}

function measureRows(m: Record<string, unknown>) {
  const labels: Record<string, string> = {
    factor: "Factor between the values",
    violated_bound: "Bound broken",
    distance: "Distance beyond the bound",
    tolerance_applied: "Rounding tolerance allowed",
    gap: "Gap between mean and median",
    std_dev: "Standard deviation",
    ratio_gap_to_sd: "Gap divided by SD",
    sd_upper_bound: "Largest SD the range allows",
    mean_median_ratio: "Mean / median",
    exact_power_of_ten: "Exact power of ten",
    k: "Power of ten (k)",
    divergent_pairs: "Disagreeing pairs",
    matched_pairs: "Pairs compared",
    observations: "Observations affected",
    sum: "Sum of shares",
    sites: "Sites affected",
    max_relative_excess: "Largest relative excess",
  };
  return Object.entries(m)
    .filter(([k]) => !(k === "k" && m.exact_power_of_ten !== true))
    .filter(([k, v]) => labels[k] && v !== null && v !== undefined && typeof v !== "object")
    .map(([k, v]) => [labels[k], typeof v === "boolean" ? (v ? "yes" : "no") : typeof v === "number" ? num(v) : String(v)]);
}

export default function FindingDetail() {
  const { id = "" } = useParams();
  const { runId } = useRun();
  const { data, error } = useApi<Detail>(`/findings/${encodeURIComponent(id)}`, [runId]);
  const [explained, setExplained] = useState<Detail["explanation"] | null>(null);
  const llm = useLlm();
  const [rephrasing, setRephrasing] = useState(false);
  const [rephraseErr, setRephraseErr] = useState<string | null>(null);
  const [liveCheck, setLiveCheck] = useState<{ outcome: OperationOutcome; checked_at: string } | null>(null);
  const [liveErr, setLiveErr] = useState<string | null>(null);
  const [rawOpen, setRawOpen] = useState(false);
  useDocumentTitle(data ? `${data.finding.rule_id} on ${data.finding.resource.display ?? data.finding.resource.resource_id}` : "Finding");

  if (error)
    return (
      <ErrorNote
        error={`This finding is not part of the current run (${error}). Findings are recomputed on every scan.`}
        action={<Link className="text-karst underline" to="/findings">Back to all findings</Link>}
      />
    );
  if (!data) return <Loading what="the finding" />;
  const f = data.finding;
  const key = `${f.resource.resource_type}/${f.resource.resource_id}`;
  const ruler = rulerFor(data);
  const explanation = explained ?? data.explanation;
  const server = liveCheck?.outcome ?? data.server_validation;

  const askServer = async () => {
    setLiveErr(null);
    try {
      setLiveCheck(await post(`/validate/${f.resource.resource_type}/${encodeURIComponent(f.resource.resource_id)}`, {}));
    } catch (e) {
      setLiveErr((e as Error).message);
    }
  };

  const exportFinding = () => {
    const url = URL.createObjectURL(new Blob([JSON.stringify(f, null, 2)], { type: "application/json" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = `${f.id}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };
  const src = f.provenance?.source;
  const factor = typeof f.evidence.measures.factor === "number" ? (f.evidence.measures.factor as number) : null;
  const highlight = f.evidence.observed.map((o) => o.fhir_path).filter((x): x is string => !!x);

  return (
    <article className="space-y-8">
      <nav aria-label="Breadcrumb" className="text-sm text-ink-2">
        <Link to="/findings" className="text-karst underline underline-offset-2">
          Findings
        </Link>{" "}
        <span aria-hidden="true">/</span> {f.rule_id}
      </nav>

      <header>
        <div className="flex flex-wrap items-center gap-2.5">
          <SeverityBadge severity={f.severity} category={f.category} />
          <span className="readout text-sm text-ink-2">{f.rule_id}</span>
          {src && <SourceBadge source={src} />}
        </div>
        <h1 className="m-0 mt-3 max-w-[34ch] text-[clamp(1.7rem,3vw,2.3rem)] font-bold leading-tight tracking-tight">
          {f.resource.display ?? key}
        </h1>
        <p className="mt-3 max-w-[70ch] text-lg leading-relaxed">{sentence(pretty(f.summary.replace(`${f.resource.display ?? ""}: `, "")))}</p>
      </header>

      <section aria-label="What is wrong and why" className="grid overflow-hidden rounded-lg border border-line bg-panel lg:grid-cols-[minmax(0,1fr)_minmax(0,1.3fr)]">
        <div className="border-b border-line p-5 lg:border-b-0 lg:border-r">
          <h2 className="m-0 text-[0.78rem] font-bold uppercase tracking-[0.1em] text-ink-2">Observed</h2>
          <dl className="m-0 mt-3 space-y-2.5">
            {f.evidence.observed.map((o, i) => (
              <div key={i} className="flex items-baseline justify-between gap-4 border-b border-line pb-2 last:border-b-0">
                <dt className="text-ink-2">{o.label}</dt>
                <dd className="readout m-0 text-right text-2xl font-semibold">
                  {num(o.value)} <span className="text-base font-normal text-ink-2">{unit(o.unit)}</span>
                </dd>
              </div>
            ))}
          </dl>
        </div>
        <div className="p-5">
          <h2 className="m-0 text-[0.78rem] font-bold uppercase tracking-[0.1em] text-ink-2">Why it was flagged</h2>
          <p className="mb-0 mt-3 text-lg leading-snug">{f.evidence.expected}</p>
          <p className="mb-0 mt-2 text-ink-2">
            It does not hold here: <code className="code text-ink">{f.evidence.constraint}</code>.
            {factor !== null && factor > 1 && <> The values differ by a factor of <strong className="readout text-ink">{num(factor)}</strong>.</>}
          </p>
          <div className="mt-4 rounded-md border border-sulfur/50 bg-sulfur-soft px-4 py-3">
            <p className="m-0 font-semibold">
              Root cause: <span className="uppercase tracking-wide">unknown</span>
            </p>
            <p className="m-0 mt-1 text-sm text-ink-2">
              Data Doctor shows that these values cannot all be right. It does not claim to know which one is wrong, or why.
            </p>
          </div>
          <p className="mb-0 mt-3 text-sm text-ink-2">
            Confidence {f.confidence_label} (<span className="readout">{f.confidence}</span>), rule {data.rule.id} version {data.rule.version}.
          </p>
        </div>
      </section>

      {f.resource.resource_type === "Observation" && (
        <div>
          <TwoVerdicts serverOutcome={server} findings={[f, ...data.same_resource]} record={f.resource.display ?? key} />
          <p className="mt-2 text-sm text-ink-3">
            {liveCheck
              ? `Server asked live at ${when(liveCheck.checked_at)}.`
              : data.server_validation
                ? f.provenance?.source.kind === "live"
                  ? `Server asked during this live scan (${when(f.provenance.source.fetched_at)}).`
                  : "Server verdict recorded when the snapshot was taken."
                : "No server verdict stored for this run."}{" "}
            <button type="button" onClick={askServer} className="text-karst underline underline-offset-2">
              Ask the server now
            </button>
            {liveErr && <span className="ml-2 text-cinnabar">{liveErr}</span>}
          </p>
        </div>
      )}

      <div className="grid gap-8 lg:grid-cols-[1.35fr_1fr]">
        <Section id="ev-h" title="Evidence">
          {ruler && ruler.values.length > 1 && (
            <div className="mb-4 rounded-lg border border-line bg-panel p-4">
              <MagnitudeRuler {...ruler} caption={f.resource.display ?? undefined} animate={false} />
            </div>
          )}
          <div className="overflow-x-auto rounded-lg border border-line">
            <table className="data">
              <caption className="sr-only">Values observed in the record</caption>
              <thead>
                <tr>
                  <th scope="col">Published as</th>
                  <th scope="col" className="text-right">
                    Value
                  </th>
                  <th scope="col">Where in the record (FHIRPath)</th>
                </tr>
              </thead>
              <tbody>
                {f.evidence.observed.map((o, i) => (
                  <tr key={i}>
                    <td>{o.label}</td>
                    <td className="readout whitespace-nowrap text-right">
                      {num(o.value)} {unit(o.unit)}
                    </td>
                    <td className="code text-sm text-ink-2">{o.fhir_path ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {measureRows(f.evidence.measures).length > 0 && (
            <dl className="mt-4 grid grid-cols-[auto_1fr] gap-x-6 gap-y-1 text-[0.95rem]">
              {measureRows(f.evidence.measures).map(([k, v]) => (
                <div key={k} className="contents">
                  <dt className="text-ink-2">{k}</dt>
                  <dd className="readout m-0">{v}</dd>
                </div>
              ))}
            </dl>
          )}
          <dl className="mt-5 grid gap-x-6 gap-y-1.5 border-t border-line pt-4 text-sm sm:grid-cols-[8rem_1fr]">
            <dt className="text-ink-2">Resource</dt>
            <dd className="code m-0 break-all">{key}</dd>
            <dt className="text-ink-2">Rule</dt>
            <dd className="m-0"><span className="code">{data.rule.id}</span> v{data.rule.version}: {data.rule.title}</dd>
            {src && (
              <>
                <dt className="text-ink-2">Source</dt>
                <dd className="m-0 break-words">{src.kind === "live" ? "Live" : `Snapshot ${src.snapshot_id}`}, {src.base_url}</dd>
                <dt className="text-ink-2">Retrieved</dt>
                <dd className="m-0">{when(src.fetched_at)}</dd>
              </>
            )}
            {f.provenance && (
              <>
                <dt className="text-ink-2">Record version</dt>
                <dd className="m-0">{f.provenance.resource_version_id ?? "—"}, last updated {f.provenance.resource_last_updated ?? "—"}</dd>
                <dt className="text-ink-2">Record sha256</dt>
                <dd className="code m-0 break-all">{f.provenance.resource_sha256}</dd>
                <dt className="text-ink-2">Checked with</dt>
                <dd className="m-0 break-words">rules {f.provenance.rules_version}, knowledge {f.provenance.knowledge_version}, {f.provenance.ig_source}</dd>
              </>
            )}
            <dt className="text-ink-2">Finding id</dt>
            <dd className="code m-0 break-all">{f.id}</dd>
          </dl>
        </Section>

        <div className="min-w-0 space-y-8">
          <Section id="mean-h" title="Why it matters">
            <p className="m-0">{pretty(f.interpretation)}</p>
            {f.hypotheses.length > 0 && (
              <div className="mt-3 rounded-md border border-dashed border-line-strong p-3">
                <p className="m-0 text-sm font-semibold text-ink-2">Possible explanations, not verified</p>
                <ul className="mb-0 mt-1 pl-5 text-[0.95rem] text-ink-2">
                  {f.hypotheses.map((h) => (
                    <li key={h}>{h}</li>
                  ))}
                </ul>
              </div>
            )}
          </Section>
          <Section id="safe-h" title="Safe conclusion">
            <p className="m-0">{safeConclusion(f.severity, f.resource.display ?? key)}</p>
          </Section>
          <Section id="act-h" title="Suggested action">
            <p className="m-0">{f.remediation}</p>
            <div className="mt-4 flex flex-wrap gap-2">
              <a href="#tr-h" className="inline-flex items-center rounded-md border border-line-strong bg-panel px-3.5 py-2 text-[0.95rem] font-semibold text-ink no-underline hover:bg-sunk">
                View impact
              </a>
              {data.raw && <Button onClick={() => setRawOpen(true)}>View raw resource</Button>}
              <Button onClick={exportFinding}>Export finding</Button>
            </div>
            <p className="mb-0 mt-3 text-sm text-ink-3">
              Rule {data.rule.id} v{data.rule.version}: {data.rule.rationale}
            </p>
          </Section>
        </div>
      </div>

      {f.lineage && (
        <Section id="lin-h" title="Where these values first appear">
          <Lineage lineage={f.lineage} />
        </Section>
      )}

      <Section id="tr-h" title="What this affects">
        <TraceGraph impact={data.impact} recordLabel={f.resource.display ?? key} />
      </Section>

      <Section id="ex-h" title={explanation.method === "template" ? "In plain words" : "AI explanation"}>
        <div className="max-w-[72ch] whitespace-pre-line leading-relaxed">{explanation.text}</div>
        <p className="mt-2 text-sm text-ink-3">
          {explanation.method === "template" ? (
            "Written from the finding by a fixed template."
          ) : (
            <>
              Generated from the deterministic finding evidence. Rephrased by <ModelBadge name={explanation.method.replace(/^llm:/, "")} /> from
              the finding's facts only; its numbers and any stated cause were checked against the finding. It decides nothing.
            </>
          )}
          {explanation.fallback_reason && ` (${explanation.fallback_reason}; template used.)`}{" "}
          {explanation.method !== "template" && (
            <button type="button" className="text-karst underline underline-offset-2" onClick={() => setExplained(null)}>
              Show the full template version
            </button>
          )}
        </p>
        {llm.activeName && explanation.method === "template" && !explanation.fallback_reason && (
          <button type="button" disabled={rephrasing}
            className="mt-3 inline-flex max-w-full items-center gap-1.5 rounded-md border border-line-strong bg-panel px-3.5 py-2 text-[0.95rem] text-ink hover:bg-sunk disabled:cursor-wait disabled:opacity-70"
            onClick={async () => {
              setRephrasing(true);
              setRephraseErr(null);
              try {
                setExplained(await post(`/findings/${encodeURIComponent(f.id)}/explain`, llm.body));
              } catch (e) {
                setRephraseErr(String(e instanceof Error ? e.message : e));
              } finally {
                setRephrasing(false);
              }
            }}>
            {rephrasing ? "Rephrasing with" : "Rephrase with"} <ProviderIcon id={describeModel(llm.activeName).provider} className="h-4 w-4" />
            <span className="font-semibold">{describeModel(llm.activeName).label}</span>{" "}
            <span className="min-w-0 truncate text-ink-2">{describeModel(llm.activeName).model}{rephrasing ? "…" : ""}</span>
          </button>
        )}
        {rephrasing && <p role="status" className="m-0 mt-1 text-sm text-ink-3">A local model can take up to a minute on the first request.</p>}
        {rephraseErr && <p role="alert" className="m-0 mt-1 text-sm text-ink-3">Rephrasing failed ({rephraseErr}); the template above stands.</p>}
      </Section>

      {data.record && f.resource.resource_type === "Observation" && (data.record.stats.length > 0 || data.record.value) && (
        <details className="mt-10 rounded-lg border border-line bg-panel">
          <summary className="cursor-pointer px-4 py-3 text-lg font-bold">What if? Change the numbers of this record</summary>
          <div className="border-t border-line p-3 sm:p-4">
            <WhatIfLab observationId={f.resource.resource_id} record={data.record} />
          </div>
        </details>
      )}

      {(data.same_resource.length > 0 || f.related_resources.length > 0) && (
        <Section id="rel-h" title="Related">
          {data.same_resource.length > 0 && (
            <>
              <p className="m-0 text-ink-2">Other findings on this record:</p>
              <ul className="mt-1 pl-5">
                {data.same_resource.map((x) => (
                  <li key={x.id}>
                    <FindingLink id={x.id}>
                      {x.rule_id}: {x.title}
                    </FindingLink>{" "}
                    <span className="text-ink-3">({x.severity.toLowerCase()})</span>
                  </li>
                ))}
              </ul>
            </>
          )}
          {f.related_resources.length > 0 && (
            <p className="text-ink-2">
              Also involves {f.related_resources.length} other record{f.related_resources.length > 1 ? "s" : ""}:{" "}
              {f.related_resources.slice(0, 8).map((r) => r.display ?? r.resource_id).join(", ")}
              {f.related_resources.length > 8 ? ", …" : ""}
            </p>
          )}
        </Section>
      )}

      {data.raw && (
        <RawResourceDrawer
          open={rawOpen}
          onClose={() => setRawOpen(false)}
          title={`${key}, exactly as served`}
          resource={data.raw}
          highlight={highlight}
          source={src ? <>{src.kind === "live" ? "Live" : `Snapshot ${src.snapshot_id}`}, retrieved {when(src.fetched_at)} from {src.base_url}</> : null}
        />
      )}
      <p className="text-sm text-ink-3">
        <Button onClick={() => download("/reports/operation-outcome.json")}>Download FHIR OperationOutcome (all findings)</Button>
      </p>
    </article>
  );
}
