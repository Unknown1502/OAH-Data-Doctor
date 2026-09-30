import type { ClaimRung } from "../lib/types";

const STYLE: Record<ClaimRung["status"], { fill: string; text: string; glyph: string; word: string }> = {
  supported: { fill: "bg-algae border-algae", text: "text-algae", glyph: "✓", word: "supported" },
  conditional: { fill: "bg-sulfur border-sulfur", text: "text-sulfur", glyph: "≈", word: "with caveats" },
  unsupported: { fill: "bg-slate/40 border-slate", text: "text-slate", glyph: "✕", word: "not supported" },
  blocked: { fill: "bg-cinnabar border-cinnabar", text: "text-cinnabar", glyph: "⊘", word: "blocked by broken records" },
  not_claimed: { fill: "bg-transparent border-line-strong border-dashed", text: "text-ink-3", glyph: "–", word: "not claimed" },
};

/**
 * How far the evidence reaches: Observation, Description, Comparison, Association, Causation. Each step restates the
 * deterministic verdict for that rung; "your claim" marks the rung the claim needs, "evidence reaches here" the highest
 * rung the data supports.
 */
export default function EvidenceLadder({ rungs, upTo }: { rungs: ClaimRung[]; upTo: string | null }) {
  if (!rungs.length) return null;
  const claimed = rungs.find((r) => r.claimed);
  return (
    <figure className="m-0">
      <figcaption className="text-ink-2">
        {upTo ? (
          <>
            The evidence reaches <strong className="text-ink">{upTo}</strong>
            {claimed && claimed.label !== upTo ? <>; your claim needs <strong className="text-ink">{claimed.label}</strong>.</> : "."}
          </>
        ) : (
          <>The evidence does not support any rung{claimed ? <>; your claim needs <strong className="text-ink">{claimed.label}</strong>.</> : "."}</>
        )}
      </figcaption>
      <ol className="m-0 mt-4 grid list-none grid-cols-5 items-end gap-2 p-0 sm:gap-3" aria-label="Evidence ladder">
        {rungs.map((r, i) => {
          const s = STYLE[r.status];
          return (
            <li key={r.level} className="flex min-w-0 flex-col items-center text-center">
              <span className={`mb-1 h-5 text-xs font-semibold ${r.claimed ? "text-karst" : "text-transparent"}`} aria-hidden={!r.claimed}>
                {r.claimed ? "your claim" : "."}
              </span>
              <span
                aria-hidden="true"
                className={`flex w-full items-start justify-center rounded-t-md border-2 pt-1.5 text-lg font-bold ${s.fill} ${r.status === "not_claimed" ? s.text : "text-chalk"} ${r.claimed ? "ring-2 ring-karst ring-offset-2 ring-offset-chalk" : ""}`}
                style={{ height: `${2.4 + i * 1.3}rem` }}
              >
                {s.glyph}
              </span>
              <span className="flex h-[3.6rem] flex-col items-center">
                <span className="mt-1.5 text-sm font-semibold leading-tight">{r.label}</span>
                <span className={`text-xs leading-tight ${s.text}`}>{s.word}</span>
                {upTo === r.label && <span className="mt-0.5 text-[0.7rem] font-semibold leading-tight text-algae">evidence reaches here</span>}
              </span>
            </li>
          );
        })}
      </ol>
      <ul className="m-0 mt-4 list-none space-y-1.5 p-0 text-sm">
        {rungs.filter((r) => r.why).map((r) => (
          <li key={r.level} className="flex gap-2">
            <span className={`w-4 shrink-0 text-center ${STYLE[r.status].text}`} aria-hidden="true">{STYLE[r.status].glyph}</span>
            <span>
              <strong>{r.label}</strong>
              <span className="sr-only"> ({STYLE[r.status].word})</span>: <span className="text-ink-2">{r.why}</span>
            </span>
          </li>
        ))}
      </ul>
    </figure>
  );
}
