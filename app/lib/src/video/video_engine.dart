import 'dart:io';

/// One interface over FFmpeg, split by platform behind the scenes.
///
/// WHY: `ffmpeg_kit_flutter` was retired in early 2025 (binaries pulled, never
/// supported Windows). So we abstract it: Android uses the maintained
/// `ffmpeg_kit_flutter_new` fork (MediaCodec HW accel); Windows runs a bundled
/// FFmpeg 8.x sidecar binary via `Process.start` (gives NVENC and stays LGPL-clean).
abstract interface class VideoEngine {
  /// Run an FFmpeg command, streaming progress in 0..1 (best-effort).
  Stream<double> run(List<String> args, {double? expectedDurationSec});

  /// Normalize a freshly captured clip to CFR 1080x1920/60 before upload — the
  /// research's mandatory first step (phone capture is VFR and drifts otherwise).
  Future<File> normalizeForUpload(File input, File output);

  Future<void> dispose();
}

/// Selects the right implementation for the current platform.
VideoEngine createVideoEngine() {
  if (Platform.isAndroid || Platform.isIOS) {
    // ignore: avoid_dynamic_calls
    return _androidEngineFactory();
  }
  return _desktopEngineFactory();
}

// These are wired in the platform-specific files; kept as late bindings so this
// file has no hard import of a platform plugin (which would break the other build).
late VideoEngine Function() _androidEngineFactory;
late VideoEngine Function() _desktopEngineFactory;

void registerAndroidEngine(VideoEngine Function() f) => _androidEngineFactory = f;
void registerDesktopEngine(VideoEngine Function() f) => _desktopEngineFactory = f;
