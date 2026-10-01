import { useEffect, useState, type ReactNode } from "react";
import { useRun } from "../components/Shell";
import { Button, Chip, ErrorNote, FindingLink, Loading, Metric, SeverityShape, Verdict, useDocumentTitle } from "../components/ui";
import { api, download, useApi } from "../lib/api";
import { num, pretty, SEVERITY_ORDER, SEVERITY_TEXT, unit as unitText, when } from "../lib/format";
import type { Calculation, FindingCompact, FindingDetail, Overview, RuleSpec, Severity, SupportRow } from "../lib/types";

const STATUS_TEXT: Record<SupportRow["status"], string> = {
  USABLE: "Usable",
  USABLE_WITH_CAVEATS: "Usable with caveats",
  PARTLY_USABLE: "Partly usable",
  NOT_USABLE: "Do not use until reviewed",
};

const EXPORTS = [
  { path: "/reports/report.html", title: "Researcher report (HTML)", body: "Readable summary: what the data can support, findings by rule, comparisons, claims, limitations." },
  { path: "/reports/report.md", title: "Researcher report (Markdown)", body: "The same report for repositories, wikis and pull requests." },
  { path: "/reports/operation-outcome.json", title: "FHIR OperationOutcome bundle", body: "One OperationOutcome per affected resource, issues with FHIRPath expressions. Validated against FHIR R4." },
  { path: "/reports/findings.json", title: "Findings (JSON)", body: "Every finding with evidence, provenance, lineage and the run summary. Schema in schemas/finding.schema.json." },
];

const SECTIONS = [
  ["exec", "Executive finding"],
  ["health", "Dataset health"],
  ["crit", "Critical findings"],
  ["cons", "Scientific consequences"],
  ["cmp", "Comparability"],
  ["claims", "Claim safety"],
  ["prov", "Provenance"],
  ["rules", "Rules applied"],
  ["appx", "Technical appendix"],
] as const;

const SEV_TEXT_CLASS: Record<Severity, string> = { CRITICAL: "text-cinnabar", ERROR: "text-ochre", WARNING: "text-sulfur", INFO: "text-slate" };

/** What kind of statement something is. Every statement in the report is one of these four, never presented as another. */
type Kind = "OBSERVED" | "DERIVED" | "INFERRED" | "UNKNOWN";
const KIND_TEXT: Record<Kind, string> = {
  OBSERVED: "read from the FHIR server or the verified snapshot, verbatim",
  DERIVED: "computed from observed values by deterministic rules",
  INFERRED: "a hypothesis that fits the evidence; not verified",
  UNKNOWN: "not established by the evidence",
};

function KindTag({ kind }: { kind: Kind }) {
  const style = {
    OBSERVED: "border-line-strong text-ink-2",
    DERIVED: "border-line-strong text-ink-2",
    INFERRED: "border-dashed border-line-strong text-ink-2",
    UNKNOWN: "border-sulfur/50 bg-sulfur-soft text-sulfur",
  }[kind];
  return (
    <span className={`inline-block whitespace-nowrap rounded border px-1.5 py-px align-[1px] text-[0.68rem] font-bold uppercase tracking-[0.08em] ${style}`}>
      {kind.toLowerCase()}
    </span>
  );
}

function Part({ id, n, title, kinds = [], children }: { id: string; n: number; title: string; kinds?: Kind[]; children: ReactNode }) {
  return (
    <section aria-labelledby={`${id}-h`} className="report-part mt-12 border-t border-line pt-6">
      <h2 id={`${id}-h`} className="m-0 flex flex-wrap items-baseline gap-x-3 gap-y-1 text-xl font-bold tracking-tight">
        <span className="readout text-sm font-semibold text-ink-3">{n}</span>
        {title}
        {kinds.length > 0 && (
          <span className="flex gap-1.5">
            {kinds.map((k) => (
              <KindTag key={k} kind={k} />
            ))}
          </span>
        )}
      </h2>
      <div className="mt-4">{children}</div>
    </section>
  );
}

/** The audit as a document: every number from this run, sections in reading order, printable as it stands. */
export default function Report() {
  useDocumentTitle("Report");
  const { runId } = useRun();
  const ov = useApi<Overview>("/overview", [runId]);
  const sup = useApi<SupportRow[]>("/support", [runId]);
  const crit = useApi<{ items: FindingCompact[] }>("/findings?severity=CRITICAL&limit=2000", [runId]);
  const rules = useApi<RuleSpec[]>("/rules", [runId]);
  const heroId = ov.data?.hero_finding?.id;
  const hero = useApi<FindingDetail>(heroId ? `/findings/${encodeURIComponent(heroId)}` : null, [runId]);
  const o = ov.data;
  const s = o?.summary;
  const sv = s?.server_validation;
  const h = hero.data;
  const tally = (xs: string[]) => Object.entries(xs.reduce<Record<string, number>>((a, v) => ({ ...a, [v]: (a[v] ?? 0) + 1 }), {}));
  // Every finding on the most important record, with the backend's own calculation for each (derived statements).
  const [recordFindings, setRecordFindings] = useState<{ rule: string; calc: Calculation | null; hypotheses: string[] }[] | null>(null);
  useEffect(() => {
    if (!h) return;
    let alive = true;
    const ids = [h.finding.id, ...h.same_resource.map((x) => x.id)];
    Promise.all(ids.map((id) => api<FindingDetail>(`/findings/${encodeURIComponent(id)}`)))
      .then((ds) => alive && setRecordFindings(ds.map((d) => ({ rule: d.finding.rule_id, calc: d.calculation, hypotheses: d.finding.hypotheses }))))
      .catch(() => alive && setRecordFindings([]));
    return () => {
      alive = false;
    };
  }, [h]);

  if (ov.error) return <ErrorNote error={`Could not load the audit: ${ov.error}`} />;
  if (!o || !s) return <Loading what="the report" />;
  const usable = s.oah_observations - s.oah_observations_with_blocking;
  const avg = h?.record?.stats.find((x) => x.stat === "average");
  const notUsable = (sup.data ?? []).filter((r) => r.status === "NOT_USABLE");

  return (
    <article className="report-doc mx-auto max-w-[900px] rounded-lg border border-line bg-panel px-5 py-8 sm:px-10 sm:py-10">
      <header>
        <p className="m-0 text-sm font-semibold text-ink-2">OAH Data Doctor</p>
        <h1 className="m-0 mt-1 text-[2rem] font-bold leading-tight tracking-tight">Evidence integrity report</h1>
        <dl className="m-0 mt-5 grid gap-x-6 gap-y-1.5 text-sm sm:grid-cols-[9rem_1fr]">
          <dt className="text-ink-2">Dataset</dt>
          <dd className="m-0">
            OneAquaHealth FHIR sandbox: {num(s.observations_checked)} observations, {num(s.oah_observations)} of them official OAH examples
          </dd>
          <dt className="text-ink-2">Source</dt>
          <dd className="m-0 break-all">{o.source.base_url}</dd>
          <dt className="text-ink-2">Mode</dt>
          <dd className="m-0">
            {o.source.kind === "live" ? "Live: read from the server during the audit" : `Verified snapshot ${o.source.snapshot_id}, fetched ${when(o.source.fetched_at)}`}
          </dd>
          <dt className="text-ink-2">Audit timestamp</dt>
          <dd className="m-0">{when(o.created_at)}</dd>
          <dt className="text-ink-2">Audit id</dt>
          <dd className="code m-0 break-all">{o.run_id}</dd>
        </dl>
        <div className="no-print mt-6 flex flex-wrap gap-2">
          <Button kind="primary" onClick={() => window.print()}>Print or save as PDF</Button>
          <a className="inline-flex rounded-md border border-line-strong px-3.5 py-2 font-semibold text-ink no-underline hover:bg-sunk" href="/api/reports/report.html" target="_blank" rel="noreferrer">
            Open the HTML report
          </a>
          <Button onClick={() => download("/reports/findings.json")}>Download JSON</Button>
          <Button onClick={() => download("/reports/operation-outcome.json")}>Export FHIR OperationOutcome</Button>
        </div>
        <dl className="m-0 mt-8 grid gap-x-4 gap-y-1 text-sm sm:grid-cols-[6.5rem_1fr]" aria-label="How to read this report">
          {(Object.keys(KIND_TEXT) as Kind[]).map((k) => (
            <div key={k} className="contents">
              <dt>
                <KindTag kind={k} />
              </dt>
              <dd className="m-0 text-ink-2">{KIND_TEXT[k]}</dd>
            </div>
          ))}
        </dl>
        <nav aria-label="Report contents" className="no-print mt-8">
          <p className="m-0 mb-2 text-[0.72rem] font-bold uppercase tracking-[0.1em] text-ink-2">Contents</p>
          <ol className="m-0 grid list-none gap-x-6 gap-y-1 p-0 text-sm sm:grid-cols-3">
            {SECTIONS.map(([id, t], i) => (
              <li key={id}>
                <a href={`#${id}-h`} className="text-ink underline decoration-line-strong underline-offset-2 hover:text-karst">
                  <span className="readout text-ink-3">{i + 1}</span> {t}
                </a>
              </li>
            ))}
          </ol>
        </nav>
      </header>

      <Part id="exec" n={1} title="Executive finding">
        {h && avg && h.record ? (
          <dl className="m-0 grid max-w-[72ch] gap-x-4 gap-y-3 sm:grid-cols-[6.5rem_minmax(0,1fr)]" aria-label="Most important record">
            <dt><KindTag kind="OBSERVED" /></dt>
            <dd className="m-0">
              <span className="font-semibold">{h.finding.resource.display}</span> (<span className="code">{h.finding.resource.resource_type}/{h.finding.resource.resource_id}</span>)
              is published with{" "}
              {h.record.stats.map((x, i) => (
                <span key={x.stat}>
                  {i > 0 && ", "}
                  {x.stat} <strong className="readout">{num(x.value)}&nbsp;{unitText(x.unit)}</strong>
                </span>
              ))}
              . The FHIR server's own validator says:{" "}
              {h.server_validation
                ? h.server_validation.issue.map((i) => i.diagnostics ?? i.severity).join("; ")
                : "not checked in this run"}
              .
            </dd>
            <dt><KindTag kind="DERIVED" /></dt>
            <dd className="m-0">
              {recordFindings === null ? (
                "Loading the calculations…"
              ) : (
                <ul className="m-0 list-none space-y-1 p-0">
                  {recordFindings.map((r) => (
                    <li key={r.rule}>
                      <span className="code text-ink-2">{r.rule}</span>{" "}
                      {r.calc ? (
                        <>
                          {r.calc.steps[0] && (
                            <span className="readout">
                              {r.calc.steps[0].expression} = {r.calc.steps[0].result};{" "}
                            </span>
                          )}
                          {r.calc.result}
                          {r.calc.check && (
                            <>
                              {" "}
                              <span className="code">{r.calc.check.constraint}</span> does not hold ({r.calc.check.evaluated}).
                            </>
                          )}
                        </>
                      ) : (
                        "flagged by a rule that does no arithmetic; see the finding."
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </dd>
            <dt><KindTag kind="INFERRED" /></dt>
            <dd className="m-0">
              {recordFindings && recordFindings.some((r) => r.hypotheses.length)
                ? Array.from(new Set(recordFindings.flatMap((r) => r.hypotheses))).join(" ")
                : "No hypothesis is offered for this record."}
            </dd>
            <dt><KindTag kind="UNKNOWN" /></dt>
            <dd className="m-0">Root cause: which published value is wrong, and why, is not established. No value is corrected.</dd>
          </dl>
        ) : null}
        <ul className="mb-0 mt-5 max-w-[72ch] space-y-1.5 pl-5" aria-label="The whole audit">
          <li>
            {num(s.findings_total)} findings: {SEVERITY_ORDER.filter((k) => s.findings_by_severity[k]).map((k) => `${s.findings_by_severity[k]} ${SEVERITY_TEXT[k].toLowerCase()}`).join(", ")}.
          </li>
          <li>
            {num(usable)} of {num(s.oah_observations)} official records can be used as published (no error or critical finding).
          </li>
          {sv?.flagged_observations_validated ? (
            <li>
              {num(sv.flagged_observations_passing_server_validation)} of {num(sv.flagged_observations_validated)} flagged records pass the FHIR
              server's own validation: conformance checking does not see these problems.
            </li>
          ) : null}
        </ul>
      </Part>

      <Part id="health" n={2} title="Dataset health" kinds={["DERIVED"]}>
        <dl className="m-0 grid grid-cols-2 gap-x-6 gap-y-5 md:grid-cols-4">
          <Metric label="Observations checked" value={num(s.observations_checked)} note={`${num(s.oah_observations)} official`} />
          <Metric label="Findings" value={num(s.findings_total)} note={`${num(s.affected_resources)} records affected`} />
          <Metric label="Usable as published" value={`${num(usable)} of ${num(s.oah_observations)}`} note="official records" />
          {sv?.flagged_observations_validated ? (
            <Metric
              label="Flagged, yet server-valid"
              value={`${num(sv.flagged_observations_passing_server_validation)} of ${num(sv.flagged_observations_validated)}`}
              note="HAPI $validate, no error"
              critical={sv.flagged_observations_passing_server_validation > 0}
            />
          ) : (
            <Metric label="Third-party resources" value={num(s.resources_by_scope["third-party"] ?? 0)} note="not judged" />
          )}
        </dl>
        <p className="mb-0 mt-5 max-w-[72ch] text-ink-2">
          {num(s.resources_by_scope["third-party"] ?? 0)} resources written to the open sandbox by other users were read but not judged.
          Findings by category:{" "}
          {Object.entries(o.findings_by_category)
            .map(([c, n]) => `${n} ${c.toLowerCase()}`)
            .join(", ")}
          .
        </p>
      </Part>

      <Part id="crit" n={3} title="Critical findings" kinds={["OBSERVED", "DERIVED"]}>
        {crit.data && crit.data.items.length > 0 ? (
          <>
            <p className="m-0 text-ink-2">
              {num(crit.data.items.length)} critical findings. The first {num(Math.min(12, crit.data.items.length))} are listed; the JSON and
              OperationOutcome exports hold all of them.
            </p>
            <ol className="m-0 mt-3 list-none p-0">
              {crit.data.items.slice(0, 12).map((f) => (
                <li key={f.id} className="grid gap-x-4 border-b border-line py-2.5 last:border-b-0 sm:grid-cols-[8.5rem_minmax(0,1fr)]">
                  <span className="flex items-baseline gap-1.5 text-sm">
                    <span className={SEV_TEXT_CLASS[f.severity]}>
                      <SeverityShape severity={f.severity} />
                    </span>
                    <span className="code text-ink-2">{f.rule_id}</span>
                  </span>
                  <span className="min-w-0">
                    <FindingLink id={f.id}>{f.resource.display ?? f.resource.resource_id}</FindingLink>
                    <span className="block text-sm text-ink-2">{pretty(f.summary.replace(`${f.resource.display ?? ""}: `, ""))}</span>
                  </span>
                </li>
              ))}
            </ol>
          </>
        ) : (
          <p className="m-0 text-ink-2">{crit.data ? "No critical findings in this audit." : "Loading…"}</p>
        )}
      </Part>

      <Part id="cons" n={4} title="Scientific consequences" kinds={["DERIVED"]}>
        {h && <p className="m-0 max-w-[72ch]">{h.impact.statement}</p>}
        <p className="mb-0 mt-3 max-w-[72ch] text-ink-2">
          {notUsable.length} published data set and indicator combinations should not be used until reviewed. One row per data set and
          indicator; status follows from the error and critical findings on its records.
        </p>
        {sup.error && <ErrorNote error={sup.error} />}
        {!sup.data && !sup.error && <Loading what="the support table" />}
        {sup.data && (
          <div className="mt-4 max-h-[70vh] overflow-auto rounded-md border border-line" tabIndex={0} role="region" aria-labelledby="cons-h">
            <table className="data dense">
              <caption className="sr-only">What each data set and indicator can and cannot support</caption>
              <thead>
                <tr>
                  <th scope="col">Data set</th>
                  <th scope="col">Indicator</th>
                  <th scope="col">Records</th>
                  <th scope="col">Status</th>
                  <th scope="col">Can support</th>
                  <th scope="col">Cannot support</th>
                </tr>
              </thead>
              <tbody>
                {sup.data.map((r) => (
                  <tr key={`${r.library_id}-${r.indicator_key}`}>
                    <td>{r.library_title}</td>
                    <td>{r.indicator_label}</td>
                    <td className="readout whitespace-nowrap">
                      {r.observations}
                      <span className="block text-xs text-ink-3">{r.years.join(", ")}</span>
                    </td>
                    <td className="whitespace-nowrap">
                      <Chip text={STATUS_TEXT[r.status]} toneOf={r.status} />
                    </td>
                    <td className="max-w-[28ch]">{r.can_support.join("; ") || "—"}</td>
                    <td className="max-w-[32ch] text-ink-2">{r.cannot_support.join("; ")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Part>

      <Part id="cmp" n={5} title="Comparability" kinds={["DERIVED"]}>
        <p className="m-0 text-ink-2">
          {tally(o.comparisons.map((c) => c.verdict)).map(([v, n]) => `${n} ${v.toLowerCase().replace(/_/g, " ")}`).join(", ")}.
        </p>
        <ul className="m-0 mt-3 list-none p-0">
          {o.comparisons.map((c) => (
            <li key={c.id} className="flex flex-wrap items-start justify-between gap-2 border-b border-line py-2 text-[0.95rem] last:border-b-0">
              <span className="max-w-[56ch]">{pretty(c.a)} <span className="text-ink-3">vs</span> {pretty(c.b)}</span>
              <Verdict value={c.verdict} />
            </li>
          ))}
        </ul>
      </Part>

      <Part id="claims" n={6} title="Claim safety" kinds={["DERIVED"]}>
        <p className="m-0 text-ink-2">{tally(o.claims.map((c) => c.verdict)).map(([v, n]) => `${n} ${v.toLowerCase()}`).join(", ")}.</p>
        <ul className="m-0 mt-3 list-none p-0">
          {o.claims.map((c) => (
            <li key={c.id} className="flex flex-wrap items-start justify-between gap-2 border-b border-line py-2 text-[0.95rem] last:border-b-0">
              <span className="max-w-[56ch]">{pretty(c.text)}</span>
              <Verdict value={c.verdict} />
            </li>
          ))}
        </ul>
      </Part>

      <Part id="prov" n={7} title="Provenance" kinds={["OBSERVED"]}>
        <dl className="m-0 grid gap-x-6 gap-y-1.5 text-sm sm:grid-cols-[11rem_1fr]">
          <dt className="text-ink-2">Server</dt>
          <dd className="m-0 break-all">{o.source.base_url}</dd>
          <dt className="text-ink-2">Retrieved</dt>
          <dd className="m-0">{when(o.source.fetched_at)}</dd>
          <dt className="text-ink-2">Mode</dt>
          <dd className="m-0">{o.source.kind === "live" ? "Live" : `Snapshot ${o.source.snapshot_id}`}</dd>
          {o.source.manifest_sha256 && (
            <>
              <dt className="text-ink-2">Snapshot manifest sha256</dt>
              <dd className="code m-0 break-all">{o.source.manifest_sha256}</dd>
            </>
          )}
          {o.source.fallback_reason && (
            <>
              <dt className="text-ink-2">Why not live</dt>
              <dd className="m-0">{o.source.fallback_reason}</dd>
            </>
          )}
          <dt className="text-ink-2">Resources read</dt>
          <dd className="m-0">
            {Object.entries(s.resources_by_type)
              .map(([t, n]) => `${num(n)} ${t}`)
              .join(", ")}
          </dd>
          <dt className="text-ink-2">Rules version</dt>
          <dd className="code m-0">{o.rules_version}</dd>
          <dt className="text-ink-2">Knowledge version</dt>
          <dd className="code m-0">{o.knowledge_version}</dd>
          <dt className="text-ink-2">OAH IG source commit</dt>
          <dd className="code m-0 break-all">{o.ig_commit}</dd>
        </dl>
        <p className="mb-0 mt-3 text-sm text-ink-3">Data Doctor reads only (GET and $validate); it never writes to the server or corrects a value.</p>
      </Part>

      <Part id="rules" n={8} title="Rules applied">
        {rules.data ? (
          <div className="overflow-x-auto rounded-md border border-line" tabIndex={0} role="region" aria-labelledby="rules-h">
            <table className="data dense">
              <caption className="sr-only">Every rule applied in this audit and its number of findings</caption>
              <thead>
                <tr>
                  <th scope="col">Rule</th>
                  <th scope="col">What it checks</th>
                  <th scope="col">Severity</th>
                  <th scope="col" className="text-right">Findings</th>
                </tr>
              </thead>
              <tbody>
                {rules.data.map((r) => (
                  <tr key={r.id}>
                    <td className="code whitespace-nowrap">{r.id}</td>
                    <td>{r.title}</td>
                    <td className="whitespace-nowrap text-sm text-ink-2">{r.severity.charAt(0) + r.severity.slice(1).toLowerCase()}</td>
                    <td className="readout text-right">{r.findings ?? 0}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <Loading what="the rules" />
        )}
      </Part>

      <Part id="appx" n={9} title="Technical appendix">
        <h3 className="m-0 text-base font-semibold">Exports</h3>
        <ul className="m-0 mt-3 grid list-none gap-3 p-0 md:grid-cols-2">
          {EXPORTS.map((e) => (
            <li key={e.path} className="flex flex-col justify-between gap-3 rounded-md border border-line p-4">
              <div>
                <p className="m-0 font-semibold">{e.title}</p>
                <p className="m-0 mt-1 text-sm text-ink-2">{e.body}</p>
              </div>
              <div className="no-print">
                {e.path.endsWith(".html") ? (
                  <a className="inline-flex rounded-md border border-line-strong px-3.5 py-2 font-semibold text-ink no-underline hover:bg-sunk" href={`/api${e.path}`} target="_blank" rel="noreferrer">
                    Open {e.title.toLowerCase()}
                  </a>
                ) : (
                  <Button onClick={() => download(e.path)}>Download {e.title.split(" (")[0].toLowerCase()}</Button>
                )}
              </div>
            </li>
          ))}
        </ul>
        <h3 className="mb-0 mt-8 text-base font-semibold">Limitations</h3>
        <ul className="mb-0 mt-2 max-w-[75ch] space-y-1.5 pl-5 text-ink-2">
          <li>A finding proves that published values cannot all be right. It does not say which value is wrong or why.</li>
          <li>Cohort sizes, sample counts and data coverage are not published, so differences between cohorts cannot be tested for significance.</li>
          <li>OAH profile checks are transcribed from the Implementation Guide source, because the sandbox hosts no profiles.</li>
          <li>Typical ranges are general; values outside them are reported as unusual, never as wrong.</li>
          <li>The impact trace covers only the analyses Data Doctor computes, not every possible use of the data.</li>
        </ul>
      </Part>
    </article>
  );
}
