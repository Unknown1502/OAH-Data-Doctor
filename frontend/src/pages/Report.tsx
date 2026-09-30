import { useRun } from "../components/Shell";
import { Button, Chip, ErrorNote, Loading, useDocumentTitle } from "../components/ui";
import { download, useApi } from "../lib/api";
import { when } from "../lib/format";
import type { Overview, SupportRow } from "../lib/types";

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

  return (
    <article>
      <h1 className="m-0 text-4xl font-bold tracking-tight">Report and exports</h1>
      {ov.data && (
        <p className="mt-2 max-w-[75ch] text-lg text-ink-2">
          Run {ov.data.run_id}, from the {ov.data.source.kind === "live" ? "live sandbox" : `snapshot ${ov.data.source.snapshot_id}`} fetched{" "}
          {when(ov.data.source.fetched_at)}. Every number in these files is computed from that data; nothing is typed in by hand.
        </p>
      )}

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
