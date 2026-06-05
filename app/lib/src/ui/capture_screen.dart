import 'dart:io';

import 'package:camera/camera.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../state/pipeline.dart';

/// §3 Module C capture — record raw A-roll at high bitrate/60fps. The user keeps
/// talking through mistakes; the engine removes silence, fillers, and bad takes.
class CaptureScreen extends ConsumerStatefulWidget {
  const CaptureScreen({super.key});
  @override
  ConsumerState<CaptureScreen> createState() => _CaptureScreenState();
}

class _CaptureScreenState extends ConsumerState<CaptureScreen> {
  CameraController? _controller;
  bool _recording = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _init();
  }

  Future<void> _init() async {
    try {
      final cameras = await availableCameras();
      final front = cameras.firstWhere(
        (c) => c.lensDirection == CameraLensDirection.front,
        orElse: () => cameras.first,
      );
      final controller = CameraController(
        front,
        ResolutionPreset.veryHigh,
        enableAudio: true,
        // Request 60fps + high bitrate. Some Android devices silently cap at 30fps
        // (flutter/flutter#167719) — production should validate and fall back to a
        // native CameraX MethodChannel; the engine re-normalizes to 60fps CFR anyway.
        mediaSettings: const MediaSettings(
          fps: 60,
          videoBitrate: 12000000,
          audioBitrate: 128000,
        ),
      );
      await controller.initialize();
      if (mounted) setState(() => _controller = controller);
    } on CameraException catch (e) {
      if (mounted) setState(() => _error = e.description);
    }
  }

  Future<void> _toggle() async {
    final c = _controller;
    if (c == null) return;
    if (_recording) {
      final file = await c.stopVideoRecording();
      ref.read(pipelineProvider.notifier).setRecording(File(file.path));
      if (mounted) Navigator.of(context).pop();
    } else {
      await c.startVideoRecording();
      setState(() => _recording = true);
    }
  }

  @override
  void dispose() {
    _controller?.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.black,
      body: SafeArea(
        child: Stack(children: [
          if (_controller != null)
            Center(child: AspectRatio(aspectRatio: 9 / 16, child: CameraPreview(_controller!)))
          else if (_error != null)
            Center(child: Text('Camera error: $_error', style: const TextStyle(color: Colors.redAccent)))
          else
            const Center(child: CircularProgressIndicator()),
          Positioned(
            top: 8, left: 8,
            child: IconButton(
              icon: const Icon(Icons.close, color: Colors.white),
              onPressed: () => Navigator.of(context).pop(),
            ),
          ),
          Align(
            alignment: Alignment.bottomCenter,
            child: Padding(
              padding: const EdgeInsets.only(bottom: 40),
              child: GestureDetector(
                onTap: _controller == null ? null : _toggle,
                child: Container(
                  width: 78, height: 78,
                  decoration: BoxDecoration(
                    shape: BoxShape.circle,
                    color: _recording ? Colors.redAccent : Colors.white,
                    border: Border.all(color: Colors.white24, width: 4),
                  ),
                  child: Icon(_recording ? Icons.stop : Icons.fiber_manual_record,
                      color: _recording ? Colors.white : Colors.redAccent, size: 34),
                ),
              ),
            ),
          ),
        ]),
      ),
    );
  }
}
