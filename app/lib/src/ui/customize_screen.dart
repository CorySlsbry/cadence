import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/engine_models.dart';
import '../state/pipeline.dart';

/// §3 Module D — Layout Customization. Exposes the plan parameters as direct
/// controls; edits mutate the GenerationPlan and re-render via the engine.
class CustomizeScreen extends ConsumerStatefulWidget {
  const CustomizeScreen({super.key});
  @override
  ConsumerState<CustomizeScreen> createState() => _CustomizeScreenState();
}

class _CustomizeScreenState extends ConsumerState<CustomizeScreen> {
  String _zone = 'bottom';
  String _style = 'fade';
  double _zoom = 1.12;
  double _saturation = 1.08;
  double _contrast = 1.05;
  bool _rendering = false;

  @override
  Widget build(BuildContext context) {
    final plan = ref.watch(pipelineProvider).plan;
    return Scaffold(
      appBar: AppBar(title: const Text('Customize')),
      body: ListView(
        padding: const EdgeInsets.all(20),
        children: [
          _section('Caption position'),
          SegmentedButton<String>(
            segments: const [
              ButtonSegment(value: 'top', label: Text('Top 15%')),
              ButtonSegment(value: 'center', label: Text('Center')),
              ButtonSegment(value: 'bottom', label: Text('Bottom 80%')),
            ],
            selected: {_zone},
            onSelectionChanged: (s) => setState(() => _zone = s.first),
          ),
          const SizedBox(height: 24),
          _section('Caption entry'),
          SegmentedButton<String>(
            segments: const [
              ButtonSegment(value: 'fade', label: Text('Fade (200ms)')),
              ButtonSegment(value: 'pop', label: Text('Hard pop')),
            ],
            selected: {_style},
            onSelectionChanged: (s) => setState(() => _style = s.first),
          ),
          const SizedBox(height: 24),
          _slider('Smart jump-cut zoom', _zoom, 1.0, 1.2,
              (v) => setState(() => _zoom = v), '${((_zoom - 1) * 100).toStringAsFixed(0)}%'),
          _slider('Saturation', _saturation, 0.6, 1.6,
              (v) => setState(() => _saturation = v), _saturation.toStringAsFixed(2)),
          _slider('Contrast', _contrast, 0.7, 1.4,
              (v) => setState(() => _contrast = v), _contrast.toStringAsFixed(2)),
          const SizedBox(height: 24),
          FilledButton(
            onPressed: plan == null || _rendering ? null : () => _apply(plan),
            child: _rendering
                ? const SizedBox(height: 22, width: 22, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.black))
                : const Text('Apply & re-render'),
          ),
        ],
      ),
    );
  }

  Future<void> _apply(GenerationPlan plan) async {
    setState(() => _rendering = true);
    plan
      ..setCaptionZone(_zone)
      ..setCaptionStyle(_style)
      ..setSmartZoom(_zoom)
      ..setGrade(saturation: _saturation, contrast: _contrast);
    await ref.read(pipelineProvider.notifier).reRender(plan);
    if (mounted) {
      setState(() => _rendering = false);
      Navigator.of(context).pop();
    }
  }

  Widget _section(String t) => Padding(
        padding: const EdgeInsets.only(bottom: 10),
        child: Text(t, style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 15)),
      );

  Widget _slider(String label, double value, double min, double max,
      ValueChanged<double> onChanged, String display) {
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [
        Text(label, style: const TextStyle(fontWeight: FontWeight.w600)),
        Text(display, style: const TextStyle(color: Colors.white54)),
      ]),
      Slider(value: value, min: min, max: max, onChanged: onChanged),
      const SizedBox(height: 8),
    ]);
  }
}
