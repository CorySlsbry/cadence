import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'src/ui/home_screen.dart';
import 'src/ui/theme.dart';
import 'src/video/video_engine.dart';
import 'src/video/video_engine_android.dart';
import 'src/video/video_engine_desktop.dart';

void main() {
  // Wire the platform engine factories (keeps platform plugins out of the shared
  // interface file, so each build only links the binary it can use).
  registerAndroidEngine(() => AndroidVideoEngine());
  registerDesktopEngine(() => DesktopVideoEngine());
  if (!(Platform.isAndroid || Platform.isIOS)) {
    // On desktop the Android plugin import is dead code; tree-shaken out.
  }
  runApp(const ProviderScope(child: CadenceApp()));
}

class CadenceApp extends StatelessWidget {
  const CadenceApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Cadence',
      debugShowCheckedModeBanner: false,
      theme: CadenceTheme.dark,
      home: const HomeScreen(),
    );
  }
}
