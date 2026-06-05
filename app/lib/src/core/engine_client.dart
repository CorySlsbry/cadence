import 'dart:convert';
import 'dart:io';

import 'package:http/http.dart' as http;

import 'engine_models.dart';

/// Typed client for the Cadence Python engine (localhost HTTP sidecar).
///
/// The engine does ALL heavy lifting (analysis, cleaning, rendering); this client
/// is a thin, strongly-typed wrapper the rest of the app talks to.
class EngineClient {
  EngineClient({Uri? baseUrl, http.Client? httpClient})
      : _base = baseUrl ?? Uri.parse('http://127.0.0.1:8765'),
        _http = httpClient ?? http.Client();

  final Uri _base;
  final http.Client _http;

  Future<bool> health() async {
    try {
      final res = await _http.get(_base.resolve('/health')).timeout(
            const Duration(seconds: 3),
          );
      if (res.statusCode != 200) return false;
      return (jsonDecode(res.body) as Map)['status'] == 'ok';
    } on Exception {
      return false;
    }
  }

  Future<EngineCapabilities> capabilities() async {
    final res = await _http.get(_base.resolve('/capabilities'));
    _ensureOk(res);
    return EngineCapabilities.fromJson(jsonDecode(res.body) as Map<String, dynamic>);
  }

  /// Analyze a reference video; returns the aesthetic + pacing fingerprint.
  Future<ReferenceAnalysis> analyze(File reference) async {
    final req = http.MultipartRequest('POST', _base.resolve('/analyze'))
      ..files.add(await http.MultipartFile.fromPath('reference', reference.path));
    final res = await http.Response.fromStream(await _http.send(req));
    _ensureOk(res);
    final body = jsonDecode(res.body) as Map<String, dynamic>;
    return ReferenceAnalysis.fromJson(body['analysis'] as Map<String, dynamic>);
  }

  /// Full pipeline: clean the raw recording, match the reference, apply the brand,
  /// render, and return the result + the editable generation plan.
  Future<SynthesizeResult> synthesize({
    required File recording,
    File? reference,
    Transcript? transcript,
    String? boardId,
    bool aggressiveFillers = false,
  }) async {
    final req = http.MultipartRequest('POST', _base.resolve('/synthesize'))
      ..files.add(await http.MultipartFile.fromPath('recording', recording.path));
    if (reference != null) {
      req.files.add(await http.MultipartFile.fromPath('reference', reference.path));
    }
    if (transcript != null) {
      req.fields['transcript_json'] = jsonEncode(transcript.toJson());
    }
    if (boardId != null) req.fields['board_id'] = boardId;
    req.fields['aggressive_fillers'] = aggressiveFillers.toString();

    final res = await http.Response.fromStream(await _http.send(req));
    _ensureOk(res);
    return SynthesizeResult.fromJson(jsonDecode(res.body) as Map<String, dynamic>);
  }

  /// Re-render after the user edits the plan in the Module D customization UI.
  Future<RenderResult> render(GenerationPlan plan) async {
    final res = await _http.post(
      _base.resolve('/render'),
      headers: {'content-type': 'application/json'},
      body: jsonEncode({'plan': plan.toJson()}),
    );
    _ensureOk(res);
    final body = jsonDecode(res.body) as Map<String, dynamic>;
    return RenderResult.fromJson(body['result'] as Map<String, dynamic>);
  }

  Future<File> download(String downloadUrl, File target) async {
    final res = await _http.get(_base.resolve(downloadUrl));
    _ensureOk(res);
    await target.writeAsBytes(res.bodyBytes);
    return target;
  }

  // -- brand board -------------------------------------------------------- //
  Future<BrandBoard> createBoard(String name) async {
    final res = await _http.post(
      _base.resolve('/brand/boards'),
      headers: {'content-type': 'application/json'},
      body: jsonEncode({'name': name}),
    );
    _ensureOk(res);
    return BrandBoard.fromJson(jsonDecode(res.body) as Map<String, dynamic>);
  }

  Future<List<BrandBoard>> listBoards() async {
    final res = await _http.get(_base.resolve('/brand/boards'));
    _ensureOk(res);
    return (jsonDecode(res.body) as List)
        .map((e) => BrandBoard.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  Future<void> addWatermark(String boardId, File asset,
      {double opacity = 1.0, String anchor = 'bottom_right', double scale = 0.18}) async {
    final req = http.MultipartRequest(
        'POST', _base.resolve('/brand/boards/$boardId/assets'))
      ..files.add(await http.MultipartFile.fromPath('file', asset.path))
      ..fields['kind'] = 'watermark'
      ..fields['anchor'] = anchor
      ..fields['opacity'] = opacity.toString()
      ..fields['scale'] = scale.toString();
    final res = await http.Response.fromStream(await _http.send(req));
    _ensureOk(res);
  }

  Future<void> setCaptionStyle(String boardId,
      {String? primaryHex, String? outlineHex, String? fontPath}) async {
    final res = await _http.put(
      _base.resolve('/brand/boards/$boardId/caption-style'),
      headers: {'content-type': 'application/json'},
      body: jsonEncode({
        'primary_hex': primaryHex,
        'outline_hex': outlineHex,
        'font_path': fontPath,
      }),
    );
    _ensureOk(res);
  }

  void _ensureOk(http.Response res) {
    if (res.statusCode >= 400) {
      throw EngineException(res.statusCode, res.body);
    }
  }

  void close() => _http.close();
}

class EngineException implements Exception {
  EngineException(this.statusCode, this.body);
  final int statusCode;
  final String body;
  @override
  String toString() => 'EngineException($statusCode): $body';
}
