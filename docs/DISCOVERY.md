# Discovery (D1–D8)

Everything below was observed on the live sandbox on **2026-09-30** (UTC). Each item gives the exact request,
timestamp and a short response excerpt. Nothing here is assumed. Where a fact could not be verified it is marked
**UNVERIFIED**.

- Sandbox base URL: `https://sandbox.hl7europe.eu/oneaquahealth/fhir`
- Context: the sandbox's DNS record disappeared on 2026-09-23 ([hl7-eu/oah#8](https://github.com/hl7-eu/oah/issues/8)). On 2026-09-30 it resolved again (`65.109.92.210`), and every request below returned HTTP 200 unless stated otherwise.
- Frozen copy: snapshot `2026-09-30T09-08-55Z` (manifest sha256 `49995f970d8dfa40d6af4b596a7fe6d730ca78ad732d7f948d005dea5f6a1af6`, 948 files, verified).

## D1. Metadata, FHIR version, hosted profiles

| Request | Time (UTC) | Result |
|---|---|---|
| `GET /metadata` | 08:36:48 | 200 in 2.6 s. `fhirVersion: 4.0.1`, `software: HAPI FHIR Server 8.2.0`, header `X-Powered-By: HAPI FHIR 8.2.0 REST Server (FHIR Server; FHIR 4.0.1/R4)` |
| `GET /StructureDefinition?_summary=count` | 08:37:16 | `total: 0`: **no profiles are hosted** |
| `GET /ValueSet`, `/CodeSystem`, `/ImplementationGuide` (`_count=200`) | 08:38 | 0 resources each |

The CapabilityStatement advertises `$validate`, `$get-resource-counts` and read/search on every R4 type. It also
advertises `update`, `patch` and `delete`: **the sandbox is writable by anyone**. Data Doctor never writes
(the client refuses any method except GET, and POST to `$validate`; see `tests/unit/test_fhir_client.py`).

The OAH IG website (`https://build.fhir.org/ig/hl7-eu/oah/`) returned **404** at 08:47. The IG source on GitHub
(`hl7-eu/oah`, commit `b907cf0869b5`, 2026-06-11) was used instead. It supplied FSH profiles, the temporary
CodeSystem, 468 example instance ids and the source CSVs (`knowledge/oah/sources.json`).

## D2. Search parameters and paging

| Request | Time | Result |
|---|---|---|
| `GET /Observation?_count=5` | 08:37:16 | 5 entries; `next` = `…/fhir?_getpages=55ea5a2f-…&_getpagesoffset=5&_count=5&_bundletype=searchset` (HAPI paging) |
| `GET /Observation?_count=200` (+ 2 `next` pages) | 08:37:29 | 450 unique ids over 3 pages; max page latency 2.08 s |
| `GET /Observation?_summary=count` | 08:37:15 | `total: 450` |
| `GET /$get-resource-counts` | 08:37:06 | `Observation 519, Location 28, Group 27, Library 18, Organization 8, Practitioner 13, Provenance 37, Device 6, …` |
| `GET /Library?description=Benevento&_count=100` | 09:27 | 12 entries, **all** Benevento. The previously reported quirk (non-Benevento libraries returned) **did not reproduce** today |
| `GET /Library?title:contains=Benevento` | 09:27 | 13 entries (includes `Library-Benevento-All`) |
| `GET /Observation?subject=Location/Loc-Almyros&_count=200` | 09:27 | 135 entries |
| `GET /Observation?code=http://snomed.info/sct\|703421000` | 09:27 | **HTTP 400** (Tomcat) unless `\|` is URL-encoded |
| `GET /Observation?_profile=…/observation-health-measure-oah&_summary=count` | 09:27 | `total: 141` |
| `GET /Observation?focus=Group/Group-OS-Female` | 09:27 | 9 entries |
| `GET /Group?characteristic-value=30525-0$ge35` (the IG's own example query in `_samples/queries/test.http`) | 09:27 | **0 entries** |

Decisions that follow from this:
- `$get-resource-counts` over-counts searchable resources (519 vs 450 Observations). We assume it includes deleted
  versions (**UNVERIFIED**). All counts in Data Doctor come from paged search.
- Data Doctor always pages through `Bundle.link[next]`, never trusts search filters, and filters client-side on
  `resourceType`. The client refuses `next` links that point to another host.

## D3. `$validate`

| Request | Time | Result |
|---|---|---|
| `GET /Observation/Obs-Almyros-TemperatureWater-2013/$validate` | 08:42:16 | 200, `severity: information`, **"No issues detected during validation"** |
| `POST /Observation/$validate` with `profile=…/observation-with-component-oah` | 08:42:17 | 200 with 2 × `error`: *"Profile reference … has not been checked because it could not be found, and the validator is set to not fetch unknown profiles"* |
| Snapshot: `GET …/$validate` for all 385 OAH-IG Observations | 09:08–09:11 | **0 with an error**. 244 report "No issues detected"; 141 (health measures) carry one best-practice *warning* only |

So `$validate` works, but only against base R4. It **cannot** check OAH profiles, and it accepts a water temperature of
198,000 °C. All 125 official observations that Data Doctor flags ERROR/CRITICAL passed the server's own validation
with zero errors (computed per run as `summary.server_validation`).

## D4. Resource counts; Location / Specimen / Group encoding

Paged search on 2026-09-30T09:08:55Z (snapshot): **Observation 450, Location 24, Group 27, Library 18,
Organization 5, Device 6, Provenance 31**. Specimen: 0.

Of these, the OAH IG defines 450 as examples. The other 111 (numeric ids such as `Observation/460`) were written to the
shared sandbox by other hackathon projects (profiles such as `…/streampulse/…` and `…/streamlink-oneaquahealth/…`).
Some of those third-party resources also declare OAH profiles. Data Doctor therefore scopes on the **IG example id
list**, not on `meta.profile`.

Encoding:
- **Location**: `LocationOah` with `position` (lat/long), `partOf` hierarchy (`Loc-Almyros → Location/Almyros`),
  SNOMED type `420531007` (river/stream) or `288520005` (city). All 12 `Loc-Benevento-NN` sites carry the
  **identical** position `41.129, 14.781`. `Loc-Nordre-Aker` has no position.
- **Group**: `GroupOah`, `type = person`, `actual = false`, no `member`, **no `quantity`** (cohort sizes are not
  published). Age is LOINC `30525-0` with `valueRange` in UCUM `a` (open-ended upper bound for "70-plus"/"All").
  Sex is LOINC `46098-0` with `administrative-gender`. `exclude = false` everywhere.
- **Specimen**: none on the server.
- The IG defines 18 site-specific Benevento cohorts (`Group-BN-BN1-All`, …, `Group-BN-BN3-Female-Age-35-74`) that
  are **absent** from the server. No live observation references them.

## D5. How health indicators are encoded (Oslo and Benevento)

- Code system `http://hl7.eu/fhir/ig/oah/CodeSystem/temporarySystem-oah-eu`. Oslo (Nordre Aker) uses
  `bmi-above-30`, `bmi-below-18/25/30`, `diabate-copd-cvd`, `no-diabate-copd-cvd`, `long-term-disease`,
  `no-long-term-disease` and `mental-health`. Benevento uses `obesity`, `cvd`, `diabetes`, `diabetes-treatment`,
  `high-blood-pression`, `high-blood-pression-treatment`, `hypertension`, `hypercholesterolemia-treatment` and
  `cholesterolemia-190/240`.
- Every value is `valueQuantity` in UCUM `%` with `effectivePeriod` 2024-01-01..2024-12-31.
  `subject` = Location, `focus` = Group.
- Oslo cohorts: All / Male / Female / six age bands (18–29 … 70+). Benevento cohorts: Male/Female 35–74, per site
  (BN1–BN3 → `Loc-Benevento-01..03`).
- In the IG CodeSystem every one of these concepts is *defined* as "% of people … — Cases of disease prevalence per
  100.000 inhabitants" (FSH lines 66–85). That is per-100 and per-100,000 in the same definition.
- `hypertension` is displayed as "% of people under treatment for hypertension" and
  `high-blood-pression-treatment` as "% of people under treatment for high blood pressure". Both appear in the source
  CSV with different values (e.g. BN1 women 23 % vs 33 %).

## D6. The anchor record

`GET /Observation/Obs-Almyros-TemperatureWater-2013` (via paged search, 08:37:29, and again in the snapshot at
09:08:55). Live values, verbatim:

| component (observation-statistics) | value | unit |
|---|---|---|
| average | 198000 | Cel |
| maximum | 211000 | Cel |
| minimum | 185000 | Cel |
| std-dev | 18385 | Cel |
| median | 19.8 | Cel |

`meta.versionId 1`, `lastUpdated 2025-11-15T15:39:36.751+00:00`, performer "Hellenic Government Chemical Service".
These **match the IG example**. The same values appear in the IG source file `_samples/crete/Almyros_gov_chem_analysis.csv`
line 125 (`2013;Temperature (water);°C;198000,00;211000,00;185000,00;18385,00;19,80`), so the inconsistency predates FHIR
conversion. Root cause: **unknown**. The pattern is systemic: 100 Almyros records have a median outside [min, max],
and 101 have a mean/median ratio ≥ 100 (most exactly 10⁴).

## D7. Rate limits, response times, stability

- 30 discovery requests plus ~1,350 snapshot/audit requests: no HTTP 429, no 5xx, no throttling headers.
- Latency: median 0.63 s, max 2.08 s (a 200-entry page). A full snapshot with 385 `$validate` calls took 2 min 19 s.
- Stability: the host was unreachable for about a week before discovery (D0). Data Doctor uses a 0.25 s polite delay,
  retries with exponential backoff (honouring `Retry-After`), a SQLite HTTP cache, and falls back automatically to
  the latest verified snapshot with a visible banner.
- The sandbox is writable, and third-party writes happened during the hackathon (e.g. `Observation/603…666`
  on 2026-09-29). Live results can therefore change between runs, and each run records its fetch time and resource hashes.

## D8. Licence and terms

- The IG source (`sushi-config.yaml`) has its licence line commented out (`# license: CC0-1.0`), and the repository
  has no LICENSE file. **Licence: UNVERIFIED.** We credit the OneAquaHealth Project and HL7 Europe everywhere, and we
  keep IG-derived files separate under `knowledge/oah/` with their commit and sha256.
- Hackathon rules (Devpost, read 2026-09-30): a public repository with code and documentation is required. We found
  no explicit AI-disclosure clause; we disclose anyway (see README).
- This is an independent project, not endorsed by OneAquaHealth, HL7 Europe or IEEE (see NOTICE).
