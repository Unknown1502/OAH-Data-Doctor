# 07 — Demo and submission

## Submission requirements (Devpost, re-read 2026-10-01)

Source: https://oneaquahealth-ieee-hackathon.devpost.com/ (overview, rules and updates pages).

- **Deadline:** 2026-10-04, 21:00 PDT (extended from 30 September; the rules page still shows the old date, the updates page
  announces the extension).
- **Required:** track alignment statement; project description (problem, solution, target users, expected impact); demo video
  of 3–5 minutes; public code repository with source and documentation; working prototype, mockup or proof of concept.
- **Rules:** original work built during the hackathon period; no copyright, licensing or third-party IP violations; every
  participant registered on Devpost. No explicit AI-disclosure clause was found; we disclose anyway.
- **Eligibility:** the official OneAquaHealth hackathon page (https://www.oneaquahealth.eu/oneaquahealth-ieee-global-hackathon/,
  read 2026-10-01) says "Form a team or participate individually", and the latest Devpost announcement says "You can
  participate individually or as part of a team": **individual participation is not a blocker.** The Devpost overview still
  lists "Students only"; the official page and the rules page state no student condition. **Student eligibility: ORGANIZER
  CONFIRMATION REQUIRED** (or the owner confirms student status).
- **Judging:** impact and alignment with the OneAquaHealth mission 30 %, innovation 20 %, technical implementation 20 %,
  usability 15 %, feasibility and scalability 15 % (rules page; 1–10 per criterion, weighted).

## Publishing the data: answered

**The organisers allowed it.** Asked on the Devpost discussion board
([thread](https://oneaquahealth-ieee-hackathon.devpost.com/forum_topics/45406-can-a-public-repo-include-a-copy-of-the-oneaquahealth-fhir-sandbox-data),
posted 2026-10-01):

> May we include this copy of the sandbox data (and the IG spreadsheet) in our public GitHub repository, with attribution to
> OneAquaHealth and HL7 Europe?

Reply from Pradyumna Amasebail Kodgi, hackathon Manager (shown "about 7 hours" after the question, 1–2 October 2026):

> Yes you can include sandbox data

The question named both the sandbox copy and the IG source spreadsheet; the reply names the sandbox data. Recorded in the README
("Data, attribution and licensing") and docs/DISCOVERY.md D8. **Publish this repository** (with its data). The sanitized copy
below stays documented as a fallback and is no longer needed.

The background, as it was before the answer:

The repository contains OneAquaHealth data, in its files and in its git history:

- the sandbox snapshot under `data/snapshots/` (561 resources and 385 validation outcomes, 4.1 MB), which the offline demo,
  the tests and CI read;
- files derived from the IG source under `knowledge/oah/`, including a copy of the IG's source spreadsheet
  `upstream/Almyros_gov_chem_analysis.csv` (used for lineage);
- raw value excerpts in docs/GATE0_REPORT.md.

The licence of that data is **UNVERIFIED** (docs/DISCOVERY.md D8: the IG's `sushi-config.yaml` has its licence line commented
out, and the IG repository has no LICENSE file). Attribution alone is not assumed to be enough.

- (Before the answer) Do not push this repository to the public remote until the organisers answer. Answered above: allowed.
- Do not commit a new snapshot either (new snapshots and re-fetched IG source files are git-ignored for that reason).

Questions for the organisers (Devpost discussion board or the OneAquaHealth Slack):

1. May the sandbox data (a dated copy of the 561 resources) be redistributed in a public GitHub repository?
2. May copied OneAquaHealth IG source files (the Almyros source spreadsheet from `hl7-eu/oah`) be redistributed?
3. If not, is a private repository shared with the judges acceptable?
4. If not, is a public repository without the raw data acceptable, where the data is captured from the sandbox by a documented,
   reproducible command?

### If the organisers permit publication

Record in README ("Attribution and licence") and docs/DISCOVERY.md D8: the source (OneAquaHealth FHIR sandbox, HL7 Europe;
IG `hl7-eu/oah` at the pinned commit), the attribution, the permission or licence (who granted it, where, when), and the
retrieval date of the snapshot (2026-09-30T09:08:55Z). Then push.

### If permission is denied or stays unclear: publish a sanitized history

A sanitized copy is prepared next to this repository, in `../oah-data-doctor-public` (not pushed): the same commits without the
sandbox snapshot and the copied spreadsheet in any of them. CI captures the data when a repository carries none, and the README
explains the two capture commands. To publish it: `cd ../oah-data-doctor-public && git remote add origin
https://github.com/Unknown1502/OAH-Data-Doctor.git && git push -u origin main`. If this repository gets more commits, regenerate
the copy with the commands below.

Deleting the files in a new commit is not enough: they would remain in the git history. Rewrite the history of a copy and
publish that copy. Tested on 2026-10-01 in a throwaway clone (the working repository was not changed):

```bash
git clone --no-local --single-branch --branch main oah-data-doctor oah-data-doctor-public
cd oah-data-doctor-public
git remote remove origin
FILTER_BRANCH_SQUELCH_WARNING=1 git filter-branch --index-filter \
  'git rm -r --cached --ignore-unmatch -q data/snapshots knowledge/oah/upstream' --prune-empty -- main
git for-each-ref --format='delete %(refname)' refs/original | git update-ref --stdin
git reflog expire --expire=now --all && git gc --prune=now
git rev-list --objects --all | grep -cE 'data/snapshots/|Almyros_gov_chem_analysis'   # must print 0
```

Measured result: 651 raw-data objects before, 0 after; 48 commits became 47 (one commit only added the snapshot). Without the
data, 38 backend tests fail and 17 error (they read the snapshot). In the app, a user recovers both parts with one click:
**Download the data** (shown when nothing is saved, and under *Sources & rules*; D-032; 74 s on 2026-10-01, same 346 findings).
The live sandbox works without it. From the command line, two commands do the same; both need the sandbox and GitHub to be
reachable:

```bash
python scripts/build_knowledge.py     # re-fetches the IG files at the pinned commit (byte-identical except the spreadsheet)
python tasks.py snapshot              # captures the sandbox (111 s on 2026-10-01)
```

After that, all tests passed again (253 passed, 1 skipped; the same as a full clone without the optional `ai` extra). Before
publishing a sanitized copy, also: decide whether the raw excerpts in docs/GATE0_REPORT.md stay; make the CI capture a
snapshot (or skip the snapshot steps), because it currently verifies the committed one; replace the offline-demo instructions
with "capture a snapshot first"; and remove the backup branch from the copy (`--single-branch` above already leaves it out).

## Checklist

- [x] Organisers' answer on redistributing sandbox data: "Yes you can include sandbox data" (Devpost discussion board,
      1–2 October 2026; above).
- [ ] Owner confirms eligibility (student status; see above).
- [ ] Human reviewer marks the 20-finding sample in docs/GATE0_REPORT.md: TRUE POSITIVE, FALSE POSITIVE or UNCERTAIN, with a
      reason, for each.
- [x] Fresh-clone test (2026-10-01, short path on Windows): `git clone …`, `python tasks.py setup` (73 s),
      `python tasks.py test`, `python tasks.py e2e`, `DD_SOURCE=snapshot DD_LLM_PROVIDER=none python tasks.py run` and
      `python tasks.py acceptance` (90/90). Results in docs/STATUS.md.
- [x] Offline test (2026-10-01): snapshot mode with the FHIR server address pointed at an unreachable host and no language
      model: acceptance 90/90.
- [x] Demo video: final film rendered and QA'd (2026-10-02): `artifacts/demo/demo-final.mp4`, 4:27, ElevenLabs voice,
      fact-checked against the app (docs/DEMO_FINAL.md).
- [ ] One human watch-and-listen of the whole film, then upload it (YouTube or Vimeo) and add the link.
- [ ] Push this repository (permission obtained), confirm the repository URL in docs/SUBMISSION.md (already filled in:
      https://github.com/Unknown1502/OAH-Data-Doctor) and add the video link.
- [ ] Paste docs/SUBMISSION.md into Devpost; add screenshots from docs/img/.

## Documents

README.md (overview, computed results, reviewer questions, quick start, limitations, AI disclosure, attribution),
docs/SUBMISSION.md (Devpost text), docs/DEMO_SCRIPT.md (video script and fallback), docs/DISCOVERY.md, docs/GATE0_REPORT.md,
docs/EVALUATION.md, docs/VALIDATION.md, docs/STATUS.md (verification log).
