# Cadence — Flutter Client

The capture + control + preview surface for the Cadence engine. Targets **Windows
desktop** and **Android** (optimized for the Galaxy S25 Ultra's high-bitrate sensor).

> **Status:** This is a complete, architecturally-faithful scaffold. It was authored
> against the current (2026) package APIs but has **not** been compiled or device-tested
> in the engine's build environment (no Flutter SDK / no Android device was attached).
> Run `flutter pub get` on a machine with the Flutter SDK to build it. The Python
> engine, by contrast, is fully tested and verified (see `../engine`).

## Architecture

```
 Flutter UI (Riverpod)
   │  capture (camera + CameraX, 60fps high-bitrate)
   │  control (4-stage workflow + Module D customization sliders)
   │  preview (result + re-render)
   ▼
 EngineClient  ──HTTP──►  Python `cadence` engine (localhost :8765)
   ▲                         analysis · cleaning · synthesis · render (FFmpeg)
   │
 VideoEngine (platform split, local FFmpeg for capture-normalize/thumbnails)
   ├─ Android : ffmpeg_kit_flutter_new (MediaCodec)
   └─ Desktop : bundled FFmpeg 8.x sidecar via Process.start (NVENC, LGPL-clean)
```

The heavy lifting lives in Python; the app stays responsive because all FFmpeg work
runs off the UI isolate (sidecar process on desktop; native session on Android).

## Key files
| File | Role |
|---|---|
| `lib/src/core/engine_client.dart` | Typed HTTP client for the engine sidecar |
| `lib/src/core/engine_models.dart` | JSON DTOs incl. the editable `GenerationPlan` |
| `lib/src/video/video_engine.dart` | Platform-split FFmpeg interface (+ desktop/android impls) |
| `lib/src/state/pipeline.dart` | Riverpod providers + the workflow `Notifier` |
| `lib/src/ui/home_screen.dart` | The 4-stage workflow hub |
| `lib/src/ui/capture_screen.dart` | High-bitrate camera capture |
| `lib/src/ui/customize_screen.dart` | §3 Module D layout customization |

## Running
1. Start the engine: `python -m cadence.cli serve` (or `cadence serve`) → `http://127.0.0.1:8765`.
2. On **desktop**, bundle a static FFmpeg 8.x binary at `assets/bin/ffmpeg.exe`.
3. `flutter pub get && flutter run -d windows` (or `-d <android-device>`).

## 2026 package notes
- `ffmpeg_kit_flutter` was **retired Jan 2025** — we use the maintained `ffmpeg_kit_flutter_new` (LGPL variant) on Android.
- `camera` + `camera_android_camerax` `MediaSettings(fps:60)` can be silently capped to 30fps on some devices; the engine re-normalizes to 60fps CFR regardless.
- Riverpod v3 `Notifier`/`AsyncNotifier` for job state.
