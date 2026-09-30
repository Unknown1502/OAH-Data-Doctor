import type { Finding } from "../lib/types";

const HEADER = ["Year", "Parameter", "Unit", "AVERAGE", "MAX", "MIN", "STDEV", "MEDIAN"];
const STAT_FOR: Record<string, string> = { AVERAGE: "average", MAX: "maximum", MIN: "minimum", STDEV: "std-dev", MEDIAN: "median" };

/** The IG source-file row a FHIR record was generated from, with each statistic matched against the FHIR value. */
export default function Lineage({ lineage }: { lineage: NonNullable<Finding["lineage"]> }) {
  const cells = lineage.raw_row.split(";");
  return (
    <div>
      <p className="m-0 max-w-[75ch] text-ink-2">{lineage.statement}</p>
      <div className="mt-3 overflow-x-auto rounded-lg border border-line">
        <table className="data">
          <caption className="sr-only">Source row {lineage.locator}</caption>
          <thead>
            <tr>
              {HEADER.map((h) => (
                <th key={h} scope="col">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            <tr>
              {HEADER.map((h, i) => {
                const stat = STAT_FOR[h];
                const matched = stat ? lineage.matches[stat] : undefined;
                return (
                  <td key={h} className="code">
                    {cells[i] ?? ""}
                    {matched !== undefined && (
                      <span className={`ml-1.5 text-xs ${matched ? "text-algae" : "text-cinnabar"}`}>
                        {matched ? "= FHIR" : "≠ FHIR"}
                      </span>
                    )}
                  </td>
                );
              })}
            </tr>
          </tbody>
        </table>
      </div>
      <p className="m-0 mt-2 text-sm text-ink-3">
        <a className="text-karst underline underline-offset-2" href={lineage.source} target="_blank" rel="noreferrer">
          {lineage.locator}
        </a>{" "}
        in the OneAquaHealth IG source repository.
      </p>
    </div>
  );
}
