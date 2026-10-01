# Demo script (about 4 minutes)

One story, in this order: **valid structure → scientific problem → proof → downstream impact → comparability → claim
safety → report.** Start with the contradiction. No team introduction, logo, login, architecture or AI model on screen.

Numbers in the "Say" column are what the screens showed on 2026-10-01 (live audit and snapshot gave the same results). They
are computed on every scan, so **read them from the screen**; if a number differs, say what the screen says.

## Before recording

1. Start with the language model off, so nothing on screen depends on it:
   `DD_LLM_PROVIDER=none python tasks.py run` (live, falls back to the snapshot automatically), or
   `DD_SOURCE=snapshot DD_LLM_PROVIDER=none python tasks.py run` for a guaranteed offline take.
2. Browser at http://127.0.0.1:8321, window 1440 × 900, zoom 100 %, dark theme. Wait until the strip under the top bar
   says "Audit complete", then select **Dismiss**.
3. Open a second tab on the scale finding of the same record: **Findings** → Rule **SEM-SCALE-001** → *Mean and median
   differ by orders of magnitude* for *Water temperature, Almyros monitoring reach, 2013*. Go back to the first tab.

## Script

| Time | Screen | Say | Do |
|---|---|---|---|
| 0:00–0:20 | **Data health** (`/`), top | "This is real OneAquaHealth data: the 2013 annual water temperature of the Almyros stream in Crete. Its average is 198,000 degrees Celsius. The FHIR server's own validator: no issues detected. Data Doctor: four findings on the same record. FHIR checks the shape. We check whether the evidence can be true." | Point at the headline, then at the two verdict panels: *FHIR server's own validator ✓ No issues detected during validation* and *OAH Data Doctor: 4 findings* |
| 0:20–1:00 | **Data health**, *Dataset status*; then the **finding** page | "And it is not one record. 260 of 385 official records can be used as published. 125 are flagged, and all 125 pass the server's validation. Let's open the evidence. Minimum 185,000, maximum 211,000, and a median of 19.8. A median is the middle value of the same data. It can never be below its own minimum." | Scroll to *Dataset status*; point at *Flagged, yet server-valid: 125 of 125*. Scroll back up, select **Open the evidence for this record**. Point at step 1 *Observed* of the evidence chain |
| 1:00–1:40 | **Finding** (SEM-STAT-001), *Evidence chain*; second tab (SEM-SCALE-001) | "Minimum divided by median: 9,343. The rule says minimum ≤ median ≤ maximum; here 19.8 is below 185,000, so it does not hold. Root cause: unknown. We never guess, and we never correct a value. On the same record, 198,000 divided by 19.8 is exactly 10,000, ten to the fourth. That fits a scale error, and we label it a hypothesis. The same numbers are in the Implementation Guide's source spreadsheet: the problem predates FHIR." | Point at steps 2–6. Switch to the second tab: point at *average / median = 198,000 / 19.8 = 10,000* and *exactly 10⁴*, then *Possible explanations, not verified*. Scroll to *Where these values first appear* (line 125) |
| 1:40–2:10 | Same page, **What this affects** | "What does this record contaminate? Within the analyses Data Doctor computes, it feeds one data set, one indicator profile, two annual series, one comparison and two published claims. We show only dependencies we actually compute. Nothing is estimated." | Scroll to *What this affects*; select the claim box *median water temperature …*; point at *Depends on* and *Used by* |
| 2:10–2:50 | **Compare** (`/compare`) | "Can obesity in Benevento be compared with Oslo? Women aged 35 to 74 against adults aged 18 to 29. Unit, period and aggregation are direct; measure and method are conditional; population is not comparable. These are different people. What you can do instead: compare with the Oslo cohorts whose ages overlap. And Almyros 2013 against 2014: comparable in principle, but blocked until the data owner reviews the records." | Select the chip *Obesity prevalence: Benevento monitoring site 01, Female, 35-74 y, 2024 vs Nordre Aker, 18-29 y, 2024*; point down the *Comparability matrix*, then *What you can do instead*. Select the chip *Water temperature: Almyros monitoring reach, 2013 vs … 2014* → *Blocked by integrity findings* |
| 2:50–3:30 | **Check a claim** (`/claims`) | "Now a researcher's sentence. 'Water temperature at Almyros increased from 2013 to 2020.' Blocked: the series is built on flagged records, so no safe trend statement can be made yet. 'PM2.5 causes cardiovascular disease in Benevento.' Unsupported: the evidence reaches description; the claim needs causation. And here is what you can safely say instead." | Select the example *Water temperature at Almyros increased from 2013 to 2020*; point at *Blocked* and *What you can safely say*. Select *PM2.5 causes cardiovascular disease in Benevento*; point at the evidence ladder and *What you can safely say* |
| 3:30–4:00 | **Report** (`/report`) | "Everything ends in an evidence integrity report: dataset, source, live or snapshot, audit time, every rule applied, and provenance down to the record hash. It exports as FHIR OperationOutcome, validated against R4. The same audit runs offline from a sha256-verified snapshot and gives the same findings. Deterministic rules, read-only, no AI deciding anything. FHIR tells you the data is well formed. Data Doctor tells you whether it makes scientific sense." | Point at the header (*Dataset, Source, Mode, Audit timestamp*), the contents list, then scroll to *7 Provenance* and *9 Technical appendix* |

Narration is about 410 words: about 3 minutes of speech at 140 words a minute, plus about 45 seconds of clicking, scrolling
and pauses, so about 4 minutes. **Not yet rehearsed with a stopwatch**: time one take and trim the 1:00–1:40 segment first if it
runs long.

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
