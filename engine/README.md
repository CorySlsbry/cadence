# Cadence Engine

The production video-processing engine behind Cadence — a headless, deterministic
Python service that **analyzes** a reference video, **cleans** raw A-roll, and
**synthesizes** a premium 1080×1920/60fps vertical video that matches the reference's
look and pacing. Exposed as a CLI and a localhost HTTP sidecar (consumed by the
Flutter client).

## Design stance
- **Ports & adapters.** Heavy/optional ML (Whisper, embeddings, OCR) lives behind
  interfaces; the algorithmic core is pure and fully unit-tested. The engine runs and
  is 100% testable **without any ML dependency**.
- **Dependency-light core.** numpy + Pillow + FastAPI only. The transition detector,
  K-means palette, silence/filler/retake logic, and the FFmpeg filtergraphs are all
  implemented and tested in-repo (not delegated to an unverifiable black box).
- **Real FFmpeg 8.x.** Hardware encoder selection (NVENC/AMF/QSV) with a validated
  software fallback; trim/concat editing; animated ASS captions; punch-in via
  `scale+crop` (not jittery `zoompan`); reference-derived color grade.

## Install
```bash
python -m venv .venv && . .venv/Scripts/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt                           # core
pip install -r requirements-ml.txt                        # optional: real ASR + semantic retakes
pip install -e .                                           # exposes the `cadence` CLI
```
Requires an `ffmpeg`/`ffprobe` 8.x on PATH (build with `--enable-libass`; `--enable-nvenc`
and `--enable-whisper` recommended).

## CLI
```bash
cadence analyze reference.mp4 --out analysis.json
cadence clean raw.mp4 --transcript words.json --out edl.json --render cleaned.mp4
cadence synthesize raw.mp4 --reference reference.mp4 --transcript words.json \
        --brand-db brand.db --board <id> --out final.mp4 --plan-out plan.json
cadence render plan.json --out final.mp4
cadence brand --brand-db brand.db create "My Brand"
cadence serve --port 8765            # local HTTP sidecar
```

## HTTP API (sidecar)
| Method | Path | Purpose |
|---|---|---|
| GET | `/health`, `/capabilities` | liveness + available encoders / ML |
| POST | `/analyze` | reference → aesthetic + pacing fingerprint |
| POST | `/clean` | raw recording → edit-decision list |
| POST | `/synthesize` | full pipeline → rendered mp4 (job + download url) |
| POST | `/render` | render an (edited) generation plan |
| GET | `/download/{job_id}` | stream the rendered mp4 |
| * | `/brand/boards...` | brand-board CRUD |

## Pipeline
```
reference.mp4 ─► [A] analyze ─► ReferenceAnalysis (palette, cuts, text zones, pacing)
raw A-roll    ─► [C] clean   ─► EditDecisionList (silence + filler + bad-take removed)
              ─► [D/§4] plan ─► GenerationPlan (clips, captions, grade, watermark)  ── editable
              ─► [§4] render ─► final.mp4  (1080×1920 @ 60fps)
```
Brand equity (logos, palettes, fonts, captions) persists in SQLite (Module B) and is
applied at synthesis.

## Tests
```bash
pytest                       # all (incl. real-ffmpeg integration + render)
pytest -m "not slow"         # skip the heaviest renders
pytest -m ml                 # the faster-whisper adapter (needs the ml extra)
```
Every integration test generates its own synthetic media with a **known ground truth**
and asserts against an independent oracle.

## Module map
| Module | Package | What it does |
|---|---|---|
| A — Analyzer | `cadence/analysis` | K-means palette + exposure, adaptive transition detection + type, text-zone mapping, pacing |
| B — Brand board | `cadence/brandboard` | SQLite persistence of logos/palettes/fonts/captions |
| C — Cleaning | `cadence/cleaning` | RMS+word-gap silence, filler scrub, retake detection, EDL |
| D + §4 — Synthesis | `cadence/synthesis` | generation plan, ASS captions, filtergraph render w/ HW fallback |
| — FFmpeg | `cadence/ffmpeg` | runner (encoder smoke-test), probe, pure filtergraph builders |
| — Transcription | `cadence/transcription` | faster-whisper / ffmpeg-whisper / injected adapters |
