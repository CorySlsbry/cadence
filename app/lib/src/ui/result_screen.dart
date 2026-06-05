import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../state/pipeline.dart';
import 'customize_screen.dart';

class ResultScreen extends ConsumerWidget {
  const ResultScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final state = ref.watch(pipelineProvider);
    final result = state.result?.result;

    return Scaffold(
      appBar: AppBar(title: const Text('Your video')),
      body: Padding(
        padding: const EdgeInsets.all(20),
        child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          Expanded(
            child: Card(
              child: Center(
                child: Column(mainAxisSize: MainAxisSize.min, children: [
                  const Icon(Icons.play_circle_fill, size: 72, color: Color(0xFFFFD60A)),
                  const SizedBox(height: 12),
                  Text(
                    result == null
                        ? 'Rendered'
                        : '${result.width}×${result.height} • ${result.fps.toStringAsFixed(0)}fps • ${result.durationSec.toStringAsFixed(1)}s',
                    style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w600),
                  ),
                  if (result != null)
                    Padding(
                      padding: const EdgeInsets.only(top: 4),
                      child: Text('encoder: ${result.encoder}${result.usedHardware ? " (GPU)" : ""}',
                          style: const TextStyle(color: Colors.white38, fontSize: 12)),
                    ),
                  if (state.outputFile != null)
                    Padding(
                      padding: const EdgeInsets.only(top: 8),
                      child: Text(state.outputFile!.path, style: const TextStyle(color: Colors.white24, fontSize: 11)),
                    ),
                ]),
              ),
            ),
          ),
          const SizedBox(height: 16),
          FilledButton.icon(
            icon: const Icon(Icons.tune),
            label: const Text('Customize layout'),
            onPressed: state.plan == null
                ? null
                : () => Navigator.of(context).push(
                      MaterialPageRoute(builder: (_) => const CustomizeScreen()),
                    ),
          ),
        ]),
      ),
    );
  }
}
