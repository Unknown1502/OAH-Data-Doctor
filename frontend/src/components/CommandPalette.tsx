import { useEffect, useId, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../lib/api";
import type { FindingCompact, LocationItem, ObservationItem, RuleSpec } from "../lib/types";

export interface Command {
  label: string;
  hint?: string;
  keywords?: string;
  run: () => void;
}

interface Item {
  group: string;
  label: string;
  hint: string;
  keywords: string;
  run: () => void;
}

const GROUP_ORDER = ["Commands", "Pages", "Findings", "Records", "Places", "Rules"];

/**
 * Ctrl+K: go anywhere, search everything that was actually audited (findings, records, places, rules) and run commands.
 * The index is built from the API when the palette opens; nothing is invented.
 */
export default function CommandPalette({ open, onClose, commands, pages }: {
  open: boolean;
  onClose: () => void;
  commands: Command[];
  pages: { to: string; label: string }[];
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const input = useRef<HTMLInputElement>(null);
  const uid = useId();
  const nav = useNavigate();
  const [q, setQ] = useState("");
  const [active, setActive] = useState(0);
  const [data, setData] = useState<{ findings: FindingCompact[]; obs: ObservationItem[]; locs: LocationItem[]; rules: RuleSpec[] } | null>(null);
  const [loadErr, setLoadErr] = useState<string | null>(null);

  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    if (open && !d.open) {
      d.showModal();
      setQ("");
      setActive(0);
      input.current?.focus();
      Promise.all([
        api<{ items: FindingCompact[] }>("/findings?limit=2000"),
        api<{ items: ObservationItem[] }>("/observations"),
        api<{ items: LocationItem[] }>("/locations"),
        api<RuleSpec[]>("/rules"),
      ]).then(([f, o, l, r]) => setData({ findings: f.items, obs: o.items, locs: l.items, rules: r }), (e: Error) => setLoadErr(e.message));
    } else if (!open && d.open) d.close();
  }, [open]);

  const go = (to: string) => () => {
    ref.current?.close();
    nav(to);
  };

  const items = useMemo<Item[]>(() => {
    const out: Item[] = [
      ...commands.map((c) => ({ group: "Commands", label: c.label, hint: c.hint ?? "", keywords: c.keywords ?? "", run: () => { ref.current?.close(); c.run(); } })),
      ...pages.map((p) => ({ group: "Pages", label: p.label, hint: p.to, keywords: "", run: go(p.to) })),
    ];
    if (data) {
      out.push(...data.findings.map((f) => ({ group: "Findings", label: `${f.rule_id}: ${f.resource.display ?? f.resource.resource_id}`, hint: f.severity.toLowerCase(),
        keywords: `${f.id} ${f.title} ${f.resource.resource_id} ${f.summary}`, run: go(`/findings/${encodeURIComponent(f.id)}`) })));
      out.push(...data.obs.map((o) => ({ group: "Records", label: `${o.indicator}, ${o.location ?? "no site"}${o.year ? `, ${o.year}` : ""}${o.cohort ? `, ${o.cohort}` : ""}`,
        hint: o.worst ? o.worst.toLowerCase() : "no problems", keywords: `${o.id} ${o.indicator_key ?? ""}`,
        run: go(o.worst_finding ? `/findings/${encodeURIComponent(o.worst_finding)}` : `/data?q=${encodeURIComponent(o.id)}`) })));
      out.push(...data.locs.map((l) => ({ group: "Places", label: l.name ?? l.id, hint: `${l.observations} records`, keywords: l.id, run: go(`/data?place=${encodeURIComponent(l.id)}`) })));
      out.push(...data.rules.map((r) => ({ group: "Rules", label: `${r.id}: ${r.title}`, hint: `${r.findings ?? 0} findings`, keywords: r.category, run: go(`/findings?rule=${r.id}`) })));
    }
    return out;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data, commands, pages]);

  const terms = q.toLowerCase().split(/\s+/).filter(Boolean);
  const matches = (terms.length
    ? items.filter((it) => terms.every((t) => `${it.label} ${it.keywords} ${it.hint}`.toLowerCase().includes(t)))
    : items.filter((it) => it.group === "Commands" || it.group === "Pages")
  )
    .sort((a, b) => GROUP_ORDER.indexOf(a.group) - GROUP_ORDER.indexOf(b.group))
    .slice(0, 40);
  const current = Math.min(active, Math.max(0, matches.length - 1));

  const onKey = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActive((a) => Math.min(matches.length - 1, a + 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((a) => Math.max(0, a - 1));
    } else if (e.key === "Enter" && matches[current]) {
      e.preventDefault();
      matches[current].run();
    }
  };

  useEffect(() => {
    document.getElementById(`${uid}-o-${current}`)?.scrollIntoView({ block: "nearest" });
  }, [current, uid]);

  let lastGroup = "";
  return (
    <dialog ref={ref} onClose={onClose} aria-label="Search and commands"
      className="mx-auto mt-[12vh] w-[min(40rem,calc(100vw-2rem))] rounded-xl border border-line bg-panel p-0 text-ink">
      <div className="flex items-center gap-2 border-b border-line px-4">
        <svg viewBox="0 0 16 16" className="h-4 w-4 shrink-0 text-ink-3" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.6">
          <circle cx="7" cy="7" r="4.5" />
          <path d="m10.5 10.5 3.5 3.5" strokeLinecap="round" />
        </svg>
        <input
          ref={input}
          role="combobox"
          aria-expanded="true"
          aria-controls={`${uid}-list`}
          aria-activedescendant={matches[current] ? `${uid}-o-${current}` : undefined}
          aria-label="Search findings, records, places, rules, pages and commands"
          value={q}
          onChange={(e) => {
            setQ(e.target.value);
            setActive(0);
          }}
          onKeyDown={onKey}
          placeholder="Search findings, records, places, rules, or type a command"
          className="w-full bg-transparent py-3.5 text-[1.02rem] outline-none"
          autoComplete="off"
          spellCheck={false}
        />
        <kbd className="readout rounded border border-line px-1.5 text-xs text-ink-3">Esc</kbd>
      </div>
      <ul id={`${uid}-list`} role="listbox" aria-label="Results" className="m-0 max-h-[55vh] list-none overflow-y-auto p-2">
        {matches.map((it, i) => {
          const header = it.group !== lastGroup;
          lastGroup = it.group;
          return (
            <li key={`${it.group}-${it.label}-${i}`} role="presentation">
              {header && <p className="m-0 px-2 pb-1 pt-2 text-xs font-semibold text-ink-3" aria-hidden="true">{it.group}</p>}
              <div
                id={`${uid}-o-${i}`}
                role="option"
                aria-selected={i === current}
                onMouseMove={() => setActive(i)}
                onClick={() => it.run()}
                className={`flex cursor-pointer items-baseline justify-between gap-3 rounded-md px-2.5 py-2 ${i === current ? "bg-karst-soft text-ink" : "text-ink-2"}`}
              >
                <span className="min-w-0 truncate">{it.label}</span>
                <span className="shrink-0 text-xs text-ink-3">{it.hint}</span>
              </div>
            </li>
          );
        })}
        {!matches.length && (
          <li className="px-3 py-6 text-center text-ink-2">
            {data ? `Nothing in this audit matches "${q}".` : loadErr ? `Could not load the search index (${loadErr}).` : "Loading the search index…"}
          </li>
        )}
      </ul>
      <p className="m-0 border-t border-line px-4 py-2 text-xs text-ink-3">
        Arrow keys to move, Enter to open. Searches only what this audit read and found.
      </p>
    </dialog>
  );
}
