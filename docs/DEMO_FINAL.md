# Demo video: production record

How the 3–5 minute demo video is made, so it can be reproduced and checked. The video is built from the running app; nothing
in the product was changed for it.

## Status

- **Pipeline:** complete. Real-UI capture, storyboard, captions, motion graphics, voice, render.
- **Voice:** the final voice is **ElevenLabs** (text to speech with timestamps), and it needs `ELEVENLABS_API_KEY`, which was not
  available when this was written. A **draft** with the Windows built-in voice exists for checking timing; it is visibly
  watermarked "DRAFT" and is not for submission.
- **Length:** draft 4:01. The final render stretches deliberate pauses (never speech) toward about 3:50, inside 3–5 minutes.

## Recording configuration

| Setting | Value |
|---|---|
| App | `DD_SOURCE=snapshot DD_STARTUP_LIVE=0 DD_LLM_PROVIDER=none python tasks.py run` |
| Data | verified snapshot `2026-09-30T09-08-55Z` (manifest sha256 `a80584b5…`); the same findings were reproduced live on 2026-10-01 (docs/STATUS.md) |
| Language model | off (the sidebar shows "Language model: off") |
| Browser | Chromium (Playwright), 1440 × 900 at device pixel ratio 2, dark theme, reduced motion |
| Output | 1920 × 1080, 30 fps, H.264 (CRF 17), AAC 192 kb/s, loudness normalised to −16 LUFS (true peak −1.5 dB) |

## Commands

The pipeline lives outside the repository (`../artifacts/demo/pipeline/`), so no generated media enters git.

```powershell
# 1. app (above), then capture the real UI along the demo path (frames + element boxes):
node capture.cjs
# 2. voice: final (ElevenLabs) or draft (Windows voice, timing only)
$env:ELEVENLABS_API_KEY = "<key>"; .\make-final.ps1            # lists 3 candidate voices and writes samples
.\make-final.ps1 -VoiceId <voice_id>                            # voice + render -> ..\demo-final.mp4
python voice.py sapi; python render.py --out ..\draft          # draft only
```

## Browser path (all real clicks and scrolls)

1. **Data health** (`/`): dismiss the audit strip.
2. **Finding** `F-SEM-SCALE-001-3d690239c32e` (the scale finding of `Observation/Obs-Almyros-TemperatureWater-2013`):
   - scroll to the evidence chain, then to the root cause;
   - scroll to *Evidence* (FHIRPath table), then to the provenance rows;
   - **View raw resource**, then Escape;
   - scroll to *Where these values first appear*;
   - scroll to *What this affects*, then select the claim node.
3. **Compare** (`/compare`):
   - the chip *Obesity prevalence … Female, 35-74 y … vs Nordre Aker, 18-29 y*; scroll to the verdict, then to the matrix;
   - back to the top, then the chip *Water temperature … 2013 vs … 2014*.
4. **Check a claim** (`/claims`):
   - the example *PM10 at Benevento site 04 exceeded the WHO guideline in 2018*; scroll to the ladder;
   - the example *PM2.5 causes cardiovascular disease in Benevento*; scroll to the ladder and *What you can safely say*.
5. **Report** (`/report`): scroll to *Executive finding*, then to *Provenance*.

## Scene timeline (draft render)

| Time | Scene |
|---|---|
| 0:00.0–0:22.8 | 1. The contradiction: FHIR Pass vs Data Doctor Critical; 198,000 °C; median 19.8; 198,000 ÷ 19.8 = 10,000 = 10⁴ |
| 0:22.8–0:57.0 | 2. The record: average, maximum, minimum, median, as published |
| 0:57.0–1:23.9 | 3. The proof: the calculation, "exactly 10⁴", the rule that does not hold, root cause unknown |
| 1:23.9–1:48.8 | 4. The evidence: FHIRPath, resource, rule, source, retrieval time, hash, raw record, IG source spreadsheet |
| 1:48.8–2:11.9 | 5. What it affects: the impact trace, a claim's dependencies |
| 2:11.9–2:48.3 | 6. Comparability: matrix with direct, conditional, hard blocker; what can still be compared; blocked until reviewed |
| 2:48.3–3:20.3 | 7. Claim safety: a supported claim (reaches comparison), a causal claim (unsupported; reaches description) |
| 3:20.3–3:56.0 | 8. The report: observed, derived, inferred, unknown; provenance; model off; "a layer above FHIR" diagram |
| 3:56.0–4:01.0 | End card |

The final render writes its own `scene-timestamps.json`; the timings shift slightly with the voice.

## Narration

About 380 words in 42 lines; the full text, scene by scene, is written with every render (`demo-script-final.md`).

The voice is given "Fire" for FHIR and "W.H.O." for WHO; the captions show FHIR and WHO. The narration never says the
correct value is 19.8 °C, never says the data is corrupted, and never credits AI with a finding. It does say:
- root cause unknown;
- the model was off;
- the trace covers the analyses Data Doctor computes;
- the recording uses the snapshot, and the same finding was reproduced live.

## Captions and motion graphics

- **Caption timing** comes from the voice's own word timings: ElevenLabs character alignment for the final, the Windows
  synthesizer's progress events for the draft (rescaled to the audio; approximate).
- **Caption format:** segments of up to 54 characters, burned in and also exported as `captions.srt`. A caption moves to the top
  whenever it would cover the highlighted evidence.
- **Motion graphics** are drawn in post-production over real screenshots, never in the app:
  - highlight boxes with a soft spotlight;
  - labels;
  - a zooming virtual camera;
  - a cursor showing where the real click happened;
  - two cards with values read from the app's API ("from the published record" and "198,000 ÷ 19.8 = 10,000 = 10⁴ exactly");
  - chapter labels;
  - an animated "layer above FHIR" diagram;
  - an end card.
- **Fact check:** the renderer stops if any narrated value differs from what the app shows (`storyboard.check_facts`). That
  covers the four published values, the calculation and "exactly 10⁴", the impact counts, and snapshot mode.

## Known limitations

- The final voice has not been generated yet (no `ELEVENLABS_API_KEY`); the draft voice is robotic and timing-only.
- Nobody has listened to the audio. The voice must get one human listen-through before submission.
- The cursor is drawn in post-production at the real click positions; the clicks themselves were made by the browser
  automation.
- The end card names the repository URL, which only works once the repository is pushed (docs/07).
