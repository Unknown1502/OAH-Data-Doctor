import { useMemo } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useRun } from "../components/Shell";
import { ErrorNote, Loading, SeverityShape, SeverityTag, useDocumentTitle } from "../components/ui";
import { useApi } from "../lib/api";
import { pretty, sentence, SEVERITY_MEANING, SEVERITY_ORDER, SEVERITY_TEXT } from "../lib/format";
import type { FindingCompact, RuleSpec, Severity } from "../lib/types";

interface FindingsResponse {
  total: number;
  items: FindingCompact[];
  facets: { severity: Record<string, number>; rule: Record<string, number>; category: Record<string, number>; scope: Record<string, number> };
}

export default function Findings() {
  useDocumentTitle("Findings");
  const { runId } = useRun();
  const [params, setParams] = useSearchParams();
  const severity = params.get("severity") ?? "";
  const rule = params.get("rule") ?? "";
  const q = params.get("q") ?? "";
  const scope = params.get("scope") ?? "";
  const query = new URLSearchParams({ ...(severity && { severity }), ...(rule && { rule }), ...(q && { q }), ...(scope && { scope }) }).toString();
  const res = useApi<FindingsResponse>(`/findings${query ? `?${query}` : ""}`, [runId]);
  const all = useApi<FindingsResponse>("/findings?limit=1", [runId]);
  const rules = useApi<RuleSpec[]>("/rules", [runId]);
  const titles = useMemo(() => Object.fromEntries((rules.data ?? []).map((r) => [r.id, r.title])), [rules.data]);

  const set = (k: string, v: string) => {
    const next = new URLSearchParams(params);
    if (v) next.set(k, v);
    else next.delete(k);
    setParams(next, { replace: true });
  };
  const facets = all.data?.facets;

  return (
    <article>
      <h1 className="m-0 text-4xl font-bold tracking-tight">Findings</h1>
      <p className="mt-2 max-w-[70ch] text-lg text-ink-2">
        Every finding names the rule, the record, the exact field, the values observed and the constraint they break. None claims to
        know why a value is wrong.
      </p>

      <form className="mt-6 flex flex-wrap items-end gap-4 rounded-xl border border-line bg-panel p-4" role="search" onSubmit={(e) => e.preventDefault()}>
        <fieldset className="m-0 border-0 p-0">
          <legend className="mb-1 text-sm text-ink-2">Severity</legend>
          <div className="flex flex-wrap gap-1.5">
            {["", ...SEVERITY_ORDER].map((s) => {
              const active = severity === s;
              const count = s ? facets?.severity[s] ?? 0 : all.data?.total;
              if (s && !count) return null;
              return (
                <button
                  key={s || "all"}
                  type="button"
                  aria-pressed={active}
                  onClick={() => set("severity", s)}
                  title={s ? SEVERITY_MEANING[s as Severity] : "Show every severity"}
                  className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-sm ${
                    active ? "border-karst bg-karst-soft font-semibold text-karst" : "border-line text-ink-2 hover:bg-sunk"
                  }`}
                >
                  {s && <SeverityShape severity={s as Severity} />}
                  {s ? SEVERITY_TEXT[s as Severity] : "All"} <span className="readout">{count ?? ""}</span>
                </button>
              );
            })}
          </div>
        </fieldset>
        <div>
          <label htmlFor="f-rule" className="mb-1 block text-sm text-ink-2">
            Rule
          </label>
          <select id="f-rule" value={rule} onChange={(e) => set("rule", e.target.value)} className="max-w-[22rem] rounded-md border border-line bg-panel px-2 py-1.5">
            <option value="">All rules</option>
            {Object.entries(facets?.rule ?? {})
              .sort()
              .map(([r, n]) => (
                <option key={r} value={r}>
                  {r} {titles[r] ? `(${titles[r]})` : ""}: {n}
                </option>
              ))}
          </select>
        </div>
        <div>
          <label htmlFor="f-scope" className="mb-1 block text-sm text-ink-2">
            Records
          </label>
          <select id="f-scope" value={scope} onChange={(e) => set("scope", e.target.value)} className="rounded-md border border-line bg-panel px-2 py-1.5">
            <option value="">All records</option>
            <option value="oah-ig">Official OAH examples</option>
            <option value="third-party">Written by others to the sandbox</option>
          </select>
        </div>
        <div className="grow">
          <label htmlFor="f-q" className="mb-1 block text-sm text-ink-2">
            Search
          </label>
          <input
            id="f-q"
            type="search"
            defaultValue={q}
            onChange={(e) => set("q", e.target.value)}
            placeholder="e.g. Almyros, PM2.5, median"
            className="w-full min-w-[12rem] rounded-md border border-line bg-panel px-2 py-1.5"
          />
        </div>
      </form>

      {res.error && <div className="mt-6"><ErrorNote error={res.error} /></div>}
      {!res.data && !res.error && <Loading what="findings" />}
      {res.data && (
        <>
          <p className="mt-6 text-ink-2" aria-live="polite">
            {res.data.total} finding{res.data.total === 1 ? "" : "s"}
            {res.data.total > res.data.items.length ? `, showing the first ${res.data.items.length}` : ""}.
          </p>
          {res.data.total === 0 ? (
            <p className="rounded-xl border border-line bg-panel p-6 text-ink-2">
              No findings match these filters. Clear a filter to see more.
            </p>
          ) : (
            <div className="overflow-x-auto rounded-xl border border-line bg-panel">
              <table className="data">
                <caption className="sr-only">Findings, most severe first</caption>
                <thead>
                  <tr>
                    <th scope="col">Severity</th>
                    <th scope="col">Record</th>
                    <th scope="col">What is wrong</th>
                    <th scope="col">Rule</th>
                    <th scope="col">Confidence</th>
                  </tr>
                </thead>
                <tbody>
                  {res.data.items.map((f) => (
                    <tr key={f.id}>
                      <td>
                        <SeverityTag severity={f.severity} />
                      </td>
                      <td className="min-w-[12rem]">
                        <Link to={`/findings/${encodeURIComponent(f.id)}`} className="font-semibold text-karst underline underline-offset-2">
                          {f.resource.display ?? f.resource.resource_id}
                        </Link>
                        <span className="block text-sm text-ink-3">
                          {f.resource.resource_type}
                          {f.scope === "third-party" ? ", written by a third party" : ""}
                        </span>
                      </td>
                      <td className="max-w-[46ch]">{sentence(pretty(f.summary.replace(`${f.resource.display ?? ""}: `, "")))}</td>
                      <td className="whitespace-nowrap">
                        {f.rule_id}
                        <span className="block text-sm text-ink-3">{titles[f.rule_id]}</span>
                      </td>
                      <td className="whitespace-nowrap">
                        {f.confidence_label} <span className="readout text-sm text-ink-3">{f.confidence}</span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </article>
  );
}
