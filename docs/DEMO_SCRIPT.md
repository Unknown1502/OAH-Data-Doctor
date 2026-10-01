# Demo script (about 4 minutes)

One story, in this order: **valid structure → scientific problem → proof → downstream impact → comparability → claim
safety → report.** Start with the contradiction. No team introduction, logo, login, architecture or AI model on screen.

Numbers in the "Say" column are what the screens showed on 2026-10-01 (live audit and snapshot gave the same results). They
are computed on every scan, so **read them from the screen**; if a number differs, say what the screen says.

## Before recording

1. Start the app with the language model off, so nothing on screen depends on a model, a network or a remote service:
   - **Primary (reliable take):** `DD_SOURCE=snapshot DD_LLM_PROVIDER=none python tasks.py run`. The top bar says
     *Snapshot · Captured 30 Sept 2026, 09:08 UTC · sha256 verified*. Works without internet.
   - **Secondary (live credibility, when the sandbox is up):** `DD_SOURCE=live DD_LLM_PROVIDER=none python tasks.py run`.
     The top bar says *Live · OAH FHIR sandbox · fetched N min ago* once the live audit completes. If the sandbox is
     unreachable, the app keeps showing the verified snapshot, labelled *Snapshot*, and the strip under the top bar says
     *Audit failed … Failed: Connecting to the FHIR server*. Then record with the primary configuration.
   - PowerShell: `$env:DD_SOURCE="snapshot"; $env:DD_LLM_PROVIDER="none"; python tasks.py run`.
   The sidebar then shows *Language model: off*.
2. Browser at http://127.0.0.1:8321, window 1440 × 900, zoom 100 %, dark theme. Wait until the strip under the top bar
   says "Audit complete", then select **Dismiss**.
3. Open a second tab on the scale finding of the same record: **Findings** → Rule **SEM-SCALE-001** → *Mean and median
   differ by orders of magnitude* for *Water temperature, Almyros monitoring reach, 2013*. Go back to the first tab.

## Script

| Time | Screen | Say | Do |
|---|---|---|---|
| 0:00–0:20 | **Data health** (`/`), top | "This OneAquaHealth record passes FHIR validation. Data Doctor finds a scientific consistency problem: the 2013 annual water temperature of the Almyros stream in Crete is published as 198,000 degrees Celsius." | Point at the two verdict panels: *✓ Pass, No issues detected during validation* and *◆ Critical, 4 findings*; then at *198,000 °C* in the headline |
| 0:20–0:55 | **Finding** SEM-STAT-001, *Evidence chain* step 1; second tab (SEM-SCALE-001), step 1 | "These are the published values. Minimum 185,000, maximum 211,000, median 19.8. A median is the middle value of the same data: it can never be below its own minimum. And the average is 198,000 degrees, against that median of 19.8." | Select **Open the evidence for this record**; point at step 1 *Observed* and step 4 *19.8 < 185,000, does not hold*. Switch to the second tab: point at *average 198,000 °C* and *median 19.8 °C* |
| 0:55–1:20 | Second tab, steps 2–6 | "198,000 divided by 19.8 is 10,000: exactly ten to the fourth. This is a reproducible calculation from the source values. A power of ten fits a scale error, but that is a hypothesis. Root cause remains unknown, and nothing is corrected." | Point at *average / median = 198,000 / 19.8 = 10,000*, *exactly 10⁴*, *Possible explanations, not verified*, *Root cause: UNKNOWN* |
| 1:20–1:55 | Same page, **Evidence** | "Every finding is inspectable: the resource, the exact field and FHIRPath, the rule and its version, the source, and when it was retrieved, down to the record's hash. Here is the record exactly as the server returned it, with the flagged fields highlighted. The same numbers are in the Implementation Guide's own source spreadsheet." | Scroll to *Evidence*: the FHIRPath table, then *Resource, Rule, Source, Retrieved, Record sha256*; select **View raw resource**, then close it; scroll to *Where these values first appear* (line 125) |
| 1:55–2:25 | Same page, **What this affects** | "What does this record affect? Within the analyses Data Doctor computes, it feeds one data set, one indicator profile, two annual series, one comparison and two claims. The trace shows only dependencies Data Doctor itself establishes; nothing is estimated." | Scroll to *What this affects*; select the claim box *median water temperature …*; point at *Depends on* and *Used by* |
| 2:25–3:00 | **Compare** (`/compare`) | "Can obesity in Benevento be compared with Oslo? Women aged 35 to 74 against adults aged 18 to 29. Unit, period and aggregation are direct; measure and method are conditional; population is a hard blocker: these are different people. What can still be compared safely: the Oslo cohorts whose ages overlap. And Almyros 2013 against 2014 is blocked until the records are reviewed." | Select the chip *Obesity prevalence: Benevento monitoring site 01, Female, 35-74 y, 2024 vs Nordre Aker, 18-29 y, 2024*; point down the *Comparability matrix* (*hard blocker* under Population), then *What you can do instead*. Select the chip *Water temperature: Almyros monitoring reach, 2013 vs … 2014* |
| 3:00–3:35 | **Check a claim** (`/claims`) | "Now a researcher's sentence. 'PM10 at Benevento site 04 exceeded the WHO guideline in 2018': supported; the evidence reaches comparison. 'PM2.5 causes cardiovascular disease in Benevento': unsupported; the claim needs causation, and the evidence reaches description. Here is what you can safely say instead." | Select the example *PM10 at Benevento site 04 exceeded the WHO guideline in 2018*; point at *Supported* and the evidence ladder. Select *PM2.5 causes cardiovascular disease in Benevento*; point at the ladder and *What you can safely say* |
| 3:35–4:00 | **Report** (`/report`) | "The report separates what was observed, what was derived, what is only a hypothesis and what is unknown, with provenance and every rule applied. It runs offline from a verified snapshot and gives the same result. Data Doctor does not replace FHIR validation. It adds an evidence integrity layer above it, showing whether scientifically meaningful conclusions can safely be drawn from the data." | Point at the header (*Dataset, Source, Mode, Audit timestamp*), the *Observed / Derived / Inferred / Unknown* rows of *1 Executive finding*, then *7 Provenance* |

Narration is about 370 words: about 2 minutes 40 seconds of speech at 140 words a minute, plus about 1 minute 15 seconds
of clicking, scrolling, tab switches and pauses, so about 4 minutes. **Not yet rehearsed with a stopwatch**: time one take;
if it runs long, shorten the 1:20–1:55 evidence segment first (skip the raw-resource drawer).

## Words to use and to avoid

- Say "flagged", "cannot all be right as published", "root cause unknown", "consistent with a scale error (hypothesis)".
- Never say "the correct value is 19.8 °C", "the data is corrupted", "a typo", or that Data Doctor "fixed" anything.
- Never say "AI found" or "AI decided": no model decides a finding or a verdict. Keep the language model off in the recording.

## Fallback

- **Sandbox down:** the app opens on the latest verified snapshot and says so in the top bar ("Snapshot", capture time,
  "sha256 verified") with a banner. The script is unchanged; say "we are on the verified snapshot from <date>".
- **Browser fails:** `python tools/oah_audit.py audit --source snapshot` prints the full summary (findings by rule, the
  anchor's values, 125/125 server-valid); `/api/reports/report.html` opens the report.
- **Screenshots:** `docs/img/`.
