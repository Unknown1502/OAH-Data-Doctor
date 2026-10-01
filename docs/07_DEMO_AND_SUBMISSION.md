# 07 — Demo and submission

## Submission requirements (Devpost, re-read 2026-10-01)

Source: https://oneaquahealth-ieee-hackathon.devpost.com/ (overview, rules and updates pages).

- **Deadline:** 2026-10-04, 21:00 PDT (extended from 30 September; the rules page still shows the old date, the updates page
  announces the extension).
- **Required:** track alignment statement; project description (problem, solution, target users, expected impact); demo video
  of 3–5 minutes; public code repository with source and documentation; working prototype, mockup or proof of concept.
- **Rules:** original work built during the hackathon period; no copyright, licensing or third-party IP violations; every
  participant registered on Devpost. No explicit AI-disclosure clause was found; we disclose anyway.
- **Eligibility:** the overview lists "students only". The extension update allows individuals and teams. UNVERIFIED for this
  project: the owner must confirm student status.
- **Judging:** impact and alignment with the OneAquaHealth mission 30 %, innovation 20 %, technical implementation 20 %,
  usability 15 %, feasibility and scalability 15 % (rules page; 1–10 per criterion, weighted).

## Open question before publishing (human decision)

The repository contains OneAquaHealth data, in its files and in its git history:

- the sandbox snapshot under `data/snapshots/` (561 resources and 385 validation outcomes, 4.1 MB), which the offline demo,
  the tests and CI read;
- files derived from the IG source under `knowledge/oah/`, including a copy of the IG's source spreadsheet
  `upstream/Almyros_gov_chem_analysis.csv` (used for lineage);
- raw value excerpts in docs/GATE0_REPORT.md.

The licence of that data is **UNVERIFIED** (docs/DISCOVERY.md D8: the IG's `sushi-config.yaml` has its licence line commented
out, and the IG repository has no LICENSE file).

- Do **not** push the repository to the public remote until the organisers answer whether sandbox data may be redistributed.
- Do not commit a new snapshot either (it would add more raw sandbox data to the history).
- If redistribution is not allowed, the options need a decision: a repository without the snapshot (users then capture their
  own with `python tasks.py snapshot`; tests and CI that read the snapshot would have to change), or a private repository
  shared with the judges, if the organisers accept that.

## Checklist

- [ ] Organisers' answer on redistributing sandbox data (above). Ask on the Devpost discussion board or the OneAquaHealth Slack.
- [ ] Owner confirms eligibility (students only).
- [ ] Human reviewer marks the 20-finding sample in docs/GATE0_REPORT.md (true or false positive for each).
- [ ] Fresh-clone test: `git clone … && python tasks.py setup && python tasks.py test && python tasks.py run`, then in a
      second terminal `python tasks.py acceptance` (every endpoint against its expected outcome; exit 0 = all passed).
- [ ] Offline test: disconnect the network, `DD_SOURCE=snapshot python tasks.py run`, walk docs/DEMO_SCRIPT.md.
- [ ] Record the video following docs/DEMO_SCRIPT.md (about 4 minutes; language model off; time one rehearsal first).
- [ ] After the licence answer: push, then confirm the repository URL in docs/SUBMISSION.md (already filled in:
      https://github.com/Unknown1502/OAH-Data-Doctor) and add the video link.
- [ ] Paste docs/SUBMISSION.md into Devpost; add screenshots from docs/img/.

## Documents

README.md (overview, computed results, quick start, limitations, AI disclosure, attribution), docs/SUBMISSION.md (Devpost text),
docs/DEMO_SCRIPT.md (video script and fallback), docs/DISCOVERY.md, docs/GATE0_REPORT.md, docs/EVALUATION.md, docs/VALIDATION.md.
