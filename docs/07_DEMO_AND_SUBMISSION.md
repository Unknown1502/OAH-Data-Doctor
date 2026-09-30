# 07 — Demo and submission

## Submission requirements (Devpost, read 2026-09-30)

- Public code repository with source and documentation: this repository.
- Track alignment statement, project description (problem, solution, users, impact), working prototype, 3–5 minute demo video.
- Deadline: 2026-10-04, 21:00 PDT.

## Checklist

- [ ] Human reviewer signs off the 20-finding sample in docs/GATE0_REPORT.md (regenerate first: `python tasks.py gate0`).
- [ ] `python tasks.py snapshot` shortly before recording, if the sandbox is reachable, then `python scripts/render_docs.py`
      (README and docs/SUBMISSION.md numbers come from the latest snapshot) and commit.
- [ ] Fresh-clone test: `git clone … && python tasks.py setup && python tasks.py test && python tasks.py run`, then in a
      second terminal `python tasks.py acceptance` (every endpoint against its expected outcome; exit 0 = all passed).
- [ ] Offline test: disconnect the network, `DD_SOURCE=snapshot python tasks.py run`, walk the demo script.
- [ ] Record the video following docs/DEMO_SCRIPT.md (3–5 minutes).
- [ ] Push to a public GitHub repository; replace the placeholder rules canonical URL (DECISIONS D-009) if desired.
- [ ] Paste docs/SUBMISSION.md into Devpost; add the repository URL, video URL and screenshots from docs/img/.
- [ ] Confirm the AI-disclosure wording against the hackathon rules page on submission day.

## Documents

README.md (overview, computed results, quick start, limitations, AI disclosure, attribution), docs/SUBMISSION.md (Devpost text),
docs/DEMO_SCRIPT.md (video script and fallback), docs/DISCOVERY.md, docs/GATE0_REPORT.md, docs/EVALUATION.md, docs/VALIDATION.md.
