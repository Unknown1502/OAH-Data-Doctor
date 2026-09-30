import { useId, useState, type DragEvent } from "react";
import { Link } from "react-router-dom";
import { Button, ErrorNote, SeverityTag, useDocumentTitle } from "../components/ui";
import { api, post } from "../lib/api";
import { num, SEVERITY_ORDER, SEVERITY_TEXT, when } from "../lib/format";
import type { CheckResult, ObservationItem, Overview } from "../lib/types";

const MAX_BYTES = 5_000_000;

type Starter = { label: string; load: () => Promise<string> };

async function resourceJson(id: string) {
  return (await api<{ resource: Record<string, unknown> }>(`/resources/Observation/${encodeURIComponent(id)}`)).resource;
}

export default function CheckData() {
  useDocumentTitle("Check your data");
  const uid = useId();
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [result, setResult] = useState<CheckResult | null>(null);
  const [dragging, setDragging] = useState(false);

  const starters: Starter[] = [
    {
      label: "The 198,000 °C record, as published",
      load: async () => {
        const ov = await api<Overview>("/overview");
        return JSON.stringify(await resourceJson(ov.hero_finding!.resource.resource_id), null, 2);
      },
    },
    {
      label: "A published record with no problems",
      load: async () => {
        const obs = await api<{ items: ObservationItem[] }>("/observations");
        const clean = obs.items.find((o) => o.findings === 0 && o.statistics.length >= 4) ?? obs.items.find((o) => o.findings === 0);
        return JSON.stringify(await resourceJson(clean!.id), null, 2);
      },
    },
    {
      label: "Both, as a Bundle",
      load: async () => {
        const ov = await api<Overview>("/overview");
        const obs = await api<{ items: ObservationItem[] }>("/observations");
        const clean = obs.items.find((o) => o.findings === 0 && o.statistics.length >= 4) ?? obs.items.find((o) => o.findings === 0);
        const entry = [await resourceJson(ov.hero_finding!.resource.resource_id), await resourceJson(clean!.id)].map((resource) => ({ resource }));
        return JSON.stringify({ resourceType: "Bundle", type: "collection", entry }, null, 2);
      },
    },
  ];

  const loadStarter = async (s: Starter) => {
    setErr(null);
    setResult(null);
    try {
      setText(await s.load());
    } catch (e) {
      setErr(`Could not load the example: ${(e as Error).message}`);
    }
  };

  const readFile = async (file: File | undefined) => {
    if (!file) return;
    setResult(null);
    if (file.size > MAX_BYTES) {
      setErr(`${file.name} is ${num(Math.round(file.size / 1e6))} MB; at most 5 MB per check. Split it, or use the command line.`);
      return;
    }
    setErr(null);
    setText(await file.text());
  };

  const onDrop = (e: DragEvent) => {
    e.preventDefault();
    setDragging(false);
    void readFile(e.dataTransfer.files[0]);
  };

  const check = async () => {
    setBusy(true);
    setErr(null);
    setResult(null);
    try {
      setResult(await post<CheckResult>("/check", { content: text }));
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const s = result?.summary;
  return (
    <article>
      <h1 className="m-0 text-[clamp(1.9rem,3.6vw,2.7rem)] font-bold leading-tight tracking-tight">Check your own data</h1>
      <p className="mt-3 max-w-[70ch] text-lg text-ink-2">
        Bring FHIR data from anywhere. Data Doctor runs the same rules on it, with the published OneAquaHealth data as context, so
        your records are also compared with their published series and places. Your data is checked in memory and not stored.
      </p>

      <section aria-labelledby="ways-h" className="mt-8">
        <h2 id="ways-h" className="sr-only">Ways to give Data Doctor your data</h2>
        <ol className="m-0 grid list-none gap-3 p-0 md:grid-cols-3">
          <li className="rounded-xl border border-line bg-panel p-4">
            <p className="m-0 font-semibold">Here, in the browser</p>
            <p className="m-0 mt-1 text-sm text-ink-2">Paste or drop one FHIR resource, a Bundle, a JSON array or NDJSON (one resource per line), up to 5 MB.</p>
          </li>
          <li className="rounded-xl border border-line bg-panel p-4">
            <p className="m-0 font-semibold">From a terminal or a data pipeline</p>
            <p className="m-0 mt-1 text-sm text-ink-2">
              <code className="code">python tools/oah_audit.py check my-data.ndjson</code> exits with status 1 when it finds an error, so it can stop a
              pipeline before bad data is published.
            </p>
          </li>
          <li className="rounded-xl border border-line bg-panel p-4">
            <p className="m-0 font-semibold">A whole FHIR server</p>
            <p className="m-0 mt-1 text-sm text-ink-2">
              <code className="code">DD_FHIR_BASE=https://your-server/fhir python tasks.py run</code> audits another server, read-only. Range checks
              use the measures Data Doctor knows; statistical and structural checks apply to any data.
            </p>
          </li>
        </ol>
      </section>

      <section aria-labelledby="in-h" className="mt-8 rounded-xl border border-line bg-panel p-4 sm:p-5">
        <h2 id="in-h" className="m-0 text-xl font-bold">Your data</h2>
        <p className="mb-0 mt-1 text-sm text-ink-2">Start from a real published record and edit it, or bring your own:</p>
        <div className="mt-2 flex flex-wrap gap-2">
          {starters.map((st) => (
            <button key={st.label} type="button" onClick={() => loadStarter(st)}
              className="rounded-full border border-line px-3 py-1 text-sm text-ink-2 hover:border-karst hover:text-karst">
              {st.label}
            </button>
          ))}
        </div>

        <label htmlFor={`${uid}-t`} className="mt-4 block font-semibold">FHIR JSON or NDJSON</label>
        <textarea
          id={`${uid}-t`}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onDragOver={(e) => {
            e.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={onDrop}
          rows={12}
          spellCheck={false}
          placeholder={'{"resourceType": "Observation", ...}   or drop a .json / .ndjson file here'}
          className={`code mt-1.5 w-full rounded-lg border bg-chalk px-3 py-2 text-sm leading-relaxed ${dragging ? "border-karst ring-2 ring-karst" : "border-line-strong"}`}
        />
        <div className="mt-3 flex flex-wrap items-center gap-3">
          <Button kind="primary" onClick={check} disabled={!text.trim() || busy}>{busy ? "Checking…" : "Check this data"}</Button>
          <label className="cursor-pointer rounded-lg border border-line-strong bg-panel px-3.5 py-2 text-[0.95rem] font-semibold hover:bg-sunk">
            Choose a file
            <input type="file" accept=".json,.ndjson,.jsonl,application/json,application/fhir+json" className="sr-only"
              onChange={(e) => void readFile(e.target.files?.[0])} />
          </label>
          {text && (
            <button type="button" onClick={() => { setText(""); setResult(null); setErr(null); }} className="text-sm text-ink-2 underline underline-offset-2">
              Clear
            </button>
          )}
          <span className="text-sm text-ink-3">{text ? `${num(text.length)} characters` : ""}</span>
        </div>
      </section>

      {err && <div className="mt-4"><ErrorNote error={err} /></div>}

      {result && s && (
        <section aria-labelledby="res-h" className="mt-8" aria-live="polite">
          <h2 id="res-h" className="m-0 text-2xl font-bold tracking-tight">
            {s.findings_total
              ? `${num(s.with_findings)} of ${num(s.checked)} record${s.checked > 1 ? "s" : ""} ${s.with_findings > 1 ? "have" : "has"} problems`
              : `No problems in ${num(s.checked)} record${s.checked > 1 ? "s" : ""}`}
          </h2>
          <p className="mt-1 text-ink-2">
            {s.findings_total
              ? `${num(s.findings_total)} finding${s.findings_total > 1 ? "s" : ""}: ${SEVERITY_ORDER.filter((k) => s.by_severity[k]).map((k) => `${s.by_severity[k]} ${SEVERITY_TEXT[k].toLowerCase()}`).join(", ")}.`
              : "Every rule passes."}{" "}
            Context: the published data ({s.context.kind === "live" ? `live, fetched ${when(s.context.fetched_at)}` : `snapshot of ${when(s.context.fetched_at)}`}).
          </p>
          {result.notes.length > 0 && (
            <ul className="mt-2 text-sm text-ink-3">{result.notes.map((n) => <li key={n}>{n}</li>)}</ul>
          )}

          <table className="data mt-4">
            <caption className="sr-only">Records checked</caption>
            <thead>
              <tr>
                <th scope="col">Record</th>
                <th scope="col">What it is</th>
                <th scope="col" className="text-right">Findings</th>
              </tr>
            </thead>
            <tbody>
              {result.resources.map((r) => (
                <tr key={r.key}>
                  <td className="whitespace-nowrap">
                    {r.findings ? <a href={`#f-${r.key}`} className="text-karst underline underline-offset-2">{r.key}</a> : r.key}
                  </td>
                  <td>
                    {r.display}
                    {r.identical_to_published && <span className="ml-2 rounded-full bg-sunk px-2 text-xs text-ink-2">identical to the published record</span>}
                    {r.replaces_published && <span className="ml-2 rounded-full bg-karst-soft px-2 text-xs text-karst">your version of a published record</span>}
                  </td>
                  <td className="text-right">
                    {r.worst ? <SeverityTag severity={r.worst} /> : <span className="text-algae">✓ none</span>}
                    {r.findings > 1 && <span className="readout ml-2 text-ink-2">×{r.findings}</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          {result.findings.length > 0 && (
            <ul className="m-0 mt-6 list-none space-y-3 p-0">
              {result.findings.map((f, i) => (
                <li key={`${f.id}-${i}`} id={i === result.findings.findIndex((x) => x.resource.key === f.resource.key) ? `f-${f.resource.key}` : undefined}
                  className="rounded-xl border border-line bg-panel p-4">
                  <div className="flex flex-wrap items-center gap-2">
                    <SeverityTag severity={f.severity} />
                    <span className="readout text-sm text-ink-2">{f.rule_id}</span>
                    <span className="font-semibold">{f.title}</span>
                  </div>
                  <p className="mb-0 mt-2">{f.summary}</p>
                  <details className="mt-2">
                    <summary className="cursor-pointer text-sm font-semibold text-karst">Evidence and what to do</summary>
                    <dl className="mt-2 grid gap-x-4 gap-y-1 text-sm sm:grid-cols-[10rem_1fr]">
                      <dt className="text-ink-3">Record</dt><dd className="m-0">{f.resource.key}{f.resource.fhir_path ? `, ${f.resource.fhir_path}` : ""}</dd>
                      <dt className="text-ink-3">Constraint</dt><dd className="m-0 code">{f.evidence.constraint}</dd>
                      <dt className="text-ink-3">Expected</dt><dd className="m-0">{f.evidence.expected}</dd>
                      <dt className="text-ink-3">Observed</dt>
                      <dd className="m-0">{f.evidence.observed.map((o) => `${o.label} ${num(o.value as number)}${o.unit ? ` ${o.unit}` : ""}`).join("; ")}</dd>
                      <dt className="text-ink-3">Meaning</dt><dd className="m-0">{f.interpretation}</dd>
                      <dt className="text-ink-3">What to do</dt><dd className="m-0">{f.remediation}</dd>
                    </dl>
                  </details>
                </li>
              ))}
            </ul>
          )}
          <p className="mt-6 text-sm text-ink-3">
            Findings use the same rules as the published audit; see <Link to="/sources" className="text-karst underline underline-offset-2">Sources and rules</Link>.
          </p>
        </section>
      )}
    </article>
  );
}
