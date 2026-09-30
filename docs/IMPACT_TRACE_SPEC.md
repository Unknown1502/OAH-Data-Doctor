# Impact trace specification

**Rule: report only the impact the graph actually computes.** Never "affects N analyses" by estimate.

## Nodes

| Type | Created from | Meaning |
|---|---|---|
| observation, location, group | the dataset | records |
| library | `Library.content` membership | published data-set collections containing the record |
| profile | library × indicator (for members with a known indicator) | the per-indicator summary shown in the researcher report ("what this data can support") |
| series | site × indicator × statistic (average, median), annual, ≥ 3 points | the annual series used by trend claims |
| comparison | `knowledge/analyses/catalog.yaml` + comparisons users ran (persisted) + comparisons embedded in claims | the comparability engine's outputs |
| claim | catalog + claims users ran (persisted) | the guardrail's outputs |

## Edges (downstream, "is consumed by")

observation → library (member-of), observation → profile (summarised-in), observation → series (point-of),
observation → comparison (input-to), observation → claim (evidence-for), location/group → observation, series and comparison
(context-of), comparison → claim and series → claim (basis-of).

## Impact of a finding

Start nodes are the finding's resource plus its related resources. For terminology-level findings (CodeSystem) only the related
records are used. A breadth-first traversal collects every reachable library, profile, series, comparison and claim, with depth
and the node it came through. The UI draws the reachable nodes and the traversed edges. The statement is generated from the counts.

## Guarantees (tested)

- For the anchor record the trace lists exactly the two Almyros temperature trend claims and the 2013-vs-2014 comparison, plus
  1 library and 2 series (`test_trace_of_anchor_lists_exactly_the_computed_analyses`).
- Removing the comparison partner from the data removes the comparison from the trace, and the series shrink to 5 points
  (`test_trace_counts_change_when_data_change`).
- A comparison run by a user appears in the trace of its inputs (`test_compare_and_user_analysis_enters_the_trace`).
