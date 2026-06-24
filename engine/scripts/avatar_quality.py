"""Avatar quality benchmark — score how close a rendered talking-avatar is to the real you,
WITHOUT a human in the loop (the visual analog of cory-voice/score_mos.py's UTMOS gate).

Four objective metrics, each PLUGGABLE + GRACEFUL (returns None if its model isn't installed
on this box — the deploy GPU box installs them):
  - face_sim  : identity  — face-embedding cosine (candidate frames vs your reference)  [w .40]
  - lse_c     : lip-sync  — SyncNet LSE-C confidence, via an env command (higher=better) [w .30]
  - voice_sim : voice     — speaker-embedding cosine (candidate audio vs your reference) [w .20]
  - utmos     : naturalness — cory-voice/score_mos.py UTMOS                               [w .10]
composite = weighted mean over the metrics that are AVAILABLE (re-normalized).

Loop usage (the point): render the SAME script across candidate settings (model / res / fps and
your different reference takes) -> score each -> keep the highest composite. Metrics get ~90% of
the way; ONE human side-by-side stays the acceptance gate (honest bar ~level-4, not HeyGen-5).

  python avatar_quality.py --reference you.webm cand_a.mp4 cand_b.mp4 [--json]

Install (deploy GPU box):  pip install opencv-python-headless numpy deepface resemblyzer soundfile librosa
  + SyncNet for LSE-C, exposed via  AVATAR_SYNCNET_CMD="python /models/syncnet/run.py --video {video}"
    (must print a float LSE-C on stdout). UTMOS via the cory-voice score_mos.py path.
"""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import tempfile

WEIGHTS = {"face_sim": 0.40, "lse_c": 0.30, "voice_sim": 0.20, "utmos": 0.10}
SCORE_MOS = os.environ.get(
    "SCORE_MOS_PY", r"C:\Users\Cory\.claude\skills\cory-voice\references\score_mos.py"
)


def _cosine(a, b) -> float:
    import numpy as np

    a, b = np.asarray(a, dtype="float64").ravel(), np.asarray(b, dtype="float64").ravel()
    d = (np.linalg.norm(a) * np.linalg.norm(b)) or 1.0
    return float(np.dot(a, b) / d)


def _extract_audio(video: str) -> str | None:
    out = os.path.join(tempfile.gettempdir(), f"_aq_{pathlib.Path(video).stem}.wav")
    try:
        subprocess.run(["ffmpeg", "-y", "-i", video, "-ac", "1", "-ar", "16000", out],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return out
    except Exception:  # noqa: BLE001
        return None


def _frames(video: str, n: int = 8):
    """Sample up to n evenly-spaced RGB frames (None if opencv missing/unreadable)."""
    try:
        import cv2
    except Exception:  # noqa: BLE001
        return None
    cap = cv2.VideoCapture(video)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    if total <= 0:
        cap.release()
        return None
    idxs = [int(total * (i + 0.5) / n) for i in range(n)]
    out = []
    for i in idxs:
        cap.set(cv2.CAP_PROP_POS_FRAMES, i)
        ok, fr = cap.read()
        if ok:
            out.append(cv2.cvtColor(fr, cv2.COLOR_BGR2RGB))
    cap.release()
    return out or None


def face_sim(reference: str, candidate: str) -> float | None:
    """Mean face-embedding cosine between candidate frames and the reference (ArcFace via
    deepface). Internal benchmark only — not shipped in the product."""
    try:
        import numpy as np
        from deepface import DeepFace
    except Exception:  # noqa: BLE001
        return None
    rf, cf = _frames(reference, 4), _frames(candidate, 8)
    if not rf or not cf:
        return None

    def embed(frame):
        try:
            reps = DeepFace.represent(frame, model_name="ArcFace", enforce_detection=False)
            return reps[0]["embedding"] if reps else None
        except Exception:  # noqa: BLE001
            return None

    ref_vecs = [v for v in (embed(f) for f in rf) if v is not None]
    cand_vecs = [v for v in (embed(f) for f in cf) if v is not None]
    if not ref_vecs or not cand_vecs:
        return None
    ref_mean = np.mean(ref_vecs, axis=0)
    sims = [_cosine(ref_mean, c) for c in cand_vecs]
    return round(float(sum(sims) / len(sims)), 4)


def voice_sim(reference: str, candidate: str) -> float | None:
    """Speaker-embedding cosine (Resemblyzer) between the candidate's and reference's audio."""
    try:
        from resemblyzer import VoiceEncoder, preprocess_wav
    except Exception:  # noqa: BLE001
        return None
    ra, ca = _extract_audio(reference), _extract_audio(candidate)
    if not ra or not ca:
        return None
    try:
        enc = VoiceEncoder()
        re_ = enc.embed_utterance(preprocess_wav(ra))
        ce_ = enc.embed_utterance(preprocess_wav(ca))
        return round(_cosine(re_, ce_), 4)
    except Exception:  # noqa: BLE001
        return None


def lse_c(candidate: str) -> float | None:
    """SyncNet LSE-C via an env command template (must print a float). Deploy-wired, like the
    gen model commands — keeps SyncNet's repo/deps off this stack until the GPU box."""
    tmpl = os.environ.get("AVATAR_SYNCNET_CMD", "").strip()
    if not tmpl:
        return None
    try:
        out = subprocess.run(tmpl.format(video=candidate), shell=True, check=True,
                             capture_output=True, text=True, timeout=600).stdout.strip()
        return round(float(out.split()[-1]), 4)
    except Exception:  # noqa: BLE001
        return None


def utmos(candidate: str) -> float | None:
    aud = _extract_audio(candidate)
    if not aud or not os.path.exists(SCORE_MOS):
        return None
    try:
        out = subprocess.run([sys.executable, SCORE_MOS, "--json", aud],
                             check=True, capture_output=True, text=True, timeout=600).stdout
        return list(json.loads(out).values())[0]
    except Exception:  # noqa: BLE001
        return None


def score_render(reference: str, candidate: str) -> dict:
    m = {
        "face_sim": face_sim(reference, candidate),
        "lse_c": lse_c(candidate),
        "voice_sim": voice_sim(reference, candidate),
        "utmos": utmos(candidate),
    }
    # composite = weighted mean over AVAILABLE metrics, each normalized to ~[0,1]
    norm = {"face_sim": lambda v: v, "voice_sim": lambda v: v,
            "lse_c": lambda v: max(0.0, min(v / 10.0, 1.0)),   # LSE-C ~0..10
            "utmos": lambda v: max(0.0, min((v - 1.0) / 4.0, 1.0))}  # MOS 1..5
    num = den = 0.0
    for k, v in m.items():
        if v is not None:
            num += WEIGHTS[k] * norm[k](v)
            den += WEIGHTS[k]
    m["composite"] = round(num / den, 4) if den else None
    return m


def main() -> None:
    args = sys.argv[1:]
    as_json = "--json" in args
    args = [a for a in args if a != "--json"]
    reference = None
    if "--reference" in args:
        i = args.index("--reference")
        reference = args[i + 1]
        del args[i : i + 2]
    if not reference or not args:
        sys.stderr.write("usage: avatar_quality.py --reference you.webm cand1.mp4 cand2.mp4 [--json]\n")
        sys.exit(2)
    results = {pathlib.Path(c).name: score_render(reference, c) for c in args}
    if as_json:
        print(json.dumps(results, indent=2))
    else:
        ranked = sorted(results.items(), key=lambda kv: -(kv[1]["composite"] or -1))
        for name, m in ranked:
            print(f"{m['composite']!s:>7}  {name}  "
                  f"(face {m['face_sim']} · sync {m['lse_c']} · voice {m['voice_sim']} · utmos {m['utmos']})")
        print("\nWinner ->", ranked[0][0] if ranked else "none")


if __name__ == "__main__":
    main()
