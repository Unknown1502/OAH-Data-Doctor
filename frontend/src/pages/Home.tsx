import { Link } from "react-router-dom";
import TwoVerdicts from "../components/TwoVerdicts";
import WhatIfLab from "../components/WhatIfLab";
import { useRun } from "../components/Shell";
import { Chip, ErrorNote, Loading, Readout, SeverityShape, Verdict, useDocumentTitle } from "../components/ui";
import { useApi } from "../lib/api";
import { num, pretty, SEVERITY_ORDER, SEVERITY_TEXT, unit as unitText, when } from "../lib/format";
import type { FindingDetail, Overview, RuleSpec, SupportRow } from "../lib/types";

const STATUS_TEXT: Record<SupportRow["status"], string> = {
  USABLE: "Usable",
  USABLE_WITH_CAVEATS: "Usable with caveats",
  PARTLY_USABLE: "Partly usable",
  NOT_USABLE: "Do not use until reviewed",
};

export default function Home() {
  useDocumentTitle("Data health");
  const { runId } = useRun();
  const ov = useApi<Overview>("/overview", [runId]);
  const heroId = ov.data?.hero_finding?.id;
  const hero = useApi<FindingDetail>(heroId ? `/findings/${encodeURIComponent(heroId)}` : null, [runId]);
  const rules = useApi<RuleSpec[]>("/rules", [runId]);
  const support = useApi<SupportRow[]>("/support", [runId]);

  if (ov.error) return <ErrorNote error={`Could not load the audit: ${ov.error}`} />;
  if (!ov.data) return <Loading what="the latest audit" />;
  const o = ov.data;
  const s = o.summary;
  const h = hero.data;
  const avg = h?.record?.stats.find((x) => x.stat === "average");
  const serverOk = h?.server_validation && !h.server_validation.issue.some((i) => i.severity === "error" || i.severity === "fatal");
  const sv = s.server_validation;
  const statusCounts = (support.data ?? []).reduce<Record<string, number>>((acc, r) => ({ ...acc, [r.status]: (acc[r.status] ?? 0) + 1 }), {});
  const maxSite = Math.max(1, ...Object.values(o.blocking_by_site));

  return (
    <article>
      <section aria-labelledby="run-h" className="mb-10 border-b border-line pb-6">
        <h2 id="run-h" className="m-0 mb-4 text-sm font-semibold text-ink-2">
          Data health: can you trust this dataset? What this audit read and found
        </h2>
        <dl className="m-0 grid grid-cols-2 gap-6 md:grid-cols-4">
          <Readout label="Observations checked" value={num(s.observations_checked)} note={`${num(s.oah_observations)} official OAH examples`} />
          <Readout
            label="Findings"
            value={num(s.findings_total)}
            note={SEVERITY_ORDER.filter((k) => s.findings_by_severity[k]).map((k) => `${s.findings_by_severity[k]} ${SEVERITY_TEXT[k].toLowerCase()}`).join(", ")}
          />
          <Readout
            label="Official records safe to use as published"
            value={`${num(s.oah_observations - s.oah_observations_with_blocking)} of ${num(s.oah_observations)}`}
            note="no error or critical finding"
          />
          {sv?.flagged_observations_validated ? (
            <Readout
              label="Flagged records the server calls valid"
              value={`${num(sv.flagged_observations_passing_server_validation)} of ${num(sv.flagged_observations_validated)}`}
              note="HAPI $validate reported no error"
              tone="bad"
            />
          ) : (
            <Readout label="Affected records" value={num(s.affected_resources)} />
          )}
        </dl>
      </section>
      <section aria-labelledby="hero-h" className="mb-12">
        <p className="m-0 mb-3 text-ink-2">
          A record from the {o.source.kind === "live" ? "live OneAquaHealth sandbox" : `OneAquaHealth sandbox snapshot of ${when(o.source.fetched_at)}`}
        </p>
        {h && avg && h.record ? (
          <h1 id="hero-h" className="m-0 max-w-[22ch] text-[clamp(2rem,4.6vw,3.4rem)] font-bold leading-[1.05] tracking-tight">
            A {h.record.indicator?.toLowerCase()} of <span className="whitespace-nowrap">{num(avg.value)}&nbsp;{unitText(avg.unit)}</span>{" "}
            {serverOk ? "passes FHIR validation." : "is published as fact."}
          </h1>
        ) : (
          <h1 id="hero-h" className="m-0 text-4xl font-bold tracking-tight">
            Does this data make scientific sense?
          </h1>
        )}
        {h && (
          <p className="mt-5 max-w-[68ch] text-lg leading-relaxed text-ink-2">
            It is the {h.record?.year} annual summary for {h.record?.location}, published with a median of{" "}
            {num(h.record?.stats.find((x) => x.stat === "median")?.value ?? null)}&nbsp;{unitText(avg?.unit)}. Those numbers cannot describe the same water. FHIR checks that data has the right shape; Data Doctor
            checks whether it can be true, traces what it would contaminate, and tells you what you can still safely conclude.
          </p>
        )}
        {h && (
          <div className="mt-6 max-w-[860px]">
            <TwoVerdicts serverOutcome={h.server_validation} findings={[h.finding, ...h.same_resource]} record={h.finding.resource.display ?? ""} />
          </div>
        )}
        {h && (
          <div className="mt-5">
            <p className="m-0 max-w-[70ch] text-ink-2">
              <strong className="text-ink">What it may affect:</strong> {h.impact.statement}
            </p>
            <p className="mb-0 mt-4 flex flex-wrap items-center gap-x-6 gap-y-3">
              <Link className="inline-flex rounded-lg border border-karst bg-karst px-4 py-2 font-semibold text-chalk no-underline hover:brightness-110" to={`/findings/${encodeURIComponent(h.finding.id)}`}>
                Open the evidence for this record
              </Link>
              <Link className="font-semibold text-karst underline underline-offset-4" to="/findings">
                See all {num(s.findings_total)} findings
              </Link>
            </p>
          </div>
        )}
        {h?.record && (
          <section aria-labelledby="lab-h" className="mt-10">
            <h2 id="lab-h" className="m-0 text-2xl font-bold tracking-tight">
              Change the numbers yourself
            </h2>
            <p className="mb-4 mt-1 max-w-[70ch] text-ink-2">
              Edit any value of this record and watch the rules react. Then ask the real FHIR server about the same numbers: it
              checks the shape of the data, not whether it can be true.
            </p>
            <WhatIfLab observationId={h.finding.resource.resource_id} record={h.record} />
          </section>
        )}

      </section>


      <div className="grid gap-12 lg:grid-cols-[1.1fr_1fr]">
        <section aria-labelledby="sites-h" className="min-w-0">
          <h2 id="sites-h" className="m-0 mb-1 text-2xl font-bold tracking-tight">
            Where the blocking findings are
          </h2>
          <p className="mt-0 text-ink-2">Error and critical findings on official records, by monitoring site. Select a site to see its findings.</p>
          <ul className="m-0 list-none space-y-2.5 p-0">
            {Object.entries(o.blocking_by_site).map(([site, n]) => (
              <li key={site}>
                <Link to={`/findings?q=${encodeURIComponent(site)}`} className="group block rounded-md text-ink no-underline">
                  <div className="flex items-baseline justify-between gap-3 text-[0.95rem]">
                    <span className="group-hover:text-karst group-hover:underline">{site}</span>
                    <span className="readout font-semibold">{n}</span>
                  </div>
                  <div className="mt-1 h-2 rounded-full bg-sunk" aria-hidden="true">
                    <div className="h-2 rounded-full bg-cinnabar group-hover:bg-karst" style={{ width: `${(100 * n) / maxSite}%` }} />
                  </div>
                </Link>
              </li>
            ))}
          </ul>

          <h2 className="mb-1 mt-10 text-2xl font-bold tracking-tight">Rules that fired</h2>
          <p className="mt-0 text-ink-2">Each rule is a deterministic check with its own tests. Select a rule to see its findings.</p>
          {rules.data && (
            <table className="data">
              <caption className="sr-only">Rules and number of findings in this run</caption>
              <thead>
                <tr>
                  <th scope="col">Rule</th>
                  <th scope="col">What it checks</th>
                  <th scope="col" className="text-right">
                    Findings
                  </th>
                </tr>
              </thead>
              <tbody>
                {rules.data
                  .filter((r) => r.findings)
                  .sort((a, b) => (b.findings ?? 0) - (a.findings ?? 0))
                  .map((r) => (
                    <tr key={r.id}>
                      <td className="whitespace-nowrap">
                        <Link className="text-karst underline underline-offset-2" to={`/findings?rule=${r.id}`}>
                          {r.id}
                        </Link>
                      </td>
                      <td>{r.title}</td>
                      <td className="readout text-right">{r.findings}</td>
                    </tr>
                  ))}
              </tbody>
            </table>
          )}
        </section>

        <section aria-labelledby="sup-h" className="min-w-0">
          <h2 id="sup-h" className="m-0 mb-1 text-2xl font-bold tracking-tight">
            What the data can support
          </h2>
          <p className="mt-0 text-ink-2">
            Each published data set and indicator, judged by the findings on its records.{" "}
            <Link className="text-karst underline underline-offset-2" to="/report">
              Full table in the report
            </Link>
          </p>
          <ul className="m-0 mb-6 flex list-none flex-wrap gap-2 p-0">
            {(["USABLE", "USABLE_WITH_CAVEATS", "PARTLY_USABLE", "NOT_USABLE"] as const)
              .filter((k) => statusCounts[k])
              .map((k) => (
                <li key={k}>
                  <Chip text={`${STATUS_TEXT[k]}: ${statusCounts[k]}`} toneOf={k} />
                </li>
              ))}
          </ul>

          <h2 className="mb-1 mt-2 text-2xl font-bold tracking-tight">Checks we ran on this data</h2>
          <p className="mt-0 text-ink-2">Recomputed on every scan, so their verdicts follow the data.</p>
          <h3 className="mb-2 mt-5 text-lg font-semibold">Comparisons</h3>
          <ul className="m-0 list-none space-y-2 p-0">
            {o.comparisons.map((c) => (
              <li key={c.id} className="flex flex-wrap items-start justify-between gap-2 border-b border-line pb-2 text-[0.95rem]">
                <Link to={`/compare?id=${c.id}`} className="max-w-[46ch] text-ink no-underline hover:text-karst">
                  {pretty(c.a)} <span className="text-ink-3">vs</span> {pretty(c.b)}
                </Link>
                <Verdict value={c.verdict} />
              </li>
            ))}
          </ul>
          <h3 className="mb-2 mt-6 text-lg font-semibold">Claims</h3>
          <ul className="m-0 list-none space-y-2 p-0">
            {o.claims.map((c) => (
              <li key={c.id} className="flex flex-wrap items-start justify-between gap-2 border-b border-line pb-2 text-[0.95rem]">
                <Link to={`/claims?id=${c.id}`} className="max-w-[46ch] text-ink no-underline hover:text-karst">
                  {pretty(c.text)}
                </Link>
                <Verdict value={c.verdict} />
              </li>
            ))}
          </ul>
        </section>
      </div>

      <p className="mt-12 text-sm text-ink-3">
        Run <span className="code">{o.run_id}</span>, rules {o.rules_version}, knowledge {o.knowledge_version}, OAH IG source commit{" "}
        {o.ig_commit.slice(0, 8)}. Severity marks: <SeverityShape severity="CRITICAL" /> critical, <SeverityShape severity="ERROR" /> error,{" "}
        <SeverityShape severity="WARNING" /> warning.
      </p>
    </article>
  );
}
