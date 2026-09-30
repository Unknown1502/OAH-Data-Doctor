import { useEffect, useId, useMemo, useRef, useState } from "react";
import { post } from "../lib/api";
import { num, unit as unitText } from "../lib/format";
import type { FindingDetail, LabResult, LabValidation } from "../lib/types";
import MagnitudeRuler, { type RulerValue } from "./MagnitudeRuler";
import { SeverityShape } from "./ui";

const ORDER = ["minimum", "median", "average", "maximum", "std-dev", "value"];
const LABEL: Record<string, string> = {
  minimum: "Minimum",
  median: "Median",
  average: "Mean",
  maximum: "Maximum",
  "std-dev": "Standard deviation",
  value: "Value",
};
const LEVEL = new Set(["minimum", "median", "average", "maximum", "value"]);

function published(record: NonNullable<FindingDetail["record"]>): Record<string, number> {
  const out: Record<string, number> = {};
  for (const s of record.stats) if (s.value !== null && ORDER.includes(s.stat)) out[s.stat] = s.value;
  if (!record.stats.length && record.value?.value != null) out.value = record.value.value;
  return out;
}

const failText = (n: number) => (n === 1 ? "1 rule fails" : `${n} rules fail`);

const parse = (s: string) => (s.trim() === "" ? NaN : Number(s.replace(/[\s,]/g, "")));

/** Values far (in decades) from the rest of the record, for the ruler only; the verdicts come from the rules. */
function outlying(values: RulerValue[], band: { min?: number; max?: number } | null): string[] {
  const outside = band ? values.filter((v) => (band.max !== undefined && v.value > band.max) || (band.min !== undefined && v.value < band.min)) : [];
  if (outside.length && outside.length < values.length) return outside.map((v) => v.label);
  const logs = values.map((v) => Math.log10(v.value)).sort((a, b) => a - b);
  const mid = logs[Math.floor(logs.length / 2)];
  const far = values.filter((v) => Math.abs(Math.log10(v.value) - mid) > 1.5);
  return far.length && far.length < values.length ? far.map((v) => v.label) : [];
}

/**
 * The point of Data Doctor, hands on: change the numbers of a real published record and watch the rules react, and
 * ask the FHIR server's own validator about the same numbers. Everything runs on a copy; nothing is stored.
 */
export default function WhatIfLab({ observationId, record }: { observationId: string; record: NonNullable<FindingDetail["record"]> }) {
  const uid = useId();
  const original = useMemo(() => published(record), [record]);
  const fields = ORDER.filter((k) => k in original);
  const [inputs, setInputs] = useState<Record<string, string>>(() => Object.fromEntries(fields.map((k) => [k, String(original[k])])));
  const [result, setResult] = useState<LabResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [checking, setChecking] = useState(false);
  const [server, setServer] = useState<{ forKey: string; data: LabValidation } | null>(null);
  const [serverBusy, setServerBusy] = useState(false);
  const [serverErr, setServerErr] = useState<string | null>(null);
  const seq = useRef(0);

  const values = useMemo(() => Object.fromEntries(fields.map((k) => [k, parse(inputs[k] ?? "")])), [fields, inputs]);
  const valid = fields.every((k) => Number.isFinite(values[k]));
  const valuesKey = JSON.stringify(values);
  const u = unitText(record.stats.find((s) => s.unit)?.unit ?? record.value?.code ?? null);

  useEffect(() => {
    if (!valid) return;
    const my = ++seq.current;
    setChecking(true);
    const t = window.setTimeout(async () => {
      try {
        const r = await post<LabResult>("/lab/observation", { observation_id: observationId, values });
        if (my === seq.current) {
          setResult(r);
          setError(null);
        }
      } catch (e) {
        if (my === seq.current) setError((e as Error).message);
      } finally {
        if (my === seq.current) setChecking(false);
      }
    }, 250);
    return () => window.clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [valuesKey, valid, observationId]);

  const askServer = async () => {
    setServerBusy(true);
    setServerErr(null);
    try {
      setServer({ forKey: valuesKey, data: await post<LabValidation>("/lab/observation/validate", { observation_id: observationId, values }) });
    } catch (e) {
      setServerErr((e as Error).message);
    } finally {
      setServerBusy(false);
    }
  };

  const set = (k: string, v: string) => setInputs((cur) => ({ ...cur, [k]: v }));
  const reset = () => setInputs(Object.fromEntries(fields.map((k) => [k, String(original[k])])));
  const apply = (next: Record<string, number>) => setInputs((cur) => ({ ...cur, ...Object.fromEntries(Object.entries(next).map(([k, v]) => [k, String(v)])) }));

  // "Everything but the median is off by a power of ten": offered only when mean and median are decades apart.
  const k = original.average && original.median ? Math.round(Math.log10(original.average / original.median)) : 0;
  const scaleIdea = Math.abs(k) >= 2
    ? Object.fromEntries(["average", "minimum", "maximum", "std-dev"].filter((s) => s in original).map((s) => [s, Number((original[s] / 10 ** k).toPrecision(6))]))
    : null;
  const medianAbove = "median" in original && "maximum" in original ? { median: Number((Math.abs(original.maximum) * 1.5 || 1).toPrecision(6)) } : null;

  const rulerValues: RulerValue[] = fields
    .filter((f) => LEVEL.has(f) && Number.isFinite(values[f]))
    .map((f) => ({ label: f === "average" ? "mean" : f, value: values[f] }));
  const band = record.hard && (!record.canonical_unit || record.stats.every((s) => !s.unit || s.unit === record.canonical_unit))
    ? { min: record.hard.min, max: record.hard.max, label: "physically possible" }
    : null;
  const plotted = rulerValues.filter((v) => v.value > 0);

  const serverFresh = server && server.forKey === valuesKey;
  const serverErrors = server?.data.outcome.issue.filter((i) => i.severity === "error" || i.severity === "fatal") ?? [];
  const fired = result?.checks.filter((c) => c.fired) ?? [];

  return (
    <div className="rounded-lg border border-line bg-panel p-4 sm:p-5">
      <div className="grid gap-6 lg:grid-cols-[minmax(0,17rem)_minmax(0,1fr)]">
        <fieldset className="m-0 min-w-0 border-0 p-0">
          <legend className="mb-2 font-semibold">The published numbers{u ? ` (${u})` : ""}</legend>
          <div className="space-y-2.5">
            {fields.map((f) => {
              const changed = Number.isFinite(values[f]) && values[f] !== original[f];
              const bad = !Number.isFinite(values[f]);
              return (
                <div key={f}>
                  <div className="flex items-baseline justify-between gap-2 text-sm">
                    <label htmlFor={`${uid}-${f}`} className="font-semibold text-ink">{LABEL[f]}</label>
                    <span id={`${uid}-${f}-hint`} className="text-ink-3">{changed ? `published ${num(original[f])}` : "as published"}</span>
                  </div>
                  <input
                    id={`${uid}-${f}`}
                    inputMode="decimal"
                    value={inputs[f] ?? ""}
                    onChange={(e) => set(f, e.target.value)}
                    aria-invalid={bad || undefined}
                    aria-describedby={bad ? `${uid}-${f}-hint ${uid}-${f}-err` : `${uid}-${f}-hint`}
                    className={`readout mt-1 w-full rounded-md border bg-chalk px-3 py-1.5 text-lg ${bad ? "border-cinnabar" : changed ? "border-karst ring-1 ring-karst" : "border-line-strong"}`}
                  />
                  {bad && <p id={`${uid}-${f}-err`} className="m-0 mt-1 text-sm text-cinnabar">Enter a number.</p>}
                </div>
              );
            })}
          </div>
          <div className="mt-4 flex flex-col items-start gap-2 text-sm">
            {scaleIdea && (
              <button type="button" onClick={() => apply(scaleIdea)} className="text-left text-karst underline underline-offset-2">
                Test an idea: what if everything but the median were {num(10 ** Math.abs(k))}× too {k > 0 ? "large" : "small"}?
              </button>
            )}
            {medianAbove && (
              <button type="button" onClick={() => apply(medianAbove)} className="text-left text-karst underline underline-offset-2">
                Put the median above the maximum
              </button>
            )}
            <button type="button" onClick={reset} className="text-left text-ink-2 underline underline-offset-2">
              Back to the published numbers
            </button>
          </div>
          <p className="mb-0 mt-4 text-sm text-ink-3">
            You are editing a copy. The published record is never changed, and nothing is saved.
          </p>
        </fieldset>

        <div className="min-w-0">
          {plotted.length > 0 && <MagnitudeRuler values={plotted} unit={record.stats.find((s) => s.unit)?.unit ?? record.value?.code ?? null} band={band} outliers={outlying(plotted, band)} animate={false} />}

          <div className="mt-4 grid gap-3 sm:grid-cols-2">
            <div className="rounded-lg border border-line bg-chalk p-3.5">
              <p className="m-0 text-sm text-ink-2">FHIR server's own validator</p>
              {serverFresh ? (
                <p className={`m-0 mt-2 flex items-center gap-2 text-lg font-semibold ${serverErrors.length ? "text-cinnabar" : "text-algae"}`}>
                  <span aria-hidden="true">{serverErrors.length ? "✗" : "✓"}</span>
                  {serverErrors.length ? `${serverErrors.length} error(s)` : server.data.outcome.issue[0]?.diagnostics ?? "Accepted"}
                </p>
              ) : (
                <p className="m-0 mt-2 text-ink-3">{server ? "The numbers changed since you asked." : "Not asked about these numbers yet."}</p>
              )}
              <button
                type="button"
                onClick={askServer}
                disabled={serverBusy || !valid}
                className="mt-3 rounded-lg border border-karst bg-panel px-3 py-1.5 text-sm font-semibold text-karst hover:bg-karst-soft disabled:cursor-wait disabled:opacity-60"
              >
                {serverBusy ? "Asking the server…" : "Ask the real FHIR server"}
              </button>
              {serverErr && <p role="alert" className="m-0 mt-2 text-sm text-cinnabar">{serverErr}</p>}
              <p className="m-0 mt-2 text-xs text-ink-3">
                Sends these numbers to the sandbox's <code className="code">$validate</code>, which checks and stores nothing
                {serverFresh ? `; checked ${server.data.checked_at.replace("T", " ").replace("Z", " UTC")}. ${server.data.note}` : "."}
              </p>
            </div>
            <div className={`rounded-lg border-2 p-3.5 ${fired.length ? "border-cinnabar/60 bg-cinnabar-soft" : "border-algae/50 bg-algae-soft"}`}>
              <p className="m-0 text-sm text-ink-2">OAH Data Doctor</p>
              <p className={`m-0 mt-2 flex items-center gap-2 text-lg font-semibold ${fired.length ? "text-cinnabar" : "text-algae"}`}>
                {result?.worst ? <SeverityShape severity={result.worst} size={14} /> : <span aria-hidden="true">✓</span>}
                {result ? (fired.length ? failText(fired.length) : "Every rule passes") : "Checking…"}
              </p>
              <p className="m-0 mt-2 text-xs text-ink-3">{checking ? "Re-checking…" : "Re-checked as you type, by the same deterministic rules."}</p>
            </div>
          </div>

          {error && <p role="alert" className="mt-3 text-cinnabar">{error}</p>}
          <p className="sr-only" aria-live="polite">
            {result ? (fired.length ? `${failText(fired.length)}: ${fired.map((c) => c.rule_id).join(", ")}.` : "Every rule passes.") : ""}
          </p>

          {result && (
            <ul className="m-0 mt-4 list-none space-y-1.5 p-0" aria-label="Rules checked on these numbers">
              {result.checks.map((c) => (
                <li key={`${c.rule_id}-${c.fired}`} className={`lab-flip rounded-md px-2.5 py-1.5 ${c.fired ? "bg-cinnabar-soft" : ""}`}>
                  <div className="flex flex-wrap items-baseline gap-x-2">
                    <span className={`inline-flex w-4 justify-center ${c.fired ? "text-cinnabar" : "text-algae"}`}>
                      {c.fired && c.severity ? <SeverityShape severity={c.severity} /> : <span aria-hidden="true">✓</span>}
                    </span>
                    <span className="sr-only">{c.fired ? "Fails:" : "Passes:"}</span>
                    <span className="readout text-sm text-ink-2">{c.rule_id}</span>
                    <span className={c.fired ? "font-semibold text-ink" : "text-ink-2"}>{c.title}</span>
                    {c.fired !== c.was_fired && (
                      <span className="rounded-full bg-sunk px-2 text-xs text-ink-2">{c.fired ? "new with your numbers" : "fails as published"}</span>
                    )}
                  </div>
                  {c.fired && c.summary && <p className="m-0 mt-0.5 pl-6 text-sm text-ink-2">{c.summary}</p>}
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}
