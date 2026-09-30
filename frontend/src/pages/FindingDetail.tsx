import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import Lineage from "../components/Lineage";
import MagnitudeRuler from "../components/MagnitudeRuler";
import TraceGraph from "../components/TraceGraph";
import TwoVerdicts from "../components/TwoVerdicts";
import { useRun } from "../components/Shell";
import { Button, ErrorNote, FindingLink, Loading, SeverityTag, useDocumentTitle } from "../components/ui";
import { download, post, useApi } from "../lib/api";
import { num, pretty, sentence, unit, when } from "../lib/format";
import { rulerFor } from "../lib/ruler";
import type { FindingDetail as Detail, OperationOutcome } from "../lib/types";

function Section({ id, title, children }: { id: string; title: string; children: React.ReactNode }) {
  return (
    <section aria-labelledby={id} className="border-t border-line pt-6">
      <h2 id={id} className="m-0 mb-3 text-xl font-bold tracking-tight">
        {title}
      </h2>
      {children}
    </section>
  );
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
  const { runId, status } = useRun();
  const { data, error } = useApi<Detail>(`/findings/${encodeURIComponent(id)}`, [runId]);
  const [explained, setExplained] = useState<Detail["explanation"] | null>(null);
  const [liveCheck, setLiveCheck] = useState<{ outcome: OperationOutcome; checked_at: string } | null>(null);
  const [liveErr, setLiveErr] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
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
  const copyJson = async () => {
    try {
      await navigator.clipboard.writeText(JSON.stringify(f, null, 2));
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      setCopied(false);
    }
  };

  return (
    <article className="space-y-8">
      <nav aria-label="Breadcrumb" className="text-sm text-ink-2">
        <Link to="/findings" className="text-karst underline underline-offset-2">
          Findings
        </Link>{" "}
        <span aria-hidden="true">/</span> {f.rule_id}
      </nav>

      <header>
        <div className="flex flex-wrap items-center gap-3">
          <SeverityTag severity={f.severity} />
          <span className="text-ink-2">
            {f.rule_id}: {f.title}
          </span>
          <span className="text-ink-2">
            Confidence {f.confidence_label} (<span className="readout">{f.confidence}</span>)
          </span>
        </div>
        <h1 className="m-0 mt-3 max-w-[30ch] text-[clamp(1.8rem,3.6vw,2.7rem)] font-bold leading-tight tracking-tight">
          {f.resource.display ?? key}
        </h1>
        <p className="mt-4 max-w-[70ch] text-lg leading-relaxed">{sentence(pretty(f.summary.replace(`${f.resource.display ?? ""}: `, "")))}</p>
      </header>

      {ruler && ruler.values.length > 1 && (
        <div className="rounded-xl border border-line bg-panel p-5">
          <MagnitudeRuler {...ruler} caption={f.resource.display ?? undefined} animate={false} />
        </div>
      )}

      {f.resource.resource_type === "Observation" && (
        <div>
          <TwoVerdicts serverOutcome={server} findings={[f, ...data.same_resource]} record={f.resource.display ?? key} />
          <p className="mt-2 text-sm text-ink-3">
            {liveCheck
              ? `Server asked live at ${when(liveCheck.checked_at)}.`
              : data.server_validation
                ? "Server verdict recorded when the snapshot was taken."
                : "No server verdict stored for this run."}{" "}
            <button type="button" onClick={askServer} className="text-karst underline underline-offset-2">
              Ask the server now
            </button>
            {liveErr && <span className="ml-2 text-cinnabar">{liveErr}</span>}
          </p>
        </div>
      )}

      <div className="grid gap-8 lg:grid-cols-[1.25fr_1fr]">
        <Section id="ev-h" title="Evidence">
          <p className="m-0 text-ink-2">
            Constraint: <strong className="text-ink">{f.evidence.constraint}</strong>
          </p>
          <p className="mt-1 text-ink-2">{f.evidence.expected}</p>
          <div className="mt-3 overflow-x-auto rounded-lg border border-line">
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
        </Section>

        <Section id="mean-h" title="What it means">
          <p className="m-0">{pretty(f.interpretation)}</p>
          <p className="mt-3">
            <strong>Root cause:</strong> {f.root_cause === "unknown" ? "unknown. Data Doctor shows that these values cannot all be right; it does not claim to know which one is wrong, or why." : f.root_cause}
          </p>
          {f.hypotheses.length > 0 && (
            <div className="mt-3 rounded-lg border border-dashed border-line-strong p-3">
              <p className="m-0 text-sm font-semibold text-ink-2">Possible explanations, not verified</p>
              <ul className="mb-0 mt-1 pl-5 text-[0.95rem] text-ink-2">
                {f.hypotheses.map((h) => (
                  <li key={h}>{h}</li>
                ))}
              </ul>
            </div>
          )}
          <p className="mt-3">
            <strong>What to do:</strong> {f.remediation}
          </p>
          <p className="mt-3 text-sm text-ink-3">
            Rule {data.rule.id} v{data.rule.version}: {data.rule.rationale}
          </p>
        </Section>
      </div>

      {f.lineage && (
        <Section id="lin-h" title="Where these values first appear">
          <Lineage lineage={f.lineage} />
        </Section>
      )}

      <Section id="tr-h" title="What this record would contaminate">
        <TraceGraph impact={data.impact} recordLabel={f.resource.display ?? key} />
      </Section>

      <Section id="ex-h" title="In plain words">
        <div className="max-w-[72ch] whitespace-pre-line leading-relaxed">{explanation.text}</div>
        <p className="mt-2 text-sm text-ink-3">
          {explanation.method === "template"
            ? "Written from the finding by a fixed template."
            : `Rephrased by ${explanation.method.replace("llm:", "")} from the finding's facts only; numbers are checked against the evidence.`}
          {explanation.fallback_reason && ` (${explanation.fallback_reason}; template used.)`}{" "}
          {status?.llm === "anthropic" && explanation.method === "template" && (
            <button type="button" className="text-karst underline underline-offset-2" onClick={async () => setExplained(await post(`/findings/${encodeURIComponent(f.id)}/explain`, {}))}>
              Rephrase with Claude
            </button>
          )}
        </p>
      </Section>

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

      <Section id="raw-h" title="Raw FHIR and provenance">
        {data.raw && (
          <details className="rounded-lg border border-line bg-panel">
            <summary className="px-4 py-2 font-semibold">
              {f.resource.resource_type}/{f.resource.resource_id} exactly as served
            </summary>
            <pre className="json m-0 max-h-[28rem] overflow-auto border-t border-line px-4 py-3">{JSON.stringify(data.raw, null, 2)}</pre>
          </details>
        )}
        {f.provenance && (
          <dl className="mt-4 grid gap-x-6 gap-y-1 text-sm sm:grid-cols-[auto_1fr]">
            <dt className="text-ink-2">Source</dt>
            <dd className="m-0">
              {f.provenance.source.kind === "live" ? "Live" : `Snapshot ${f.provenance.source.snapshot_id}`}, {f.provenance.source.base_url}, fetched{" "}
              {when(f.provenance.source.fetched_at)}
            </dd>
            <dt className="text-ink-2">Record version</dt>
            <dd className="m-0">
              {f.provenance.resource_version_id ?? "—"}, last updated {f.provenance.resource_last_updated ?? "—"}
            </dd>
            <dt className="text-ink-2">Record sha256</dt>
            <dd className="code m-0 break-all">{f.provenance.resource_sha256}</dd>
            <dt className="text-ink-2">Checked with</dt>
            <dd className="m-0">
              rules {f.provenance.rules_version}, knowledge {f.provenance.knowledge_version}, {f.provenance.ig_source}
            </dd>
            <dt className="text-ink-2">Finding id</dt>
            <dd className="code m-0">{f.id}</dd>
          </dl>
        )}
        <div className="mt-4 flex flex-wrap gap-3">
          <Button onClick={copyJson}>{copied ? "Copied finding JSON" : "Copy finding JSON"}</Button>
          <Button onClick={() => download("/reports/operation-outcome.json")}>Download FHIR OperationOutcome (all findings)</Button>
        </div>
      </Section>
    </article>
  );
}
