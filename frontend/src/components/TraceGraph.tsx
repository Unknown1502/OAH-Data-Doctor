import { useLayoutEffect, useRef, useState } from "react";
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

export default function TraceGraph({ impact, recordLabel }: { impact: Impact; recordLabel: string }) {
  const wrap = useRef<HTMLDivElement>(null);
  const [paths, setPaths] = useState<string[]>([]);
  const nodes = impact.reachable;
  const cols = COLUMNS.map((c) => ({ ...c, nodes: nodes.filter((n) => c.types.includes(n.type)) })).filter((c) => c.nodes.length);

  useLayoutEffect(() => {
    const el = wrap.current;
    if (!el) return;
    const draw = () => {
      const box = el.getBoundingClientRect();
      const pos = (id: string) => {
        const n = el.querySelector<HTMLElement>(`[data-node="${CSS.escape(id)}"]`);
        if (!n) return null;
        const r = n.getBoundingClientRect();
        return { l: r.left - box.left, r: r.right - box.left, y: r.top - box.top + r.height / 2 };
      };
      const out: string[] = [];
      for (const [a, b] of impact.edges) {
        const pa = pos(impact.start.includes(a) ? "__start" : a);
        const pb = pos(b);
        if (!pa || !pb || pb.l <= pa.r) continue;
        const mx = (pa.r + pb.l) / 2;
        out.push(`M${pa.r} ${pa.y} C${mx} ${pa.y}, ${mx} ${pb.y}, ${pb.l} ${pb.y}`);
      }
      setPaths(out);
    };
    draw();
    const ro = new ResizeObserver(draw);
    ro.observe(el);
    return () => ro.disconnect();
  }, [impact]);

  if (!nodes.length) {
    return <p className="text-ink-2">{impact.statement}</p>;
  }

  return (
    <div>
      <p className="m-0 mb-4 max-w-[70ch] text-ink-2">{impact.statement} Only analyses that Data Doctor actually computes are shown; nothing is estimated.</p>
      <div ref={wrap} className="relative overflow-x-auto" aria-hidden="true">
        <svg className="pointer-events-none absolute inset-0 h-full w-full" style={{ minWidth: 760 }}>
          {paths.map((d, i) => (
            <path key={i} d={d} fill="none" stroke="var(--line-strong)" strokeWidth={1.4} />
          ))}
        </svg>
        <div className="relative grid gap-8" style={{ gridTemplateColumns: `minmax(150px,1fr) repeat(${cols.length}, minmax(170px,1.2fr))`, minWidth: 760 }}>
          <div className="flex flex-col justify-center">
            <div data-node="__start" className="rounded-lg border-2 border-cinnabar bg-cinnabar-soft px-3 py-2 text-sm font-semibold text-cinnabar">
              {recordLabel}
            </div>
          </div>
          {cols.map((c) => (
            <div key={c.key} className="flex flex-col justify-center gap-2">
              <p className="m-0 text-sm font-semibold text-ink-2">{c.title}</p>
              {c.nodes.map((n) => (
                <div key={n.id} data-node={n.id} className="rounded-lg border border-line bg-panel px-3 py-2 text-sm">
                  <span className="block text-ink-3">{TYPE_TEXT[n.type]}</span>
                  <span className="block text-ink">{pretty(n.label)}</span>
                  {typeof n.attrs.verdict === "string" && (
                    <span className="mt-1 block [&>span]:whitespace-normal">
                      <Verdict value={n.attrs.verdict} />
                    </span>
                  )}
                </div>
              ))}
            </div>
          ))}
        </div>
      </div>
      <ul className="sr-only">
        {nodes.map((n) => (
          <li key={n.id}>
            {TYPE_TEXT[n.type]}: {n.label}
            {typeof n.attrs.verdict === "string" ? `, verdict ${n.attrs.verdict}` : ""}
          </li>
        ))}
      </ul>
    </div>
  );
}
