import 'dart:io';

import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/engine_models.dart';
import '../state/pipeline.dart';
import 'capture_screen.dart';
import 'result_screen.dart';

class HomeScreen extends ConsumerWidget {
  const HomeScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final state = ref.watch(pipelineProvider);
    final ctrl = ref.read(pipelineProvider.notifier);

    ref.listen(pipelineProvider, (_, next) {
      if (next.stage == PipelineStage.done && context.mounted) {
        Navigator.of(context).push(MaterialPageRoute(builder: (_) => const ResultScreen()));
      }
    });

    return Scaffold(
      appBar: AppBar(
        title: const Text('Cadence', style: TextStyle(fontWeight: FontWeight.w800, letterSpacing: -0.5)),
        actions: const [_EngineStatus(), SizedBox(width: 16)],
      ),
      body: ListView(
        padding: const EdgeInsets.all(20),
        children: [
          const _Hero(),
          _StageCard(
            index: 1,
            title: 'Reference',
            subtitle: state.analysis == null
                ? 'Pick a TikTok-style reference to match its look & pacing'
                : 'Matched • ${state.analysis!.transitionCount} cuts • ${state.analysis!.cutDensityPerMin.toStringAsFixed(0)} cuts/min',
            done: state.analysis != null,
            trailing: FilledButton(
              onPressed: () async {
                final f = await _pickVideo();
                if (f != null) {
                  ctrl.setReference(f);
                  await ctrl.analyzeReference();
                }
              },
              child: Text(state.analysis == null ? 'Pick' : 'Re-pick'),
            ),
            child: state.analysis != null ? _PaletteRow(state.analysis!) : null,
          ),
          _StageCard(
            index: 2,
            title: 'Capture',
            subtitle: state.recording == null
                ? 'Record raw A-roll — keep talking through mistakes, we clean it'
                : 'Captured: ${state.recording!.path.split(Platform.pathSeparator).last}',
            done: state.recording != null,
            trailing: FilledButton(
              onPressed: () => Navigator.of(context).push(
                MaterialPageRoute(builder: (_) => const CaptureScreen()),
              ),
              child: const Text('Record'),
            ),
          ),
          _StageCard(
            index: 3,
            title: 'Brand',
            subtitle: state.boardId == null ? 'Apply your logo, colors & captions' : 'Brand applied',
            done: state.boardId != null,
            trailing: const _BrandPicker(),
          ),
          const SizedBox(height: 12),
          FilledButton(
            onPressed: state.recording == null || state.stage == PipelineStage.synthesizing
                ? null
                : () => ctrl.synthesize(),
            child: state.stage == PipelineStage.synthesizing
                ? const SizedBox(height: 22, width: 22, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.black))
                : const Text('Synthesize Premium Video'),
          ),
          if (state.stage == PipelineStage.error)
            Padding(
              padding: const EdgeInsets.only(top: 16),
              child: Text(state.message ?? 'Something went wrong',
                  style: const TextStyle(color: Colors.redAccent)),
            ),
        ],
      ),
    );
  }

  Future<File?> _pickVideo() async {
    final res = await FilePicker.platform.pickFiles(type: FileType.video);
    final path = res?.files.single.path;
    return path == null ? null : File(path);
  }
}

class _Hero extends StatelessWidget {
  const _Hero();
  @override
  Widget build(BuildContext context) {
    return const Padding(
      padding: EdgeInsets.only(bottom: 12, top: 4),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text('Studio-grade short-form,\nfrom one raw take.',
            style: TextStyle(fontSize: 26, height: 1.15, fontWeight: FontWeight.w800, letterSpacing: -0.8)),
        SizedBox(height: 8),
        Text('Analyze a reference, record once, and let the engine clean and stitch it to match.',
            style: TextStyle(color: Colors.white60, height: 1.4)),
      ]),
    );
  }
}

class _StageCard extends StatelessWidget {
  const _StageCard({
    required this.index,
    required this.title,
    required this.subtitle,
    required this.done,
    required this.trailing,
    this.child,
  });
  final int index;
  final String title;
  final String subtitle;
  final bool done;
  final Widget trailing;
  final Widget? child;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(18),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Row(children: [
            CircleAvatar(
              radius: 16,
              backgroundColor: done ? const Color(0xFFFFD60A) : Colors.white12,
              child: done
                  ? const Icon(Icons.check, size: 18, color: Colors.black)
                  : Text('$index', style: const TextStyle(fontWeight: FontWeight.bold)),
            ),
            const SizedBox(width: 14),
            Expanded(
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text(title, style: const TextStyle(fontSize: 17, fontWeight: FontWeight.w700)),
                const SizedBox(height: 2),
                Text(subtitle, style: const TextStyle(color: Colors.white54, fontSize: 13)),
              ]),
            ),
            const SizedBox(width: 12),
            trailing,
          ]),
          if (child != null) Padding(padding: const EdgeInsets.only(top: 14), child: child!),
        ]),
      ),
    );
  }
}

class _PaletteRow extends StatelessWidget {
  const _PaletteRow(this.analysis);
  final ReferenceAnalysis analysis;
  @override
  Widget build(BuildContext context) {
    return Row(
      children: analysis.palette.take(6).map((hex) {
        final c = Color(int.parse('FF${hex.substring(1)}', radix: 16));
        return Container(
          width: 34, height: 34,
          margin: const EdgeInsets.only(right: 8),
          decoration: BoxDecoration(color: c, borderRadius: BorderRadius.circular(8)),
        );
      }).toList(),
    );
  }
}

class _BrandPicker extends ConsumerWidget {
  const _BrandPicker();
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final boards = ref.watch(brandBoardsProvider);
    return boards.when(
      data: (list) => list.isEmpty
          ? FilledButton(
              onPressed: () async {
                await ref.read(engineClientProvider).createBoard('My Brand');
                ref.invalidate(brandBoardsProvider);
              },
              child: const Text('Create'),
            )
          : DropdownButton<String>(
              hint: const Text('Select'),
              value: ref.watch(pipelineProvider).boardId,
              items: [for (final b in list) DropdownMenuItem(value: b.id, child: Text(b.name))],
              onChanged: (id) => id == null ? null : ref.read(pipelineProvider.notifier).setBoard(id),
            ),
      loading: () => const SizedBox(height: 20, width: 20, child: CircularProgressIndicator(strokeWidth: 2)),
      error: (_, __) => const Icon(Icons.cloud_off, color: Colors.redAccent),
    );
  }
}

class _EngineStatus extends ConsumerWidget {
  const _EngineStatus();
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final caps = ref.watch(capabilitiesProvider);
    return caps.when(
      data: (c) => Row(children: [
        Icon(Icons.bolt, size: 16, color: c.hasHardwareEncoder ? const Color(0xFFFFD60A) : Colors.white38),
        const SizedBox(width: 4),
        Text(c.hasHardwareEncoder ? 'GPU' : 'CPU', style: const TextStyle(fontSize: 12, color: Colors.white54)),
      ]),
      loading: () => const Text('…', style: TextStyle(color: Colors.white38)),
      error: (_, __) => const Tooltip(message: 'Engine offline', child: Icon(Icons.cloud_off, color: Colors.redAccent, size: 18)),
    );
  }
}
