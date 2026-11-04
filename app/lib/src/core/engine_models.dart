// Dart mirrors of the engine's JSON contract. Kept deliberately thin — these are
// transport DTOs, not the source of truth (the Python `cadence.models` is).

class EngineCapabilities {
  EngineCapabilities({required this.videoEncoders, required this.ml});
  final List<String> videoEncoders;
  final Map<String, bool> ml;

  factory EngineCapabilities.fromJson(Map<String, dynamic> j) => EngineCapabilities(
        videoEncoders: (j['video_encoders'] as List).cast<String>(),
        ml: (j['ml'] as Map).map((k, v) => MapEntry(k as String, v as bool)),
      );

  bool get hasHardwareEncoder =>
      videoEncoders.any((e) => e.contains('nvenc') || e.contains('amf') || e.contains('qsv'));
}

class Word {
  Word(this.text, this.start, this.end, [this.prob = 1.0]);
  final String text;
  final double start;
  final double end;
  final double prob;
  Map<String, dynamic> toJson() => {'text': text, 'start': start, 'end': end, 'prob': prob};
  factory Word.fromJson(Map<String, dynamic> j) =>
      Word(j['text'] as String, (j['start'] as num).toDouble(), (j['end'] as num).toDouble(),
          (j['prob'] as num?)?.toDouble() ?? 1.0);
}

class Transcript {
  Transcript(this.words, {this.language = 'en'});
  final List<Word> words;
  final String language;
  Map<String, dynamic> toJson() =>
      {'language': language, 'words': words.map((w) => w.toJson()).toList()};
}

class ReferenceAnalysis {
  ReferenceAnalysis({
    required this.width,
    required this.height,
    required this.durationSec,
    required this.palette,
    required this.transitionCount,
    required this.cutDensityPerMin,
    required this.raw,
  });
  final int width;
  final int height;
  final double durationSec;
  final List<String> palette;
  final int transitionCount;
  final double cutDensityPerMin;
  final Map<String, dynamic> raw;

  factory ReferenceAnalysis.fromJson(Map<String, dynamic> j) {
    final media = j['media'] as Map<String, dynamic>;
    final cp = j['color_profile'] as Map<String, dynamic>;
    final palette = (cp['palette'] as List)
        .map((s) => (s as Map)['color']['hex'] as String)
        .toList();
    return ReferenceAnalysis(
      width: media['width'] as int,
      height: media['height'] as int,
      durationSec: (media['duration'] as num).toDouble(),
      palette: palette,
      transitionCount: (j['transitions'] as List).length,
      cutDensityPerMin: ((j['pacing'] as Map)['cut_density_per_min'] as num).toDouble(),
      raw: j,
    );
  }
}

/// The editable §4 Generation Plan. The Module D customization UI mutates this and
/// posts it back to /render.
class GenerationPlan {
  GenerationPlan(this.raw);
  final Map<String, dynamic> raw;

  factory GenerationPlan.fromJson(Map<String, dynamic> j) => GenerationPlan(j);
  Map<String, dynamic> toJson() => raw;

  int get fps => (raw['output'] as Map)['fps'] as int;
  List<dynamic> get captions => (raw['captions'] as List?) ?? const [];

  // Convenience mutators for the customization sliders.
  void setCaptionZone(String zone) {
    for (final c in captions) {
      (c as Map)['zone'] = zone;
    }
  }

  void setCaptionStyle(String style) {
    for (final c in captions) {
      (c as Map)['style'] = style;
    }
  }

  void setSmartZoom(double zoom) {
    final clips = (raw['clips'] as List?) ?? const [];
    for (var i = 0; i < clips.length; i++) {
      (clips[i] as Map)['zoom'] = i == 0 ? 1.0 : zoom;
    }
  }

  void setGrade({double? saturation, double? contrast, double? brightness}) {
    final g = (raw['color_grade'] as Map);
    if (saturation != null) g['saturation'] = saturation;
    if (contrast != null) g['contrast'] = contrast;
    if (brightness != null) g['brightness'] = brightness;
  }
}

class RenderResult {
  RenderResult({
    required this.width,
    required this.height,
    required this.fps,
    required this.durationSec,
    required this.encoder,
    required this.usedHardware,
  });
  final int width;
  final int height;
  final double fps;
  final double durationSec;
  final String encoder;
  final bool usedHardware;

  factory RenderResult.fromJson(Map<String, dynamic> j) => RenderResult(
        width: j['width'] as int,
        height: j['height'] as int,
        fps: (j['fps'] as num).toDouble(),
        durationSec: (j['duration'] as num).toDouble(),
        encoder: j['encoder'] as String,
        usedHardware: j['used_hardware'] as bool,
      );
}

class SynthesizeResult {
  SynthesizeResult({
    required this.jobId,
    required this.downloadUrl,
    required this.plan,
    required this.result,
  });
  final String jobId;
  final String downloadUrl;
  final GenerationPlan plan;
  final RenderResult result;

  factory SynthesizeResult.fromJson(Map<String, dynamic> j) => SynthesizeResult(
        jobId: j['job_id'] as String,
        downloadUrl: j['download_url'] as String,
        plan: GenerationPlan.fromJson(j['plan'] as Map<String, dynamic>),
        result: RenderResult.fromJson(j['result'] as Map<String, dynamic>),
      );
}

class BrandBoard {
  BrandBoard({required this.id, required this.name, required this.assetCount});
  final String id;
  final String name;
  final int assetCount;
  factory BrandBoard.fromJson(Map<String, dynamic> j) => BrandBoard(
        id: j['id'] as String,
        name: j['name'] as String,
        assetCount: (j['assets'] as List?)?.length ?? 0,
      );
}
