import { useLayoutEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { pretty } from "../lib/format";
import type { Impact, ImpactNode } from "../lib/types";
import { Verdict } from "./ui";

const COLUMNS: { key: string; title: string; types: ImpactNode["type"][] }[] = [
  { key: "c", title: "Published collections", types: ["library", "profile"] },
  { key: "s", title: "Derived series", types: ["series"] },
  { key: "a", title: "Comparisons", types: ["comparison"] },
  { key: "l", title: "Claims", types: ["claim"] },
];

const TYPE_TEXT: Record<ImpactNode["type"], string> = {
  library: "Data set",
  profile: "Indicator profile",
  series: "Annual series",
  comparison: "Comparison",
  claim: "Claim",
};

const RELATION: Record<string, string> = {
  "member-of": "is a record of",
  "summarised-in": "is summarised in",
  "point-of": "is a point of",
  "input-to": "is an input to",
  "evidence-for": "is evidence for",
  "basis-of": "is the basis of",
};

const START = "__start";

/** Where a node can be opened in the app, when it is an analysis the user can inspect. */
function linkFor(n: ImpactNode): string | null {
  if (n.type === "comparison") return `/compare?id=${encodeURIComponent(n.id.replace(/^comparison:/, ""))}`;
  if (n.type === "claim") return `/claims?id=${encodeURIComponent(n.id.replace(/^claim:/, ""))}`;
  return null;
}

/**
 * What a record would contaminate: the dependency graph Data Doctor actually computed (nothing estimated). Select a node
 * to highlight everything it depends on and everything that depends on it; the details list the same relations as text.
 */
export default function TraceGraph({ impact, recordLabel }: { impact: Impact; recordLabel: string }) {
  const wrap = useRef<HTMLDivElement>(null);
  const [paths, setPaths] = useState<{ d: string; a: string; b: string }[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const nodes = impact.reachable;
  const byId = useMemo(() => new Map(nodes.map((n) => [n.id, n])), [nodes]);
  const edges = useMemo(() => impact.edges.map(([a, b, rel]) => ({ a: impact.start.includes(a) ? START : a, b, rel })), [impact]);
  const cols = COLUMNS.map((c) => ({ ...c, nodes: nodes.filter((n) => c.types.includes(n.type)) })).filter((c) => c.nodes.length);

  // The selected node's path: everything upstream (to the record) and downstream (what it feeds).
  const onPath = useMemo(() => {
    if (!selected) return null;
    const set = new Set([selected]);
    const walk = (dir: "up" | "down") => {
      const queue = [selected];
      while (queue.length) {
        const cur = queue.shift()!;
        for (const e of edges) {
          const next = dir === "up" ? (e.b === cur ? e.a : null) : e.a === cur ? e.b : null;
          if (next && !set.has(next)) {
            set.add(next);
            queue.push(next);
          }
        }
      }
    };
    walk("up");
    walk("down");
    return set;
  }, [selected, edges]);

  useLayoutEffect(() => {
    const el = wrap.current;
    if (!el) return;
    const draw = () => {
      const box = el.getBoundingClientRect();
      const pos = (id: string) => {
        const n = el.querySelector<HTMLElement>(`[data-node="${CSS.escape(id)}"]`);
        if (!n) return null;
        const r = n.getBoundingClientRect();
        return { l: r.left - box.left + el.scrollLeft, r: r.right - box.left + el.scrollLeft, y: r.top - box.top + r.height / 2 };
      };
      const out: { d: string; a: string; b: string }[] = [];
      for (const e of edges) {
        const pa = pos(e.a);
        const pb = pos(e.b);
        if (!pa || !pb || pb.l <= pa.r) continue;
        const mx = (pa.r + pb.l) / 2;
        out.push({ d: `M${pa.r} ${pa.y} C${mx} ${pa.y}, ${mx} ${pb.y}, ${pb.l} ${pb.y}`, a: e.a, b: e.b });
      }
      setPaths(out);
    };
    draw();
    const ro = new ResizeObserver(draw);
    ro.observe(el);
    return () => ro.disconnect();
  }, [edges]);

  if (!nodes.length) {
    return <p className="text-ink-2">{impact.statement} No verified dependency has been computed for this record.</p>;
  }

  const sel = selected && selected !== START ? byId.get(selected) : null;
  const dim = (id: string) => onPath !== null && !onPath.has(id);
  const label = (id: string) => (id === START ? recordLabel : pretty(byId.get(id)?.label ?? id));
  const dependsOn = selected ? edges.filter((e) => e.b === selected) : [];
  const usedBy = selected ? edges.filter((e) => e.a === selected) : [];

  return (
    <div>
      <p className="m-0 mb-4 max-w-[70ch] text-ink-2">
        {impact.statement} Only analyses that Data Doctor actually computes are shown; nothing is estimated. Select a box to follow its path.
      </p>
      <div ref={wrap} className="relative overflow-x-auto pb-2" tabIndex={-1}>
        <svg className="pointer-events-none absolute inset-0 h-full" style={{ minWidth: 760, width: "100%" }} aria-hidden="true">
          {paths.map((p, i) => {
            const on = onPath !== null && onPath.has(p.a) && onPath.has(p.b);
            return (
              <path key={i} d={p.d} fill="none" stroke={on ? "var(--karst)" : "var(--line-strong)"} strokeWidth={on ? 2.4 : 1.4}
                opacity={onPath !== null && !on ? 0.35 : 1} />
            );
          })}
        </svg>
        <div className="relative grid gap-8" style={{ gridTemplateColumns: `minmax(150px,1fr) repeat(${cols.length}, minmax(170px,1.2fr))`, minWidth: 760 }}>
          <div className="flex flex-col justify-center">
            <button
              type="button"
              data-node={START}
              aria-pressed={selected === START}
              onClick={() => setSelected(selected === START ? null : START)}
              className={`rounded-lg border-2 border-cinnabar bg-cinnabar-soft px-3 py-2 text-left text-sm font-semibold text-cinnabar ${selected === START ? "ring-2 ring-karst" : ""}`}
            >
              <span className="block text-xs font-normal">This record</span>
              {recordLabel}
            </button>
          </div>
          {cols.map((c) => (
            <div key={c.key} className="flex flex-col justify-center gap-2">
              <p className="m-0 text-sm font-semibold text-ink-2">{c.title}</p>
              {c.nodes.map((n) => (
                <button
                  type="button"
                  key={n.id}
                  data-node={n.id}
                  aria-pressed={selected === n.id}
                  onClick={() => setSelected(selected === n.id ? null : n.id)}
                  className={`rounded-lg border bg-panel px-3 py-2 text-left text-sm transition-opacity ${selected === n.id ? "border-karst ring-2 ring-karst" : "border-line hover:border-karst"} ${dim(n.id) ? "opacity-40" : ""}`}
                >
                  <span className="block text-ink-3">{TYPE_TEXT[n.type]}</span>
                  <span className="block text-ink">{pretty(n.label)}</span>
                  {typeof n.attrs.verdict === "string" && (
                    <span className="mt-1 block [&>span]:whitespace-normal">
                      <Verdict value={n.attrs.verdict} />
                    </span>
                  )}
                </button>
              ))}
            </div>
          ))}
        </div>
      </div>

      {selected && (
        <div className="mt-4 rounded-xl border border-karst/50 bg-panel p-4" aria-live="polite">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <p className="m-0">
              <span className="text-sm text-ink-3">{sel ? TYPE_TEXT[sel.type] : "This record"}</span>
              <span className="block font-semibold">{label(selected)}</span>
            </p>
            <button type="button" onClick={() => setSelected(null)} className="text-sm text-ink-2 underline underline-offset-2">
              Clear the selection
            </button>
          </div>
          <dl className="mb-0 mt-3 grid gap-x-6 gap-y-1.5 text-sm sm:grid-cols-[8rem_1fr]">
            {sel && typeof sel.attrs.verdict === "string" && (
              <>
                <dt className="text-ink-2">Verdict</dt>
                <dd className="m-0"><Verdict value={sel.attrs.verdict} /></dd>
              </>
            )}
            <dt className="text-ink-2">Depends on</dt>
            <dd className="m-0">
              {dependsOn.length ? dependsOn.map((e) => <span key={e.a + e.rel} className="block">{label(e.a)} <span className="text-ink-3">({RELATION[e.rel] ?? e.rel} this)</span></span>) : "—"}
            </dd>
            <dt className="text-ink-2">Used by</dt>
            <dd className="m-0">
              {usedBy.length ? usedBy.map((e) => <span key={e.b + e.rel} className="block">{label(e.b)} <span className="text-ink-3">(this {RELATION[e.rel] ?? e.rel} it)</span></span>) : "Nothing further that Data Doctor computes."}
            </dd>
            {sel && linkFor(sel) && (
              <>
                <dt className="text-ink-2">Open</dt>
                <dd className="m-0">
                  <Link to={linkFor(sel)!} className="text-karst underline underline-offset-2">See this {TYPE_TEXT[sel.type].toLowerCase()} and its evidence</Link>
                </dd>
              </>
            )}
          </dl>
        </div>
      )}
    </div>
  );
}
