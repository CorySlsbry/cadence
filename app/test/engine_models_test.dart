import 'package:cadence_app/src/core/engine_models.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  group('GenerationPlan', () {
    Map<String, dynamic> samplePlan() => {
          'output': {'width': 1080, 'height': 1920, 'fps': 60},
          'clips': [
            {'source': 'a.mp4', 'in_point': 0.0, 'out_point': 2.0, 'zoom': 1.0},
            {'source': 'a.mp4', 'in_point': 3.0, 'out_point': 5.0, 'zoom': 1.0},
          ],
          'captions': [
            {'text': 'hi', 'start': 0.0, 'end': 1.0, 'zone': 'bottom', 'style': 'fade'},
          ],
          'color_grade': {'saturation': 1.0, 'contrast': 1.0, 'brightness': 0.0},
        };

    test('mutators update the underlying JSON', () {
      final plan = GenerationPlan.fromJson(samplePlan());
      plan
        ..setCaptionZone('center')
        ..setCaptionStyle('pop')
        ..setSmartZoom(1.15)
        ..setGrade(saturation: 1.2);

      final cap = plan.captions.first as Map;
      expect(cap['zone'], 'center');
      expect(cap['style'], 'pop');
      // First clip stays at 1.0; later clips get the punch-in.
      final clips = plan.toJson()['clips'] as List;
      expect((clips[0] as Map)['zoom'], 1.0);
      expect((clips[1] as Map)['zoom'], 1.15);
      expect((plan.toJson()['color_grade'] as Map)['saturation'], 1.2);
    });

    test('round-trips through json', () {
      final plan = GenerationPlan.fromJson(samplePlan());
      expect(plan.fps, 60);
      expect(GenerationPlan.fromJson(plan.toJson()).fps, 60);
    });
  });

  group('EngineCapabilities', () {
    test('detects hardware encoders', () {
      final caps = EngineCapabilities.fromJson({
        'video_encoders': ['libx264', 'h264_nvenc'],
        'ml': {'faster_whisper': true, 'sentence_transformers': false},
      });
      expect(caps.hasHardwareEncoder, isTrue);
      expect(caps.ml['faster_whisper'], isTrue);
    });
  });
}
