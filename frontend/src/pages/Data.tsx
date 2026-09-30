import { useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import SeriesChart, { type SeriesPoint } from "../components/SeriesChart";
import { useRun } from "../components/Shell";
import { ErrorNote, Loading, SeverityTag, SourceBadge, useDocumentTitle } from "../components/ui";
import { useApi } from "../lib/api";
import { exact, num, unit as unitText, when } from "../lib/format";
import type { Knowledge, LocationItem, ObservationItem, Overview } from "../lib/types";

const STAT_LABEL: Record<string, string> = { average: "Mean", median: "Median", minimum: "Minimum", maximum: "Maximum", "std-dev": "SD", value: "Value" };
const PAGE = 60;

/** The period as published: a year for annual summaries, the date for single measurements. */
function periodOf(o: ObservationItem): string {
  const p = o.period;
  if (p?.start && p.end && p.start.slice(0, 4) === p.end.slice(0, 4) && p.start.slice(5) === "01-01" && p.end.slice(5) === "12-31") return p.start.slice(0, 4);
  if (o.date) return o.date.slice(0, 10);
  if (p?.start && p?.end) return `${p.start.slice(0, 10)} to ${p.end.slice(0, 10)}`;
  return o.year ? String(o.year) : "—";
}

const STAT_ORDER = ["value", "average", "median", "minimum", "maximum", "std-dev"];
const isSummary = (o: ObservationItem) => Object.keys(o.stats).length > 0;
// Annual summaries and single measurements of the same measure are different kinds of data: never one series.
const seriesKey = (o: ObservationItem) => `${o.indicator_key ?? o.indicator}|${o.location_id ?? ""}|${o.cohort ?? ""}|${isSummary(o) ? "summary" : "single"}`;

export default function Data() {
  useDocumentTitle("The published data");
  const { runId, status } = useRun();
  const obs = useApi<{ total: number; items: ObservationItem[] }>("/observations", [runId]);
  const locs = useApi<{ total: number; items: LocationItem[] }>("/locations", [runId]);
  const ov = useApi<Overview>("/overview", [runId]);
  const kn = useApi<Knowledge>("/knowledge", [runId]);
  const [params, setParams] = useSearchParams();
  const [shown, setShown] = useState(PAGE);
  const set = (k: string, v: string) => {
    const next = new URLSearchParams(params);
    if (v) next.set(k, v);
    else next.delete(k);
    setParams(next, { replace: true });
    setShown(PAGE);
  };

  const items = useMemo(() => obs.data?.items ?? [], [obs.data]);
  const series = useMemo(() => {
    const groups = new Map<string, ObservationItem[]>();
    for (const o of items) groups.set(seriesKey(o), [...(groups.get(seriesKey(o)) ?? []), o]);
    return [...groups.entries()]
      .map(([key, v]) => ({ key, items: [...v].sort((a, b) => periodOf(a).localeCompare(periodOf(b))) }))
      .filter((s) => new Set(s.items.map(periodOf)).size >= 2)
      .map((s) => ({ ...s, label: `${s.items[0].indicator}, ${s.items[0].location ?? "no site"}${s.items[0].cohort ? `, ${s.items[0].cohort}` : ""} (${isSummary(s.items[0]) ? "annual summaries" : "single measurements"})` }))
      .sort((a, b) => a.label.localeCompare(b.label));
  }, [items]);

  if (obs.error || locs.error) return <ErrorNote error={`Could not load the data: ${obs.error ?? locs.error}`} />;
  if (!obs.data || !locs.data || !ov.data) return <Loading what="the published data" />;

  const base = status?.fhir_base ?? ov.data.source.base_url;
  const src = ov.data.source;
  const summary = ov.data.summary;
  const heroId = ov.data.hero_finding?.resource.resource_id;
  const hero = items.find((o) => o.id === heroId);

  // Series chart selection (defaults to the anchor record's series).
  const sKey = params.get("series") ?? (hero ? seriesKey(hero) : series[0]?.key ?? "");
  const current = series.find((s) => s.key === sKey) ?? series[0];
  const statsInSeries = current
    ? STAT_ORDER.filter((s) => current.items.some((o) => (s === "value" ? o.value !== null : o.stats[s] !== undefined && o.stats[s] !== null)))
    : [];
  const stat = params.get("stat") && statsInSeries.includes(params.get("stat")!) ? params.get("stat")! : statsInSeries.includes("average") ? "average" : statsInSeries[0];
  const points: SeriesPoint[] = (current?.items ?? [])
    .map((o) => ({ label: periodOf(o), value: (stat === "value" ? o.value : o.stats[stat]) as number, worst: o.worst }))
    .filter((p) => typeof p.value === "number");
  const ind = current ? kn.data?.indicators[current.items[0].indicator_key ?? ""] : undefined;
  const hard = current && kn.data ? kn.data.plausibility.indicators[current.items[0].indicator_key ?? ""]?.hard : undefined;
  const seriesUnit = current?.items[0].unit ?? null;
  const band = hard && ind && ind.unit === seriesUnit ? { min: hard.min, max: hard.max } : null;

  // Records table.
  const q = (params.get("q") ?? "").toLowerCase();
  const place = params.get("place") ?? "";
  const measure = params.get("measure") ?? "";
  const statusF = params.get("status") ?? "";
  const sort = params.get("sort") ?? "measure";
  const rows = items
    .filter((o) => (!place || o.location_id === place) && (!measure || o.indicator_key === measure))
    .filter((o) => !statusF || (statusF === "problems" ? o.blocking : !o.blocking))
    .filter((o) => !q || `${o.id} ${o.indicator} ${o.location} ${o.cohort ?? ""}`.toLowerCase().includes(q))
    .sort((a, b) => {
      const k = (o: ObservationItem) => (sort === "place" ? `${o.location}|${o.indicator}|${periodOf(o)}` : sort === "period" ? `${periodOf(o)}|${o.indicator}|${o.location}` : `${o.indicator}|${o.location}|${periodOf(o)}`);
      return k(a).localeCompare(k(b));
    });
  const measures = [...new Map(items.map((o) => [o.indicator_key ?? "", o.indicator ?? o.indicator_key ?? ""])).entries()].sort((a, b) => a[1].localeCompare(b[1]));
  const officialLocs = locs.data.items.filter((l) => l.observations > 0);
  const flagged = items.filter((o) => o.blocking).length;

  return (
    <article>
      <h1 className="m-0 text-[clamp(1.9rem,3.6vw,2.7rem)] font-bold leading-tight tracking-tight">The published data</h1>
      <p className="mt-3 max-w-[70ch] text-lg text-ink-2">
        Every official OneAquaHealth record Data Doctor reads, shown exactly as published: no rounding, no unit conversion, no
        corrections. Open any record on the FHIR server to compare it with the source.
      </p>

      <section aria-labelledby="prov-h" className="mt-6 rounded-xl border border-line bg-panel p-4 sm:p-5">
        <h2 id="prov-h" className="m-0 text-lg font-bold">Where it comes from</h2>
        <dl className="mb-0 mt-3 grid gap-x-6 gap-y-2 sm:grid-cols-[12rem_1fr]">
          <dt className="text-ink-2">Server</dt>
          <dd className="m-0 min-w-0 break-words">
            OneAquaHealth FHIR sandbox, operated by HL7 Europe:{" "}
            <a href={base} target="_blank" rel="noopener noreferrer" className="text-karst underline underline-offset-2">{base}</a> (FHIR R4)
          </dd>
          <dt className="text-ink-2">This copy</dt>
          <dd className="m-0 flex flex-wrap items-center gap-2">
            <SourceBadge source={src} />
            {src.kind === "snapshot" && src.manifest_sha256 && <span className="text-sm text-ink-3">verified snapshot, sha256 {src.manifest_sha256.slice(0, 12)}…</span>}
          </dd>
          <dt className="text-ink-2">Official records</dt>
          <dd className="m-0">
            {num(obs.data.total)} observations at {num(officialLocs.length)} places, from the OneAquaHealth Implementation Guide (source commit{" "}
            <span className="code">{ov.data.ig_commit.slice(0, 8)}</span>). {num(flagged)} have an error or critical finding.
          </dd>
          <dt className="text-ink-2">Also on the server</dt>
          <dd className="m-0">
            {num(summary.resources_by_scope["third-party"] ?? 0)} resources written by other users of the open sandbox: shown in counts, never judged.
          </dd>
          <dt className="text-ink-2">Resources read</dt>
          <dd className="m-0 text-ink-2">{Object.entries(summary.resources_by_type).map(([t, n]) => `${num(n)} ${t}`).join(", ")}</dd>
        </dl>
      </section>

      <section aria-labelledby="sites-h" className="mt-10">
        <h2 id="sites-h" className="m-0 text-2xl font-bold tracking-tight">Monitoring places</h2>
        <div className="mt-3 overflow-x-auto rounded-xl border border-line bg-panel" tabIndex={0} role="region" aria-label="Table of monitoring places">
          <table className="data m-0">
            <thead>
              <tr>
                <th scope="col">Place</th>
                <th scope="col">Coordinates</th>
                <th scope="col" className="text-right">Records</th>
                <th scope="col" className="text-right">Measures</th>
                <th scope="col">Years</th>
                <th scope="col">With problems</th>
                <th scope="col"><span className="sr-only">Actions</span></th>
              </tr>
            </thead>
            <tbody>
              {officialLocs.map((l) => (
                <tr key={l.id}>
                  <td>
                    <span className="font-semibold">{l.name ?? l.id}</span>
                    <span className="block text-sm text-ink-3">{l.id}</span>
                  </td>
                  <td className="readout whitespace-nowrap text-sm">{l.latitude !== null && l.longitude !== null ? `${exact(l.latitude)}, ${exact(l.longitude)}` : "not published"}</td>
                  <td className="readout text-right">{num(l.observations)}</td>
                  <td className="readout text-right">{num(l.measures)}</td>
                  <td className="readout whitespace-nowrap">{l.years ? (l.years[0] === l.years[1] ? l.years[0] : `${l.years[0]}–${l.years[1]}`) : "—"}</td>
                  <td className="min-w-[9rem]">
                    <div className="flex items-center gap-2">
                      <span className="readout w-10 text-right">{num(l.with_problems)}</span>
                      <span className="h-2 flex-1 rounded-full bg-sunk" aria-hidden="true">
                        <span className="block h-2 rounded-full bg-cinnabar" style={{ width: `${l.observations ? (100 * l.with_problems) / l.observations : 0}%` }} />
                      </span>
                    </div>
                  </td>
                  <td className="whitespace-nowrap text-sm">
                    <button type="button" onClick={() => set("place", l.id)} className="text-karst underline underline-offset-2">Show its records</button>{" "}
                    <a href={`${base}/Location/${encodeURIComponent(l.id)}`} target="_blank" rel="noopener noreferrer" className="ml-2 text-karst underline underline-offset-2"
                      aria-label={`Open Location/${l.id} on the FHIR server`}>FHIR</a>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {current && (
        <section aria-labelledby="ser-h" className="mt-10">
          <h2 id="ser-h" className="m-0 text-2xl font-bold tracking-tight">Values over time</h2>
          <p className="mt-1 max-w-[75ch] text-ink-2">One published statistic of one measure at one place, over time. Each point is coloured by its record's most severe finding (red diamond: error or critical), so a plausible value can still sit on a record that has problems elsewhere.</p>
          <div className="mt-3 flex flex-wrap items-end gap-3">
            <label className="flex min-w-0 flex-col text-sm font-semibold">
              Measure and place
              <select value={current.key} onChange={(e) => { set("series", e.target.value); }} className="mt-1 max-w-[34rem] rounded-md border border-line-strong bg-panel px-2 py-1.5 font-normal">
                {series.map((s) => <option key={s.key} value={s.key}>{s.label}</option>)}
              </select>
            </label>
            <label className="flex flex-col text-sm font-semibold">
              Statistic
              <select value={stat} onChange={(e) => set("stat", e.target.value)} className="mt-1 rounded-md border border-line-strong bg-panel px-2 py-1.5 font-normal">
                {statsInSeries.map((s) => <option key={s} value={s}>{STAT_LABEL[s] ?? s}</option>)}
              </select>
            </label>
          </div>
          <div className="mt-4 rounded-xl border border-line bg-panel p-4">
            {points.length > 0 ? (
              <SeriesChart points={points} unit={seriesUnit} band={band} title={`${STAT_LABEL[stat] ?? stat} of ${current.label}`}
                bandNote={band && hard ? `Physically possible for ${ind?.label.toLowerCase() ?? "this measure"}: ${hard.min !== undefined ? exact(hard.min) : "no lower limit"} to ${hard.max !== undefined ? exact(hard.max) : "no upper limit"} ${unitText(seriesUnit)}. ${hard.rationale}` : null} />
            ) : (
              <p className="m-0 text-ink-2">This statistic is not published for this series.</p>
            )}
          </div>
          <div className="mt-3 overflow-x-auto" tabIndex={0} role="region" aria-label="Values in the chart">
            <table className="data m-0">
              <caption className="sr-only">{`${STAT_LABEL[stat] ?? stat} of ${current.label}, as published`}</caption>
              <thead>
                <tr>
                  <th scope="col">Period</th>
                  {statsInSeries.map((s) => <th key={s} scope="col" className="text-right">{STAT_LABEL[s] ?? s}</th>)}
                  <th scope="col">Unit</th>
                  <th scope="col">Status</th>
                </tr>
              </thead>
              <tbody>
                {current.items.map((o) => (
                  <tr key={o.id}>
                    <td className="readout whitespace-nowrap">{periodOf(o)}</td>
                    {statsInSeries.map((s) => (
                      <td key={s} className={`readout text-right ${s === stat ? "font-semibold" : ""}`}>{exact(s === "value" ? o.value : o.stats[s] ?? null)}</td>
                    ))}
                    <td>{unitText(o.unit)}</td>
                    <td>{o.worst ? <Link to={`/findings/${encodeURIComponent(o.worst_finding!)}`} className="no-underline"><SeverityTag severity={o.worst} /></Link> : <span className="text-algae">✓ none</span>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      <section aria-labelledby="rec-h" className="mt-10">
        <h2 id="rec-h" className="m-0 text-2xl font-bold tracking-tight">Every official record</h2>
        <div className="mt-3 flex flex-wrap items-end gap-3">
          <label className="flex flex-col text-sm font-semibold">
            Search
            <input value={params.get("q") ?? ""} onChange={(e) => set("q", e.target.value)} placeholder="measure, place or id"
              className="mt-1 w-56 rounded-md border border-line-strong bg-panel px-2 py-1.5 font-normal" />
          </label>
          <label className="flex flex-col text-sm font-semibold">
            Place
            <select value={place} onChange={(e) => set("place", e.target.value)} className="mt-1 max-w-[16rem] rounded-md border border-line-strong bg-panel px-2 py-1.5 font-normal">
              <option value="">All places</option>
              {officialLocs.map((l) => <option key={l.id} value={l.id}>{l.name ?? l.id}</option>)}
            </select>
          </label>
          <label className="flex flex-col text-sm font-semibold">
            Measure
            <select value={measure} onChange={(e) => set("measure", e.target.value)} className="mt-1 max-w-[16rem] rounded-md border border-line-strong bg-panel px-2 py-1.5 font-normal">
              <option value="">All measures</option>
              {measures.map(([k, label]) => <option key={k} value={k}>{label}</option>)}
            </select>
          </label>
          <label className="flex flex-col text-sm font-semibold">
            Status
            <select value={statusF} onChange={(e) => set("status", e.target.value)} className="mt-1 rounded-md border border-line-strong bg-panel px-2 py-1.5 font-normal">
              <option value="">All records</option>
              <option value="problems">With problems</option>
              <option value="clean">Without problems</option>
            </select>
          </label>
          <label className="flex flex-col text-sm font-semibold">
            Sort by
            <select value={sort} onChange={(e) => set("sort", e.target.value)} className="mt-1 rounded-md border border-line-strong bg-panel px-2 py-1.5 font-normal">
              <option value="measure">Measure</option>
              <option value="place">Place</option>
              <option value="period">Period</option>
            </select>
          </label>
        </div>
        <p className="mt-3 text-sm text-ink-2" aria-live="polite">
          Showing {num(Math.min(shown, rows.length))} of {num(rows.length)} records{rows.length !== items.length ? ` (filtered from ${num(items.length)})` : ""}.
        </p>
        <div className="mt-2 max-h-[75vh] overflow-auto rounded-xl border border-line bg-panel" tabIndex={0} role="region" aria-label="Table of records">
          <table className="data m-0">
            <caption className="sr-only">Official records, values exactly as published</caption>
            <thead className="sticky top-0 z-10 bg-panel">
              <tr>
                <th scope="col">Measure</th>
                <th scope="col">Place</th>
                <th scope="col">Period</th>
                <th scope="col">Population</th>
                {["value", "average", "median", "minimum", "maximum", "std-dev"].map((s) => <th key={s} scope="col" className="text-right">{STAT_LABEL[s]}</th>)}
                <th scope="col">Unit</th>
                <th scope="col">Status</th>
                <th scope="col">Source</th>
              </tr>
            </thead>
            <tbody>
              {rows.slice(0, shown).map((o) => (
                <tr key={o.id}>
                  <td className="min-w-[13rem]">
                    <span className="font-semibold">{o.indicator}</span>
                    <span className="block break-all text-xs text-ink-3">{o.id}</span>
                  </td>
                  <td className="min-w-[11rem]">{o.location ?? "—"}</td>
                  <td className="readout whitespace-nowrap">{periodOf(o)}</td>
                  <td className="text-sm">{o.cohort ?? "—"}</td>
                  <td className="readout text-right">{exact(o.value)}</td>
                  {["average", "median", "minimum", "maximum", "std-dev"].map((s) => <td key={s} className="readout text-right">{exact(o.stats[s] ?? null)}</td>)}
                  <td className="whitespace-nowrap">{unitText(o.unit)}</td>
                  <td className="whitespace-nowrap">
                    {o.worst ? (
                      <Link to={`/findings/${encodeURIComponent(o.worst_finding!)}`} className="no-underline" aria-label={`${o.findings} finding${o.findings > 1 ? "s" : ""}, worst ${o.worst.toLowerCase()}: open`}>
                        <SeverityTag severity={o.worst} />
                      </Link>
                    ) : (
                      <span className="text-algae">✓ none</span>
                    )}
                  </td>
                  <td>
                    <a href={`${base}/Observation/${encodeURIComponent(o.id)}`} target="_blank" rel="noopener noreferrer" className="text-karst underline underline-offset-2"
                      aria-label={`Open Observation/${o.id} on the FHIR server`}>FHIR</a>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {shown < rows.length && (
          <button type="button" onClick={() => setShown((n) => n + PAGE)} className="mt-3 rounded-lg border border-line-strong bg-panel px-3.5 py-2 font-semibold hover:bg-sunk">
            Show {num(Math.min(PAGE, rows.length - shown))} more
          </button>
        )}
        <p className="mt-4 text-sm text-ink-3">
          Values are shown with every published decimal. "Status" is the most severe finding on the record; see{" "}
          <Link to="/findings" className="text-karst underline underline-offset-2">all findings</Link> for the evidence. {src.kind === "live" ? "Live data fetched" : "Snapshot of"} {when(src.fetched_at)}.
        </p>
      </section>
    </article>
  );
}
