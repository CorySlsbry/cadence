# Cadence Engine — Adopted Engineering Decisions

Distilled from parallel deep research (5 subsystems) and adapted to this engine's
"dependency-light, fully-testable core + optional ML upgrades" stance.

## Global rules
- **CFR-normalize first.** Phone/TikTok footage is VFR; every downstream timestamp
  assumes constant fps or it silently drifts. The engine normalizes raw A-roll to
  `1080x1920, 60fps, yuv420p, setsar=1` before analysis/render.
- **EDL is the contract.** Cleaning stages emit time-ranges only; the renderer is the
  single consumer. Merge silence+filler+retake cuts → sort → merge overlaps → invert
  to KEEP → frame-snap (`round(t*fps)/fps`).
- **Architecture:** Python does ALL heavy analysis/render; the Flutter client is the
  capture + control + preview surface, talking to the engine over a local HTTP daemon.

## Subsystem 1 — Transitions / pacing
- Adopt the **AdaptiveDetector** idea in a dependency-light numpy detector: HSV
  `content_val` per adjacent frame pair + **rolling-window ratio** (fire when a frame's
  score ≥ `3.0×` its neighborhood mean and above a `min_content_val≈15` floor).
- Classify TYPE from the raw (unsmoothed) curve shape: isolated spike → HARD_CUT;
  multi-frame plateau → CROSSFADE/DISSOLVE; mean-luma crossing toward black → FADE.
- `min_scene_len ≈ 0.4s` to suppress double-fires; SSIM is a secondary confirm signal.
- Optional upgrade backend: PySceneDetect `scenedetect[opencv]`; TransNetV2 for dissolves.

## Subsystem 2 — Silence / filler removal
- Silence = (a) RMS/dBFS `< -40dB` sustained `> 300ms`, AND/OR (b) inter-word gap
  `> 0.5s` from the transcript. Pad kept ranges by ~60–80ms so consonants aren't clipped.
- Filler default set = pure hesitations `{um,uh,uhm,erm,ah,eh,hmm,mm,mhm}`; discourse
  markers `{like,so,basically,actually,literally,you know,...}` behind an `aggressive` flag.
- Word timing via faster-whisper `word_timestamps=True`, `vad min_silence_duration_ms=300-500`.

## Subsystem 3 — Bad-take / retake
- **Precision over recall** — deleting the wrong take is catastrophic. Default matcher is
  lexical+n-gram (token Dice on 3-grams + common-prefix + LCS ratio) gated by a pause and a
  look-ahead window; semantic `all-MiniLM-L6-v2` cosine is an optional precision booster.
- Flag a retake when `(ngram high) OR (cosine ≥ 0.82 AND pause-separated AND within window)`;
  union-find clusters of ≥2 attempts → **keep only the LAST**. Snap cut to the silence midpoint.

## Subsystem 4 — Render filtergraph (FFmpeg 8.x)
- **trim/atrim + setpts/asetpts=PTS-STARTPTS + concat** for cuts (most reliable A/V sync).
- Punch-in via animated **`scale='iw*(1+Z*min(t/D,1))':-1:eval=frame,crop=W:H`** — NOT zoompan
  (integer-rounds → jitter). Wrap sizes in `trunc(../2)*2` (odd dims crash yuv420p).
- Graph order: normalize → punch-in → grade (`eq`/`curves`/`colorbalance`) → xfade →
  subtitles(ASS) → watermark → encode. Grade BEFORE captions so the LUT never shifts text.
- Animated captions via a generated **.ass** file: `{\an5\pos(540,Y)\fad(in,out)}` for FADE,
  `{\fscx0\fscy0\t(0,180,\fscx100\fscy100)}` for POP. Y: top=288, center=960, bottom=1536.
- ASS colors are `&HAABBGGRR&` (alpha-inverted). Escape Windows subtitle paths.
- Encode: prefer `h264_nvenc -preset p7 -tune hq -rc vbr -cq 19 -b:v 0 ...`; smoke-test the
  encoder first; fall back to `libx264 -crf 18 -preset slow`. Always `-movflags +faststart`.

## Subsystem 5 — Flutter client
- Split FFmpeg by platform behind one `VideoEngine` interface: Android →
  `ffmpeg_kit_flutter_new` (LGPL variant); Windows → bundled gyan.dev FFmpeg sidecar via
  `Process.start` (gives NVENC, LGPL-clean). Riverpod v3 `AsyncNotifier` for jobs.
- Camera: `camera` + `camera_android_camerax` with `MediaSettings(fps:60, videoBitrate)`;
  fall back to native CameraX MethodChannel (the plugin silently caps 30fps on some devices).
- On-device ML: `flutter_onnxruntime` (all platforms). Avoid retired `ffmpeg_kit`.
