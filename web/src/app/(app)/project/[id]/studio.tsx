"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { createClient } from "@/lib/supabase/client";
import { Button, Card, Label, Badge } from "@/components/ui";
import { StickyActionBar } from "@/components/sticky-action-bar";
import { formatDuration } from "@/lib/utils";
import type { BrandBoard, Project, ProjectEdl, RenderJob } from "@/lib/types";
import { edlWithKept, fmtTime, segmentsFromEdl } from "@/lib/edl-edit";
import { Recorder } from "./recorder";
import { SocialPanel } from "./social-panel";
import { ClipsPanel, HooksPanel, RepurposePanel } from "./creator-panels";

type BrollMode = "none" | "images" | "ai" | "background";
type PresetName = "cinematic" | "cinematic_film" | "clean_ugc" | "documentary" | "gritty_doc" | "custom";

// Every control the panel exposes, in the exact JSON vocabulary parse_customization reads.
type ControlState = {
  // CLEAN
  auto_clean: boolean;
  remove_silences: boolean;
  cut_sensitivity: "gentle" | "balanced" | "aggressive";
  filler_aggressiveness: 0 | 1 | 2;
  snap_cuts_to_words: boolean;
  audio_crossfade: boolean;
  crossfade_ms: number;
  detect_retakes: boolean;
  retake_strictness: number;
  trim_dead_air: boolean;
  lead_pad_sec: number;
  tail_pad_sec: number;
  min_kept_segment_sec: number;
  // MOTION
  smart_zoom: boolean;
  zoom_intensity: number;
  // LOOK
  color_grade: boolean;
  grade_intensity: number; // 0–100
  film_stock: string;
  film_grain: boolean;
  film_grain_amount: number; // 0–40
  letterbox: boolean;
  // CAMERA (b-roll optics)
  lens: string;
  aperture: number;
  lighting: string;
  time_of_day: string;
  camera_angle: string;
  shot_type: string;
  // CAPTIONS
  captions: boolean;
  caption_style: "fade" | "pop";
  caption_zone: "top" | "center" | "bottom" | "auto";
  caption_mode: "standard" | "karaoke";
  hook: string;
  // BRAND
  watermark: boolean;
};

const BASE: ControlState = {
  auto_clean: true,
  remove_silences: true,
  cut_sensitivity: "balanced",
  filler_aggressiveness: 1,
  snap_cuts_to_words: true,
  audio_crossfade: true,
  crossfade_ms: 20,
  detect_retakes: true,
  retake_strictness: 0.82,
  trim_dead_air: true,
  lead_pad_sec: 0.08,
  tail_pad_sec: 0.15,
  min_kept_segment_sec: 0.4,
  smart_zoom: true,
  zoom_intensity: 1.12,
  color_grade: true,
  grade_intensity: 70,
  film_stock: "digital_clean",
  film_grain: false,
  film_grain_amount: 12,
  letterbox: false,
  lens: "50mm",
  aperture: 2.8,
  lighting: "soft_natural",
  time_of_day: "unset",
  camera_angle: "eye_level",
  shot_type: "medium",
  captions: true,
  caption_style: "pop",
  caption_zone: "bottom",
  caption_mode: "standard",
  hook: "",
  watermark: true,
};

// Each preset is a complete bundle (§D). `broll` carries the matching b-roll source.
const PRESETS: Record<Exclude<PresetName, "custom">, Partial<ControlState> & { broll: BrollMode }> = {
  cinematic: { lens: "85mm", aperture: 2.8, film_stock: "portra_400", lighting: "soft_natural", letterbox: false, film_grain: true, film_grain_amount: 12, zoom_intensity: 1.14, color_grade: true, caption_style: "pop", caption_zone: "bottom", broll: "ai" },
  cinematic_film: { lens: "anamorphic", aperture: 2.8, film_stock: "vision3", lighting: "low_key", letterbox: true, film_grain: true, film_grain_amount: 16, zoom_intensity: 1.12, color_grade: true, caption_style: "fade", caption_zone: "bottom", broll: "ai" },
  clean_ugc: { lens: "35mm", aperture: 5.6, film_stock: "digital_clean", lighting: "high_key", letterbox: false, film_grain: false, film_grain_amount: 0, zoom_intensity: 1.1, color_grade: false, caption_style: "pop", caption_zone: "bottom", filler_aggressiveness: 1, broll: "none" },
  documentary: { lens: "35mm", aperture: 5.6, film_stock: "digital_clean", lighting: "soft_natural", letterbox: false, film_grain: false, film_grain_amount: 0, zoom_intensity: 1.1, color_grade: true, caption_style: "fade", caption_zone: "bottom", broll: "ai" },
  gritty_doc: { lens: "35mm", aperture: 5.6, film_stock: "bleach_bypass", lighting: "low_key", letterbox: false, film_grain: true, film_grain_amount: 24, zoom_intensity: 1.12, color_grade: true, caption_style: "fade", caption_zone: "bottom", filler_aggressiveness: 2, broll: "ai" },
};

const LENSES: [string, string][] = [["24mm", "24mm wide"], ["35mm", "35mm"], ["50mm", "50mm"], ["85mm", "85mm portrait"], ["100mm_macro", "100mm macro"], ["anamorphic", "Anamorphic"]];
const STOCKS: [string, string][] = [["digital_clean", "Digital"], ["portra_400", "Portra 400"], ["vision3", "Vision3"], ["teal_orange", "Teal/Orange"], ["bleach_bypass", "Bleach bypass"], ["bw_trix", "B&W Tri-X"], ["cross_process", "Cross-process"]];
const LIGHTING: [string, string][] = [["high_key", "High-key"], ["soft_natural", "Soft natural"], ["golden_hour", "Golden hour"], ["low_key", "Low-key"], ["chiaroscuro", "Chiaroscuro"], ["neon", "Neon"]];
const TIMES: [string, string][] = [["unset", "Auto"], ["sunrise", "Sunrise"], ["midday", "Midday"], ["golden_hour", "Golden"], ["blue_hour", "Blue hr"], ["night", "Night"]];
const ANGLES: [string, string][] = [["eye_level", "Eye level"], ["low_angle", "Low"], ["high_angle", "High"], ["overhead", "Overhead"], ["dutch", "Dutch"], ["ots", "OTS"]];
const SHOTS: [string, string][] = [["ecu", "Extreme CU"], ["closeup", "Close-up"], ["medium", "Medium"], ["wide", "Wide"], ["aerial", "Aerial"], ["ots", "OTS"]];
const APERTURES = [1.4, 2.8, 5.6, 11, 16];

export function Studio({
  project,
  boards: initialBoards,
  userId,
}: {
  project: Project;
  boards: BrandBoard[];
  userId: string;
}) {
  const supabase = createClient();
  const [referencePath, setReferencePath] = useState<string | null>(project.reference_path);
  const [recordingPath, setRecordingPath] = useState<string | null>(null);
  const [recordingName, setRecordingName] = useState<string | null>(null);
  const [boards, setBoards] = useState<BrandBoard[]>(initialBoards);
  const [boardId, setBoardId] = useState<string | null>(project.brand_board_id);
  const [tab, setTab] = useState<"record" | "upload">("record");
  const [brollPaths, setBrollPaths] = useState<string[]>((project.broll_paths as string[] | null) ?? []);
  const [brollMode, setBrollMode] = useState<BrollMode>("ai");
  // Remember the last non-AI source so the Simple-mode AI toggle can restore it (not reset to Off).
  const [lastBrollMode, setLastBrollMode] = useState<BrollMode>("images");
  const [brollCaption, setBrollCaption] = useState(false);
  const [brollQuality, setBrollQuality] = useState<"fast" | "standard" | "ultra">("standard");
  const [bgDynamic, setBgDynamic] = useState(false); // Replace-BG: per-moment AI b-roll background vs one static image
  const [pacing, setPacing] = useState<"natural" | "between" | "match">("between");
  const [multiclip, setMulticlip] = useState(false);
  const [multiclipCount, setMulticlipCount] = useState(4);
  const [musicPath, setMusicPath] = useState<string | null>(null);
  const [musicVolume, setMusicVolume] = useState(0.18);

  const [mode, setMode] = useState<"simple" | "pro">("simple");
  const [preset, setPreset] = useState<PresetName>("cinematic");
  const [ctl, setCtl] = useState<ControlState>({ ...BASE, ...PRESETS.cinematic });

  // Hidden, owner-only: re-voice the video in Cory's synthesized voice. Gated on plan==='admin'.
  const [isAdmin, setIsAdmin] = useState(false);
  const [voiceover, setVoiceover] = useState("");
  const adminChecked = useRef(false);
  useEffect(() => {
    if (adminChecked.current) return;
    adminChecked.current = true;
    supabase.from("profiles").select("plan").single().then(({ data }) => setIsAdmin(data?.plan === "admin"));
  }, [supabase]);

  const [uploading, setUploading] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [job, setJob] = useState<RenderJob | null>(null);
  const [resultUrl, setResultUrl] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Editing any Pro control drops the preset chip to "custom" but preserves all edits.
  const update = useCallback((patch: Partial<ControlState>) => {
    setCtl((c) => ({ ...c, ...patch }));
    setPreset("custom");
  }, []);

  function applyPreset(name: Exclude<PresetName, "custom">) {
    const { broll, ...fields } = PRESETS[name];
    setCtl({ ...BASE, ...fields });
    if (broll !== "ai") setLastBrollMode(broll);
    setBrollMode(broll);
    setPreset(name);
  }

  function changeBrollMode(m: BrollMode) {
    if (m !== "ai") setLastBrollMode(m);
    setBrollMode(m);
    setPreset("custom");
  }
  function changePacing(p: "natural" | "between" | "match") {
    setPacing(p);
    setPreset("custom");
  }

  // -- templates (saved render presets) --------------------------------- //
  const [templates, setTemplates] = useState<{ id: string; name: string; customization: Record<string, unknown> }[]>([]);
  const loadTemplates = useCallback(async () => {
    try {
      const r = await fetch("/api/templates");
      if (r.ok) setTemplates((await r.json()).templates ?? []);
    } catch { /* non-fatal */ }
  }, []);
  useEffect(() => { void loadTemplates(); }, [loadTemplates]);

  async function saveTemplate() {
    const name = window.prompt("Name this template (saves your current settings):")?.trim();
    if (!name) return;
    const snapshot = { ctl, preset, pacing, brollMode, brollQuality, brollCaption, bgDynamic, multiclip, multiclipCount };
    try {
      const r = await fetch("/api/templates", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ name, customization: snapshot }),
      });
      if (!r.ok) { setError("Couldn't save template."); return; }
      await loadTemplates();
    } catch { setError("Couldn't save template."); }
  }

  function loadTemplate(c: Record<string, unknown>) {
    if (c.ctl && typeof c.ctl === "object") setCtl({ ...BASE, ...(c.ctl as Partial<ControlState>) });
    if (typeof c.preset === "string") setPreset(c.preset as PresetName);
    if (typeof c.pacing === "string") setPacing(c.pacing as "natural" | "between" | "match");
    if (typeof c.brollMode === "string") setBrollMode(c.brollMode as BrollMode);
    if (typeof c.brollQuality === "string") setBrollQuality(c.brollQuality as "fast" | "standard" | "ultra");
    if (typeof c.brollCaption === "boolean") setBrollCaption(c.brollCaption);
    if (typeof c.bgDynamic === "boolean") setBgDynamic(c.bgDynamic);
    if (typeof c.multiclip === "boolean") setMulticlip(c.multiclip);
    if (typeof c.multiclipCount === "number") setMulticlipCount(c.multiclipCount);
  }

  async function deleteTemplate(id: string) {
    try {
      await fetch(`/api/templates?id=${encodeURIComponent(id)}`, { method: "DELETE" });
      await loadTemplates();
    } catch { /* non-fatal */ }
  }

  // -- uploads ----------------------------------------------------------- //
  const upload = useCallback(
    async (file: Blob, kind: string, ext: string) => {
      const rand = Math.random().toString(36).slice(2, 8);
      const path = `${userId}/${project.id}/${kind}-${Date.now()}-${rand}.${ext}`;
      const { error } = await supabase.storage
        .from("uploads")
        .upload(path, file, { upsert: true, contentType: file.type || "video/webm" });
      if (error) throw error;
      return path;
    },
    [supabase, userId, project.id],
  );

  async function onReference(file: File) {
    setError(null);
    setUploading("reference");
    try {
      const path = await upload(file, "reference", file.name.split(".").pop() || "mp4");
      await supabase.from("projects").update({ reference_path: path }).eq("id", project.id);
      setReferencePath(path);
    } catch (e) {
      setError(msg(e));
    } finally {
      setUploading(null);
    }
  }

  async function onRecording(file: Blob, name: string, ext: string) {
    setError(null);
    setUploading("recording");
    try {
      const path = await upload(file, "recording", ext);
      setRecordingPath(path);
      setRecordingName(name);
    } catch (e) {
      setError(msg(e));
    } finally {
      setUploading(null);
    }
  }

  // Persist the project's b-roll image list so it survives reloads + is reused across renders.
  const persistBroll = useCallback(async (paths: string[]) => {
    setBrollPaths(paths);
    try {
      await supabase.from("projects").update({ broll_paths: paths }).eq("id", project.id);
    } catch { /* non-fatal — keep the local list even if the save fails */ }
  }, [supabase, project.id]);

  async function onBroll(files: FileList) {
    setError(null);
    setUploading("broll");
    try {
      const added: string[] = [];
      for (const f of Array.from(files)) {
        const path = await upload(f, "broll", f.name.split(".").pop() || "png");
        added.push(path);
      }
      await persistBroll([...brollPaths, ...added]);
    } catch (e) {
      setError(msg(e));
    } finally {
      setUploading(null);
    }
  }

  // -- brand ------------------------------------------------------------- //
  async function createBoard() {
    const name = prompt("Brand board name", "My Brand");
    if (!name) return;
    const { data, error } = await supabase
      .from("brand_boards")
      .insert({ user_id: userId, name })
      .select("id, name, caption_primary, caption_outline")
      .single();
    if (error || !data) return setError(msg(error));
    setBoards((b) => [...b, data as BrandBoard]);
    selectBoard(data.id);
  }

  async function selectBoard(id: string | null) {
    setBoardId(id);
    await supabase.from("projects").update({ brand_board_id: id }).eq("id", project.id);
  }

  // -- generate ---------------------------------------------------------- //
  function buildCustomization(): Record<string, unknown> {
    return {
      preset: preset === "custom" ? undefined : preset,
      // CLEAN
      auto_clean: ctl.auto_clean,
      remove_silences: ctl.remove_silences,
      cut_sensitivity: ctl.cut_sensitivity,
      filler_aggressiveness: ctl.filler_aggressiveness,
      remove_fillers: ctl.filler_aggressiveness > 0,
      snap_cuts_to_words: ctl.snap_cuts_to_words,
      audio_crossfade: ctl.audio_crossfade,
      crossfade_ms: ctl.crossfade_ms,
      detect_retakes: ctl.detect_retakes,
      retake_strictness: ctl.retake_strictness,
      trim_dead_air: ctl.trim_dead_air,
      lead_pad_sec: ctl.lead_pad_sec,
      tail_pad_sec: ctl.tail_pad_sec,
      min_kept_segment_sec: ctl.min_kept_segment_sec,
      // MOTION
      smart_zoom: ctl.smart_zoom,
      zoom_intensity: ctl.zoom_intensity,
      // LOOK
      color_grade: ctl.color_grade,
      grade_intensity: ctl.grade_intensity,
      film_stock: ctl.film_stock,
      film_grain: ctl.film_grain,
      film_grain_amount: ctl.film_grain ? ctl.film_grain_amount : 0,
      framing: ctl.letterbox ? "letterbox_239" : "full_916",
      letterbox: ctl.letterbox,
      // CAMERA
      lens: ctl.lens,
      aperture: ctl.aperture,
      lighting: ctl.lighting,
      time_of_day: ctl.time_of_day,
      camera_angle: ctl.camera_angle,
      shot_type: ctl.shot_type,
      // CAPTIONS
      captions: ctl.captions,
      caption_style: ctl.caption_style,
      caption_zone: ctl.caption_zone,
      caption_mode: ctl.caption_mode === "karaoke" ? "karaoke" : "legacy",
      hook: ctl.hook.trim() || undefined,
      // BRAND
      watermark: ctl.watermark,
      // B-ROLL
      broll_paths: brollPaths,
      broll_mode: brollMode,
      broll_quality: brollQuality,
      broll_caption: brollCaption,
      ai_broll: brollMode === "ai" || (brollMode === "background" && bgDynamic),
      pacing,
      ...(multiclip ? { multiclip: { count: multiclipCount } } : {}),
      ...(musicPath ? { music_path: musicPath, music_volume: musicVolume } : {}),
      ...(isAdmin && voiceover.trim() ? { voiceover: { script: voiceover.trim() } } : {}),
    };
  }

  async function onMusic(file: File) {
    setError(null);
    setUploading("music");
    try {
      setMusicPath(await upload(file, "music", file.name.split(".").pop() || "mp3"));
    } catch (e) {
      setError(msg(e));
    } finally {
      setUploading(null);
    }
  }

  async function generate() {
    if (!recordingPath) return;
    setError(null);
    setResultUrl(null);
    const res = await fetch("/api/render", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        projectId: project.id,
        recordingPath,
        referencePath,
        aggressiveFillers: ctl.filler_aggressiveness >= 2,
        customization: buildCustomization(),
      }),
    });
    const data = await res.json();
    if (!res.ok) {
      setError(data.error ?? "Could not start render");
      return;
    }
    setJob({ id: data.jobId, status: "queued", progress: 0 } as RenderJob);
    startPolling(data.jobId);
  }

  // Re-render the same take with an edited cut list (drop segments) — skips re-cleaning.
  async function fixRerender(edlOverride: ProjectEdl) {
    if (!recordingPath) return;
    setError(null);
    setResultUrl(null);
    const res = await fetch("/api/render", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        projectId: project.id,
        recordingPath,
        referencePath,
        aggressiveFillers: ctl.filler_aggressiveness >= 2,
        customization: { ...buildCustomization(), edl_override: edlOverride },
      }),
    });
    const data = await res.json();
    if (!res.ok) { setError(data.error ?? "Could not start render"); return; }
    setJob({ id: data.jobId, status: "queued", progress: 0 } as RenderJob);
    startPolling(data.jobId);
  }

  function startPolling(jobId: string) {
    if (pollRef.current) clearInterval(pollRef.current);
    pollRef.current = setInterval(async () => {
      const { data } = await supabase.from("render_jobs").select("*").eq("id", jobId).single();
      if (!data) return;
      setJob(data as RenderJob);
      if (data.status === "done" && data.output_path) {
        const { data: signed } = await supabase.storage
          .from("outputs")
          .createSignedUrl(data.output_path, 3600);
        if (signed) setResultUrl(signed.signedUrl);
        stopPolling();
      } else if (data.status === "error") {
        setError(data.error ?? "Render failed");
        stopPolling();
      }
    }, 2500);
  }
  function stopPolling() {
    if (pollRef.current) clearInterval(pollRef.current);
    pollRef.current = null;
  }
  useEffect(() => () => stopPolling(), []);

  // Reset to a clean record-ready state: discard the current take + any finished result
  // so you can shoot and render new videos back-to-back. Called by the footage "Clear"
  // button, the result-screen "Make another", and automatically when a new take starts.
  function clearFootage() {
    stopPolling();
    setRecordingPath(null);
    setRecordingName(null);
    setResultUrl(null);
    setJob(null);
    setError(null);
  }

  const rendering = job && (job.status === "queued" || job.status === "processing");
  const cameraLive = brollMode === "ai" || brollMode === "background";

  return (
    <div className="space-y-6 pb-28 sm:pb-6">
      <div className="flex items-center justify-between">
        <div>
          <Link href="/dashboard" className="text-sm text-white/40 hover:text-white">← Projects</Link>
          <h1 className="mt-1 text-2xl font-bold">{project.name}</h1>
        </div>
      </div>

      {error && (
        <div className="rounded-xl border border-red-500/20 bg-red-500/5 p-4 text-sm text-red-300">{error}</div>
      )}

      <div className="grid gap-4 sm:gap-6 lg:grid-cols-2">
        {/* Reference */}
        <Card>
          <SectionHead n="1" title="Reference style" done={!!referencePath} />
          <p className="mb-4 text-sm text-white/45">Upload a clip whose look & pacing you want to match.</p>
          <FileButton accept="video/*" busy={uploading === "reference"} onFile={onReference}
            label={referencePath ? "Replace reference" : "Upload reference video"} />
          {referencePath && <Badge tone="good" className="mt-3">Reference ready</Badge>}
        </Card>

        {/* Footage */}
        <Card>
          <SectionHead n="2" title="Your footage" done={!!recordingPath} />
          <div className="mb-4 flex gap-2">
            <TabBtn active={tab === "record"} onClick={() => setTab("record")}>Record</TabBtn>
            <TabBtn active={tab === "upload"} onClick={() => setTab("upload")}>Upload</TabBtn>
          </div>
          {tab === "record" ? (
            <Recorder
              onRecorded={(blob) => onRecording(blob, "recording.webm", "webm")}
              onRecordStart={clearFootage}
            />
          ) : (
            <FileButton accept="video/*" busy={uploading === "recording"}
              onFile={(f) => onRecording(f, f.name, f.name.split(".").pop() || "mp4")}
              label="Upload a raw clip" />
          )}
          {recordingPath && (
            <div className="mt-3 flex items-center gap-3">
              <Badge tone="good">{recordingName ?? "Footage"} ready</Badge>
              <button onClick={clearFootage} className="text-xs text-white/45 hover:text-white">Clear / re-record</button>
            </div>
          )}
        </Card>

        {/* Brand */}
        <Card>
          <SectionHead n="3" title="Brand" done={!!boardId} />
          <p className="mb-4 text-sm text-white/45">Optional. Apply a saved logo + caption styling.</p>
          <div className="flex items-center gap-2">
            <select
              value={boardId ?? ""}
              onChange={(e) => selectBoard(e.target.value || null)}
              className="flex-1 rounded-xl border border-white/10 bg-white/[0.03] px-4 py-3 text-sm"
            >
              <option value="">No brand</option>
              {boards.map((b) => (
                <option key={b.id} value={b.id}>{b.name}</option>
              ))}
            </select>
            <Button variant="outline" onClick={createBoard}>＋ New</Button>
          </div>
          {boardId && <BrandEditor boardId={boardId} userId={userId} onError={setError} onBrollAdded={(paths) => void persistBroll([...brollPaths, ...paths])} />}
        </Card>

        {/* B-roll */}
        <Card>
          <SectionHead n="4" title="B-roll & background" done={brollMode !== "none"} />
          <div className="mb-4">
            <Segmented label="Source" value={brollMode}
              options={[["none", "Off"], ["images", "My images"], ["ai", "AI ✨"], ["background", "Replace BG"]]}
              onChange={(v) => changeBrollMode(v as BrollMode)} />
          </div>
          {brollMode === "ai" && (
            <p className="mb-4 rounded-xl border border-[var(--accent)]/20 bg-[var(--accent)]/5 p-3 text-sm text-white/70">
              We read what you&apos;re saying and generate a <b>photoreal cutaway per moment</b> — e.g.
              say “Claude skills” and the frame shows it. Images you add below steer the brand look.
            </p>
          )}
          {brollMode === "background" && (
            <p className="mb-4 rounded-xl border border-[var(--accent)]/20 bg-[var(--accent)]/5 p-3 text-sm text-white/70">
              We <b>cut out the speaker</b> and drop them over a contextual b-roll background generated from
              your words (or your first uploaded image). Your camera background disappears.
            </p>
          )}
          {brollMode === "background" && (
            <label className="mb-4 flex items-start gap-2 text-sm text-white/70">
              <input type="checkbox" className="mt-0.5" checked={bgDynamic}
                onChange={(e) => { setBgDynamic(e.target.checked); setPreset("custom"); }} />
              <span><b>Dynamic AI background</b> — generate a fresh image per talking point, so the background changes as you speak. Off = one contextual background image.</span>
            </label>
          )}
          {(brollMode === "ai" || brollMode === "background") && (
            <div className="mb-4">
              <Slider label="Image quality"
                value={["fast", "standard", "ultra"].indexOf(brollQuality)} min={0} max={2} step={1}
                display={{ fast: "Fast · $0.02 / image", standard: "Standard · $0.04 / image", ultra: "Ultra · $0.06 / image" }[brollQuality]}
                onChange={(i) => { setBrollQuality((["fast", "standard", "ultra"] as const)[i]); setPreset("custom"); }} />
              <p className="mt-1 text-xs text-white/35">
                Higher tiers render sharper, more detailed AI imagery (Imagen&nbsp;4). Charged per image generated, inside your credit budget.
              </p>
            </div>
          )}
          {brollMode !== "none" && (
            <>
              <p className="mb-3 text-sm text-white/45">
                {brollMode === "ai"
                  ? "Optional brand/style reference images:"
                  : brollMode === "background"
                    ? "Optional: a background image to use instead of a generated one."
                    : "Add screenshots/images — we animate them and cut to them over your voice."}
              </p>
              <BrollUploader busy={uploading === "broll"} count={brollPaths.length} onFiles={onBroll} onClear={() => void persistBroll([])} />
              {brollMode === "ai" && (
                <label className="mt-3 flex items-center gap-2 text-sm text-white/60">
                  <input type="checkbox" checked={brollCaption} onChange={(e) => { setBrollCaption(e.target.checked); setPreset("custom"); }} />
                  Overlay a guaranteed caption banner on each cutaway
                </label>
              )}
            </>
          )}
        </Card>
      </div>

      {/* Control panel */}
      <Card>
        <div className="mb-5 flex items-center justify-between">
          <SectionHead n="5" title="Look & feel" done />
          <div className="flex gap-1 rounded-xl border border-white/10 p-1 text-sm">
            <button onClick={() => setMode("simple")}
              className={`rounded-lg px-3 py-1.5 ${mode === "simple" ? "bg-white/10 text-white" : "text-white/45 hover:text-white"}`}>Simple</button>
            <button onClick={() => setMode("pro")}
              className={`rounded-lg px-3 py-1.5 ${mode === "pro" ? "bg-white/10 text-white" : "text-white/45 hover:text-white"}`}>Pro</button>
          </div>
        </div>

        {/* Presets — always visible */}
        <div className="mb-6">
          <Label>Preset</Label>
          <div className="flex flex-wrap gap-2">
            {([
              ["cinematic", "Cinematic"],
              ["cinematic_film", "Cinematic Film"],
              ["clean_ugc", "Clean UGC"],
              ["documentary", "Documentary"],
              ["gritty_doc", "Gritty Doc"],
            ] as [Exclude<PresetName, "custom">, string][]).map(([v, l]) => (
              <button key={v} onClick={() => applyPreset(v)}
                className={`rounded-full border px-4 py-2 text-sm transition ${preset === v ? "border-[var(--accent)] bg-[var(--accent)] text-black" : "border-white/10 text-white/60 hover:text-white"}`}>
                {l}
              </button>
            ))}
            {preset === "custom" && (
              <span className="rounded-full border border-white/15 px-4 py-2 text-sm text-white/50">Custom</span>
            )}
          </div>
        </div>

        {/* Templates — your saved settings */}
        <div className="mb-6">
          <div className="mb-1 flex items-center justify-between">
            <Label>Templates</Label>
            <button onClick={saveTemplate} className="text-xs text-[var(--accent)] hover:underline">＋ Save current</button>
          </div>
          {templates.length === 0 ? (
            <p className="text-sm text-white/40">No saved templates yet. Set things up, then &quot;Save current&quot; to reuse them.</p>
          ) : (
            <div className="flex flex-wrap gap-2">
              {templates.map((t) => (
                <span key={t.id} className="flex items-center gap-1 rounded-full border border-white/10 py-1 pl-4 pr-1 text-sm text-white/70 hover:text-white">
                  <button onClick={() => loadTemplate(t.customization)} className="py-1">{t.name}</button>
                  <button onClick={() => deleteTemplate(t.id)} title="Delete template" className="rounded-full px-2 text-white/30 hover:text-white">×</button>
                </span>
              ))}
            </div>
          )}
        </div>

        {mode === "simple" ? (
          <div className="space-y-5">
            <Segmented label="Pacing (how fast it cuts)" value={pacing}
              options={[["natural", "Calm"], ["between", "Balanced"], ["match", "Punchy"]]}
              onChange={(v) => changePacing(v as "natural" | "between" | "match")} />
            <Segmented label="Caption position" value={ctl.caption_zone}
              options={[["top", "Top"], ["center", "Center"], ["bottom", "Bottom"], ["auto", "Auto"]]}
              onChange={(v) => update({ caption_zone: v as ControlState["caption_zone"] })} />
            <Toggle
              label={brollMode === "background" ? "Dynamic AI background" : "AI b-roll cutaways"}
              hint={brollMode === "background"
                ? "A fresh AI background per talking point, behind the speaker (~$0.04 each, $10 cap)"
                : "Photoreal images generated from your words (~$0.04 each, $10 cap)"}
              checked={brollMode === "background" ? bgDynamic : brollMode === "ai"}
              onChange={(on) => {
                if (brollMode === "background") { setBgDynamic(on); setPreset("custom"); }
                else changeBrollMode(on ? "ai" : lastBrollMode);
              }} />
          </div>
        ) : (
          <div className="space-y-3">
            {/* CLEAN */}
            <Disclosure title="Clean" subtitle="Cut silences, fillers & bad takes">
              <Toggle label="Auto-clean (silences, fillers, retakes)" checked={ctl.auto_clean}
                onChange={(v) => update({ auto_clean: v })} />
              <Toggle label="Remove silent gaps" hint="Independent of fillers/retakes — keep pauses but still drop bad takes"
                checked={ctl.remove_silences} disabled={!ctl.auto_clean} onChange={(v) => update({ remove_silences: v })} />
              <Segmented label="Cut sensitivity" value={ctl.cut_sensitivity} disabled={!ctl.auto_clean || !ctl.remove_silences}
                options={[["gentle", "Gentle"], ["balanced", "Balanced"], ["aggressive", "Aggressive"]]}
                onChange={(v) => update({ cut_sensitivity: v as ControlState["cut_sensitivity"] })} />
              <Segmented label="Filler removal" value={String(ctl.filler_aggressiveness)} disabled={!ctl.auto_clean}
                options={[["0", "Keep"], ["1", "Default"], ["2", "Aggressive"]]}
                onChange={(v) => update({ filler_aggressiveness: Number(v) as 0 | 1 | 2 })} />
              <Toggle label="Snap cuts to word boundaries" hint="Stops cuts clipping the start/end of words"
                checked={ctl.snap_cuts_to_words} disabled={!ctl.auto_clean} onChange={(v) => update({ snap_cuts_to_words: v })} />
              <Toggle label="Audio crossfade seams" hint="Feathers each cut so jumps don't pop"
                checked={ctl.audio_crossfade} onChange={(v) => update({ audio_crossfade: v })} />
              <Slider label="Crossfade length" value={ctl.crossfade_ms} min={0} max={60} step={2}
                disabled={!ctl.audio_crossfade} display={`${ctl.crossfade_ms}ms`} onChange={(v) => update({ crossfade_ms: v })} />
              <Toggle label="Detect & drop repeated takes" checked={ctl.detect_retakes} disabled={!ctl.auto_clean}
                onChange={(v) => update({ detect_retakes: v })} />
              <Slider label="Retake strictness" value={ctl.retake_strictness} min={0.7} max={0.95} step={0.01}
                disabled={!ctl.auto_clean || !ctl.detect_retakes} display={ctl.retake_strictness.toFixed(2)}
                onChange={(v) => update({ retake_strictness: v })} />
              <Toggle label="Trim dead air at the start" checked={ctl.trim_dead_air} disabled={!ctl.auto_clean}
                onChange={(v) => update({ trim_dead_air: v })} />
              <Slider label="Lead pad" value={ctl.lead_pad_sec} min={0} max={0.3} step={0.01}
                disabled={!ctl.auto_clean} display={`${Math.round(ctl.lead_pad_sec * 1000)}ms`}
                onChange={(v) => update({ lead_pad_sec: v })} />
              <Slider label="Tail pad" value={ctl.tail_pad_sec} min={0} max={0.4} step={0.01}
                disabled={!ctl.auto_clean} display={`${Math.round(ctl.tail_pad_sec * 1000)}ms`}
                onChange={(v) => update({ tail_pad_sec: v })} />
              <Slider label="Min kept segment" value={ctl.min_kept_segment_sec} min={0.2} max={1.5} step={0.05}
                disabled={!ctl.auto_clean} display={`${ctl.min_kept_segment_sec.toFixed(2)}s`}
                onChange={(v) => update({ min_kept_segment_sec: v })} />
            </Disclosure>

            {/* MOTION */}
            <Disclosure title="Motion" subtitle="Smart jump-cut punch-in">
              <Toggle label="Smart zoom on cuts" checked={ctl.smart_zoom} onChange={(v) => update({ smart_zoom: v })} />
              <Slider label="Zoom intensity" value={ctl.zoom_intensity} min={1} max={1.2} step={0.01}
                disabled={!ctl.smart_zoom} display={`${Math.round((ctl.zoom_intensity - 1) * 100)}%`}
                onChange={(v) => update({ zoom_intensity: v })} />
            </Disclosure>

            {/* LOOK */}
            <Disclosure title="Look" subtitle="Color grade, film stock, grain & framing">
              <Toggle label="Color grade to reference" checked={ctl.color_grade} onChange={(v) => update({ color_grade: v })} />
              <Slider label="Grade intensity" value={ctl.grade_intensity} min={0} max={100} step={5}
                disabled={!ctl.color_grade} display={`${ctl.grade_intensity}%`} onChange={(v) => update({ grade_intensity: v })} />
              <SelectRow label="Film stock" value={ctl.film_stock} options={STOCKS} onChange={(v) => update({ film_stock: v })} />
              <Toggle label="Film grain" checked={ctl.film_grain} onChange={(v) => update({ film_grain: v })} />
              <Slider label="Grain amount" value={ctl.film_grain_amount} min={0} max={40} step={2}
                disabled={!ctl.film_grain} display={grainWord(ctl.film_grain_amount)} onChange={(v) => update({ film_grain_amount: v })} />
              <Toggle label="Cinematic letterbox (2.39:1)" checked={ctl.letterbox} onChange={(v) => update({ letterbox: v })} />
            </Disclosure>

            {/* CAMERA */}
            <Disclosure title="Camera" subtitle={cameraLive ? "Optics for AI b-roll & background" : "Enable AI b-roll or Replace BG to use"}>
              {!cameraLive && (
                <p className="mb-1 text-xs text-white/35">These only steer generated imagery. Turn on AI b-roll or Replace BG (section 4) to apply them.</p>
              )}
              <SelectRow label="Lens" value={ctl.lens} options={LENSES} disabled={!cameraLive} onChange={(v) => update({ lens: v })} />
              <Segmented label="Aperture" value={String(ctl.aperture)} disabled={!cameraLive}
                options={APERTURES.map((a) => [String(a), `f/${a}`] as [string, string])}
                onChange={(v) => update({ aperture: Number(v) })} />
              <SelectRow label="Lighting" value={ctl.lighting} options={LIGHTING} disabled={!cameraLive} onChange={(v) => update({ lighting: v })} />
              <SelectRow label="Time of day" value={ctl.time_of_day} options={TIMES} disabled={!cameraLive} onChange={(v) => update({ time_of_day: v })} />
              <SelectRow label="Camera angle" value={ctl.camera_angle} options={ANGLES} disabled={!cameraLive} onChange={(v) => update({ camera_angle: v })} />
              <SelectRow label="Shot type" value={ctl.shot_type} options={SHOTS} disabled={!cameraLive} onChange={(v) => update({ shot_type: v })} />
            </Disclosure>

            {/* CAPTIONS */}
            <Disclosure title="Captions" subtitle="Burned-in word captions">
              <Toggle label="Show captions" checked={ctl.captions} onChange={(v) => update({ captions: v })} />
              <Segmented label="Entry style" value={ctl.caption_style} disabled={!ctl.captions}
                options={[["fade", "Fade"], ["pop", "Pop"]]}
                onChange={(v) => update({ caption_style: v as ControlState["caption_style"] })} />
              <Segmented label="Position" value={ctl.caption_zone} disabled={!ctl.captions}
                options={[["top", "Top"], ["center", "Center"], ["bottom", "Bottom"], ["auto", "Auto"]]}
                onChange={(v) => update({ caption_zone: v as ControlState["caption_zone"] })} />
              <Segmented label="Animation" value={ctl.caption_mode} disabled={!ctl.captions}
                options={[["standard", "Standard"], ["karaoke", "Karaoke"]]}
                onChange={(v) => update({ caption_mode: v as ControlState["caption_mode"] })} />
              <div>
                <Label>Hook card (opening line)</Label>
                <input value={ctl.hook} onChange={(e) => update({ hook: e.target.value })}
                  placeholder="Optional — a bold opener, e.g. Stop scrolling"
                  className="min-h-11 w-full rounded-xl border border-white/10 bg-white/[0.03] px-4 py-2.5 text-sm" />
              </div>
            </Disclosure>

            {/* BRAND */}
            <Disclosure title="Brand" subtitle="Watermark & pacing">
              <Toggle label="Show watermark (if brand has one)" checked={ctl.watermark} onChange={(v) => update({ watermark: v })} />
              <Segmented label="Pacing" value={pacing}
                options={[["natural", "Calm"], ["between", "Balanced"], ["match", "Punchy"]]}
                onChange={(v) => changePacing(v as "natural" | "between" | "match")} />
            </Disclosure>
          </div>
        )}
      </Card>

      {/* Owner-only voiceover (hidden from non-admin users) */}
      {isAdmin && (
        <Card>
          <div className="mb-2 flex items-center gap-2">
            <h3 className="text-sm font-semibold">Voiceover</h3>
            <span className="rounded-full bg-white/10 px-2 py-0.5 text-[10px] uppercase tracking-wide text-white/50">internal</span>
          </div>
          <p className="mb-3 text-xs text-white/40">
            Paste a script to re-voice this video in your own voice (synthesized). Leave empty to keep your recorded audio.
          </p>
          <textarea value={voiceover} onChange={(e) => setVoiceover(e.target.value)} rows={3}
            placeholder="Narration script — synthesized in your voice…"
            className="w-full resize-none rounded-xl border border-white/10 bg-black/40 p-3 text-sm text-white/85 outline-none placeholder:text-white/25 focus:border-[var(--accent)]/40" />
        </Card>
      )}

      {/* Clips & music */}
      <Card>
        <SectionHead n="6" title="Clips & music" done={multiclip || !!musicPath} />
        <div className="space-y-4">
          <Toggle label="Split into multiple clips"
            hint="Find the best moments in a longer recording and render several standalone shorts"
            checked={multiclip} onChange={setMulticlip} />
          {multiclip && (
            <Segmented label="How many clips" value={String(multiclipCount)}
              options={[["2", "2"], ["3", "3"], ["4", "4"], ["5", "5"]]}
              onChange={(v) => setMulticlipCount(Number(v))} />
          )}
          <div>
            <Label>Background music (optional)</Label>
            <div className="flex items-center gap-2">
              <FileButton accept="audio/*" busy={uploading === "music"} onFile={onMusic}
                label={musicPath ? "Replace music" : "Upload music"} />
              {musicPath && <button onClick={() => setMusicPath(null)} className="text-xs text-white/45 hover:text-white">Remove</button>}
            </div>
            {musicPath && (
              <Slider label="Music volume" value={musicVolume} min={0.05} max={0.5} step={0.01}
                display={`${Math.round(musicVolume * 100)}%`} onChange={setMusicVolume} />
            )}
            <p className="mt-1 text-xs text-white/35">Ducks automatically under your voice.</p>
          </div>
        </div>
      </Card>

      {/* Generate + result */}
      <Card className={resultUrl ? "text-center" : "border-0 bg-transparent p-0 text-center sm:border sm:border-white/[0.07] sm:bg-[var(--surface)] sm:p-6"}>
        {!job && (
          <StickyActionBar>
            <Button onClick={generate} disabled={!recordingPath || uploading === "recording"} className="w-full sm:mx-auto sm:w-auto sm:px-10">
              Generate premium video
            </Button>
            {uploading === "recording" ? (
              <p className="mt-2 text-xs text-[var(--accent)]">
                ⏳ Uploading your recording… the button lights up once it&apos;s saved — nothing is processed yet.
              </p>
            ) : !recordingPath ? (
              <p className="mt-2 text-xs text-white/45">Add footage to enable rendering.</p>
            ) : (
              <p className="mt-2 text-xs text-white/45">
                Ready. Cleaning, AI b-roll &amp; background generation all happen <em>after</em> you hit Generate.
              </p>
            )}
          </StickyActionBar>
        )}

        {rendering && (
          <StickyActionBar>
          <div className="mx-auto max-w-md">
            <div className="mb-2 flex items-center justify-between text-sm">
              <span className="text-white/60">{job!.status === "queued" ? "Queued…" : "Rendering…"}</span>
              <span className="text-white/40">{Math.round((job!.progress ?? 0) * 100)}%</span>
            </div>
            <div className="h-2 overflow-hidden rounded-full bg-white/10">
              <div className="h-full rounded-full bg-[var(--accent)] transition-all"
                style={{ width: `${Math.max(5, (job!.progress ?? 0) * 100)}%` }} />
            </div>
            <p className="mt-3 text-xs text-white/35">Analyzing reference · cleaning audio · stitching · encoding</p>
          </div>
          </StickyActionBar>
        )}

        {resultUrl && (
          <>
            {job?.clips?.length ? (
              <div className="space-y-4">
                <ClipsPanel job={job} />
                <Button variant="outline" onClick={() => { clearFootage(); setTab("record"); }}>Make another video</Button>
              </div>
            ) : (
              <div className="mx-auto max-w-[320px] space-y-4">
                <video src={resultUrl} controls playsInline className="mx-auto aspect-[9/16] w-full rounded-2xl border border-white/10 bg-black" />
                <div className="flex items-center justify-center gap-3">
                  <a href={resultUrl} download="cadence.mp4">
                    <Button>Download</Button>
                  </a>
                  <Button variant="outline" onClick={() => { clearFootage(); setTab("record"); }}>Make another video</Button>
                </div>
                {job?.result && (
                  <p className="text-xs text-white/35">
                    {job.result.width}×{job.result.height} · {Math.round(job.result.fps)}fps · {formatDuration(job.result.duration)}
                  </p>
                )}
                {job?.edl && <FixCutsPanel edl={job.edl} onReRender={fixRerender} />}
              </div>
            )}
            {job && <SocialPanel job={job} />}
            {job && <HooksPanel job={job} />}
            {job && <RepurposePanel job={job} />}
          </>
        )}
      </Card>
    </div>
  );
}

function grainWord(v: number): string {
  if (v === 0) return "Off";
  if (v < 18) return "Fine";
  if (v < 32) return "Visible";
  return "Heavy";
}

function msg(e: unknown) {
  return e instanceof Error ? e.message : typeof e === "string" ? e : "Something went wrong";
}

function SectionHead({ n, title, done }: { n: string; title: string; done?: boolean }) {
  return (
    <div className="mb-3 flex items-center gap-3">
      <span className={`flex h-7 w-7 items-center justify-center rounded-full text-xs font-bold ${done ? "bg-[var(--accent)] text-black" : "bg-white/8 text-white/60"}`}>
        {done ? "✓" : n}
      </span>
      <h3 className="font-semibold">{title}</h3>
    </div>
  );
}

function TabBtn({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button onClick={onClick}
      className={`rounded-lg px-3 py-1.5 text-sm ${active ? "bg-white/10 text-white" : "text-white/45 hover:text-white"}`}>
      {children}
    </button>
  );
}

function FileButton({ accept, label, busy, onFile }: { accept: string; label: string; busy: boolean; onFile: (f: File) => void }) {
  const ref = useRef<HTMLInputElement>(null);
  return (
    <>
      <input ref={ref} type="file" accept={accept} className="hidden"
        onChange={(e) => e.target.files?.[0] && onFile(e.target.files[0])} />
      <Button variant="outline" className="w-full" disabled={busy} onClick={() => ref.current?.click()}>
        {busy ? "Uploading…" : label}
      </Button>
    </>
  );
}

function BrollUploader({ busy, count, onFiles, onClear }: { busy: boolean; count: number; onFiles: (f: FileList) => void; onClear: () => void }) {
  const ref = useRef<HTMLInputElement>(null);
  return (
    <div className="space-y-2">
      <input ref={ref} type="file" accept="image/*" multiple className="hidden"
        onChange={(e) => e.target.files?.length && onFiles(e.target.files)} />
      <Button variant="outline" className="w-full" disabled={busy} onClick={() => ref.current?.click()}>
        {busy ? "Uploading…" : count > 0 ? `Add more (${count} added)` : "Add b-roll images"}
      </Button>
      {count > 0 && (
        <button onClick={onClear} className="text-xs text-white/40 hover:text-white">Clear all</button>
      )}
    </div>
  );
}

function Disclosure({ title, subtitle, children }: { title: string; subtitle?: string; children: React.ReactNode }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="rounded-xl border border-white/10">
      <button onClick={() => setOpen((o) => !o)} className="flex w-full items-center justify-between px-4 py-3 text-left">
        <span>
          <span className="font-medium">{title}</span>
          {subtitle && <span className="ml-2 text-xs text-white/35">{subtitle}</span>}
        </span>
        <span className={`text-white/40 transition ${open ? "rotate-180" : ""}`}>⌄</span>
      </button>
      {open && <div className="space-y-4 border-t border-white/10 px-4 py-4">{children}</div>}
    </div>
  );
}

function Toggle({ label, hint, checked, disabled, onChange }: { label: string; hint?: string; checked: boolean; disabled?: boolean; onChange: (v: boolean) => void }) {
  return (
    <label className={`flex items-start justify-between gap-4 ${disabled ? "pointer-events-none opacity-40" : ""}`}>
      <span>
        <span className="text-sm">{label}</span>
        {hint && <span className="mt-0.5 block text-xs text-white/35">{hint}</span>}
      </span>
      <button type="button" role="switch" aria-checked={checked} onClick={() => onChange(!checked)}
        className={`relative mt-0.5 h-7 w-12 shrink-0 rounded-full p-0.5 transition before:absolute before:-inset-2.5 before:content-[''] ${checked ? "bg-[var(--accent)]" : "bg-white/15"}`}>
        <span className={`block h-6 w-6 rounded-full bg-black transition ${checked ? "translate-x-5" : ""}`} />
      </button>
    </label>
  );
}

function Segmented({ label, value, options, onChange, disabled }: { label: string; value: string; options: [string, string][]; onChange: (v: string) => void; disabled?: boolean }) {
  return (
    <div className={disabled ? "pointer-events-none opacity-40" : ""}>
      <Label>{label}</Label>
      <div className="flex gap-1 rounded-xl border border-white/10 p-1">
        {options.map(([v, l]) => (
          <button key={v} onClick={() => onChange(v)}
            className={`min-h-10 flex-1 whitespace-nowrap rounded-lg px-3 py-2 text-sm ${value === v ? "bg-[var(--accent)] text-black" : "text-white/55 hover:text-white"}`}>
            {l}
          </button>
        ))}
      </div>
    </div>
  );
}

function SelectRow({ label, value, options, onChange, disabled }: { label: string; value: string; options: [string, string][]; onChange: (v: string) => void; disabled?: boolean }) {
  return (
    <div className={disabled ? "pointer-events-none opacity-40" : ""}>
      <Label>{label}</Label>
      <select value={value} onChange={(e) => onChange(e.target.value)}
        className="min-h-11 w-full rounded-xl border border-white/10 bg-white/[0.03] px-4 py-2.5 text-sm">
        {options.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
      </select>
    </div>
  );
}

function Slider({ label, value, min, max, step, display, onChange, disabled }: { label: string; value: number; min: number; max: number; step: number; display: string; onChange: (v: number) => void; disabled?: boolean }) {
  return (
    <div className={disabled ? "pointer-events-none opacity-40" : ""}>
      <div className="flex items-center justify-between">
        <Label>{label}</Label>
        <span className="text-xs text-white/45">{display}</span>
      </div>
      <input type="range" min={min} max={max} step={step} value={value}
        onChange={(e) => onChange(parseFloat(e.target.value))} className="w-full accent-[var(--accent)]" />
    </div>
  );
}

function FixCutsPanel({ edl, onReRender }: { edl: ProjectEdl; onReRender: (edl: ProjectEdl) => void }) {
  const segs = segmentsFromEdl(edl);
  const [kept, setKept] = useState<Set<number>>(() => new Set(segs.map((s) => s.index)));
  if (segs.length === 0) return null;
  const toggle = (i: number) =>
    setKept((prev) => { const n = new Set(prev); if (n.has(i)) n.delete(i); else n.add(i); return n; });
  const dropped = segs.length - kept.size;
  return (
    <details className="mt-4 rounded-xl border border-white/10 bg-white/[0.02] p-4 text-left">
      <summary className="cursor-pointer text-sm font-medium text-white/80">✂️ Fix cuts &amp; re-render</summary>
      <p className="mt-2 text-xs text-white/45">Uncheck a segment to drop it, then re-render with your current settings — no re-cleaning.</p>
      <div className="mt-3 max-h-72 space-y-1 overflow-y-auto">
        {segs.map((s) => (
          <label key={s.index} className={`flex gap-2 rounded-lg px-2 py-1.5 text-sm ${kept.has(s.index) ? "" : "opacity-40 line-through"}`}>
            <input type="checkbox" checked={kept.has(s.index)} onChange={() => toggle(s.index)} className="mt-1" />
            <span className="shrink-0 tabular-nums text-white/40">{fmtTime(s.start)}–{fmtTime(s.end)}</span>
            <span className="text-white/70">{s.text || <em className="text-white/30">(no speech)</em>}</span>
          </label>
        ))}
      </div>
      <div className="mt-3 flex items-center gap-3">
        <Button disabled={kept.size === 0} onClick={() => onReRender(edlWithKept(edl, [...kept].sort((a, b) => a - b)))}>
          Re-render{dropped > 0 ? ` (drop ${dropped})` : ""}
        </Button>
        {dropped > 0 && <span className="text-xs text-white/40">{dropped} segment{dropped > 1 ? "s" : ""} dropped</span>}
      </div>
    </details>
  );
}

function BrandEditor({ boardId, userId, onError, onBrollAdded }: { boardId: string; userId: string; onError: (s: string) => void; onBrollAdded?: (paths: string[]) => void }) {
  const supabase = createClient();
  const ref = useRef<HTMLInputElement>(null);
  const trRef = useRef<HTMLInputElement>(null);
  const [primary, setPrimary] = useState("#FFD60A");
  const [outline, setOutline] = useState("#0A0A0A");
  const [wmReady, setWmReady] = useState(false);
  const [trCount, setTrCount] = useState(0);

  async function onTransitions(files: FileList) {
    try {
      const added: string[] = [];
      for (const f of Array.from(files)) {
        const ext = f.name.split(".").pop() || "png";
        const path = `${userId}/brand/${boardId}-tr-${Date.now()}-${Math.random().toString(36).slice(2, 7)}.${ext}`;
        const { error } = await supabase.storage.from("uploads").upload(path, f, { upsert: true, contentType: f.type });
        if (error) throw error;
        await supabase.from("brand_assets").insert({
          board_id: boardId, user_id: userId, kind: "transition", name: f.name,
          storage_path: path, anchor: "center", opacity: 1.0, scale: 1.0,
        });
        added.push(path);
      }
      setTrCount((c) => c + files.length);
      if (added.length) onBrollAdded?.(added);  // also save to the project's b-roll so it persists + is used
    } catch (e) {
      onError(msg(e));
    }
  }

  async function saveColors() {
    await supabase.from("brand_boards").update({ caption_primary: primary, caption_outline: outline }).eq("id", boardId);
  }

  async function onWatermark(file: File) {
    try {
      const path = `${userId}/brand/${boardId}-wm-${Date.now()}.${file.name.split(".").pop() || "png"}`;
      const { error } = await supabase.storage.from("uploads").upload(path, file, { upsert: true, contentType: file.type });
      if (error) throw error;
      await supabase.from("brand_assets").delete().eq("board_id", boardId).eq("kind", "watermark");
      await supabase.from("brand_assets").insert({
        board_id: boardId, user_id: userId, kind: "watermark", name: file.name,
        storage_path: path, anchor: "bottom_right", opacity: 0.85, scale: 0.16,
      });
      setWmReady(true);
    } catch (e) {
      onError(msg(e));
    }
  }

  return (
    <div className="mt-4 space-y-3 border-t border-white/10 pt-4">
      <div className="flex items-center gap-3 text-sm">
        <span className="text-white/45">Caption colors</span>
        <input type="color" value={primary} onChange={(e) => setPrimary(e.target.value)} onBlur={saveColors} className="h-7 w-9 rounded" />
        <input type="color" value={outline} onChange={(e) => setOutline(e.target.value)} onBlur={saveColors} className="h-7 w-9 rounded" />
      </div>
      <input ref={ref} type="file" accept="image/png,image/webp" className="hidden"
        onChange={(e) => e.target.files?.[0] && onWatermark(e.target.files[0])} />
      <Button variant="outline" className="w-full" onClick={() => ref.current?.click()}>
        {wmReady ? "Watermark set ✓" : "Upload watermark (PNG)"}
      </Button>
      <input ref={trRef} type="file" accept="image/*" multiple className="hidden"
        onChange={(e) => e.target.files?.length && onTransitions(e.target.files)} />
      <Button variant="outline" className="w-full" onClick={() => trRef.current?.click()}>
        {trCount > 0 ? `Brand b-roll images: ${trCount} ✓` : "Add brand b-roll / transition images"}
      </Button>
    </div>
  );
}
