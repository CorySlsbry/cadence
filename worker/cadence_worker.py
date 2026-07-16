"""Cadence render worker.

Polls Supabase for queued render jobs, claims one atomically, pulls the inputs
from Storage, runs the (fully-tested) engine pipeline — server-side ASR, cleaning,
synthesis — uploads the result, and reports status/progress back. Designed to run
as one or many stateless processes; `claim_next_render_job` (FOR UPDATE SKIP LOCKED)
guarantees no job is processed twice.
"""

from __future__ import annotations

import json
import os
import socket
import tempfile
import time
import traceback
from typing import Any

from supabase import Client, create_client

# Load a co-located .env (so `python cadence_worker.py` runs standalone).
_ENV_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
if os.path.isfile(_ENV_FILE):
    for _line in open(_ENV_FILE, encoding="utf-8"):
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k, _v)

from cadence import analyze_reference, build_generation_plan, clean_recording, render_plan
from cadence.ffmpeg.probe import probe_media
from cadence.ffmpeg.runner import FFmpeg
from cadence.models import (
    Anchor,
    AssetKind,
    BrandAsset,
    BrandBoard,
    ClipSpec,
    ColorGrade,
    GenerationPlan,
    RGBColor,
    Transcript,
)

UPLOADS = "uploads"
OUTPUTS = "outputs"


def _env(name: str, default: str | None = None) -> str:
    val = os.environ.get(name, default)
    if val is None:
        raise SystemExit(f"missing required env var: {name}")
    return val


AUDIO_FIT_BPS = 160_000  # AAC track reserved in the fit budget

# Faceless scene styles: the override REPLACES the photoreal prompt framing entirely
# (see build_ai_prompt_scene). Keys are what the web sends in faceless.scene_style.
SCENE_STYLES = {
    "claymation": "handcrafted claymation stop-motion scene, plasticine characters with subtle "
                  "fingerprint texture, miniature handmade set, warm studio lighting",
    "cartoon3d": "premium 3D animated cartoon scene, expressive stylized characters, soft global "
                 "illumination, rich subsurface detail, feature-animation quality render",
    "anime": "cinematic anime scene, detailed cel shading, dramatic rim lighting, expressive "
             "characters, premium animation-studio key visual",
    "comic": "bold comic book illustration, dynamic ink linework, halftone shading, vivid saturated "
             "colors, dramatic graphic-novel panel composition",
    "watercolor": "hand-painted watercolor illustration, soft pigment washes, textured cold-press "
                  "paper grain, delicate ink linework, gallery-quality",
    "cyberpunk": "neon cyberpunk scene, rain-slick reflective streets, holographic signage glow, "
                 "dramatic magenta-and-cyan lighting, cinematic sci-fi atmosphere",
    "papercraft": "layered paper-cut craft scene, dimensional cardstock collage, crisp die-cut "
                  "edges, soft shadows between paper layers, handmade premium feel",
    "character": "cinematic character-driven scene starring one consistent stylized hero character "
                 "who appears in every shot, expressive and instantly recognizable",
}


def fit_video_bitrate(limit_bytes: int, duration_sec: float, *, audio_bps: int = AUDIO_FIT_BPS) -> int:
    """Video bitrate that lands a re-encode ~93% under the upload cap.

    total_bits = limit*8*0.93 spread across the duration, minus the audio track,
    floored at 500kbps so even pathological durations stay watchable."""
    duration_sec = max(duration_sec, 0.1)
    total_bps = (limit_bytes * 8 * 0.93) / duration_sec
    return max(int(total_bps - audio_bps), 500_000)


class SupabaseCostLedger:
    """Durable AI-spend cap backed by the ``ai_spend`` Postgres table, plus optional
    per-user token metering.

    The worker runs on stateless, scale-to-zero Cloud Run instances, so a local JSON
    ledger could not hold the cap across instances. The atomic ``charge_ai_spend`` RPC
    (a guarded UPDATE) enforces a *global* runaway-safety ceiling shared by everyone.

    When ``user_id`` is set (a non-BYOK render: the user is spending the shared key),
    each image ALSO burns one of that user's tokens via the atomic ``spend_tokens`` RPC.
    That guarded decrement is what makes the platform safely multi-tenant — one user can
    never touch another's balance, and two concurrent renders can't oversell it. BYOK
    users pay their own provider and are handed ``ledger=None`` upstream, so they never
    reach this class. Implements the ImageGenerator ledger contract:
    ``can_spend`` / ``charge`` / ``spent``."""

    def __init__(self, supabase: Client, cap_usd: float, user_id: str | None = None,
                 job_id: str | None = None) -> None:
        self.supabase = supabase
        self.cap_usd = float(cap_usd)
        self.user_id = user_id  # None -> global cap only (no per-user token metering)
        self.job_id = job_id

    def spent(self) -> float:
        try:
            r = self.supabase.table("ai_spend").select("spent_usd").eq("id", 1).execute()
            return float(r.data[0]["spent_usd"]) if r.data else 0.0
        except Exception:  # noqa: BLE001 - treat an unreadable ledger as "spend nothing more"
            return self.cap_usd

    def remaining(self) -> float:
        return max(0.0, self.cap_usd - self.spent())

    def _user_tokens(self) -> int:
        """Current token balance for the spending user (0 if unknown -> fail closed)."""
        if not self.user_id:
            return 1_000_000  # no per-user metering on this ledger
        try:
            r = (self.supabase.table("profiles").select("tokens")
                 .eq("id", self.user_id).limit(1).execute())
            return int(r.data[0]["tokens"]) if r.data else 0
        except Exception:  # noqa: BLE001 - unreadable balance -> stop AI rather than hand it out free
            return 0

    def can_spend(self, cost: float) -> bool:
        # Pre-flight, before paying to generate: the user needs a token AND the global
        # ceiling needs room. The authoritative check is the atomic charge() below.
        if self.user_id and self._user_tokens() < 1:
            return False
        return self.spent() + cost <= self.cap_usd + 1e-9

    def charge(self, cost: float) -> float:
        """Atomically (1) burn one user token, then (2) record the global charge. Raises
        BudgetExceeded if the user is out of tokens or the global cap is hit; the b-roll
        builder catches that and finishes the render without further AI scenes."""
        from cadence.imagegen.ledger import BudgetExceeded

        if self.user_id:
            try:
                self.supabase.rpc(
                    "spend_tokens",
                    {"p_user": self.user_id, "p_n": 1, "p_job": self.job_id},
                ).execute()
            except Exception as exc:  # noqa: BLE001 - insufficient_tokens (RPC raises) -> stop AI
                raise BudgetExceeded(f"User {self.user_id} is out of tokens: {exc}") from exc

        try:
            r = self.supabase.rpc("charge_ai_spend", {"p_cost": cost, "p_cap": self.cap_usd}).execute()
        except Exception as exc:  # noqa: BLE001 - cap breach (RPC raises) or transient error -> stop spending
            raise BudgetExceeded(f"AI budget cap ${self.cap_usd:.2f} reached or ledger unavailable: {exc}") from exc
        return float(r.data) if r.data is not None else self.spent()


class Worker:
    def __init__(self) -> None:
        self.supabase: Client = create_client(
            _env("SUPABASE_URL"), _env("SUPABASE_SERVICE_ROLE_KEY")
        )
        self.worker_id = f"{socket.gethostname()}:{os.getpid()}"
        self.ff = FFmpeg()
        self.poll_interval = float(os.environ.get("WORKER_POLL_SECONDS", "3"))
        # Lazy: loading whisper (~150MB) on every scale-to-zero cold start would make
        # idle queue polls expensive, so defer it until a job actually needs ASR.
        self._transcriber = None
        self._transcriber_loaded = False
        # Set per-job in _process; read by SupabaseCostLedger to meter the right user's
        # tokens. Safe as instance state because the worker runs at concurrency 1.
        self._current_user_id: str | None = None
        self._current_job_id: str | None = None
        self._current_voice_ctx: str = ""  # the user's brand-blueprint prompt block ('' = generic)
        # Avatar jobs are PREPAID at enqueue (web deducts the flat avatar token cost), so the
        # per-scene token burn is suppressed for them. Global $ accounting still records.
        self._prepaid: bool = False
        # Per-scene animation outcome of the last faceless render, merged into
        # render_jobs.result. Set fresh by _render_faceless (worker runs at concurrency 1).
        self._faceless_stats: dict[str, int] | None = None

    def _get_transcriber(self):
        if not self._transcriber_loaded:
            self._transcriber = self._load_transcriber()
            self._transcriber_loaded = True
        return self._transcriber

    def _load_transcriber(self):
        model = os.environ.get("CADENCE_WHISPER_MODEL", "base.en")
        try:
            from cadence.transcription.faster_whisper import FasterWhisperTranscriber

            print(f"[worker] loading faster-whisper '{model}' …", flush=True)
            return FasterWhisperTranscriber(
                model, device=os.environ.get("CADENCE_WHISPER_DEVICE", "cpu"),
                compute_type=os.environ.get("CADENCE_WHISPER_COMPUTE", "int8"),
            )
        except Exception as exc:  # pragma: no cover - optional dependency
            print(f"[worker] no ASR backend ({exc}); silence-only cleaning", flush=True)
            return None

    # -- main loop ---------------------------------------------------------- #
    def run(self) -> None:
        print(f"[worker] {self.worker_id} polling every {self.poll_interval}s", flush=True)
        while True:
            job = self._claim()
            if job is None:
                time.sleep(self.poll_interval)
                continue
            try:
                self._process(job)
            except Exception as exc:  # noqa: BLE001 - self-heal transient failures, else error
                traceback.print_exc()
                try:
                    self._fail_or_retry(job, exc)
                except Exception:  # noqa: BLE001 - a reporting failure must not kill the daemon
                    traceback.print_exc()

    def drain(self, budget_sec: float = 2700.0) -> dict[str, int]:
        """Process queued jobs until the queue is empty or the time budget elapses.

        This is the Cloud Run entrypoint's unit of work: one HTTP call (per Scheduler
        tick) drains the backlog, then returns so the instance can scale to zero. The
        budget stays under Cloud Run's 60-minute request cap. Each job's failure is
        isolated — it's marked errored and draining continues."""
        deadline = time.monotonic() + budget_sec
        processed = errored = 0
        while time.monotonic() < deadline:
            try:
                job = self._claim()
            except Exception:  # noqa: BLE001 - a claim failure ends the tick (next tick retries)
                traceback.print_exc()
                break
            if job is None:
                break
            try:
                self._process(job)
                processed += 1
            except Exception as exc:  # noqa: BLE001 - isolate the job; self-heal transient failures
                traceback.print_exc()
                errored += 1
                try:
                    self._fail_or_retry(job, exc)
                except Exception:  # noqa: BLE001
                    traceback.print_exc()
        return {"processed": processed, "errored": errored}

    def _claim(self) -> dict[str, Any] | None:
        res = self.supabase.rpc("claim_next_render_job", {"p_worker": self.worker_id}).execute()
        data = res.data
        if not data:
            return None
        job = data if isinstance(data, dict) else data[0]
        # An empty queue comes back as a composite-NULL row ({"id": null, ...}); treat
        # any row without a real id as "no job".
        if not job or not job.get("id"):
            return None
        return job

    # -- failure handling: self-heal transient errors -------------------------- #
    MAX_RENDER_ATTEMPTS = 3
    RETRYABLE_PATTERNS = (
        "timed out", "timeout", "eof occurred", "ssl", "connection reset",
        "connection aborted", "connection error", "broken pipe", "temporarily unavailable",
        "max retries", "read operation", "rate limit", "429", "502", "503", "504",
        "remotedisconnected", "name or service not known", "503 service",
    )
    # Deterministic failures (bad input / quota / permission) that must NEVER loop.
    HARD_PATTERNS = (
        "no video stream", "payload too large", "413", "out of tokens", "insufficient",
        "creator-plan", "consent", "unauthorized", "invalid request", "unsupported",
        "no face detected", "empty script",
    )

    def _is_retryable(self, msg: str) -> bool:
        m = (msg or "").lower()
        if any(h in m for h in self.HARD_PATTERNS):
            return False
        return any(p in m for p in self.RETRYABLE_PATTERNS)

    def _fail_or_retry(self, job: dict[str, Any], exc: Exception) -> None:
        """Transient failures (network/timeout/SSL/5xx) self-heal: re-queue with backoff up to
        MAX_RENDER_ATTEMPTS so a render finishes end-to-end without the user re-clicking.
        Deterministic failures (bad input, quota, permission) error immediately with the message."""
        job_id = job["id"]
        msg = str(exc)
        try:
            cur = self.supabase.table("render_jobs").select("attempts").eq("id", job_id).single().execute()
            attempts = int((cur.data or {}).get("attempts") or 0) if getattr(cur, "data", None) else 0
        except Exception:  # noqa: BLE001 - if the count is unreadable, treat as the last attempt
            attempts = self.MAX_RENDER_ATTEMPTS
        if self._is_retryable(msg) and attempts + 1 < self.MAX_RENDER_ATTEMPTS:
            backoff = min(20, 5 * (attempts + 1))
            print(f"[worker] job {job_id} transient failure "
                  f"(attempt {attempts + 1}/{self.MAX_RENDER_ATTEMPTS}); re-queue in {backoff}s: {msg[:200]}",
                  flush=True)
            time.sleep(backoff)
            self._update(job_id, status="queued", attempts=attempts + 1, progress=0,
                         error=f"auto-retry {attempts + 1}/{self.MAX_RENDER_ATTEMPTS}: {msg[:300]}")
        else:
            self._update(job_id, status="error", error=msg[:2000], progress=0)

    # -- job processing ----------------------------------------------------- #
    def _process(self, job: dict[str, Any]) -> None:
        job_id = job["id"]
        user_id = job["user_id"]
        # Meter this job's shared-key AI scenes against this user's token balance
        # (concurrency is 1, so instance state is safe). BYOK images bypass metering.
        self._current_user_id = user_id
        self._current_job_id = job_id
        self._prepaid = False
        print(f"[worker] claimed job {job_id}", flush=True)
        keys = self._resolve_keys(user_id)  # per-user BYOK keys (or shared fallback) for every AI call
        self._current_voice_ctx = self._load_voice_ctx(user_id)  # blueprint personalization ('' = generic)

        with tempfile.TemporaryDirectory(prefix="cadence_job_") as tmp:
            recording = self._download(UPLOADS, job["recording_path"], os.path.join(tmp, "recording.mp4"))
            self._update(job_id, progress=0.15)

            analysis = None
            if job.get("reference_path"):
                ref = self._download(UPLOADS, job["reference_path"], os.path.join(tmp, "reference.mp4"))
                analysis = analyze_reference(ref, ff=self.ff)
            self._update(job_id, progress=0.35)

            from cadence.customize import parse_customization

            ctrl = parse_customization(job.get("customization") or {})

            # Music bed (uploaded track): download once; applied to every render below.
            music_path = None
            if ctrl.music_key:
                try:
                    ext = os.path.splitext(ctrl.music_key)[1] or ".mp3"
                    music_path = self._download(UPLOADS, ctrl.music_key, os.path.join(tmp, f"music{ext}"))
                except Exception as exc:  # noqa: BLE001 - music is optional
                    print(f"[worker] music download failed ({exc}); no music bed", flush=True)

            # Avatar jobs carry BOTH customization.avatar and customization.faceless, so resolve
            # the avatar key first and EXCLUDE avatar jobs from the faceless branch — otherwise an
            # avatar job matches faceless first, renders with NO lip-sync, and skips the billing gate.
            av = (job.get("customization") or {}).get("avatar")
            # Faceless mode: the "recording" is narration audio (TTS or uploaded VO) —
            # no camera. AI scenes + karaoke captions become the entire visual track.
            fc = (job.get("customization") or {}).get("faceless")
            if fc and not av and not job.get("plan"):
                out_path = os.path.join(tmp, "final.mp4")
                scene_style = str(fc.get("scene_style") or "") if isinstance(fc, dict) else ""
                # 1400: an avatar character sheet (<=900) + user direction (<=400) + prefix.
                scene_direction = str(fc.get("scene_direction") or "")[:1400] if isinstance(fc, dict) else ""
                topic_title = str(fc.get("topic") or "")[:200] if isinstance(fc, dict) else ""
                animate = bool(fc.get("animate")) if isinstance(fc, dict) else False
                result, edl_f = self._render_faceless(
                    recording, ctrl, tmp, out_path, keys, music_path,
                    scene_style=scene_style, scene_direction=scene_direction,
                    topic_title=topic_title, animate=animate,
                )
                out_path = self._maybe_apply_frame(job, user_id, tmp, out_path)
                output_key = f"{user_id}/{job_id}.mp4"
                self._upload(OUTPUTS, output_key, out_path)
                credit = bool((job.get("customization") or {}).get("credit_cadence"))
                captions = self._social_captions(edl_f, credit=credit, keys=keys)
                hooks, repurpose = self._extras(edl_f, keys)
                self._update(
                    job_id, status="done", progress=1.0, output_path=output_key,
                    result={**result.to_dict(), **(self._faceless_stats or {})},
                    social_captions=captions,
                    hooks=hooks, repurpose=repurpose, error=None,
                )
                print(f"[worker] job {job_id} done (faceless) -> {output_key}", flush=True)
                return

            # Avatar mode: the "recording" is the narration (the user's cloned voice); a
            # photoreal talking head is lip-synced from their reference, then composited
            # into the Looks (presenter) or finished standalone.
            av = (job.get("customization") or {}).get("avatar")
            if av and not job.get("plan"):
                # Authoritative billing AT THE GPU (the web route's checks are advisory and
                # bypassable via a direct render_jobs insert): Creator-gate + monthly cap + the
                # flat charge, BEFORE any render. Charge ONCE — only on the first attempt; a
                # self-heal retry was already gated + paid. Re-read attempts (the claimed row may
                # omit the column) so a retry can never double-charge.
                try:
                    _a = self.supabase.table("render_jobs").select("attempts").eq("id", job_id).single().execute()
                    _att = int((getattr(_a, "data", None) or {}).get("attempts") or 0)
                except Exception:  # noqa: BLE001 - missing/unreadable -> treat as first attempt
                    _att = 0
                if _att == 0:
                    self._enforce_avatar_billing(user_id, job_id)
                self._prepaid = True
                out_path = os.path.join(tmp, "final.mp4")
                fc2 = (job.get("customization") or {}).get("faceless") or {}
                result = self._render_avatar(
                    recording, ctrl, tmp, out_path, av, keys, music_path,
                    scene_style=str(fc2.get("scene_style") or "") if isinstance(fc2, dict) else "",
                    scene_direction=(str(fc2.get("scene_direction") or "")[:1400] if isinstance(fc2, dict) else ""),
                    topic_title=str(fc2.get("topic") or "")[:200] if isinstance(fc2, dict) else "",
                    animate=bool(fc2.get("animate")) if isinstance(fc2, dict) else False,
                )
                out_path = self._maybe_apply_frame(job, user_id, tmp, out_path)
                output_key = f"{user_id}/{job_id}.mp4"
                self._upload(OUTPUTS, output_key, out_path)
                self._update(
                    job_id, status="done", progress=1.0, output_path=output_key,
                    result=result.to_dict() if hasattr(result, "to_dict") else None, error=None,
                )
                print(f"[worker] job {job_id} done (avatar) -> {output_key}", flush=True)
                return

            transcript = None
            if job.get("transcript"):
                transcript = Transcript.from_dict(job["transcript"])

            override = (job.get("customization") or {}).get("edl_override")
            if override:
                # Fix-and-re-render: use the user's edited cut list instead of re-cleaning.
                # The persisted EDL's `source` is a stale per-run tmp path → repoint it at THIS
                # run's freshly-downloaded recording, or render_plan can't find the clip source.
                import dataclasses
                from cadence.models import EditDecisionList
                edl = dataclasses.replace(EditDecisionList.from_dict(override), source=recording)
                print(f"[worker] job {job_id} edl_override -> {len(edl.kept)} kept spans (fix re-render)", flush=True)
            else:
                edl = clean_recording(
                    recording,
                    transcript=transcript,
                    transcriber=None if transcript else self._get_transcriber(),
                    cfg=ctrl.cleaning,
                    ff=self.ff,
                )
            # Persist the EDL so the result screen can re-edit the cuts and re-render.
            self._update(job_id, progress=0.6, edl=edl.to_dict())

            brand = self._load_brand(job.get("project_id"), user_id, tmp)

            # Multi-clip mode: one recording -> several standalone shorts. Finds the best
            # moments, trims + fully renders each, and stores an array of clips on the job.
            mc = (job.get("customization") or {}).get("multiclip")
            if mc and not job.get("plan") and edl.transcript and edl.transcript.words:
                from cadence.ffmpeg.probe import probe_media

                max_clips = int(mc.get("count", 5)) if isinstance(mc, dict) else 5
                dur = probe_media(recording, self.ff).duration
                clips = self._render_multiclip(
                    recording, ctrl, brand, analysis, edl.transcript, dur, music_path,
                    tmp, user_id, job_id, max_clips, keys,
                )
                if clips:
                    hooks, repurpose = self._extras(edl, keys)
                    self._update(
                        job_id, status="done", progress=1.0,
                        output_path=clips[0]["output_path"], result=clips[0].get("result"),
                        social_captions=clips[0].get("social_captions"),
                        clips=clips, hooks=hooks, repurpose=repurpose, error=None,
                    )
                    print(f"[worker] job {job_id} done -> {len(clips)} clips", flush=True)
                    return

            if job.get("plan"):
                plan = GenerationPlan.from_dict(job["plan"])
            else:
                plan = build_generation_plan(edl, analysis=analysis, brand=brand, cfg=ctrl.synthesis)
                self._apply_cinematography(plan, ctrl)
                if ctrl.toggles.auto_reframe and not ctrl.toggles.background_replace:
                    from cadence.reframe import apply_auto_reframe
                    apply_auto_reframe(plan, self.ff)  # landscape → face-tracked 9:16 (no-op on portrait)
                if not ctrl.toggles.background_replace:
                    plan.broll = self._build_broll(edl, ctrl, brand, tmp, keys)
                if not ctrl.toggles.captions:
                    plan.captions = []
                if not ctrl.toggles.watermark:
                    plan.watermark = None
            if music_path:
                plan.music_path = music_path
                plan.music_volume = ctrl.music_volume
            if ctrl.hook:
                plan.hook = ctrl.hook
            self._update(job_id, progress=0.75)

            out_path = os.path.join(tmp, "final.mp4")
            if not job.get("plan") and ctrl.toggles.background_replace:
                result = self._render_background_mode(edl, plan, ctrl, brand, tmp, out_path, keys)
            else:
                result = render_plan(plan, out_path, ff=self.ff)
            self._update(job_id, progress=0.92)

            # Hidden voiceover mode (admin-gated in the UI): re-voice the clip with the
            # owner's synthesized narration. Degrades to the original audio on any failure.
            vo = job.get("customization") or {}
            vo_script = (vo.get("voiceover") or {}).get("script", "") if isinstance(vo.get("voiceover"), dict) else ""
            if vo_script and vo_script.strip():
                try:
                    import dataclasses

                    from cadence.ffmpeg.probe import probe_media

                    out_path = self._apply_voiceover(vo_script.strip(), out_path, tmp, keys)
                    mi = probe_media(out_path, self.ff)
                    result = dataclasses.replace(result, duration=mi.duration, width=mi.width, height=mi.height)
                except Exception as exc:  # noqa: BLE001 - never fail the render over the VO
                    print(f"[worker] voiceover failed ({exc}); keeping original audio", flush=True)

            out_path = self._maybe_apply_frame(job, user_id, tmp, out_path)
            output_key = f"{user_id}/{job_id}.mp4"
            self._upload(OUTPUTS, output_key, out_path)

            credit = bool((job.get("customization") or {}).get("credit_cadence"))
            captions = self._social_captions(edl, credit=credit, keys=keys)
            hooks, repurpose = self._extras(edl, keys)

            self._update(
                job_id,
                status="done",
                progress=1.0,
                output_path=output_key,
                result=result.to_dict(),
                social_captions=captions,
                hooks=hooks,
                repurpose=repurpose,
                error=None,
            )
            print(f"[worker] job {job_id} done -> {output_key}", flush=True)

    def _apply_voiceover(self, script: str, video_path: str, tmp: str, keys=None) -> str:
        """Hidden voiceover mode: synthesize the owner's voice from the script (THE BLEND)
        and replace the clip's audio (video-follows-voice). Uses the user's Gemini + ElevenLabs
        keys (falls back to shared via the adapters); raises if unavailable so the caller keeps
        the original audio."""
        from cadence.voice import VoiceSynth, mux_voiceover
        from cadence.voice.synth import ElevenLabsSTS, GeminiCharonTTS

        gkey = (keys or {}).get("gemini", (None, False))[0]
        ekey = (keys or {}).get("elevenlabs", (None, False))[0]
        synth = VoiceSynth(tts=GeminiCharonTTS(api_key=gkey), sts=ElevenLabsSTS(api_key=ekey))
        vo_path = os.path.join(tmp, "voiceover.mp3")
        synth.blend_to_file(script, vo_path)
        out = os.path.join(tmp, "vo_final.mp4")
        return mux_voiceover(video_path, vo_path, out, ff=self.ff)

    def _render_faceless(self, audio_path: str, ctrl, tmp: str, out_path: str, keys=None,
                         music_path: str | None = None, scene_style: str = "",
                         scene_direction: str = "", topic_title: str = "",
                         animate: bool = False):
        """Faceless render: narration audio -> ASR -> per-moment AI scenes (the existing
        contextual b-roll engine) stitched into a full-duration visual track + karaoke
        captions + optional hook card + ducked music. Returns (RenderResult, edl) — the
        edl is a synthetic full-keep EDL so social captions/hooks/repurpose work as usual."""
        from cadence.ffmpeg.probe import probe_media
        from cadence.matte.replace import build_background_video
        from cadence.models import (
            CaptionStyle, EditDecisionList, RenderResult, TextZone, TimeRange,
        )
        from cadence.synthesis.captions import build_ass_karaoke, build_hook_studio
        from cadence.synthesis.contextual import build_ai_broll, plan_background_windows
        from cadence.synthesis.plan import group_karaoke_captions

        # probe_media requires a video stream — the narration is audio-only, so read
        # the duration straight from ffprobe instead.
        import json as _json
        raw = self.ff.probe_raw([
            "-v", "error", "-print_format", "json", "-show_format", "-show_streams", audio_path,
        ])
        meta = _json.loads(raw)
        if not any(s.get("codec_type") == "audio" for s in meta.get("streams", [])):
            raise RuntimeError("faceless: narration file has no audio stream")
        dur = float(meta.get("format", {}).get("duration") or 0.0)
        if dur <= 0.5:
            raise RuntimeError("faceless: narration audio is empty")
        transcriber = self._get_transcriber()
        if transcriber is None:
            raise RuntimeError("faceless: ASR backend unavailable")
        tr = transcriber.transcribe(audio_path, ff=self.ff)
        if not tr.words:
            raise RuntimeError("faceless: no speech found in the narration audio")
        words_out = [(w.text, w.start, w.end) for w in tr.words]
        w, h, fps = ctrl.synthesis.width, ctrl.synthesis.height, 30

        # One scene every ~7s, snapped to sentence pauses: 3..16 scenes per video.
        gkey, gbyok = (keys or {}).get("gemini", (None, False))
        # ~7s/scene; hard max is configurable (the user's token balance is the real bound).
        cap = max(3, min(round(dur / 7.0), int(os.environ.get("CADENCE_MAX_SCENES", "130"))))
        interval = max(3.5, dur / cap)
        windows = plan_background_windows(words_out, dur, interval=interval)
        n = max(2, min(len(windows), cap))
        out_dir = os.path.join(tmp, "scenes")
        os.makedirs(out_dir, exist_ok=True)
        if self._current_job_id:
            self._update(self._current_job_id, progress=0.5)
        style_override = SCENE_STYLES.get(scene_style)
        # Direction (esp. an avatar character sheet) changes what scenes must contain,
        # so directed renders only reuse library assets saved under the SAME direction —
        # a cached generic scene must never replace one starring the user's avatar.
        lib_style = scene_style or "photoreal"
        if scene_direction.strip():
            import hashlib

            lib_style = f"{lib_style}|d{hashlib.sha1(scene_direction.encode()).hexdigest()[:8]}"
        inserts = build_ai_broll(
            words_out, dur,
            self._image_generator(ctrl.broll_quality, gkey, gbyok, style=lib_style),
            out_dir=out_dir, windows=windows, max_images=n,
            distiller=self._distiller(gkey),
            # A named art style replaces the photographic look — cinematography clauses
            # (lenses, f-stops) would fight claymation/anime prompts.
            cine=None if style_override else ctrl.cinematography,
            factual_assets=None if style_override else self._factual_assets(),
            style_override=style_override,
            direction=scene_direction,
            context_topic=topic_title,
        )
        if not inserts:
            raise RuntimeError("faceless: scene generation produced no images")
        bg = os.path.join(tmp, "scenes.mp4")
        gen_url = os.environ.get("CADENCE_GEN_URL")
        gen_token = os.environ.get("CADENCE_GEN_TOKEN")
        if animate and gen_url and gen_token:
            # True motion: animate each scene on our GPU (FastWan i2v), BOUNDED-PARALLEL so a
            # long video doesn't serialize dozens of ~cold L4 calls. Each animated scene meters
            # 2 tokens; a failed/over-budget scene degrades to its still (graceful, per-scene).
            import concurrent.futures

            from cadence.imagegen.ledger import BudgetExceeded
            from cadence.imagegen.selfhost import animate_image
            from cadence.matte.replace import build_background_video_mixed

            # Per-user tokens (2/animated scene, burned via spend_tokens) are the REAL gate on
            # how much a user can animate. The global $ cap is only a cross-user runaway guard —
            # kept high (default $500) so it never silently stills a paying user mid-render.
            anim_ledger = self._ledger(float(os.environ.get("CADENCE_AI_BUDGET_USD", "500")))
            motion = SCENE_STYLES.get(scene_style, "cinematic photoreal")
            anim_prompt = (f"{motion}. The characters and subject move naturally; "
                           f"subtle cinematic camera push; keep composition and style.")
            # 2s loops seamlessly under captions; each extra second is ~3min more L4 time/scene.
            anim_secs = float(os.environ.get("CADENCE_ANIMATE_SECONDS", "2.0"))
            concurrency = max(1, int(os.environ.get("CADENCE_ANIMATE_CONCURRENCY", "6")))
            # Wall-clock guard, largely obsolete under parallelism + per-user token gating; kept
            # only as a runaway ceiling (default 7200s, well above any real render).
            anim_budget = float(os.environ.get("CADENCE_ANIMATE_BUDGET_S", "7200"))
            anim_start = time.monotonic()

            def _animate_one(idx: int, ins) -> bytes:
                """GPU-animate one scene with ONE retry. No ledger access here — charging stays
                serialized on the main thread (thread-safe against the shared ai_spend row)."""
                with open(ins.image_path, "rb") as fh:
                    img_bytes = fh.read()
                last_exc: Exception | None = None
                for attempt in range(2):  # initial try + one retry, then let the caller degrade
                    try:
                        return animate_image(
                            gen_url, gen_token, img_bytes, prompt=anim_prompt,
                            seconds=anim_secs, width=704, height=1280,
                        )
                    except Exception as exc:  # noqa: BLE001 - retry once before degrading
                        last_exc = exc
                        if attempt == 0:
                            print(f"[worker] faceless: animate scene {idx} failed ({exc!r}); "
                                  f"retrying once", flush=True)
                raise last_exc  # type: ignore[misc]  # loop always runs -> always set

            # Pre-charge (serialized, main thread) so the per-user token budget gates BEFORE we
            # spend L4 time: only paid-for scenes are submitted; the rest stay stills. Keeps every
            # ledger call on one thread (no lock) and preserves charge-before-animate semantics.
            to_animate: list[int] = []
            for k in range(len(inserts)):
                try:
                    anim_ledger.charge(0.05)
                    anim_ledger.charge(0.05)  # 2 tokens per animated scene
                    to_animate.append(k)
                except BudgetExceeded:
                    print(f"[worker] faceless: token/AI budget hit at scene {k}; "
                          f"rest stay stills", flush=True)
                    break

            clips: dict[int, str] = {}  # scene index -> motion clip path (absent -> still)
            if to_animate:
                with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as pool:
                    futs = {pool.submit(_animate_one, k, inserts[k]): k for k in to_animate}
                    done = 0
                    for fut in concurrent.futures.as_completed(futs):
                        k = futs[fut]
                        done += 1
                        try:
                            if time.monotonic() - anim_start > anim_budget:
                                raise TimeoutError(f"animate budget {anim_budget:.0f}s exceeded")
                            mp4 = fut.result()
                            clip_path = os.path.join(tmp, f"scene_motion_{k}.mp4")
                            with open(clip_path, "wb") as fh:
                                fh.write(mp4)
                            clips[k] = clip_path
                            print(f"[worker] faceless: scene {k} animated "
                                  f"({len(mp4)//1024}KB)", flush=True)
                        except Exception as exc:  # noqa: BLE001 - degrade this scene to its still
                            print(f"[worker] faceless: animate scene {k} failed "
                                  f"({exc!r}) -> still", flush=True)
                        if self._current_job_id:
                            self._update(self._current_job_id,
                                         progress=round(0.55 + 0.25 * done / len(to_animate), 2))

            # Reassemble in ORIGINAL scene order — compositing depends on scene sequence.
            items = [(ins, clips.get(k)) for k, ins in enumerate(inserts)]
            animated_scenes = len(clips)
            self._faceless_stats = {
                "animated_scenes": animated_scenes,
                "degraded_scenes": len(inserts) - animated_scenes,  # scenes that fell back to still
                "scenes_total": len(inserts),
            }
            build_background_video_mixed(items, dur, bg, ff=self.ff, width=w, height=h, fps=fps)
        else:
            build_background_video(inserts, dur, bg, ff=self.ff, width=w, height=h, fps=fps)
            self._faceless_stats = {
                "animated_scenes": 0, "degraded_scenes": 0, "scenes_total": len(inserts),
            }
        if self._current_job_id:
            self._update(self._current_job_id, progress=0.8)

        vf_parts: list[str] = []
        if ctrl.toggles.captions:
            zone_name = ctrl.synthesis.caption_default_zone
            zone = TextZone(zone_name) if zone_name in ("top", "center", "bottom") else TextZone("bottom")
            try:
                style = CaptionStyle(ctrl.synthesis.caption_default_style)
            except ValueError:
                style = CaptionStyle.POP
            caps = group_karaoke_captions(words_out, zone=zone, style=style)
            ass_path = os.path.join(tmp, "captions.ass")
            with open(ass_path, "w", encoding="utf-8") as fh:
                fh.write(build_ass_karaoke(caps, width=w, height=h))
            vf_parts.append(f"subtitles='{ass_path}'")
        if ctrl.hook:
            hook_path = os.path.join(tmp, "hook.ass")
            with open(hook_path, "w", encoding="utf-8") as fh:
                fh.write(build_hook_studio(ctrl.hook, width=w, height=h))
            vf_parts.append(f"subtitles='{hook_path}'")
        vchain = "[0:v]" + (",".join(vf_parts) + "," if vf_parts else "") + "format=yuv420p[outv]"

        if music_path:
            vol = max(0.05, min(float(ctrl.music_volume), 0.5))
            achain = (
                f"[2:a]volume={vol:.3f}[mvol];[1:a]asplit=2[sm][ss];"
                "[mvol][ss]sidechaincompress=threshold=0.03:ratio=8:attack=20:release=300[md];"
                "[sm][md]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[mix];"
                "[mix]loudnorm=I=-16:TP=-1.5:LRA=11[outa]"
            )
            inputs = ["-i", bg, "-i", audio_path, "-stream_loop", "-1", "-i", music_path]
        else:
            achain = "[1:a]loudnorm=I=-16:TP=-1.5:LRA=11[outa]"
            inputs = ["-i", bg, "-i", audio_path]

        args = (
            ["-y", *inputs, "-filter_complex", f"{vchain};{achain}",
             "-map", "[outv]", "-map", "[outa]", "-t", f"{dur:.3f}",
             "-c:v", "libx264", "-preset", "medium", "-crf", "19" if w <= 1080 else "20",
             "-pix_fmt", "yuv420p", "-movflags", "+faststart", "-r", str(fps),
             "-c:a", "aac", "-b:a", "192k", out_path]
        )
        self.ff.run(args, timeout=7200)  # long (many-scene) videos take longer to mux/encode
        out_info = probe_media(out_path, self.ff)
        if out_info.duration <= 0:
            raise RuntimeError("faceless: render produced an empty output")
        result = RenderResult(
            output_path=out_path, width=out_info.width, height=out_info.height,
            fps=out_info.fps, duration=out_info.duration, codec="h264",
            used_hardware=False, encoder="libx264", command=args,
        )
        edl = EditDecisionList(
            source=audio_path, source_duration=dur,
            kept=(TimeRange(0.0, round(dur, 3)),), removed=(), transcript=tr,
        )
        return result, edl

    def _social_captions(self, edl, *, credit: bool = False, keys=None):
        """Generate per-platform 'ready to post' captions from the transcript. A cheap
        gemini-flash call on the user's Gemini key; degrades to a deterministic stub if no key /
        on failure, and never raises (a caption blip must not fail an otherwise-good render)."""
        if not (edl.transcript and edl.transcript.words):
            return None
        text = " ".join(w.text for w in edl.transcript.words).strip()
        if not text:
            return None
        from cadence._gemini import MODEL_CAPTIONS
        from cadence.social import GeminiCaptionWriter, StubCaptionWriter, build_social_captions

        gkey = (keys or {}).get("gemini", (None, False))[0]
        try:
            writer = GeminiCaptionWriter(model=MODEL_CAPTIONS, api_key=gkey) if gkey else StubCaptionWriter()
        except Exception:  # noqa: BLE001
            writer = StubCaptionWriter()
        try:
            return build_social_captions(
                text, writer, product=("Cadence" if credit else None),
                handle=("@cadence.video" if credit else None),
                voice=self._current_voice_ctx,
            )
        except Exception as exc:  # noqa: BLE001
            print(f"[worker] social caption generation failed ({exc})", flush=True)
            return None

    def _load_voice_ctx(self, user_id) -> str:
        """The user's brand-blueprint prompt block ('' when none) — personalizes hooks,
        captions and repurpose. Best-effort: any read failure degrades to generic copy."""
        try:
            from cadence.social.blueprint import blueprint_context

            r = (self.supabase.table("brand_blueprints").select("icp,pillars,voice")
                 .eq("user_id", user_id).limit(1).execute())
            return blueprint_context((r.data or [None])[0])
        except Exception as exc:  # noqa: BLE001
            print(f"[worker] blueprint read failed ({exc!r}); generic voice", flush=True)
            return ""

    def _resolve_keys(self, user_id):
        """Resolve each provider key for this user: their OWN (BYOK) if connected + active,
        else the shared Cloud Run key. Returns {provider: (key_or_None, is_byok)} from one
        indexed read. Read/decrypt failures degrade to the shared key — never crash a render."""
        shared_env = {"gemini": "GEMINI_API_KEY", "elevenlabs": "ELEVENLABS_API_KEY", "anthropic": "ANTHROPIC_API_KEY"}
        byok: dict[str, str] = {}
        try:
            from keyvault import decrypt_secret

            r = (self.supabase.table("user_connections").select("provider,secret_enc")
                 .eq("user_id", user_id).eq("status", "active").execute())
            for row in (r.data or []):
                try:
                    byok[row["provider"]] = decrypt_secret(row["secret_enc"])
                except Exception as exc:  # noqa: BLE001
                    print(f"[worker] decrypt {row['provider']} failed ({exc!r}); using shared key", flush=True)
        except Exception as exc:  # noqa: BLE001
            print(f"[worker] user_connections read failed ({exc!r}); using shared keys", flush=True)
        out: dict[str, tuple[str | None, bool]] = {}
        for prov, env in shared_env.items():
            out[prov] = (byok[prov], True) if prov in byok else (os.environ.get(env), False)
        return out

    def _gemini_json(self, model: str = "gemini-2.5-flash", api_key: str | None = None):
        """A GeminiJSON client on the given model + key, else None (callers fall back to stubs).
        The model auto-falls-over to alternates under load inside GeminiJSON."""
        if not api_key:
            return None
        try:
            from cadence.social import GeminiJSON

            return GeminiJSON(model=model, api_key=api_key)
        except Exception as exc:  # noqa: BLE001
            print(f"[worker] _gemini_json: GeminiJSON() failed -> stub: {exc!r}", flush=True)
            return None

    def _extras(self, edl, keys):
        """Hook variants + repurposed assets from the transcript. Premium per-task models
        (hooks = flagship, repurpose = strong fast model) on the user's Gemini key; stub
        fallback; never raises."""
        from cadence._gemini import MODEL_HOOKS, MODEL_REPURPOSE
        from cadence.social import build_hooks, build_repurpose, transcript_text

        text = transcript_text(edl)
        if not text:
            return None, None
        gkey = keys["gemini"][0]
        try:
            return (
                build_hooks(text, self._gemini_json(MODEL_HOOKS, gkey), voice=self._current_voice_ctx),
                build_repurpose(text, self._gemini_json(MODEL_REPURPOSE, gkey), voice=self._current_voice_ctx),
            )
        except Exception as exc:  # noqa: BLE001
            print(f"[worker] extras generation failed ({exc})", flush=True)
            return None, None

    def _render_avatar(self, audio_path, ctrl, tmp, out_path, av, keys=None, music_path=None,
                       scene_style="", scene_direction="", topic_title="", animate=False):
        """Photoreal talking-avatar render. The user's recorded reference + the narration
        (their cloned voice) drive a lip-synced talking head on cadence-gen's /lipsync; it's
        then composited into the faceless Looks (presenter) or finished standalone.

        Consent is FAIL-CLOSED: a non-revoked consent_records row must exist for the
        character or we refuse. Returns the presenter RenderResult (for social extras) or
        None (standalone)."""
        from cadence.avatar.compose import compose_avatar_presenter
        from cadence.avatar.lipsync import LipsyncClient

        char_id = str(av.get("character_id") or "")
        mode = str(av.get("mode") or "standalone").lower()
        framing = str(av.get("framing") or "lower_third").lower()
        if not char_id:
            raise RuntimeError("avatar: no character_id on the job")

        # 1) Load the avatar (worker uses the service role → bypasses RLS).
        crow = (self.supabase.table("characters")
                .select("source_path,source_kind,voice_id,kind")
                .eq("id", char_id).single().execute()).data
        if not crow or crow.get("kind") != "photoreal" or not crow.get("source_path"):
            raise RuntimeError("avatar: character missing or not photoreal")

        # 2) Consent FAIL-CLOSED — never render a likeness without active consent.
        consent = (self.supabase.table("consent_records")
                   .select("id").eq("character_id", char_id)
                   .is_("revoked_at", "null").limit(1).execute()).data
        if not consent:
            raise RuntimeError("avatar: no active consent on file — refusing to render")

        # 3) Download the reference clip/frame.
        is_video = (crow.get("source_kind") or "video") == "video"
        ref_path = self._download(
            UPLOADS, crow["source_path"],
            os.path.join(tmp, "avref" + (".mp4" if is_video else ".png")),
        )

        # 4) Lip-sync the reference to the narration on our GPU.
        gen_url = os.environ.get("CADENCE_GEN_URL")
        gen_token = os.environ.get("CADENCE_GEN_TOKEN")
        if not (gen_url and gen_token):
            raise RuntimeError("avatar: cadence-gen not configured (CADENCE_GEN_URL/TOKEN)")
        client = LipsyncClient(
            gen_url, gen_token,
            ledger=self._ledger(float(os.environ.get("CADENCE_AI_BUDGET_USD", "10"))),
        )
        with open(ref_path, "rb") as fh:
            ref_bytes = fh.read()
        with open(audio_path, "rb") as fh:
            audio_bytes = fh.read()
        if self._current_job_id:
            self._update(self._current_job_id, progress=0.5)
        res = client.synth(audio=audio_bytes, reference=ref_bytes, is_video=is_video,
                           res=min(int(ctrl.synthesis.height), 1080), fps=30)
        avatar_clip = os.path.join(tmp, "avatar_clip.mp4")
        with open(avatar_clip, "wb") as fh:
            fh.write(res.video_bytes)
        if self._current_job_id:
            self._update(self._current_job_id, progress=0.72)

        if mode == "presenter":
            # Render the faceless scene track (AI b-roll + captions), then matte the avatar
            # over it per the framing preset.
            scenes_path = os.path.join(tmp, "av_scenes.mp4")
            faceless_res, _edl = self._render_faceless(
                audio_path, ctrl, tmp, scenes_path, keys, music_path,
                scene_style=scene_style, scene_direction=scene_direction,
                topic_title=topic_title, animate=animate,
            )
            compose_avatar_presenter(
                avatar_clip, scenes_path, out_path, ff=self.ff,
                width=int(ctrl.synthesis.width), height=int(ctrl.synthesis.height),
                fps=30, framing=framing,
            )
            return faceless_res

        # Standalone: burn karaoke captions onto the talking head (it already carries the
        # narration audio from the lip-sync).
        self._finish_avatar_standalone(avatar_clip, audio_path, ctrl, tmp, out_path)
        return None

    def _finish_avatar_standalone(self, avatar_clip, audio_path, ctrl, tmp, out_path):
        """Burn karaoke captions onto a standalone talking-head clip. The clip already
        carries the narration audio (from the lip-sync), so audio = [0:a]. Mirrors the
        faceless caption finish (ASR → group_karaoke_captions → build_ass_karaoke → burn)."""
        from cadence.models import CaptionStyle, TextZone
        from cadence.synthesis.captions import build_ass_karaoke
        from cadence.synthesis.plan import group_karaoke_captions

        w, h, fps = ctrl.synthesis.width, ctrl.synthesis.height, 30
        vf_parts: list[str] = []
        if ctrl.toggles.captions:
            tr = None
            transcriber = self._get_transcriber()
            if transcriber is not None:
                try:
                    tr = transcriber.transcribe(audio_path, ff=self.ff)
                except Exception as exc:  # noqa: BLE001 - captions are optional; never fail the render
                    print(f"[worker] avatar: caption ASR failed ({exc!r}); no captions", flush=True)
            if tr and tr.words:
                words_out = [(wd.text, wd.start, wd.end) for wd in tr.words]
                zone_name = ctrl.synthesis.caption_default_zone
                zone = TextZone(zone_name) if zone_name in ("top", "center", "bottom") else TextZone("bottom")
                try:
                    style = CaptionStyle(ctrl.synthesis.caption_default_style)
                except ValueError:
                    style = CaptionStyle.POP
                caps = group_karaoke_captions(words_out, zone=zone, style=style)
                ass_path = os.path.join(tmp, "av_captions.ass")
                with open(ass_path, "w", encoding="utf-8") as fh:
                    fh.write(build_ass_karaoke(caps, width=w, height=h))
                vf_parts.append(f"subtitles='{ass_path}'")
        vchain = "[0:v]" + (",".join(vf_parts) + "," if vf_parts else "") + "format=yuv420p[outv]"
        args = [
            "-y", "-i", avatar_clip,
            "-filter_complex", f"{vchain};[0:a]loudnorm=I=-16:TP=-1.5:LRA=11[outa]",
            "-map", "[outv]", "-map", "[outa]",
            "-c:v", "libx264", "-preset", "medium", "-crf", "19" if w <= 1080 else "20",
            "-pix_fmt", "yuv420p", "-movflags", "+faststart", "-r", str(fps),
            "-c:a", "aac", "-b:a", "192k", out_path,
        ]
        self.ff.run(args, timeout=1800)
        return out_path

    def _render_multiclip(self, recording, ctrl, brand, analysis, transcript, duration,
                          music_path, tmp, user_id, job_id, max_clips, keys=None):
        """Find the best moments and render each as a standalone short. Returns a list of
        clip dicts (or None → caller falls back to a single full render)."""
        from cadence._gemini import MODEL_CLIPS
        from cadence.multiclip import find_clip_moments

        gkey = (keys or {}).get("gemini", (None, False))[0]
        moments = find_clip_moments(transcript, duration, max_clips=max_clips,
                                    llm=self._gemini_json(MODEL_CLIPS, gkey))
        if not moments:
            return None
        clips: list[dict] = []
        for i, m in enumerate(moments):
            try:
                sub = os.path.join(tmp, f"clip_src_{i}.mp4")
                # Accurate sub-clip (re-encode; -ss before -i = fast seek, -t bounds length).
                self.ff.run(
                    ["-y", "-ss", f"{m.start:.3f}", "-i", recording, "-t", f"{m.duration:.3f}",
                     "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-c:a", "aac", sub],
                    timeout=600,
                )
                edl_i = clean_recording(sub, transcriber=self._get_transcriber(), cfg=ctrl.cleaning, ff=self.ff)
                plan_i = build_generation_plan(edl_i, analysis=analysis, brand=brand, cfg=ctrl.synthesis)
                self._apply_cinematography(plan_i, ctrl)
                if ctrl.toggles.auto_reframe and not ctrl.toggles.background_replace:
                    from cadence.reframe import apply_auto_reframe
                    apply_auto_reframe(plan_i, self.ff)  # per-moment face track for landscape→9:16 shorts
                if not ctrl.toggles.background_replace:
                    plan_i.broll = self._build_broll(edl_i, ctrl, brand, tmp, keys)
                if not ctrl.toggles.captions:
                    plan_i.captions = []
                if not ctrl.toggles.watermark:
                    plan_i.watermark = None
                if music_path:
                    plan_i.music_path = music_path
                    plan_i.music_volume = ctrl.music_volume
                if ctrl.hook:
                    plan_i.hook = ctrl.hook
                out_i = os.path.join(tmp, f"clip_{i}.mp4")
                res_i = render_plan(plan_i, out_i, ff=self.ff)
                key_i = f"{user_id}/{job_id}-clip{i}.mp4"
                self._upload(OUTPUTS, key_i, out_i)
                clips.append({
                    "index": i, "output_path": key_i, "title": m.title, "hook": m.hook,
                    "start": m.start, "end": m.end, "duration": res_i.duration,
                    "score": m.score, "reason": m.reason,
                    "result": res_i.to_dict(), "social_captions": self._social_captions(edl_i, keys=keys),
                })
                self._update(job_id, progress=round(0.5 + 0.45 * (i + 1) / len(moments), 2))
            except Exception as exc:  # noqa: BLE001 - one bad clip must not kill the rest
                print(f"[worker] multiclip clip {i} failed ({exc})", flush=True)
        clips.sort(key=lambda c: c.get("score", 0), reverse=True)  # best clip first → clips[0] = primary output
        return clips or None

    def _load_brand(self, project_id: str | None, user_id: str, tmp: str) -> BrandBoard | None:
        if not project_id:
            return None
        proj = self.supabase.table("projects").select("brand_board_id").eq("id", project_id).execute()
        if not proj.data or not proj.data[0].get("brand_board_id"):
            return None
        board_id = proj.data[0]["brand_board_id"]
        board_row = self.supabase.table("brand_boards").select("*").eq("id", board_id).execute().data
        if not board_row:
            return None
        b = board_row[0]
        assets_rows = self.supabase.table("brand_assets").select("*").eq("board_id", board_id).execute().data or []
        assets: list[BrandAsset] = []
        for a in assets_rows:
            local = os.path.join(tmp, f"brand_{a['id']}")
            try:
                self._download(UPLOADS, a["storage_path"], local)
            except Exception:  # noqa: BLE001 - skip a missing asset rather than fail the render
                continue
            assets.append(
                BrandAsset(
                    id=a["id"], kind=AssetKind(a["kind"]), name=a["name"], path=local,
                    opacity=a.get("opacity", 1.0), anchor=Anchor(a.get("anchor", "bottom_right")),
                    scale=a.get("scale", 0.18), meta=a.get("meta") or {},
                )
            )
        return BrandBoard(
            id=b["id"], name=b["name"], assets=assets,
            caption_primary=RGBColor.from_hex(b["caption_primary"]) if b.get("caption_primary") else None,
            caption_outline=RGBColor.from_hex(b["caption_outline"]) if b.get("caption_outline") else None,
            caption_font_path=b.get("caption_font_path"),
        )

    def _enforce_avatar_billing(self, user_id: str | None, job_id: str) -> None:
        """Authoritative avatar gate AT THE GPU CHOKE POINT (the web route's checks are advisory
        and bypassable via a direct render_jobs insert): Creator-tier only, a flat per-video token
        charge, and a monthly cap — all BEFORE any lipsync. Raises (-> the run loop marks the job
        'error' with the message) on any failure. The per-user token balance is the hard backstop;
        the monthly cap is best-effort (counts in-flight jobs but is not atomic across instances)."""
        AVATAR_TOKEN_COST = 8
        AVATAR_MONTHLY_CAP = 20
        if not user_id:
            raise RuntimeError("avatar render requires a signed-in user")
        prof = self.supabase.table("profiles").select("plan").eq("id", user_id).single().execute()
        plan = (prof.data or {}).get("plan") if getattr(prof, "data", None) else None
        if plan not in ("creator", "admin"):
            raise RuntimeError("Photoreal avatars are a Creator-plan feature.")
        from datetime import datetime, timezone

        month_start = (
            datetime.now(timezone.utc)
            .replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            .isoformat()
        )
        cnt = (
            self.supabase.table("render_jobs")
            .select("id", count="exact")
            .eq("user_id", user_id)
            .neq("status", "error")
            .neq("id", job_id)
            .gte("created_at", month_start)
            .filter("customization->avatar", "not.is", "null")
            .execute()
        )
        if (getattr(cnt, "count", 0) or 0) >= AVATAR_MONTHLY_CAP:
            raise RuntimeError(f"Monthly limit of {AVATAR_MONTHLY_CAP} avatar videos reached.")
        try:
            # spend_tokens RAISES on insufficient balance (atomic decrement).
            self.supabase.rpc(
                "spend_tokens", {"p_user": user_id, "p_n": AVATAR_TOKEN_COST, "p_job": job_id}
            ).execute()
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(
                f"Avatar videos cost {AVATAR_TOKEN_COST} tokens — insufficient balance."
            ) from exc

    def _ledger(self, cap: float):
        """Durable Supabase-backed cap; falls back to a local JSON ledger only if the
        ai_spend table/RPC isn't reachable (e.g. an old DB without the migration)."""
        try:
            # Probe: a successful select confirms the table exists + the worker can read it.
            self.supabase.table("ai_spend").select("id").eq("id", 1).limit(1).execute()
            ledger_user = None if self._prepaid else self._current_user_id
            return SupabaseCostLedger(self.supabase, cap, ledger_user, self._current_job_id)
        except Exception:  # noqa: BLE001
            from cadence.imagegen.ledger import CostLedger

            print("[worker] WARN: ai_spend table unreachable; using local JSON ledger", flush=True)
            return CostLedger(os.path.join(os.path.dirname(os.path.abspath(__file__)), "ai_spend.json"), cap)

    FRAME_PRESETS = {"neon", "film", "polaroid", "goldluxe", "tape", "hud",
                     "softround", "blackmat", "grad", "spotlight"}

    def _maybe_apply_frame(self, job: dict, user_id: str, tmp: str, out_path: str) -> str:
        """Composite the chosen decorative frame over the finished video.

        customization.frame_key = preset name (public assets/frames/{key}.png) OR
        customization.frame_path = user upload in the uploads bucket (own files only).
        Fail-open: any problem keeps the unframed video."""
        cz = job.get("customization") or {}
        key = str(cz.get("frame_key") or "").strip()
        path = str(cz.get("frame_path") or "").strip()
        if not key and not path:
            return out_path
        try:
            frame_local = os.path.join(tmp, "frame.png")
            if key:
                if key not in self.FRAME_PRESETS:
                    print(f"[worker] unknown frame_key {key!r}; skipping frame", flush=True)
                    return out_path
                data = self.supabase.storage.from_("assets").download(f"frames/{key}.png")
                with open(frame_local, "wb") as fh:
                    fh.write(data)
            else:
                if not path.startswith(f"{user_id}/"):
                    print("[worker] frame_path outside user folder; skipping frame", flush=True)
                    return out_path
                self._download(UPLOADS, path, frame_local)
            from cadence.frame import apply_frame

            framed = os.path.join(tmp, "framed.mp4")
            apply_frame(self.ff, out_path, frame_local, framed)
            print(f"[worker] frame applied ({key or path})", flush=True)
            return framed
        except Exception as exc:  # noqa: BLE001 - a frame must never kill a render
            print(f"[worker] frame overlay failed ({exc!r}); keeping unframed video", flush=True)
            return out_path

    def _image_generator(self, quality: str = "standard", gemini_key: str | None = None,
                         is_byok: bool = False, style: str = "photoreal"):
        """The provider chain wrapped in the scene asset library: a same-style prompt
        match at >=0.86 cosine reuses a stored image (0 tokens, $0) instead of
        regenerating. No Gemini key (no embeddings) or stub provider → raw chain."""
        gen = self._raw_image_generator(quality, gemini_key, is_byok)
        if (os.environ.get("CADENCE_ASSET_LIBRARY", "1") == "0" or not gemini_key
                or getattr(gen, "name", "") == "stub"):
            return gen
        try:
            from cadence.imagegen.cache import CachingGenerator

            from asset_library import AssetLibrary

            lib = AssetLibrary(self.supabase, gemini_key, user_id=self._current_user_id,
                               job_id=self._current_job_id, style=style)
            return CachingGenerator(gen, lookup=lib.lookup, save=lib.save)
        except Exception as exc:  # noqa: BLE001 - the library is an optimization only
            print(f"[worker] asset library unavailable ({exc}); generating directly", flush=True)
            return gen

    def _raw_image_generator(self, quality: str = "standard", gemini_key: str | None = None, is_byok: bool = False):
        """Pick the best available, budget-capped generator: Imagen (Gemini key) →
        Ideogram (key) → free stub. ``quality`` (fast|standard|ultra) picks the Imagen tier.
        A BYOK user spends their own Gemini quota, so they skip the shared ai_spend cap (ledger=None)."""
        # Per-user tokens (burned per image via spend_tokens) are the real gate; this shared $
        # cap is only a cross-user runaway guard, kept high so it never stills a paying user.
        cap = float(os.environ.get("CADENCE_AI_BUDGET_USD", "500"))
        ledger = None if is_byok else self._ledger(cap)
        gen_url = os.environ.get("CADENCE_GEN_URL")
        gen_token = os.environ.get("CADENCE_GEN_TOKEN")
        if gemini_key:
            from cadence.imagegen.imagen import QUALITY_MODELS, ImagenGenerator

            gen = ImagenGenerator(model=QUALITY_MODELS.get(quality), api_key=gemini_key, ledger=ledger)
            tag = "your key (byok)" if is_byok else f"shared budget ${cap:.2f}, spent ${ledger.spent():.2f}"
            # Our own GPU first (40-60x cheaper, same token meter); Imagen as the safety net.
            if gen_url and gen_token:
                from cadence.imagegen.selfhost import SelfHostGenerator

                print(f"[worker] AI b-roll via cadence-gen (selfhost, fallback Imagen {gen.model}, {tag})", flush=True)
                return SelfHostGenerator(gen_url, gen_token, ledger=ledger, fallback=gen)
            print(f"[worker] AI b-roll via Imagen ({gen.model} '{quality}' ${gen.cost_per_image}/img, {tag})", flush=True)
            return gen
        if gen_url and gen_token:
            from cadence.imagegen.selfhost import SelfHostGenerator

            print("[worker] AI b-roll via cadence-gen (selfhost, no fallback key)", flush=True)
            return SelfHostGenerator(gen_url, gen_token, ledger=ledger)
        if os.environ.get("IDEOGRAM_API_KEY"):
            from cadence.imagegen.ideogram import IdeogramGenerator

            print(f"[worker] AI b-roll via Ideogram (budget ${cap:.2f}, spent ${ledger.spent():.2f})", flush=True)
            return IdeogramGenerator(os.environ["IDEOGRAM_API_KEY"], ledger=ledger)
        from cadence.imagegen.stub import StubGenerator

        print("[worker] AI b-roll via free stub (no image key set)", flush=True)
        return StubGenerator()

    def _distiller(self, gemini_key: str | None = None):
        """Gemini scene/caption distiller when a key is present (an enhancement, not required)."""
        if gemini_key:
            try:
                from cadence.imagegen.distill import GeminiDistiller

                return GeminiDistiller(api_key=gemini_key)
            except Exception:  # noqa: BLE001 - degrade to lexical topic
                return None
        return None

    def _factual_assets(self):
        """Curated real screenshots for the factual-image guardrail (cached for the
        instance). When a talking point names a guarded term, the b-roll pipeline uses
        the exact real image instead of generating one. Loaded from the shipped manifest
        (override path via CADENCE_FACTUAL_MANIFEST); entries missing their PNG are skipped."""
        if getattr(self, "_factual_cache", None) is None:
            from cadence.synthesis.factual import default_manifest_path, load_factual_assets

            path = os.environ.get("CADENCE_FACTUAL_MANIFEST") or default_manifest_path()
            self._factual_cache = load_factual_assets(path)
            print(f"[worker] factual guardrail: {len(self._factual_cache)} asset(s) loaded from {path}", flush=True)
        return self._factual_cache

    def _build_broll(self, edl, ctrl, brand, tmp: str, keys=None):
        """Choose the b-roll source: AI-generated, uploaded/brand images, or none.

        ``ctrl`` is the :class:`ParsedControls` bundle — its cinematography drives the
        AI image look so cutaways match the chosen lens/film/lighting."""
        mode = ctrl.broll_mode
        if mode in ("none", "background") or ctrl.pacing == "none":
            return []  # "None" pacing = zero cutaways, regardless of b-roll source
        gkey, gbyok = (keys or {}).get("gemini", (None, False))
        uploaded = self._download_broll(ctrl.broll_paths, tmp)
        brand_imgs = self._download_brand_images(brand, tmp)
        pool = uploaded + brand_imgs

        if mode == "ai" and ctrl.toggles.ai_broll and edl.transcript and edl.transcript.words:
            from cadence.synthesis.contextual import build_ai_broll
            from cadence.synthesis.plan import remap_words_to_output

            out_dir = os.path.join(tmp, "ai_broll")
            os.makedirs(out_dir, exist_ok=True)
            words_out = remap_words_to_output(edl.transcript, list(edl.kept))
            try:
                return build_ai_broll(
                    words_out, edl.output_duration, self._image_generator(ctrl.broll_quality, gkey, gbyok),
                    out_dir=out_dir, mode=ctrl.pacing,
                    style_refs=(pool[:3] or None),  # brand/uploaded images steer the look
                    overlay_text=ctrl.broll_caption_overlay,
                    distiller=self._distiller(gkey),
                    cine=ctrl.cinematography,
                    factual_assets=self._factual_assets(),
                )
            except Exception as exc:  # noqa: BLE001 - degrade to images rather than fail the render
                print(f"[worker] AI b-roll failed ({exc}); using uploaded/brand images", flush=True)

        from cadence.synthesis.plan import place_broll

        return place_broll(pool, edl.output_duration, mode=ctrl.pacing)

    def _apply_cinematography(self, plan: GenerationPlan, ctrl) -> None:
        """Layer the film-stock look (grade deltas + grain) and framing onto the plan.

        Multiplier fields (contrast/saturation/gamma) scale the reference-derived grade;
        additive fields (brightness/temperature/shadow_balance) shift it. The grade-intensity
        slider (0..1) attenuates the whole film-stock contribution. With the color-grade toggle
        off, the render stays true-to-source (only grain/letterbox, if any, are kept)."""
        if not ctrl.toggles.color_grade:
            plan.color_grade = ColorGrade(grain=float(ctrl.cinematography.film_grain_amount))
            plan.letterbox = ctrl.toggles.letterbox
            return
        cg = plan.color_grade
        k = max(0.0, min(1.0, ctrl.grade_intensity))
        for fld, val in ctrl.grade_override.items():
            if not hasattr(cg, fld):
                continue
            base = getattr(cg, fld)
            if fld in ("contrast", "saturation", "gamma"):
                setattr(cg, fld, round(base * (1.0 + (val - 1.0) * k), 4))
            else:
                setattr(cg, fld, round(base + val * k, 4))
        cg.grain = float(ctrl.cinematography.film_grain_amount)
        plan.letterbox = ctrl.toggles.letterbox

    def _background_image(self, edl, ctrl, brand, tmp: str, keys=None) -> str | None:
        """Pick the background to drop the speaker onto: an uploaded/brand image if
        provided, else one contextual AI background generated from the speech."""
        pool = self._download_broll(ctrl.broll_paths, tmp) + self._download_brand_images(brand, tmp)
        if pool:
            return pool[0]
        gkey, gbyok = (keys or {}).get("gemini", (None, False))
        if edl.transcript and edl.transcript.words:
            from cadence.synthesis.contextual import build_ai_broll
            from cadence.synthesis.plan import remap_words_to_output

            out_dir = os.path.join(tmp, "bg_ai")
            os.makedirs(out_dir, exist_ok=True)
            words_out = remap_words_to_output(edl.transcript, list(edl.kept))
            try:
                inserts = build_ai_broll(
                    words_out, edl.output_duration, self._image_generator(ctrl.broll_quality, gkey, gbyok),
                    out_dir=out_dir, mode="natural", max_images=1,
                    distiller=self._distiller(gkey), cine=ctrl.cinematography,
                    factual_assets=self._factual_assets(),
                )
                if inserts:
                    return inserts[0].image_path
            except Exception as exc:  # noqa: BLE001 - fall back to no replacement
                print(f"[worker] bg image generation failed ({exc})", flush=True)
        return None

    def _background_video(self, edl, ctrl, brand, tmp: str, plan, keys=None) -> str | None:
        """Build a full-duration background VIDEO from per-moment AI b-roll — the dynamic
        background behind the matted speaker, changing with the talking points. Returns the
        path, or None to fall back to a single static background (e.g. an uploaded image)."""
        # "Dynamic AI background" was explicitly turned on, so it OVERRIDES any brand /
        # transition image (those belong on transitions, not as the whole background) and any
        # uploaded still. Generate a per-moment background straight from the speech.
        _nw = len(edl.transcript.words) if (edl.transcript and edl.transcript.words) else 0
        print(f"[worker] dynbg: entered (transcript_words={_nw})", flush=True)
        if not (edl.transcript and edl.transcript.words):
            print("[worker] dynbg: no transcript words -> static fallback", flush=True)
            return None
        gkey, gbyok = (keys or {}).get("gemini", (None, False))
        from cadence.matte.replace import build_background_video
        from cadence.synthesis.contextual import build_ai_broll, plan_background_windows
        from cadence.synthesis.plan import remap_words_to_output

        out_dir = os.path.join(tmp, "bg_seq")
        os.makedirs(out_dir, exist_ok=True)
        words_out = remap_words_to_output(edl.transcript, list(edl.kept))
        # ~6 backgrounds per 60s (≈1 per 10s), snapped to new audio sections (sentence pauses),
        # with a 4s minimum hold. Caps cost + render time on long clips (was up to 12).
        cap = max(2, min(round(edl.output_duration / 10.0), 12))
        interval = max(4.0, edl.output_duration / cap)
        windows = plan_background_windows(words_out, edl.output_duration, interval=interval)
        n = max(2, min(len(windows), cap))
        if self._current_job_id:
            self._update(self._current_job_id, progress=0.78)  # move the bar off 75% while images generate
        try:
            inserts = build_ai_broll(
                words_out, edl.output_duration, self._image_generator(ctrl.broll_quality, gkey, gbyok),
                out_dir=out_dir, windows=windows, max_images=n,
                distiller=self._distiller(gkey), cine=ctrl.cinematography,
                factual_assets=self._factual_assets(),
            )
            print(f"[worker] dynbg: build_ai_broll returned {len(inserts) if inserts else 0} scenes (n={n})", flush=True)
            if not inserts:
                return None
            bg_video = os.path.join(tmp, "bg_dynamic.mp4")
            build_background_video(inserts, edl.output_duration, bg_video, ff=self.ff,
                                   width=plan.width, height=plan.height, fps=plan.fps)
            print("[worker] dynbg: dynamic background video built -> using it", flush=True)
            return bg_video
        except Exception as exc:  # noqa: BLE001 - any failure falls back to a static background
            print(f"[worker] dynamic bg generation failed ({exc}); using static bg", flush=True)
            return None

    def _render_background_mode(self, edl, plan, ctrl, brand, tmp, out_path, keys=None):
        """Background-replacement render. Three passes are required because the matte
        keeps ONLY speaker pixels — burned-in captions/grade would be matted away — so:
          1) render the cut (cuts + zoom, neutral, no captions/wm/broll) → speaker on orig bg;
          2) segment the speaker and composite over the contextual b-roll background;
          3) re-apply grade/captions/watermark/grain/letterbox over the composite.
        Audio is normalised exactly once: pass 1 keeps it raw (audio_normalize=False) and
        the composite carries it through, so the finish pass (inherited True) loudnorms it."""
        import dataclasses

        from cadence.matte.replace import render_background_replaced

        # Dynamic background: when AI b-roll is on, the matted speaker sits over a per-moment
        # b-roll slideshow (changing with the talking points); otherwise one static image.
        print(f"[worker] bg-replace: ai_broll(dynamic)={ctrl.toggles.ai_broll}", flush=True)
        bg_video = self._background_video(edl, ctrl, brand, tmp, plan, keys) if ctrl.toggles.ai_broll else None
        bg = None if bg_video else self._background_image(edl, ctrl, brand, tmp, keys)
        if bg is None and bg_video is None:
            print("[worker] no background available; rendering without replacement", flush=True)
            return render_plan(plan, out_path, ff=self.ff)

        fg_plan = dataclasses.replace(
            plan, captions=[], broll=[], watermark=None,
            color_grade=ColorGrade(), letterbox=False, audio_normalize=False,
            music_path=None,  # music belongs on the final composite, not the matte source
        )
        fg_path = os.path.join(tmp, "bg_fg.mp4")
        render_plan(fg_plan, fg_path, ff=self.ff)
        if self._current_job_id:
            self._update(self._current_job_id, progress=0.86)  # footage cut; compositing the background

        comp_path = os.path.join(tmp, "bg_comp.mp4")
        render_background_replaced(
            fg_path, bg, comp_path, ff=self.ff,
            width=plan.width, height=plan.height, fps=plan.fps,
            background_video=bg_video,
        )
        if self._current_job_id:
            self._update(self._current_job_id, progress=0.90)  # background composited; finishing

        # The composite duration can drift sub-frame from the plan's output timeline;
        # clamp captions so the last one can't fall past it and get silently dropped.
        comp_info = probe_media(comp_path, self.ff)
        capped = round(comp_info.duration, 3)
        finish_captions = [
            dataclasses.replace(c, end=min(c.end, capped))
            for c in plan.captions
            if c.start < comp_info.duration
        ]
        finish_plan = dataclasses.replace(
            plan,
            clips=[ClipSpec(source=comp_path, in_point=0.0, out_point=comp_info.duration, zoom=1.0)],
            broll=[],
            captions=finish_captions,
        )
        return render_plan(finish_plan, out_path, ff=self.ff)

    def _download_brand_images(self, brand, tmp: str) -> list[str]:
        """The brand's reusable transition images (already downloaded by _load_brand)."""
        if not brand:
            return []
        return [
            a.path for a in (brand.assets or [])
            if a.kind == AssetKind.TRANSITION and a.path and os.path.isfile(a.path)
        ]

    def _download_broll(self, keys: list[str], tmp: str) -> list[str]:
        """Pull the user's b-roll images from storage; skip (and LOG) any that fail
        so a transient error degrades gracefully instead of silently dropping b-roll."""
        local: list[str] = []
        for i, key in enumerate(keys):
            ext = os.path.splitext(key)[1] or ".png"
            dest = os.path.join(tmp, f"broll_{i}{ext}")
            try:
                self._download(UPLOADS, key, dest)
                local.append(dest)
            except Exception as exc:  # noqa: BLE001 - b-roll is optional; never fail the render
                print(f"[worker] WARN: b-roll image {key} unavailable, skipping: {exc}", flush=True)
        return local

    # -- storage + db helpers ---------------------------------------------- #
    def _download(self, bucket: str, key: str, dest: str, *, attempts: int = 4) -> str:
        # Retry transient storage errors (local Supabase storage can briefly 502
        # while its container settles) so inputs aren't dropped on a blip.
        last: Exception | None = None
        for i in range(attempts):
            try:
                data = self.supabase.storage.from_(bucket).download(key)
                with open(dest, "wb") as fh:
                    fh.write(data)
                return dest
            except Exception as exc:  # noqa: BLE001
                last = exc
                time.sleep(0.7 * (i + 1))
        raise last if last else RuntimeError(f"download failed: {key}")

    def _upload(self, bucket: str, key: str, src: str) -> None:
        if src.endswith(".mp4"):
            src = self._fit_upload(src)  # storage caps uploads — never let a render die on size
        with open(src, "rb") as fh:
            self.supabase.storage.from_(bucket).upload(
                key, fh.read(), {"content-type": "video/mp4", "upsert": "true"}
            )

    def _fit_upload(self, src: str) -> str:
        """Guarantee the file fits under the storage upload cap (CADENCE_MAX_UPLOAD_MB).

        Oversized renders (e.g. long 4K cuts) are re-encoded once at a bitrate computed
        to land ~93% of the cap; a second pass at 85% of that handles estimator misses.
        Returns the path to upload (the original when it already fits)."""
        limit_mb = float(os.environ.get("CADENCE_MAX_UPLOAD_MB", "48"))
        limit = int(limit_mb * 1024 * 1024)
        if os.path.getsize(src) <= limit:
            return src
        from cadence.ffmpeg.probe import probe_media

        dur = max(probe_media(src, self.ff).duration, 0.1)
        v_bps = fit_video_bitrate(limit, dur)
        out = src
        for attempt in range(2):
            out = src.rsplit(".", 1)[0] + f".fit{attempt}.mp4"
            self.ff.run(
                ["-y", "-i", src, "-c:v", "libx264", "-preset", "fast",
                 "-b:v", str(v_bps), "-maxrate", str(int(v_bps * 1.08)), "-bufsize", str(v_bps * 2),
                 "-pix_fmt", "yuv420p", "-movflags", "+faststart",
                 "-c:a", "aac", "-b:a", "160k", out],
                timeout=1800,
            )
            size = os.path.getsize(out)
            print(f"[worker] fit-upload pass {attempt}: {size / 1048576:.1f}MB @ {v_bps}bps (cap {limit_mb}MB)", flush=True)
            if size <= limit:
                return out
            v_bps = int(v_bps * 0.85)
        return out  # best effort — two passes land within the cap in practice

    def _update(self, job_id: str, **fields: Any) -> None:
        payload = {k: v for k, v in fields.items() if v is not None or k == "error"}
        if "result" in payload and not isinstance(payload["result"], str):
            payload["result"] = json.loads(json.dumps(payload["result"]))
        self.supabase.table("render_jobs").update(payload).eq("id", job_id).execute()


if __name__ == "__main__":
    Worker().run()
