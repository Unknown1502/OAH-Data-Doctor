import { useEffect, useId, useRef, useState, type ReactNode } from "react";

type Path = (string | number)[];
interface Line {
  depth: number;
  path: Path;
  content: ReactNode;
}

/** "Observation.component[2].valueQuantity" -> ["component", 2, "valueQuantity"] (the resource type is dropped). */
export function parseFhirPath(p: string): Path {
  const out: Path = [];
  for (const seg of p.split(".").slice(1)) {
    const m = /^([^[\]]+)((?:\[\d+\])*)$/.exec(seg);
    if (!m) return out;
    out.push(m[1]);
    for (const idx of m[2].matchAll(/\[(\d+)\]/g)) out.push(Number(idx[1]));
  }
  return out;
}

const startsWith = (path: Path, prefix: Path) => prefix.length > 0 && prefix.every((p, i) => path[i] === p);

function scalar(v: unknown): ReactNode {
  if (typeof v === "string") return <span className="text-algae">{JSON.stringify(v)}</span>;
  if (typeof v === "number") return <span className="text-karst">{String(v)}</span>;
  return <span className="text-ochre">{String(v)}</span>;
}

/** JSON as lines, each knowing its path, so the lines a finding points to can be highlighted. */
function toLines(v: unknown, path: Path, depth: number, key: string | null, comma: boolean): Line[] {
  const k = key !== null ? <><span className="text-ink">{JSON.stringify(key)}</span>: </> : null;
  const c = comma ? "," : "";
  if (Array.isArray(v) || (v && typeof v === "object")) {
    const entries: [string | number, unknown][] = Array.isArray(v) ? v.map((x, i) => [i, x]) : Object.entries(v as Record<string, unknown>);
    const [open, close] = Array.isArray(v) ? ["[", "]"] : ["{", "}"];
    if (!entries.length) return [{ depth, path, content: <>{k}{open}{close}{c}</> }];
    return [
      { depth, path, content: <>{k}{open}</> },
      ...entries.flatMap(([ck, cv], i) => toLines(cv, [...path, ck], depth + 1, Array.isArray(v) ? null : String(ck), i < entries.length - 1)),
      { depth, path, content: <>{close}{c}</> },
    ];
  }
  return [{ depth, path, content: <>{k}{scalar(v)}{c}</> }];
}

/**
 * The record exactly as served, as evidence: line numbers, and the fields the finding refers to highlighted and scrolled
 * into view. A side drawer, so the investigation underneath keeps its place; Escape closes it.
 */
export default function RawResourceDrawer({ open, onClose, title, resource, highlight, source, children }: {
  open: boolean;
  onClose: () => void;
  title: string;
  resource: unknown;
  highlight: string[];
  source: ReactNode;
  children?: ReactNode;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const uid = useId();
  const [copied, setCopied] = useState(false);
  const targets = highlight.map(parseFhirPath).filter((p) => p.length);
  const lines = toLines(resource, [], 0, null, false);
  const hit = (l: Line) => targets.some((t) => startsWith(l.path, t));
  const flagged = lines.filter(hit).length;

  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    if (open && !d.open) {
      d.showModal();
      d.querySelector<HTMLElement>("[data-hit='true']")?.scrollIntoView({ block: "center" });
    } else if (!open && d.open) d.close();
  }, [open]);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(JSON.stringify(resource, null, 2));
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      setCopied(false);
    }
  };

  return (
    <dialog
      ref={ref}
      onClose={onClose}
      aria-labelledby={`${uid}-h`}
      className="drawer m-0 ml-auto h-dvh max-h-dvh w-[min(46rem,100vw)] max-w-full border-0 border-l border-line bg-panel p-0 text-ink"
    >
      <div className="flex h-full flex-col">
        <div className="flex items-start justify-between gap-3 border-b border-line px-5 py-4">
          <div className="min-w-0">
            <h2 id={`${uid}-h`} className="m-0 break-all text-lg font-bold">{title}</h2>
            <div className="mt-1 text-sm text-ink-2">{source}</div>
          </div>
          <button type="button" onClick={() => ref.current?.close()} aria-label="Close the raw resource" className="rounded-md p-1 text-ink-3 hover:bg-sunk hover:text-ink">
            <svg viewBox="0 0 16 16" className="h-5 w-5" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round">
              <path d="m4 4 8 8M12 4l-8 8" />
            </svg>
          </button>
        </div>
        <div className="flex flex-wrap items-center gap-3 border-b border-line px-5 py-2.5 text-sm">
          <span className="text-ink-2">
            {open && flagged ? (
              <>
                <span className="mr-1 inline-block h-3 w-3 rounded-sm bg-cinnabar-soft align-[-2px] ring-1 ring-cinnabar/60" aria-hidden="true" />
                Highlighted: the fields this finding refers to ({highlight.join("; ")})
              </>
            ) : (
              "Exactly as served by the FHIR server."
            )}
          </span>
          <button type="button" onClick={copy} className="ml-auto rounded-md border border-line-strong px-2.5 py-1 font-semibold hover:bg-sunk">
            {copied ? "Copied" : "Copy JSON"}
          </button>
        </div>
        {children}
        {open && (
        <div className="min-h-0 flex-1 overflow-auto" tabIndex={0} role="region" aria-label="Resource JSON">
          <div className="code py-2 text-[0.8rem] leading-[1.6]">
            {lines.map((l, i) => {
              const h = hit(l);
              return (
                <div key={i} data-hit={h || undefined} className={`flex ${h ? "bg-cinnabar-soft" : ""}`}>
                  <span aria-hidden="true" className={`w-12 shrink-0 select-none border-r pr-2 text-right text-ink-3 ${h ? "border-cinnabar" : "border-line"}`}>{i + 1}</span>
                  <span className="whitespace-pre" style={{ paddingLeft: `${0.75 + l.depth * 1.1}rem` }}>{l.content}</span>
                  {h && <span className="sr-only"> (flagged)</span>}
                </div>
              );
            })}
          </div>
        </div>
        )}
      </div>
    </dialog>
  );
}
