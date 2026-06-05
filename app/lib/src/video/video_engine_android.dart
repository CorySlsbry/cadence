import 'dart:async';
import 'dart:io';

import 'package:ffmpeg_kit_flutter_new/ffmpeg_kit.dart';
import 'package:ffmpeg_kit_flutter_new/ffmpeg_kit_config.dart';
import 'package:ffmpeg_kit_flutter_new/return_code.dart';

import 'video_engine.dart';

/// Android: the maintained `ffmpeg_kit_flutter_new` fork (FFmpeg 8.0, MediaCodec).
/// Use the LGPL ("min"/"https") binary variant to avoid GPL contamination.
class AndroidVideoEngine implements VideoEngine {
  @override
  Stream<double> run(List<String> args, {double? expectedDurationSec}) {
    final controller = StreamController<double>();
    if (expectedDurationSec != null && expectedDurationSec > 0) {
      FFmpegKitConfig.enableStatisticsCallback((stats) {
        controller.add((stats.getTime() / 1000.0 / expectedDurationSec).clamp(0.0, 1.0));
      });
    }
    FFmpegKit.executeWithArguments(args).then((session) async {
      final rc = await session.getReturnCode();
      if (ReturnCode.isSuccess(rc)) {
        controller.add(1.0);
      } else {
        controller.addError(StateError('ffmpeg-kit failed: ${await session.getFailStackTrace()}'));
      }
      await controller.close();
    });
    return controller.stream;
  }

  @override
  Future<File> normalizeForUpload(File input, File output) async {
    await run([
      '-y', '-i', input.path,
      '-vf', 'scale=1080:1920:force_original_aspect_ratio=increase,'
          'crop=1080:1920,fps=60,format=yuv420p,setsar=1',
      '-vsync', 'cfr', '-r', '60',
      '-c:v', 'h264_mediacodec', '-b:v', '12M',
      '-c:a', 'aac', '-ar', '48000', '-ac', '2',
      output.path,
    ]).drain<void>();
    return output;
  }

  @override
  Future<void> dispose() async {
    await FFmpegKit.cancel();
  }
}
