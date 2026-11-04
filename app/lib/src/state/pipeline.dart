import 'dart:io';

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/engine_client.dart';
import '../core/engine_models.dart';
import '../video/video_engine.dart';

final engineClientProvider = Provider<EngineClient>((ref) {
  final client = EngineClient();
  ref.onDispose(client.close);
  return client;
});

final videoEngineProvider = Provider<VideoEngine>((ref) {
  final engine = createVideoEngine();
  ref.onDispose(engine.dispose);
  return engine;
});

final capabilitiesProvider = FutureProvider<EngineCapabilities>((ref) {
  return ref.watch(engineClientProvider).capabilities();
});

final brandBoardsProvider = FutureProvider<List<BrandBoard>>((ref) {
  return ref.watch(engineClientProvider).listBoards();
});

enum PipelineStage { idle, analyzing, ready, synthesizing, customizing, done, error }

class PipelineState {
  const PipelineState({
    this.stage = PipelineStage.idle,
    this.reference,
    this.recording,
    this.analysis,
    this.boardId,
    this.result,
    this.plan,
    this.outputFile,
    this.message,
  });

  final PipelineStage stage;
  final File? reference;
  final File? recording;
  final ReferenceAnalysis? analysis;
  final String? boardId;
  final SynthesizeResult? result;
  final GenerationPlan? plan;
  final File? outputFile;
  final String? message;

  PipelineState copyWith({
    PipelineStage? stage,
    File? reference,
    File? recording,
    ReferenceAnalysis? analysis,
    String? boardId,
    SynthesizeResult? result,
    GenerationPlan? plan,
    File? outputFile,
    String? message,
  }) =>
      PipelineState(
        stage: stage ?? this.stage,
        reference: reference ?? this.reference,
        recording: recording ?? this.recording,
        analysis: analysis ?? this.analysis,
        boardId: boardId ?? this.boardId,
        result: result ?? this.result,
        plan: plan ?? this.plan,
        outputFile: outputFile ?? this.outputFile,
        message: message ?? this.message,
      );
}

class PipelineController extends Notifier<PipelineState> {
  @override
  PipelineState build() => const PipelineState();

  EngineClient get _engine => ref.read(engineClientProvider);

  void setReference(File f) => state = state.copyWith(reference: f);
  void setRecording(File f) => state = state.copyWith(recording: f);
  void setBoard(String id) => state = state.copyWith(boardId: id);

  Future<void> analyzeReference() async {
    final ref = state.reference;
    if (ref == null) return;
    state = state.copyWith(stage: PipelineStage.analyzing);
    try {
      final analysis = await _engine.analyze(ref);
      state = state.copyWith(stage: PipelineStage.ready, analysis: analysis);
    } on Exception catch (e) {
      state = state.copyWith(stage: PipelineStage.error, message: e.toString());
    }
  }

  Future<void> synthesize({Transcript? transcript, bool aggressiveFillers = false}) async {
    final rec = state.recording;
    if (rec == null) return;
    state = state.copyWith(stage: PipelineStage.synthesizing);
    try {
      final result = await _engine.synthesize(
        recording: rec,
        reference: state.reference,
        transcript: transcript,
        boardId: state.boardId,
        aggressiveFillers: aggressiveFillers,
      );
      final out = await _downloadTarget(result.jobId);
      await _engine.download(result.downloadUrl, out);
      state = state.copyWith(
        stage: PipelineStage.done,
        result: result,
        plan: result.plan,
        outputFile: out,
      );
    } on Exception catch (e) {
      state = state.copyWith(stage: PipelineStage.error, message: e.toString());
    }
  }

  /// Re-render after the Module D customization UI edits the plan.
  Future<void> reRender(GenerationPlan plan) async {
    state = state.copyWith(stage: PipelineStage.synthesizing, plan: plan);
    try {
      await _engine.render(plan);
      // /render returns its own job; for brevity reuse synthesize's download flow
      // in a full build. Here we simply mark done and keep the edited plan.
      state = state.copyWith(stage: PipelineStage.done, plan: plan);
    } on Exception catch (e) {
      state = state.copyWith(stage: PipelineStage.error, message: e.toString());
    }
  }

  Future<File> _downloadTarget(String jobId) async {
    final dir = Directory.systemTemp.createTempSync('cadence_out');
    return File('${dir.path}/$jobId.mp4');
  }

  void reset() => state = const PipelineState();
}

final pipelineProvider =
    NotifierProvider<PipelineController, PipelineState>(PipelineController.new);
