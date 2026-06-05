"""Real end-to-end ASR verification.

Mux the SAPI speech into a video, transcribe it with faster-whisper (real word
timestamps), then run the full cleaning pipeline and confirm it removes the filler
"um" and the repeated "this is a test" take.
"""

from __future__ import annotations

import os

from cadence.cleaning.editor import clean_recording
from cadence.config import CleaningConfig
from cadence.ffmpeg.probe import probe_media
from cadence.ffmpeg.runner import FFmpeg
from cadence.models import CutReason
from cadence.transcription.faster_whisper import FasterWhisperTranscriber

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "output")
ff = FFmpeg()
wav = os.path.join(OUT, "speech.wav")
mp4 = os.path.join(OUT, "speech.mp4")

dur = probe_media_audio_duration = None
# Build a video carrying the speech audio (testsrc2 visuals, real speech track).
ff.run([
    "-y", "-f", "lavfi", "-i", "testsrc2=s=216x384:r=30",
    "-i", wav,
    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", mp4,
], timeout=120)
info = probe_media(mp4, ff)
print(f"speech.mp4: {info.duration:.2f}s, audio={info.has_audio}")

print("loading faster-whisper base.en (first run downloads ~145MB)...")
transcriber = FasterWhisperTranscriber("base.en", device="cpu", compute_type="int8")
transcript = transcriber.transcribe(mp4, ff=ff)
print("\nREAL TRANSCRIPT (word : start-end):")
for w in transcript.words:
    print(f"  {w.text!r:14} {w.start:5.2f}-{w.end:5.2f}  p={w.prob:.2f}")

cfg = CleaningConfig(retake_similarity=0.7, retake_min_words=3)
edl = clean_recording(mp4, transcript=transcript, cfg=cfg, ff=ff)
print(f"\nEDL: source={edl.source_duration:.2f}s output={edl.output_duration:.2f}s removed={edl.removed_duration:.2f}s")
for r in edl.removed:
    print(f"  REMOVED {r.range.start:5.2f}-{r.range.end:5.2f}  {r.reason.value:9} {r.detail}")

reasons = {r.reason for r in edl.removed}
print("\nremoved reasons:", sorted(x.value for x in reasons))
print("filler removed:", CutReason.FILLER in reasons)
print("bad-take removed:", CutReason.BAD_TAKE in reasons)
