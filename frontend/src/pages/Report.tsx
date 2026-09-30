import { useRun } from "../components/Shell";
import { Button, Chip, ErrorNote, FindingLink, Loading, SeverityTag, Verdict, useDocumentTitle } from "../components/ui";
import { download, useApi } from "../lib/api";
import { num, pretty, SEVERITY_ORDER, SEVERITY_TEXT, when } from "../lib/format";
import type { FindingCompact, Overview, SupportRow } from "../lib/types";

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

export default function Report() {
  useDocumentTitle("Report");
  const { runId } = useRun();
  const ov = useApi<Overview>("/overview", [runId]);
  const sup = useApi<SupportRow[]>("/support", [runId]);
  const crit = useApi<{ items: FindingCompact[] }>("/findings?severity=CRITICAL&limit=2000", [runId]);
  const o = ov.data;
  const s = o?.summary;
  const sv = s?.server_validation;
  const tally = (xs: string[]) => Object.entries(xs.reduce<Record<string, number>>((a, v) => ({ ...a, [v]: (a[v] ?? 0) + 1 }), {}));

  return (
    <article>
      <p className="m-0 text-sm font-semibold text-ink-2">OAH Data Doctor</p>
      <h1 className="m-0 mt-1 text-4xl font-bold tracking-tight">Scientific data integrity report</h1>
      {o && (
        <dl className="mt-4 grid max-w-[60rem] gap-x-6 gap-y-1 text-sm sm:grid-cols-[9rem_1fr]">
          <dt className="text-ink-2">Audit</dt>
          <dd className="code m-0 break-all">{o.run_id}</dd>
          <dt className="text-ink-2">Source</dt>
          <dd className="m-0 break-words">
            {o.source.kind === "live" ? "Live" : `Verified snapshot ${o.source.snapshot_id}`}, {o.source.base_url}
          </dd>
          <dt className="text-ink-2">Fetched</dt>
          <dd className="m-0">{when(o.source.fetched_at)}</dd>
          <dt className="text-ink-2">Checked with</dt>
          <dd className="m-0">rules <span className="code">{o.rules_version}</span>, knowledge <span className="code">{o.knowledge_version}</span>, OAH IG source commit <span className="code">{o.ig_commit.slice(0, 8)}</span></dd>
        </dl>
      )}
      <div className="no-print mt-5 flex flex-wrap gap-2">
        <Button kind="primary" onClick={() => window.print()}>Print or save as PDF</Button>
        <a className="inline-flex rounded-lg border border-line-strong px-3.5 py-2 font-semibold text-ink no-underline hover:bg-sunk" href="/api/reports/report.html" target="_blank" rel="noreferrer">
          Open the HTML report
        </a>
        <Button onClick={() => download("/reports/findings.json")}>Download JSON</Button>
        <Button onClick={() => download("/reports/operation-outcome.json")}>Export FHIR OperationOutcome</Button>
      </div>

      {o && s && (
        <section aria-labelledby="exec-h" className="mt-10">
          <h2 id="exec-h" className="m-0 text-2xl font-bold tracking-tight">Executive summary</h2>
          <ul className="mt-3 max-w-[75ch] space-y-1.5 pl-5">
            <li>
              {num(s.observations_checked)} observations read, {num(s.oah_observations)} of them official OneAquaHealth records;{" "}
              {num(s.resources_by_scope["third-party"] ?? 0)} resources written by other users of the open sandbox were not judged.
            </li>
            <li>
              {num(s.findings_total)} findings: {SEVERITY_ORDER.filter((k) => s.findings_by_severity[k]).map((k) => `${s.findings_by_severity[k]} ${SEVERITY_TEXT[k].toLowerCase()}`).join(", ")}.
            </li>
            <li>
              {num(s.oah_observations - s.oah_observations_with_blocking)} of {num(s.oah_observations)} official records can be used as published
              (no error or critical finding).
            </li>
            {sv?.flagged_observations_validated ? (
              <li>
                {num(sv.flagged_observations_passing_server_validation)} of {num(sv.flagged_observations_validated)} flagged records pass the FHIR
                server's own validation: conformance checking does not see these problems.
              </li>
            ) : null}
            <li>
              Comparisons: {tally(o.comparisons.map((c) => c.verdict)).map(([v, n]) => `${n} ${v.toLowerCase().replace(/_/g, " ")}`).join(", ")}. Claims:{" "}
              {tally(o.claims.map((c) => c.verdict)).map(([v, n]) => `${n} ${v.toLowerCase()}`).join(", ")}.
            </li>
            <li>Root causes are not claimed: a finding shows that published values cannot all be right, not which one is wrong or why.</li>
          </ul>
        </section>
      )}

      {crit.data && crit.data.items.length > 0 && (
        <section aria-labelledby="crit-h" className="mt-10">
          <h2 id="crit-h" className="m-0 text-2xl font-bold tracking-tight">Critical findings</h2>
          <p className="mt-1 text-ink-2">
            {num(crit.data.items.length)} critical findings. The first {num(Math.min(12, crit.data.items.length))} are listed; the JSON and
            OperationOutcome exports hold all of them.
          </p>
          <ul className="m-0 mt-3 list-none space-y-2 p-0">
            {crit.data.items.slice(0, 12).map((f) => (
              <li key={f.id} className="flex flex-wrap items-baseline gap-2 border-b border-line pb-2">
                <SeverityTag severity={f.severity} />
                <span className="readout text-sm text-ink-2">{f.rule_id}</span>
                <FindingLink id={f.id}>{f.resource.display ?? f.resource.resource_id}</FindingLink>
                <span className="w-full text-sm text-ink-2">{pretty(f.summary.replace(`${f.resource.display ?? ""}: `, ""))}</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {o && (
        <div className="mt-10 grid gap-10 lg:grid-cols-2">
          <section aria-labelledby="cmp-h">
            <h2 id="cmp-h" className="m-0 text-2xl font-bold tracking-tight">Comparability</h2>
            <ul className="m-0 mt-3 list-none space-y-2 p-0">
              {o.comparisons.map((c) => (
                <li key={c.id} className="flex flex-wrap items-start justify-between gap-2 border-b border-line pb-2 text-[0.95rem]">
                  <span className="max-w-[46ch]">{pretty(c.a)} <span className="text-ink-3">vs</span> {pretty(c.b)}</span>
                  <Verdict value={c.verdict} />
                </li>
              ))}
            </ul>
          </section>
          <section aria-labelledby="cs-h">
            <h2 id="cs-h" className="m-0 text-2xl font-bold tracking-tight">Claim safety</h2>
            <ul className="m-0 mt-3 list-none space-y-2 p-0">
              {o.claims.map((c) => (
                <li key={c.id} className="flex flex-wrap items-start justify-between gap-2 border-b border-line pb-2 text-[0.95rem]">
                  <span className="max-w-[46ch]">{pretty(c.text)}</span>
                  <Verdict value={c.verdict} />
                </li>
              ))}
            </ul>
          </section>
        </div>
      )}

      <h2 className="mb-0 mt-12 text-2xl font-bold tracking-tight">Exports</h2>

      <ul className="mt-6 grid list-none gap-4 p-0 md:grid-cols-2">
        {EXPORTS.map((e) => (
          <li key={e.path} className="flex flex-col justify-between gap-3 rounded-xl border border-line bg-panel p-4">
            <div>
              <h2 className="m-0 text-lg font-bold">{e.title}</h2>
              <p className="m-0 mt-1 text-ink-2">{e.body}</p>
            </div>
            <div>
              {e.path.endsWith(".html") ? (
                <a className="inline-flex rounded-lg border border-line-strong px-3.5 py-2 font-semibold text-ink no-underline hover:bg-sunk" href={`/api${e.path}`} target="_blank" rel="noreferrer">
                  Open {e.title.toLowerCase()}
                </a>
              ) : (
                <Button onClick={() => download(e.path)}>Download {e.title.split(" (")[0].toLowerCase()}</Button>
              )}
            </div>
          </li>
        ))}
      </ul>

      <section aria-labelledby="lim-h" className="mt-12">
        <h2 id="lim-h" className="m-0 text-2xl font-bold tracking-tight">Limitations</h2>
        <ul className="mt-3 max-w-[75ch] space-y-1.5 pl-5 text-ink-2">
          <li>A finding proves that published values cannot all be right. It does not say which value is wrong or why.</li>
          <li>Cohort sizes, sample counts and data coverage are not published, so differences between cohorts cannot be tested for significance.</li>
          <li>OAH profile checks are transcribed from the Implementation Guide source, because the sandbox hosts no profiles.</li>
          <li>Typical ranges are general; values outside them are reported as unusual, never as wrong.</li>
          <li>The impact trace covers only the analyses Data Doctor computes, not every possible use of the data.</li>
        </ul>
      </section>

      <section aria-labelledby="sup-h" className="mt-12">
        <h2 id="sup-h" className="m-0 text-2xl font-bold tracking-tight">What this data can and cannot support</h2>
        <p className="mt-1 max-w-[75ch] text-ink-2">
          One row per published data set and indicator. Status follows from the error and critical findings on its records.
        </p>
        {sup.error && <ErrorNote error={sup.error} />}
        {!sup.data && !sup.error && <Loading what="the support table" />}
        {sup.data && (
          <div className="max-h-[70vh] overflow-auto rounded-xl border border-line bg-panel" tabIndex={0} role="region" aria-labelledby="sup-h">
            <table className="data">
              <caption className="sr-only">Support status per data set and indicator</caption>
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
      </section>
    </article>
  );
}
