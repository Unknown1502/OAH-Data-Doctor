import { useEffect, useId, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useRun } from "../components/Shell";
import { Button, Chip, ErrorNote, FindingLink, Loading, Verdict, useDocumentTitle } from "../components/ui";
import { post, useApi } from "../lib/api";
import { aggregationText, DIM_TEXT, num, pretty, tone, unit } from "../lib/format";
import type { Comparison, Descriptor, ObservationItem } from "../lib/types";

const optionLabel = (o: ObservationItem) =>
  [o.indicator, o.location, o.cohort, o.year && !o.date ? String(o.year) : o.date].filter(Boolean).join(", ") + (o.blocking ? " (has integrity findings)" : "");

function Picker({ label, items, value, onChange, stat, onStat }: {
  label: string;
  items: ObservationItem[];
  value: string;
  onChange: (id: string) => void;
  stat: string;
  onStat: (s: string) => void;
}) {
  const id = useId();
  const [filter, setFilter] = useState("");
  const shown = useMemo(() => {
    const f = filter.toLowerCase().trim();
    return items.filter((o) => !f || optionLabel(o).toLowerCase().includes(f) || o.id.toLowerCase().includes(f));
  }, [items, filter]);
  const groups = useMemo(() => {
    const m = new Map<string, ObservationItem[]>();
    for (const o of shown) m.set(o.location ?? "Unknown place", [...(m.get(o.location ?? "Unknown place") ?? []), o]);
    return [...m.entries()];
  }, [shown]);
  const selected = items.find((o) => o.id === value);
  return (
    <fieldset className="m-0 min-w-0 rounded-xl border border-line bg-panel p-4">
      <legend className="px-1 text-lg font-bold">{label}</legend>
      <label htmlFor={`${id}-f`} className="block text-sm text-ink-2">
        Filter records
      </label>
      <input id={`${id}-f`} type="search" value={filter} onChange={(e) => setFilter(e.target.value)} placeholder="e.g. NO2 2019, obesity, Almyros"
        className="mt-1 w-full rounded-md border border-line bg-chalk px-2 py-1.5" />
      <label htmlFor={`${id}-s`} className="mt-3 block text-sm text-ink-2">
        Record ({shown.length} shown)
      </label>
      <select id={`${id}-s`} size={9} value={value} onChange={(e) => onChange(e.target.value)} className="mt-1 w-full rounded-md border border-line bg-chalk p-1 text-[0.92rem]">
        {groups.map(([g, os]) => (
          <optgroup key={g} label={g}>
            {os.map((o) => (
              <option key={o.id} value={o.id}>
                {optionLabel(o)}
              </option>
            ))}
          </optgroup>
        ))}
      </select>
      {selected && selected.statistics.length > 0 && (
        <div className="mt-3">
          <label htmlFor={`${id}-st`} className="block text-sm text-ink-2">
            Statistic
          </label>
          <select id={`${id}-st`} value={stat} onChange={(e) => onStat(e.target.value)} className="mt-1 rounded-md border border-line bg-chalk px-2 py-1.5">
            {selected.statistics.filter((s) => s !== "std-dev").map((s) => (
              <option key={s} value={s}>
                {s === "average" ? "annual mean" : `annual ${s}`}
              </option>
            ))}
          </select>
        </div>
      )}
    </fieldset>
  );
}

const sideText = (d: Descriptor) =>
  [d.location_name, d.cohort?.label, d.period?.start === d.period?.end ? d.period?.start : d.period?.start?.slice(0, 4)].filter(Boolean).join(", ");

function Side({ d, name }: { d: Descriptor; name: string }) {
  return (
    <div className="min-w-0">
      <p className="m-0 text-sm text-ink-2">{name}</p>
      <p className="m-0 font-semibold">{pretty(d.label)}</p>
      <p className="readout m-0 mt-1 text-2xl">
        {num(d.value)} {unit(d.unit)}
      </p>
      <p className="m-0 mt-1 text-sm text-ink-3">
        {aggregationText(d.aggregation)}
        {d.method ? `; ${d.method}` : ""}
      </p>
    </div>
  );
}

export default function Compare() {
  useDocumentTitle("Compare");
  const { runId } = useRun();
  const [params] = useSearchParams();
  const obs = useApi<{ items: ObservationItem[] }>("/observations", [runId]);
  const analyses = useApi<{ comparisons: Comparison[] }>("/analyses", [runId]);
  const [a, setA] = useState("");
  const [b, setB] = useState("");
  const [sa, setSa] = useState("average");
  const [sb, setSb] = useState("average");
  const [result, setResult] = useState<Comparison | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = (c: Comparison) => {
    setA(c.a.observation_id);
    setB(c.b.observation_id);
    setSa(c.a.statistic ?? "average");
    setSb(c.b.statistic ?? "average");
    setResult(c);
  };

  useEffect(() => {
    const id = params.get("id");
    const c = analyses.data?.comparisons.find((x) => x.id === id);
    if (c) load(c);
  }, [params, analyses.data]);

  const items = obs.data?.items ?? [];
  const statOf = (id: string, s: string) => (items.find((o) => o.id === id)?.statistics.length ? s : undefined);

  const run = async () => {
    setBusy(true);
    setErr(null);
    try {
      setResult(await post<Comparison>("/compare", { a: { observation: a, statistic: statOf(a, sa) }, b: { observation: b, statistic: statOf(b, sb) } }));
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <article>
      <h1 className="m-0 text-4xl font-bold tracking-tight">Can these two numbers be compared?</h1>
      <p className="mt-2 max-w-[70ch] text-lg text-ink-2">
        Pick two published values. Data Doctor checks eight dimensions: measure, unit, medium, population, period, aggregation, method and
        record integrity. It then tells you whether the comparison is direct, needs caveats, is not valid, or is blocked by broken records.
      </p>

      {analyses.data && (
        <div className="mt-6">
          <p className="m-0 mb-2 text-ink-2">Start from a comparison we already ran:</p>
          <ul className="m-0 flex list-none flex-wrap gap-2 p-0">
            {analyses.data.comparisons.slice(0, 9).map((c) => (
              <li key={c.id}>
                <button type="button" onClick={() => load(c)}
                  className="rounded-full border border-line bg-panel px-3 py-1 text-left text-sm hover:border-karst hover:text-karst">
                  {c.a.measure_label}: {sideText(c.a)} vs {sideText(c.b)}
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}

      {obs.error && <ErrorNote error={obs.error} />}
      {!obs.data && !obs.error && <Loading what="records" />}
      {obs.data && (
        <form className="mt-6" onSubmit={(e) => { e.preventDefault(); if (a && b) run(); }}>
          <div className="grid gap-4 md:grid-cols-2">
            <Picker label="Value A" items={items} value={a} onChange={setA} stat={sa} onStat={setSa} />
            <Picker label="Value B" items={items} value={b} onChange={setB} stat={sb} onStat={setSb} />
          </div>
          <div className="mt-4 flex items-center gap-3">
            <Button kind="primary" type="submit" disabled={!a || !b || busy}>
              {busy ? "Checking…" : "Check comparability"}
            </Button>
            {(!a || !b) && <span className="text-sm text-ink-3">Choose a record on each side.</span>}
          </div>
        </form>
      )}
      {err && <div className="mt-4"><ErrorNote error={err} /></div>}

      {result && (
        <section aria-labelledby="res-h" className="mt-10" aria-live="polite">
          <h2 id="res-h" className="sr-only">
            Result
          </h2>
          <div className={`rounded-xl border-2 p-5 ${tone(result.verdict) === "good" ? "border-algae/60" : tone(result.verdict) === "blocked" ? "border-cinnabar/60" : tone(result.verdict) === "bad" ? "border-slate/60" : "border-sulfur/60"} bg-panel`}>
            <Verdict value={result.verdict} size="lg" />
            <p className="mb-0 mt-3 max-w-[75ch] text-lg">{pretty(result.summary)}</p>
            <div className="mt-5 grid gap-6 border-t border-line pt-4 sm:grid-cols-2">
              <Side d={result.a} name="A" />
              <Side d={result.b} name="B" />
            </div>
          </div>

          <div className="mt-6 overflow-x-auto rounded-xl border border-line bg-panel">
            <table className="data">
              <caption className="px-3 pt-3 text-left font-semibold">Dimension by dimension</caption>
              <thead>
                <tr>
                  <th scope="col">Dimension</th>
                  <th scope="col">Result</th>
                  <th scope="col">Why</th>
                  <th scope="col">Rule</th>
                </tr>
              </thead>
              <tbody>
                {result.dimensions.map((d) => (
                  <tr key={d.rule_id}>
                    <th scope="row" className="!bg-transparent !font-semibold !text-ink">{d.dimension}</th>
                    <td className="whitespace-nowrap">
                      <Chip text={DIM_TEXT[d.status]} toneOf={d.status === "FAIL" ? (d.rule_id === "CMP-INTEGRITY" ? "BLOCKED" : "NOT") : d.status} />
                    </td>
                    <td className="max-w-[60ch]">{pretty(d.reason)}</td>
                    <td className="code whitespace-nowrap text-sm text-ink-3">{d.rule_id}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {result.transformations.length > 0 && (
            <div className="mt-6">
              <h3 className="m-0 text-lg font-semibold">Required transformation</h3>
              <ul className="mt-1 pl-5">{result.transformations.map((t) => <li key={t}>{t}</li>)}</ul>
            </div>
          )}
          {result.blocking_findings.length > 0 && (
            <div className="mt-6">
              <h3 className="m-0 text-lg font-semibold">Findings that block this comparison</h3>
              <ul className="mt-1 pl-5">
                {result.blocking_findings.map((id) => (
                  <li key={id}><FindingLink id={id}>{id}</FindingLink></li>
                ))}
              </ul>
            </div>
          )}
          {result.supported_alternatives.length > 0 && (
            <div className="mt-6 rounded-xl border border-algae/40 bg-algae-soft p-4">
              <h3 className="m-0 text-lg font-semibold text-algae">What you can compare instead</h3>
              <ul className="mb-0 mt-1 pl-5">{result.supported_alternatives.map((t) => <li key={t}>{pretty(t)}</li>)}</ul>
            </div>
          )}
        </section>
      )}
    </article>
  );
}
