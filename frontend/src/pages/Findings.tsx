import { useMemo } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useRun } from "../components/Shell";
import { EmptyState, ErrorNote, Loading, PageHeader, SeverityShape, useDocumentTitle } from "../components/ui";
import { useApi } from "../lib/api";
import { pretty, sentence, SEVERITY_MEANING, SEVERITY_ORDER, SEVERITY_TEXT, when } from "../lib/format";
import type { FindingCompact, ObservationItem, RuleSpec, Severity } from "../lib/types";

interface FindingsResponse {
  total: number;
  items: FindingCompact[];
  facets: { severity: Record<string, number>; rule: Record<string, number>; category: Record<string, number>; scope: Record<string, number> };
}

const SEV_TEXT_CLASS: Record<Severity, string> = {
  CRITICAL: "text-cinnabar",
  ERROR: "text-ochre",
  WARNING: "text-sulfur",
  INFO: "text-slate",
};

const titleCase = (s: string) => s.charAt(0) + s.slice(1).toLowerCase();

function FilterSelect({ id, label, value, onChange, children }: { id: string; label: string; value: string; onChange: (v: string) => void; children: React.ReactNode }) {
  return (
    <div className="min-w-0">
      <label htmlFor={id} className="mb-1 block text-xs font-semibold uppercase tracking-[0.08em] text-ink-2">
        {label}
      </label>
      <select id={id} value={value} onChange={(e) => onChange(e.target.value)} className="w-full max-w-[18rem] rounded-md border border-line bg-panel px-2 py-1.5 text-sm">
        {children}
      </select>
    </div>
  );
}

/**
 * The investigation queue: one dense row per finding, most severe first. Severity, category, rule and records filter on the
 * server; place and indicator come from the observations the audit read (a finding on another resource type has neither).
 */
export default function Findings() {
  useDocumentTitle("Findings");
  const { runId, status } = useRun();
  const [params, setParams] = useSearchParams();
  const severity = params.get("severity") ?? "";
  const rule = params.get("rule") ?? "";
  const q = params.get("q") ?? "";
  const scope = params.get("scope") ?? "";
  const category = params.get("category") ?? "";
  const place = params.get("place") ?? "";
  const indicator = params.get("indicator") ?? "";
  const query = new URLSearchParams({
    limit: "2000",
    ...(severity && { severity }),
    ...(rule && { rule }),
    ...(q && { q }),
    ...(scope && { scope }),
    ...(category && { category }),
  }).toString();
  const res = useApi<FindingsResponse>(`/findings?${query}`, [runId]);
  const all = useApi<FindingsResponse>("/findings?limit=1", [runId]);
  const rules = useApi<RuleSpec[]>("/rules", [runId]);
  const obs = useApi<{ total: number; items: ObservationItem[] }>("/observations", [runId]);
  const titles = useMemo(() => Object.fromEntries((rules.data ?? []).map((r) => [r.id, r.title])), [rules.data]);
  const byId = useMemo(() => new Map((obs.data?.items ?? []).map((o) => [o.id, o])), [obs.data]);
  const places = useMemo(() => [...new Set((obs.data?.items ?? []).map((o) => o.location).filter((x): x is string => !!x))].sort(), [obs.data]);
  const indicators = useMemo(() => [...new Set((obs.data?.items ?? []).map((o) => o.indicator).filter((x): x is string => !!x))].sort(), [obs.data]);

  const set = (k: string, v: string) => {
    const next = new URLSearchParams(params);
    if (v) next.set(k, v);
    else next.delete(k);
    setParams(next, { replace: true });
  };
  const facets = all.data?.facets;
  const rows = (res.data?.items ?? []).filter((f) => {
    if (!place && !indicator) return true;
    const o = f.resource.resource_type === "Observation" ? byId.get(f.resource.resource_id) : undefined;
    return !!o && (!place || o.location === place) && (!indicator || o.indicator === indicator);
  });
  const filtered = !!(severity || rule || q || scope || category || place || indicator);
  const src = status?.source;

  return (
    <article>
      <PageHeader
        title="Findings"
        lead="Every finding names the rule, the record, the exact field, the values observed and the constraint they break. None claims to know why a value is wrong."
      />

      <form className="border-y border-line py-4" role="search" onSubmit={(e) => e.preventDefault()} aria-label="Filter findings">
        <fieldset className="m-0 border-0 p-0">
          <legend className="mb-1.5 text-xs font-semibold uppercase tracking-[0.08em] text-ink-2">Severity</legend>
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
                  className={`inline-flex items-center gap-1.5 rounded-md border px-2.5 py-1 text-sm ${
                    active ? "border-karst bg-karst-soft font-semibold text-karst" : "border-line text-ink-2 hover:border-line-strong hover:text-ink"
                  }`}
                >
                  {s && <span className={SEV_TEXT_CLASS[s as Severity]}><SeverityShape severity={s as Severity} /></span>}
                  {s ? SEVERITY_TEXT[s as Severity] : "All"} <span className={`readout ${active ? "" : "text-ink-3"}`}>{count ?? ""}</span>
                </button>
              );
            })}
          </div>
        </fieldset>
        <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
          <FilterSelect id="f-cat" label="Category" value={category} onChange={(v) => set("category", v)}>
            <option value="">All categories</option>
            {Object.entries(facets?.category ?? {})
              .sort()
              .map(([c, n]) => (
                <option key={c} value={c}>
                  {titleCase(c)}: {n}
                </option>
              ))}
          </FilterSelect>
          <FilterSelect id="f-rule" label="Rule" value={rule} onChange={(v) => set("rule", v)}>
            <option value="">All rules</option>
            {Object.entries(facets?.rule ?? {})
              .sort()
              .map(([r, n]) => (
                <option key={r} value={r}>
                  {r} {titles[r] ? `(${titles[r]})` : ""}: {n}
                </option>
              ))}
          </FilterSelect>
          <FilterSelect id="f-place" label="Place" value={place} onChange={(v) => set("place", v)}>
            <option value="">All places</option>
            {places.map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
          </FilterSelect>
          <FilterSelect id="f-ind" label="Indicator" value={indicator} onChange={(v) => set("indicator", v)}>
            <option value="">All indicators</option>
            {indicators.map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
          </FilterSelect>
          <FilterSelect id="f-scope" label="Records" value={scope} onChange={(v) => set("scope", v)}>
            <option value="">All records</option>
            <option value="oah-ig">Official OAH examples</option>
            <option value="third-party">Written by others to the sandbox</option>
          </FilterSelect>
          <div className="min-w-0">
            <label htmlFor="f-q" className="mb-1 block text-xs font-semibold uppercase tracking-[0.08em] text-ink-2">
              Search
            </label>
            <input
              id="f-q"
              type="search"
              defaultValue={q}
              onChange={(e) => set("q", e.target.value)}
              placeholder="Almyros, PM2.5, median"
              className="w-full rounded-md border border-line bg-panel px-2 py-1.5 text-sm"
            />
          </div>
        </div>
      </form>

      {res.error && <div className="mt-6"><ErrorNote error={res.error} /></div>}
      {!res.data && !res.error && <Loading what="findings" />}
      {res.data && (
        <>
          <div className="mb-3 mt-5 flex flex-wrap items-baseline justify-between gap-x-6 gap-y-1">
            <p className="m-0 text-ink" aria-live="polite">
              <span className="readout font-semibold">{rows.length}</span> finding{rows.length === 1 ? "" : "s"}
              {filtered && all.data ? <span className="text-ink-2"> of {all.data.total}</span> : null}
            </p>
            {src && (
              <p className="m-0 text-sm text-ink-3">
                Detected by the {src.kind === "live" ? "live" : "snapshot"} audit of {when(src.fetched_at)}; recomputed on every scan.
              </p>
            )}
          </div>
          {rows.length === 0 ? (
            filtered ? (
              <EmptyState title="No findings match these filters.">Clear a filter to see more.</EmptyState>
            ) : (
              <EmptyState title="Audit complete — no findings.">
                Every rule ran on the {src?.kind === "live" ? "live" : "snapshot"} data and none of them found a problem.
              </EmptyState>
            )
          ) : (
            <div className="overflow-x-auto rounded-lg border border-line" tabIndex={0} role="region" aria-label="Table of findings">
              <table className="data dense">
                <caption className="sr-only">Findings, most severe first</caption>
                <thead>
                  <tr>
                    <th scope="col">Severity</th>
                    <th scope="col">Finding</th>
                    <th scope="col" className="hidden md:table-cell">Record</th>
                    <th scope="col" className="hidden md:table-cell">Place</th>
                    <th scope="col" className="hidden md:table-cell">Rule and field</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((f) => {
                    const o = f.resource.resource_type === "Observation" ? byId.get(f.resource.resource_id) : undefined;
                    return (
                      <tr key={f.id}>
                        <td className="whitespace-nowrap">
                          <span className={`inline-flex items-center gap-1.5 text-sm font-semibold ${SEV_TEXT_CLASS[f.severity]}`}>
                            <SeverityShape severity={f.severity} />
                            {SEVERITY_TEXT[f.severity]}
                          </span>
                          <span className="block text-xs uppercase tracking-[0.06em] text-ink-3">{titleCase(f.category)}</span>
                        </td>
                        <td className="md:min-w-[22rem]">
                          <Link to={`/findings/${encodeURIComponent(f.id)}`} className="font-semibold text-ink no-underline hover:text-karst hover:underline">
                            {f.title}
                          </Link>
                          <span className="mt-0.5 line-clamp-2 text-sm text-ink-2">{sentence(pretty(f.summary.replace(`${f.resource.display ?? ""}: `, "")))}</span>
                          <span className="mt-1 block text-xs text-ink-3 md:hidden">
                            {f.resource.display ?? f.resource.resource_id}, <span className="code">{f.rule_id}</span>
                          </span>
                        </td>
                        <td className="hidden min-w-[11rem] md:table-cell">
                          <span className="block text-sm text-ink">{o?.indicator ?? f.resource.display ?? f.resource.resource_id}</span>
                          <span className="block text-xs text-ink-3">
                            {f.resource.resource_type}
                            {o?.year ? `, ${o.year}` : ""}
                            {f.scope === "third-party" ? ", third party" : ""}
                          </span>
                        </td>
                        <td className="hidden min-w-[9rem] text-sm text-ink-2 md:table-cell">{o?.location ?? "—"}</td>
                        <td className="hidden whitespace-nowrap md:table-cell">
                          <span className="code text-sm">{f.rule_id}</span>
                          {f.resource.fhir_path && <span className="code block text-xs text-ink-3">{f.resource.fhir_path.replace(/^[A-Za-z]+\./, "")}</span>}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </article>
  );
}
