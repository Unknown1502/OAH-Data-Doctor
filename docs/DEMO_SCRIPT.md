# Demo script (3–5 minutes)

Setup: `python tasks.py run` (or `DD_SOURCE=snapshot` for a guaranteed offline demo). Browser at http://127.0.0.1:8321, 1440 px
wide, light theme. Numbers on screen are computed; read them from the screen, do not memorise them.

| Time | Screen | Say | Do |
|---|---|---|---|
| 0:00 | Data health | "This is a real record from the OneAquaHealth FHIR sandbox: a 2013 annual water temperature of 198,000 °C. The server's own FHIR validator says 'No issues detected'. FHIR checks that data has the right shape. Data Doctor checks whether it can be true." | Point at the two verdicts |
| 0:25 | Magnitude ruler | "On a log scale the median, 19.8 °C, sits four decades away from the minimum, mean and maximum. Only the median is physically possible. A median can never lie outside its own minimum and maximum." | Hover the ruler |
| 0:45 | Readout strip | "Across the sandbox, every official observation passes the server's validation. Data Doctor flags this many as unsafe to use as published." | Point at the readouts |
| 1:00 | Finding detail | "Every finding shows the rule, the exact FHIRPath, the values, the constraint, and a confidence. Root cause: unknown. We never guess why." | Open the evidence |
| 1:20 | Lineage | "The same numbers are already in the Implementation Guide's source spreadsheet, row by row. The problem predates FHIR conversion, which is exactly what the data owner needs to know." | Scroll to "Where these values first appear" |
| 1:40 | Impact trace | "What would this record contaminate? The trace lists exactly which data sets, annual series, comparisons and claims use it. We only show what we actually compute; we never estimate." | Scroll to the trace |
| 2:00 | Findings | "It is not one record. Filter by critical: impossible temperatures, pH values above 14, conductivity above that of brine. And some things FHIR can never know: PM2.5 above PM10 at the same site, although PM2.5 is part of PM10." | Click Critical; search "PM2.5" |
| 2:30 | Compare | "Can we compare obesity in Benevento with Oslo? Women aged 35 to 74 against adults aged 18 to 29: not comparable. These are different people. Here are the Oslo cohorts that do overlap." | Pick the example chip |
| 3:00 | Check a claim | "A researcher writes: water temperature at Almyros increased from 2013 to 2020. Blocked: every point in the series is broken. PM10 at Benevento site 04 exceeded the WHO guideline in 2018: supported, with the exact ratio and a caveat on data coverage. And 'PM2.5 causes cardiovascular disease': unsupported, and here is what you can say instead." | Use the example chips |
| 3:40 | Report | "Everything exports as FHIR OperationOutcome, validated against R4, plus a researcher report and a table of what this data can and cannot support." | Open the HTML report |
| 4:00 | Close | "Deterministic rules, no AI deciding anything, read-only access, every number computed, live or snapshot always labelled. Data Doctor: FHIR tells you whether data is shaped correctly; we tell you whether it makes sense." | Back to Data health |

## Fallback path

- If the sandbox is down: the app shows the latest verified snapshot with a banner, and the script is unchanged. Say
  "we are on the verified snapshot from <date>".
- If the browser fails: `python tools/oah_audit.py audit --source snapshot` prints the full summary; open
  `/api/reports/report.html` or `docs/GATE0_REPORT.md`.
- Pre-recorded screenshots: `docs/img/`.
