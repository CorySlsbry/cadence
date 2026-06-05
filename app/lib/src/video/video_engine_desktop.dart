import 'dart:async';
import 'dart:io';

import 'package:path/path.dart' as p;

import 'video_engine.dart';

/// Windows/macOS/Linux: drive a bundled FFmpeg 8.x sidecar binary via Process.start.
///
/// Preferred over the Android fork's desktop build because that build is
/// software-only (no NVENC) and the full-gpl variant would GPL-contaminate the app.
/// The sidecar already runs off the UI isolate, so no extra threading is needed.
class DesktopVideoEngine implements VideoEngine {
  DesktopVideoEngine({String? ffmpegPath}) : _ffmpeg = ffmpegPath ?? _bundledFfmpeg();

  final String _ffmpeg;
  Process? _current;

  static String _bundledFfmpeg() {
    final exeDir = File(Platform.resolvedExecutable).parent.path;
    final name = Platform.isWindows ? 'ffmpeg.exe' : 'ffmpeg';
    final bundled = p.join(exeDir, 'data', 'flutter_assets', 'assets', 'bin', name);
    return File(bundled).existsSync() ? bundled : name; // fall back to PATH
  }

  static final RegExp _timeRe = RegExp(r'time=(\d+):(\d+):(\d+\.\d+)');

  @override
  Stream<double> run(List<String> args, {double? expectedDurationSec}) async* {
    final controller = StreamController<double>();
    _current = await Process.start(_ffmpeg, ['-hide_banner', '-nostdin', ...args]);
    _current!.stderr.transform(const SystemEncoding().decoder).listen((chunk) {
      if (expectedDurationSec == null || expectedDurationSec <= 0) return;
      final m = _timeRe.firstMatch(chunk);
      if (m != null) {
        final secs = int.parse(m[1]!) * 3600 + int.parse(m[2]!) * 60 + double.parse(m[3]!);
        controller.add((secs / expectedDurationSec).clamp(0.0, 1.0));
      }
    });
    unawaited(_current!.exitCode.then((code) {
      if (code == 0) {
        controller.add(1.0);
      } else {
        controller.addError(StateError('ffmpeg exited with code $code'));
      }
      controller.close();
    }));
    yield* controller.stream;
  }

  @override
  Future<File> normalizeForUpload(File input, File output) async {
    await run([
      '-y', '-i', input.path,
      '-vf', 'scale=1080:1920:force_original_aspect_ratio=increase,'
          'crop=1080:1920,fps=60,format=yuv420p,setsar=1',
      '-vsync', 'cfr', '-r', '60',
      '-c:v', 'libx264', '-crf', '16', '-preset', 'veryfast',
      '-c:a', 'aac', '-ar', '48000', '-ac', '2',
      output.path,
    ], expectedDurationSec: null).drain<void>();
    return output;
  }

  @override
  Future<void> dispose() async {
    _current?.kill();
  }
}
