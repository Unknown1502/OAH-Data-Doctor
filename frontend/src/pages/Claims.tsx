import { useEffect, useId, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { ModelBadge, describeModel, useLlm } from "../components/ModelSettings";
import { useRun } from "../components/Shell";
import { Button, ErrorNote, FindingLink, Verdict, useDocumentTitle } from "../components/ui";
import { post, useApi } from "../lib/api";
import { num, pretty, tone } from "../lib/format";
import type { ClaimResult, Knowledge, ObservationItem, ParseResult, StructuredClaim } from "../lib/types";

const TYPE_TEXT: Record<StructuredClaim["type"], string> = {
  COMPARE_HIGHER: "A is higher than B",
  TREND_INCREASE: "A value increased over time",
  EXCEEDS_THRESHOLD: "A value exceeds a limit or guideline",
  ASSOCIATION: "Two measures are associated",
  CAUSAL: "One measure causes another",
};

const EXAMPLES = [
  "Water temperature at Almyros increased from 2013 to 2020",
  "NO2 was higher at Benevento site 01 than site 02 in 2019",
  "PM10 at Benevento site 04 exceeded the WHO guideline in 2018",
  "Obesity is higher in Benevento than in Oslo",
  "PM2.5 causes cardiovascular disease in Benevento",
];

function ClaimFields({ claim }: { claim: StructuredClaim }) {
  const rows: [string, string | number | null | undefined][] = [
    ["Kind of claim", TYPE_TEXT[claim.type]],
    ["Record A", claim.subject],
    ["Record B", claim.object],
    ["Place", claim.location_id],
    ["Measure", claim.indicator_key],
    ["Outcome measure", claim.outcome_indicator_key],
    ["Statistic", claim.statistic],
    ["Threshold", claim.threshold_id],
    ["From year", claim.year_from],
    ["To year", claim.year_to],
  ];
  return (
    <dl className="m-0 grid grid-cols-[auto_1fr] gap-x-5 gap-y-1 text-[0.95rem]">
      {rows.filter(([, v]) => v !== null && v !== undefined && v !== "").map(([k, v]) => (
        <div key={k} className="contents">
          <dt className="text-ink-2">{k}</dt>
          <dd className="code m-0 break-all">{String(v)}</dd>
        </div>
      ))}
    </dl>
  );
}

function Stats({ s }: { s: Record<string, unknown> }) {
  const mk = s.mann_kendall as Record<string, unknown> | undefined;
  const rows: [string, string][] = [];
  if (Array.isArray(s.years) && Array.isArray(s.values)) rows.push(["Series", (s.years as number[]).map((y, i) => `${y}: ${num((s.values as number[])[i])}`).join(", ")]);
  if (mk) rows.push(["Mann–Kendall", `S = ${mk.S}, one-sided p = ${mk.p_one_sided} (${mk.method}, n = ${mk.n})`]);
  if (typeof s.theil_sen_slope_per_year === "number") rows.push(["Theil–Sen slope", `${num(s.theil_sen_slope_per_year)} per year`]);
  if (Array.isArray(s.missing_years) && (s.missing_years as number[]).length) rows.push(["Missing years", (s.missing_years as number[]).join(", ")]);
  if (typeof s.ratio === "number") rows.push(["Value / threshold", `${num(s.value as number)} / ${num(s.threshold as number)} ${s.unit} = ${num(s.ratio)}`]);
  if (typeof s.difference === "number") rows.push(["Difference A − B", `${num(s.difference)} ${s.unit ?? ""}`]);
  if (Array.isArray(s.paired_units)) rows.push(["Sites with both measures", `${(s.paired_units as string[]).length}: ${(s.paired_units as string[]).join(", ")}`]);
  if (!rows.length) return null;
  return (
    <dl className="m-0 mt-2 grid grid-cols-[auto_1fr] gap-x-5 gap-y-1 text-[0.95rem]">
      {rows.map(([k, v]) => (
        <div key={k} className="contents">
          <dt className="text-ink-2">{k}</dt>
          <dd className="readout m-0">{v}</dd>
        </div>
      ))}
    </dl>
  );
}

function Builder({ onRun }: { onRun: (c: StructuredClaim) => void }) {
  const { runId } = useRun();
  const id = useId();
  const kn = useApi<Knowledge>("/knowledge", [runId]);
  const obs = useApi<{ items: ObservationItem[] }>("/observations", [runId]);
  const [c, setC] = useState<StructuredClaim>({ type: "TREND_INCREASE", statistic: "average" });
  const items = obs.data?.items ?? [];
  const locations = Array.from(new Map(items.filter((o) => o.location_id).map((o) => [o.location_id!, o.location!])).entries());
  const set = (k: keyof StructuredClaim, v: string) => setC((p) => ({ ...p, [k]: v === "" ? null : ["year_from", "year_to"].includes(k) ? Number(v) : v }));
  const field = "mt-1 w-full rounded-md border border-line bg-chalk px-2 py-1.5";
  const recordSelect = (k: "subject" | "object", label: string) => (
    <div>
      <label htmlFor={`${id}-${k}`} className="block text-sm text-ink-2">{label}</label>
      <select id={`${id}-${k}`} className={field} value={c[k] ?? ""} onChange={(e) => set(k, e.target.value)}>
        <option value="">Choose a record</option>
        {items.map((o) => (
          <option key={o.id} value={o.id}>{[o.indicator, o.location, o.cohort, o.year].filter(Boolean).join(", ")}</option>
        ))}
      </select>
    </div>
  );
  const indicatorSelect = (k: "indicator_key" | "outcome_indicator_key", label: string) => (
    <div>
      <label htmlFor={`${id}-${k}`} className="block text-sm text-ink-2">{label}</label>
      <select id={`${id}-${k}`} className={field} value={c[k] ?? ""} onChange={(e) => set(k, e.target.value)}>
        <option value="">Choose a measure</option>
        {Object.entries(kn.data?.indicators ?? {}).map(([key, v]) => <option key={key} value={key}>{v.label}</option>)}
      </select>
    </div>
  );
  const ready =
    (c.type === "COMPARE_HIGHER" && c.subject && c.object) ||
    (c.type === "TREND_INCREASE" && c.location_id && c.indicator_key) ||
    (c.type === "EXCEEDS_THRESHOLD" && c.subject && c.threshold_id) ||
    ((c.type === "ASSOCIATION" || c.type === "CAUSAL") && c.indicator_key && c.outcome_indicator_key);
  return (
    <form className="grid gap-3 sm:grid-cols-2" onSubmit={(e) => { e.preventDefault(); if (ready) onRun(c); }}>
      <div className="sm:col-span-2">
        <label htmlFor={`${id}-type`} className="block text-sm text-ink-2">Kind of claim</label>
        <select id={`${id}-type`} className={field} value={c.type} onChange={(e) => setC({ type: e.target.value as StructuredClaim["type"], statistic: "average" })}>
          {Object.entries(TYPE_TEXT).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </select>
      </div>
      {c.type === "COMPARE_HIGHER" && (<>{recordSelect("subject", "Record A (claimed higher)")}{recordSelect("object", "Record B")}</>)}
      {c.type === "EXCEEDS_THRESHOLD" && (
        <>
          {recordSelect("subject", "Record")}
          <div>
            <label htmlFor={`${id}-th`} className="block text-sm text-ink-2">Limit or guideline</label>
            <select id={`${id}-th`} className={field} value={c.threshold_id ?? ""} onChange={(e) => set("threshold_id", e.target.value)}>
              <option value="">Choose a threshold</option>
              {Object.values(kn.data?.thresholds ?? {}).map((t) => <option key={t.id} value={t.id}>{t.source}: {t.value} {t.unit}</option>)}
            </select>
          </div>
        </>
      )}
      {c.type === "TREND_INCREASE" && (
        <>
          <div>
            <label htmlFor={`${id}-loc`} className="block text-sm text-ink-2">Place</label>
            <select id={`${id}-loc`} className={field} value={c.location_id ?? ""} onChange={(e) => set("location_id", e.target.value)}>
              <option value="">Choose a place</option>
              {locations.map(([lid, name]) => <option key={lid} value={lid}>{name}</option>)}
            </select>
          </div>
          {indicatorSelect("indicator_key", "Measure")}
          <div>
            <label htmlFor={`${id}-yf`} className="block text-sm text-ink-2">From year</label>
            <input id={`${id}-yf`} type="number" className={field} value={c.year_from ?? ""} onChange={(e) => set("year_from", e.target.value)} />
          </div>
          <div>
            <label htmlFor={`${id}-yt`} className="block text-sm text-ink-2">To year</label>
            <input id={`${id}-yt`} type="number" className={field} value={c.year_to ?? ""} onChange={(e) => set("year_to", e.target.value)} />
          </div>
        </>
      )}
      {(c.type === "ASSOCIATION" || c.type === "CAUSAL") && (<>{indicatorSelect("indicator_key", "Exposure")}{indicatorSelect("outcome_indicator_key", "Outcome")}</>)}
      {(c.type === "COMPARE_HIGHER" || c.type === "TREND_INCREASE" || c.type === "EXCEEDS_THRESHOLD") && (
        <div>
          <label htmlFor={`${id}-stat`} className="block text-sm text-ink-2">Statistic (for annual summaries)</label>
          <select id={`${id}-stat`} className={field} value={c.statistic ?? "average"} onChange={(e) => set("statistic", e.target.value)}>
            <option value="average">Annual mean</option>
            <option value="median">Annual median</option>
            <option value="maximum">Annual maximum</option>
          </select>
        </div>
      )}
      <div className="sm:col-span-2">
        <Button kind="primary" type="submit" disabled={!ready}>Check this claim</Button>
      </div>
    </form>
  );
}

export default function Claims() {
  useDocumentTitle("Check a claim");
  const { runId } = useRun();
  const llm = useLlm();
  const [params] = useSearchParams();
  const analyses = useApi<{ claims: ClaimResult[] }>("/analyses", [runId]);
  const [text, setText] = useState("");
  const [parsed, setParsed] = useState<ParseResult | null>(null);
  const [result, setResult] = useState<ClaimResult | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [copied, setCopied] = useState<string | null>(null);

  useEffect(() => {
    const id = params.get("id");
    const c = analyses.data?.claims.find((x) => x.id === id);
    if (c) {
      setResult(c);
      setParsed(null);
      setText(c.claim.text ?? "");
    }
  }, [params, analyses.data]);

  const evaluate = async (claim: StructuredClaim) => {
    setErr(null);
    setBusy(true);
    try {
      setResult(await post<ClaimResult>("/claims", { claim }));
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const check = async (t: string) => {
    setErr(null);
    setResult(null);
    setBusy(true);
    try {
      const p = await post<ParseResult>("/claims/parse", { text: t, ...llm.body });
      setParsed(p);
      if (p.claim) await evaluate(p.claim);
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const copy = async (s: string) => {
    try {
      await navigator.clipboard.writeText(s);
      setCopied(s);
      setTimeout(() => setCopied(null), 2000);
    } catch {
      setCopied(null);
    }
  };

  return (
    <article>
      <h1 className="m-0 text-4xl font-bold tracking-tight">Check a research claim</h1>
      <p className="mt-2 max-w-[70ch] text-lg text-ink-2">
        Write what you want to say about the data. Data Doctor turns it into a structured claim, shows you exactly how it read it, and
        decides with fixed rules whether the published data supports it, and what you can safely say instead.
      </p>

      <form className="mt-6 rounded-xl border border-line bg-panel p-4" onSubmit={(e) => { e.preventDefault(); if (text.trim()) check(text.trim()); }}>
        <label htmlFor="claim-text" className="block font-semibold">Your claim</label>
        <textarea id="claim-text" rows={2} maxLength={500} value={text} onChange={(e) => setText(e.target.value)}
          placeholder="e.g. PM2.5 at Benevento site 01 exceeded the WHO guideline in 2019"
          className="mt-2 w-full rounded-md border border-line bg-chalk px-3 py-2 text-lg" />
        <div className="mt-3 flex flex-wrap items-center gap-3">
          <Button kind="primary" type="submit" disabled={!text.trim() || busy}>{busy ? "Checking…" : "Check this claim"}</Button>
          {busy && llm.activeName && <span role="status" className="text-sm text-ink-3">{describeModel(llm.activeName).label} is helping read the claim; a local model can take up to a minute.</span>}
          <span className="text-sm text-ink-3">Try:</span>
          {EXAMPLES.map((e) => (
            <button key={e} type="button" onClick={() => { setText(e); check(e); }} className="rounded-full border border-line px-3 py-1 text-sm text-ink-2 hover:border-karst hover:text-karst">
              {e}
            </button>
          ))}
        </div>
        {llm.activeName && (
          <p className="mb-0 mt-3 text-sm text-ink-3">
            Language model helping to read claims: <ModelBadge name={llm.activeName} source={llm.config ? "yours" : "server"} />. The verdict is
            always computed by rules.
          </p>
        )}
      </form>

      <details className="mt-4 rounded-xl border border-line bg-panel">
        <summary className="px-4 py-3 font-semibold">Build a structured claim instead</summary>
        <div className="border-t border-line p-4"><Builder onRun={(c) => { setParsed(null); evaluate(c); }} /></div>
      </details>

      {err && <div className="mt-4"><ErrorNote error={err} /></div>}

      {parsed && (
        <section aria-labelledby="read-h" className="mt-8 rounded-xl border border-line bg-panel p-4">
          <h2 id="read-h" className="m-0 text-lg font-bold">How Data Doctor read your claim</h2>
          <p className="m-0 mt-1 text-sm text-ink-3">
            {parsed.method.startsWith("llm") ? (
              <>
                Read by fixed keyword rules, with gaps filled by <ModelBadge name={parsed.method.replace(/^llm:/, "")} />. The verdict below is
                still computed by rules.
              </>
            ) : parsed.method.startsWith("deterministic (")
                ? `Read by fixed keyword rules${parsed.method.slice("deterministic".length)}.`
                : "Read by fixed keyword rules."}
          </p>
          {parsed.understood.length > 0 && <p className="mt-2 text-ink-2">Understood: {parsed.understood.join("; ")}.</p>}
          {parsed.claim ? <ClaimFields claim={parsed.claim} /> : (
            <div role="alert" className="mt-2 text-cinnabar">
              {parsed.problems.join(" ")} Rephrase the claim or build it with the structured form above.
            </div>
          )}
        </section>
      )}

      {result && (
        <section aria-labelledby="verdict-h" aria-live="polite" className="mt-8">
          <div className={`rounded-xl border-2 bg-panel p-5 ${{ good: "border-algae/60", caveat: "border-sulfur/60", bad: "border-slate/60", blocked: "border-cinnabar/60", neutral: "border-line" }[tone(result.verdict)]}`}>
            <h2 id="verdict-h" className="m-0"><Verdict value={result.verdict} size="lg" /></h2>
            <p className="mb-0 mt-3 text-lg">“{pretty(result.claim_rendered)}”</p>
            <ul className="mt-3 max-w-[75ch] pl-5">{result.reasons.map((r) => <li key={r} className="mb-1">{pretty(r)}</li>)}</ul>
            <Stats s={result.statistics} />
          </div>

          {result.safe_alternatives.length > 0 && (
            <div className="mt-6 rounded-xl border border-algae/40 bg-algae-soft p-4">
              <h3 className="m-0 text-lg font-semibold text-algae">What you can safely say</h3>
              <ul className="m-0 mt-2 list-none space-y-3 p-0">
                {result.safe_alternatives.map((s) => (
                  <li key={s} className="flex flex-wrap items-start justify-between gap-3">
                    <span className="max-w-[80ch]">{pretty(s)}</span>
                    <button type="button" onClick={() => copy(s)} className="shrink-0 rounded-md border border-algae/50 px-2.5 py-1 text-sm text-algae hover:bg-panel">
                      {copied === s ? "Copied" : "Copy"}
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {result.blocking_findings.length > 0 && (
            <div className="mt-6">
              <h3 className="m-0 text-lg font-semibold">Findings that block this claim</h3>
              <ul className="mt-1 pl-5">{result.blocking_findings.slice(0, 12).map((id) => <li key={id}><FindingLink id={id}>{id}</FindingLink></li>)}</ul>
              {result.blocking_findings.length > 12 && <p className="text-sm text-ink-3">and {result.blocking_findings.length - 12} more.</p>}
            </div>
          )}

          <div className="mt-6">
            <h3 className="m-0 text-lg font-semibold">Steps the guardrail took</h3>
            <ol className="mt-2 pl-5">
              {result.rule_trace.map((t) => (
                <li key={t.step} className="mb-1">
                  <span className="code text-sm text-ink-3">{t.step}</span> {t.check}: <strong>{typeof t.outcome === "object" ? JSON.stringify(t.outcome) : String(t.outcome)}</strong>
                </li>
              ))}
            </ol>
            {result.comparison && (
              <p className="text-ink-2">
                Comparability of the two values: <Verdict value={result.comparison.verdict} />{" "}
                <Link className="text-karst underline underline-offset-2" to={`/compare?id=${result.comparison.id}`}>see every dimension</Link>
              </p>
            )}
          </div>
        </section>
      )}

      {analyses.data && !result && (
        <section aria-labelledby="ex-h" className="mt-10">
          <h2 id="ex-h" className="m-0 text-2xl font-bold tracking-tight">Claims already checked on this data</h2>
          <ul className="m-0 mt-3 list-none space-y-2 p-0">
            {analyses.data.claims.map((c) => (
              <li key={c.id} className="flex flex-wrap items-start justify-between gap-2 border-b border-line pb-2">
                <button type="button" className="max-w-[70ch] text-left hover:text-karst" onClick={() => { setResult(c); setParsed(null); }}>
                  {pretty(c.claim_rendered)}
                </button>
                <Verdict value={c.verdict} />
              </li>
            ))}
          </ul>
        </section>
      )}
    </article>
  );
}
