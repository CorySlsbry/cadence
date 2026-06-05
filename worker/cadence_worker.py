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


class SupabaseCostLedger:
    """Durable AI-spend cap backed by the ``ai_spend`` Postgres table.

    The worker runs on stateless, scale-to-zero Cloud Run instances, so a local JSON
    ledger could not hold the cap across instances. The atomic ``charge_ai_spend`` RPC
    (a guarded UPDATE) enforces the cap globally. Implements the ImageGenerator ledger
    contract: ``can_spend`` / ``charge`` / ``spent``."""

    def __init__(self, supabase: Client, cap_usd: float) -> None:
        self.supabase = supabase
        self.cap_usd = float(cap_usd)

    def spent(self) -> float:
        try:
            r = self.supabase.table("ai_spend").select("spent_usd").eq("id", 1).execute()
            return float(r.data[0]["spent_usd"]) if r.data else 0.0
        except Exception:  # noqa: BLE001 - treat an unreadable ledger as "spend nothing more"
            return self.cap_usd

    def remaining(self) -> float:
        return max(0.0, self.cap_usd - self.spent())

    def can_spend(self, cost: float) -> bool:
        return self.spent() + cost <= self.cap_usd + 1e-9

    def charge(self, cost: float) -> float:
        """Atomically record a charge; raise BudgetExceeded if it would breach the cap."""
        from cadence.imagegen.ledger import BudgetExceeded

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
            except Exception as exc:  # noqa: BLE001 - report ANY failure on the job
                traceback.print_exc()
                try:
                    self._update(job["id"], status="error", error=str(exc)[:2000], progress=0)
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
            except Exception as exc:  # noqa: BLE001 - isolate the job, keep draining
                traceback.print_exc()
                errored += 1
                try:
                    self._update(job["id"], status="error", error=str(exc)[:2000], progress=0)
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

    # -- job processing ----------------------------------------------------- #
    def _process(self, job: dict[str, Any]) -> None:
        job_id = job["id"]
        user_id = job["user_id"]
        print(f"[worker] claimed job {job_id}", flush=True)

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

            transcript = None
            if job.get("transcript"):
                transcript = Transcript.from_dict(job["transcript"])

            edl = clean_recording(
                recording,
                transcript=transcript,
                transcriber=None if transcript else self._get_transcriber(),
                cfg=ctrl.cleaning,
                ff=self.ff,
            )
            self._update(job_id, progress=0.6)

            brand = self._load_brand(job.get("project_id"), user_id, tmp)
            if job.get("plan"):
                plan = GenerationPlan.from_dict(job["plan"])
            else:
                plan = build_generation_plan(edl, analysis=analysis, brand=brand, cfg=ctrl.synthesis)
                self._apply_cinematography(plan, ctrl)
                if not ctrl.toggles.background_replace:
                    plan.broll = self._build_broll(edl, ctrl, brand, tmp)
                if not ctrl.toggles.captions:
                    plan.captions = []
                if not ctrl.toggles.watermark:
                    plan.watermark = None
            self._update(job_id, progress=0.75)

            out_path = os.path.join(tmp, "final.mp4")
            if not job.get("plan") and ctrl.toggles.background_replace:
                result = self._render_background_mode(edl, plan, ctrl, brand, tmp, out_path)
            else:
                result = render_plan(plan, out_path, ff=self.ff)
            self._update(job_id, progress=0.92)

            output_key = f"{user_id}/{job_id}.mp4"
            self._upload(OUTPUTS, output_key, out_path)

            credit = bool((job.get("customization") or {}).get("credit_cadence"))
            captions = self._social_captions(edl, credit=credit)

            self._update(
                job_id,
                status="done",
                progress=1.0,
                output_path=output_key,
                result=result.to_dict(),
                social_captions=captions,
                error=None,
            )
            print(f"[worker] job {job_id} done -> {output_key}", flush=True)

    def _social_captions(self, edl, *, credit: bool = False):
        """Generate per-platform 'ready to post' captions from the transcript. A cheap
        gemini-flash call; degrades to a deterministic stub if no key / on failure, and
        never raises (a caption blip must not fail an otherwise-good render)."""
        if not (edl.transcript and edl.transcript.words):
            return None
        text = " ".join(w.text for w in edl.transcript.words).strip()
        if not text:
            return None
        from cadence.social import GeminiCaptionWriter, StubCaptionWriter, build_social_captions

        try:
            has_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
            writer = GeminiCaptionWriter() if has_key else StubCaptionWriter()
        except Exception:  # noqa: BLE001
            writer = StubCaptionWriter()
        try:
            return build_social_captions(
                text, writer, product=("Cadence" if credit else None),
                handle=("@cadence.video" if credit else None),
            )
        except Exception as exc:  # noqa: BLE001
            print(f"[worker] social caption generation failed ({exc})", flush=True)
            return None

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

    def _ledger(self, cap: float):
        """Durable Supabase-backed cap; falls back to a local JSON ledger only if the
        ai_spend table/RPC isn't reachable (e.g. an old DB without the migration)."""
        try:
            # Probe: a successful select confirms the table exists + the worker can read it.
            self.supabase.table("ai_spend").select("id").eq("id", 1).limit(1).execute()
            return SupabaseCostLedger(self.supabase, cap)
        except Exception:  # noqa: BLE001
            from cadence.imagegen.ledger import CostLedger

            print("[worker] WARN: ai_spend table unreachable; using local JSON ledger", flush=True)
            return CostLedger(os.path.join(os.path.dirname(os.path.abspath(__file__)), "ai_spend.json"), cap)

    def _image_generator(self):
        """Pick the best available, budget-capped generator: Imagen (Gemini key) →
        Ideogram (key) → free stub."""
        cap = float(os.environ.get("CADENCE_AI_BUDGET_USD", "10"))
        ledger = self._ledger(cap)
        if os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"):
            from cadence.imagegen.imagen import ImagenGenerator

            gen = ImagenGenerator(ledger=ledger)
            print(f"[worker] AI b-roll via Imagen ({gen.model}, budget ${cap:.2f}, spent ${ledger.spent():.2f})", flush=True)
            return gen
        if os.environ.get("IDEOGRAM_API_KEY"):
            from cadence.imagegen.ideogram import IdeogramGenerator

            print(f"[worker] AI b-roll via Ideogram (budget ${cap:.2f}, spent ${ledger.spent():.2f})", flush=True)
            return IdeogramGenerator(os.environ["IDEOGRAM_API_KEY"], ledger=ledger)
        from cadence.imagegen.stub import StubGenerator

        print("[worker] AI b-roll via free stub (no image key set)", flush=True)
        return StubGenerator()

    def _distiller(self):
        """Gemini scene/caption distiller when a key is present (an enhancement, not required)."""
        if os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"):
            try:
                from cadence.imagegen.distill import GeminiDistiller

                return GeminiDistiller()
            except Exception:  # noqa: BLE001 - degrade to lexical topic
                return None
        return None

    def _build_broll(self, edl, ctrl, brand, tmp: str):
        """Choose the b-roll source: AI-generated, uploaded/brand images, or none.

        ``ctrl`` is the :class:`ParsedControls` bundle — its cinematography drives the
        AI image look so cutaways match the chosen lens/film/lighting."""
        mode = ctrl.broll_mode
        if mode in ("none", "background"):
            return []
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
                    words_out, edl.output_duration, self._image_generator(),
                    out_dir=out_dir, mode=ctrl.pacing,
                    style_refs=(pool[:3] or None),  # brand/uploaded images steer the look
                    overlay_text=ctrl.broll_caption_overlay,
                    distiller=self._distiller(),
                    cine=ctrl.cinematography,
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

    def _background_image(self, edl, ctrl, brand, tmp: str) -> str | None:
        """Pick the background to drop the speaker onto: an uploaded/brand image if
        provided, else one contextual AI background generated from the speech."""
        pool = self._download_broll(ctrl.broll_paths, tmp) + self._download_brand_images(brand, tmp)
        if pool:
            return pool[0]
        if edl.transcript and edl.transcript.words:
            from cadence.synthesis.contextual import build_ai_broll
            from cadence.synthesis.plan import remap_words_to_output

            out_dir = os.path.join(tmp, "bg_ai")
            os.makedirs(out_dir, exist_ok=True)
            words_out = remap_words_to_output(edl.transcript, list(edl.kept))
            try:
                inserts = build_ai_broll(
                    words_out, edl.output_duration, self._image_generator(),
                    out_dir=out_dir, mode="natural", max_images=1,
                    distiller=self._distiller(), cine=ctrl.cinematography,
                )
                if inserts:
                    return inserts[0].image_path
            except Exception as exc:  # noqa: BLE001 - fall back to no replacement
                print(f"[worker] bg image generation failed ({exc})", flush=True)
        return None

    def _render_background_mode(self, edl, plan, ctrl, brand, tmp, out_path):
        """Background-replacement render. Three passes are required because the matte
        keeps ONLY speaker pixels — burned-in captions/grade would be matted away — so:
          1) render the cut (cuts + zoom, neutral, no captions/wm/broll) → speaker on orig bg;
          2) segment the speaker and composite over the contextual b-roll background;
          3) re-apply grade/captions/watermark/grain/letterbox over the composite.
        Audio is normalised exactly once: pass 1 keeps it raw (audio_normalize=False) and
        the composite carries it through, so the finish pass (inherited True) loudnorms it."""
        import dataclasses

        from cadence.matte.replace import render_background_replaced

        bg = self._background_image(edl, ctrl, brand, tmp)
        if bg is None:
            print("[worker] no background available; rendering without replacement", flush=True)
            return render_plan(plan, out_path, ff=self.ff)

        fg_plan = dataclasses.replace(
            plan, captions=[], broll=[], watermark=None,
            color_grade=ColorGrade(), letterbox=False, audio_normalize=False,
        )
        fg_path = os.path.join(tmp, "bg_fg.mp4")
        render_plan(fg_plan, fg_path, ff=self.ff)

        comp_path = os.path.join(tmp, "bg_comp.mp4")
        render_background_replaced(
            fg_path, bg, comp_path, ff=self.ff,
            width=plan.width, height=plan.height, fps=plan.fps,
        )

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
        with open(src, "rb") as fh:
            self.supabase.storage.from_(bucket).upload(
                key, fh.read(), {"content-type": "video/mp4", "upsert": "true"}
            )

    def _update(self, job_id: str, **fields: Any) -> None:
        payload = {k: v for k, v in fields.items() if v is not None or k == "error"}
        if "result" in payload and not isinstance(payload["result"], str):
            payload["result"] = json.loads(json.dumps(payload["result"]))
        self.supabase.table("render_jobs").update(payload).eq("id", job_id).execute()


if __name__ == "__main__":
    Worker().run()
