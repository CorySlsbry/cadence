import 'package:flutter/material.dart';

/// Premium dark theme — deep neutrals, a single confident accent, generous space.
class CadenceTheme {
  static const _accent = Color(0xFFFFD60A); // warm signature
  static const _bg = Color(0xFF0B0B0F);
  static const _surface = Color(0xFF15151C);

  static ThemeData get dark {
    final base = ThemeData.dark(useMaterial3: true);
    return base.copyWith(
      scaffoldBackgroundColor: _bg,
      colorScheme: const ColorScheme.dark(
        primary: _accent,
        secondary: _accent,
        surface: _surface,
        onPrimary: Colors.black,
      ),
      cardTheme: CardThemeData(
        color: _surface,
        elevation: 0,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
        margin: const EdgeInsets.symmetric(vertical: 8),
      ),
      filledButtonTheme: FilledButtonThemeData(
        style: FilledButton.styleFrom(
          backgroundColor: _accent,
          foregroundColor: Colors.black,
          padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 18),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
          textStyle: const TextStyle(fontWeight: FontWeight.w700, fontSize: 16),
        ),
      ),
      appBarTheme: const AppBarTheme(backgroundColor: _bg, elevation: 0),
    );
  }
}
