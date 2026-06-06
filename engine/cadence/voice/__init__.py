"""Voiceover synthesis (internal / not user-facing yet).

THE BLEND: Gemini "Charon" flow -> ElevenLabs Speech-to-Speech into a cloned voice.
Hidden capability — wired for the owner's voice only, gated behind an admin flag.
"""

from cadence.voice.mux import build_voiceover_args, mux_voiceover
from cadence.voice.synth import (
    CORY_VOICE_ID,
    ElevenLabsSTS,
    GeminiCharonTTS,
    VoiceError,
    VoiceSynth,
)

__all__ = [
    "CORY_VOICE_ID",
    "ElevenLabsSTS",
    "GeminiCharonTTS",
    "VoiceError",
    "VoiceSynth",
    "build_voiceover_args",
    "mux_voiceover",
]
