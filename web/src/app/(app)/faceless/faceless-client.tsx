"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { createClient } from "@/lib/supabase/client";
import { Button, Card } from "@/components/ui";
import AvatarStudio from "./avatar-studio";

// Faceless studio: topic/script → narrated, AI-scene short. The form queues a job
// (script gen + TTS happen in /api/faceless); this view then tells the truth about
// progress and ends in a 9:16 player.

const VOICES = [
  { id: "Charon", name: "Charon", vibe: "Deep & cinematic" },
  { id: "Kore", name: "Kore", vibe: "Confident & clear" },
  { id: "Puck", name: "Puck", vibe: "Upbeat & friendly" },
  { id: "Aoede", name: "Aoede", vibe: "Bright & energetic" },
  { id: "Fenrir", name: "Fenrir", vibe: "Bold & intense" },
  { id: "Leda", name: "Leda", vibe: "Calm & soothing" },
] as const;

// Scene looks — the first three keep the photoreal pipeline; the rest swap in a
// full art-style override (claymation, cartoon, anime, …) for every AI scene.
const LOOKS = [
  ["cinematic", "Cinematic", "Photoreal, premium"],
  ["film", "Film", "35mm grade"],
  ["clean", "Clean", "Bright UGC"],
  ["claymation", "Claymation", "Stop-motion clay"],
  ["cartoon3d", "3D Cartoon", "Feature-animation"],
  ["anime", "Anime", "Cel-shaded drama"],
  ["comic", "Comic Book", "Inked panels"],
  ["watercolor", "Watercolor", "Hand-painted"],
  ["cyberpunk", "Cyberpunk", "Neon noir"],
  ["papercraft", "Paper Craft", "Layered cutouts"],
  ["character", "Character", "One hero, every scene"],
] as const;

type LookKey = (typeof LOOKS)[number][0];

// Style tiles live in the public assets bucket → swappable without a deploy.
const TILE_BASE = `${process.env.NEXT_PUBLIC_SUPABASE_URL}/storage/v1/object/public/assets/styles`;

// Publish targets — a user's connected accounts are grouped under these platforms.
const PLATFORM_ORDER = ["x", "tiktok", "instagram", "facebook", "linkedin", "youtube"] as const;
const PLATFORM_LABELS: Record<string, string> = {
  x: "X", tiktok: "TikTok", instagram: "Instagram", facebook: "Facebook", linkedin: "LinkedIn", youtube: "YouTube",
};

// Length options (seconds → label). Anything above the plan's max_length_sec renders locked.
const LENGTHS = [
  ["30", "30s"], ["60", "60s"], ["90", "90s"], ["300", "5m"], ["480", "8m"], ["900", "15m"],
] as const;
type LengthKey = (typeof LENGTHS)[number][0];

type SocialConn = { id: string; platform: string; username: string | null; label: string | null };
type PublishResult = { ok: boolean; url?: string; error?: string; note?: string };

type ElVoice = { voice_id: string; name: string; category: string; preview_url: string | null };

// Encoded voice value for the cast selects: "g:Charon" | "e:<voiceId>:<name>"
type CastChar = { desc: string; v: string };
type AvatarChar = { id: string; name: string; sheet: string; photo_path: string | null };
const castProvider = (v: string) => (v.startsWith("e:") ? "elevenlabs" : "gemini");

type VoiceSel =
  | { provider: "gemini"; id: string }
  | { provider: "elevenlabs"; id: string; name: string };

type JobRow = {
  status: "queued" | "processing" | "done" | "error";
  progress: number;
  output_path: string | null;
  error: string | null;
};

function Seg<T extends string>({
  value, options, onChange, label,
}: { value: T; options: readonly (readonly [T, string])[]; onChange: (v: T) => void; label: string }) {
  return (
    <div>
      <p className="mb-1.5 text-xs font-medium text-white/65">{label}</p>
      <div className="flex flex-wrap gap-1.5">
        {options.map(([v, text]) => (
          <button
            key={v}
            type="button"
            onClick={() => onChange(v)}
            aria-pressed={value === v}
            className={`press rounded-xl border px-3.5 py-2 text-sm font-medium transition-colors ${
              value === v
                ? "border-[var(--accent)]/60 bg-[var(--accent)]/15 text-white"
                : "border-white/10 bg-white/[0.03] text-white/60 hover:bg-white/5 hover:text-white/85"
            }`}
          >
            {text}
          </button>
        ))}
      </div>
    </div>
  );
}

/** Tiny play/stop control for voice previews — one shared <audio> across the page. */
function PlayDot({ playing, onClick, disabled }: { playing: boolean; onClick: () => void; disabled?: boolean }) {
  return (
    <button
      type="button"
      onClick={(e) => { e.stopPropagation(); onClick(); }}
      disabled={disabled}
      aria-label={playing ? "Stop preview" : "Play preview"}
      className={`press flex h-7 w-7 shrink-0 items-center justify-center rounded-full border text-[10px] transition-colors ${
        playing
          ? "border-[var(--accent)] bg-[var(--accent)] text-black"
          : "border-white/20 bg-white/5 text-white/70 hover:border-[var(--accent)]/60 hover:text-white"
      } disabled:cursor-not-allowed disabled:opacity-40`}
    >
      {playing ? "■" : "▶"}
    </button>
  );
}

function stageFor(p: number, status: string): string {
  if (status === "queued") return "Queued — a render slot opens in under a minute";
  if (p < 0.45) return "Transcribing the narration";
  if (p < 0.55) return "Planning the scenes";
  if (p < 0.82) return "Generating AI scenes";
  if (p < 0.95) return "Compositing video, captions, and sound";
  return "Finishing up";
}

export function FacelessClient({ maxLengthSec, plan }: { maxLengthSec: number; plan: string }) {
  const supabase = useMemo(() => createClient(), []);
  const [mode, setMode] = useState<"topic" | "script">("topic");
  const [topic, setTopic] = useState("");
  const [script, setScript] = useState("");
  const [voiceSel, setVoiceSel] = useState<VoiceSel>({ provider: "gemini", id: "Charon" });
  const [castMode, setCastMode] = useState<"single" | "duo">("single");
  const [charA, setCharA] = useState<CastChar>({ desc: "", v: "g:Charon" });
  const [charB, setCharB] = useState<CastChar>({ desc: "", v: "g:Leda" });
  const [look, setLook] = useState<LookKey>("cinematic");
  const [direction, setDirection] = useState("");
  const [avatars, setAvatars] = useState<AvatarChar[]>([]);
  const [avatarSel, setAvatarSel] = useState<string | null>(null);
  const [avatarBusy, setAvatarBusy] = useState(false);
  const [avatarMsg, setAvatarMsg] = useState<string | null>(null);
  const [showAvatarStudio, setShowAvatarStudio] = useState(false);
  const avatarFileRef = useRef<HTMLInputElement | null>(null);
  const [lengthSec, setLengthSec] = useState<LengthKey>("60");
  const [resolution, setResolution] = useState<"1080p" | "4k">("1080p");
  // Default to real AI motion (FastWan i2v on our GPU) — animated scenes are the product's
  // core value; users can switch to "stills" for a faster/cheaper render.
  const [sceneMode, setSceneMode] = useState<"stills" | "motion">("motion");
  // Premium "Cinematic motion" (Wan A14B on dedicated GPUs) — Agency plan, ≤2-min videos.
  // The server enforces both; this mirrors the length-selector's plan gating in the UI.
  const [cinematic, setCinematic] = useState(false);
  const cinematicAllowed = plan === "agency" || plan === "admin";
  const cinematicLengthOk = Number(lengthSec) <= 120;

  // Voice previews — one shared audio element; whichever key is playing owns it.
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const [playingKey, setPlayingKey] = useState<string | null>(null);

  // ElevenLabs (BYOK) voices + in-app cloning.
  const [elConnected, setElConnected] = useState<boolean | null>(null);
  const [elVoices, setElVoices] = useState<ElVoice[]>([]);
  const [cloneName, setCloneName] = useState("");
  const [cloneBusy, setCloneBusy] = useState(false);
  const [cloneMsg, setCloneMsg] = useState<string | null>(null);
  const [recState, setRecState] = useState<"idle" | "recording">("idle");
  const [recSeconds, setRecSeconds] = useState(0);
  const [sample, setSample] = useState<File | null>(null);
  const recRef = useRef<MediaRecorder | null>(null);
  const recChunks = useRef<Blob[]>([]);
  const recTimer = useRef<ReturnType<typeof setInterval> | null>(null);

  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Multi-account publish: connected accounts, the chosen subset, per-account results.
  const [connections, setConnections] = useState<SocialConn[]>([]);
  const [selectedConns, setSelectedConns] = useState<Set<string>>(new Set());
  const [publishBusy, setPublishBusy] = useState(false);
  const [publishResults, setPublishResults] = useState<Record<string, PublishResult>>({});
  const [publishMsg, setPublishMsg] = useState<string | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  const [title, setTitle] = useState<string>("");
  const [job, setJob] = useState<JobRow | null>(null);
  const [videoUrl, setVideoUrl] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const [autoGen, setAutoGen] = useState(false);
  const autoTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const lastFiredInput = useRef<string>("");

  // ~1 scene / 7s, matching the worker's cap (CADENCE_MAX_SCENES=130) — so a long video's
  // token estimate is honest (a 15-min motion render is ~384 tokens, not the old "48").
  const scenes = Math.max(3, Math.min(Math.round(Number(lengthSec) / 7), 130));

  const connsByPlatform = useMemo(() => {
    const m: Record<string, SocialConn[]> = {};
    for (const c of connections) (m[c.platform] ??= []).push(c);
    return m;
  }, [connections]);
  const publishNotes = useMemo(
    () => [...new Set(Object.values(publishResults).map((r) => r.note).filter((n): n is string => !!n))],
    [publishResults],
  );

  useEffect(() => () => {
    if (pollRef.current) clearInterval(pollRef.current);
    if (recTimer.current) clearInterval(recTimer.current);
    audioRef.current?.pause();
    recRef.current?.stream.getTracks().forEach((t) => t.stop());
  }, []);

  // Auto-generate is opt-in and remembered per browser.
  useEffect(() => { setAutoGen(localStorage.getItem("ch_autogen") === "1"); }, []);

  // Cinematic motion caps at 2-minute videos (v1) — picking a longer length switches it off
  // rather than letting the request 422 at the server.
  useEffect(() => {
    if (!cinematicLengthOk && cinematic) setCinematic(false);
  }, [cinematicLengthOk, cinematic]);

  useEffect(() => {
    fetch("/api/faceless/voices")
      .then((r) => r.json())
      .then((d: { connected?: boolean; voices?: ElVoice[] }) => {
        setElConnected(Boolean(d.connected));
        setElVoices(d.voices ?? []);
      })
      .catch(() => setElConnected(false));
  }, []);

  useEffect(() => {
    fetch("/api/avatar")
      .then((r) => r.json())
      .then((d: { characters?: AvatarChar[] }) => setAvatars(d.characters ?? []))
      .catch(() => {});
  }, []);

  // Connected social accounts (id + label + platform) drive the multi-select publisher.
  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const { data } = await supabase.rpc("my_social_connections");
        if (active) setConnections((data ?? []) as SocialConn[]);
      } catch {
        /* publisher just stays empty if this fails */
      }
    })();
    return () => {
      active = false;
    };
  }, [supabase]);

  async function createAvatar(files: FileList | null) {
    if (!files || files.length === 0) return;
    setAvatarBusy(true);
    setAvatarMsg(null);
    try {
      const allowed = new Set(["image/jpeg", "image/png", "image/webp"]);
      const picked = Array.from(files).filter((f) => allowed.has(f.type)).slice(0, 3);
      if (picked.length === 0) throw new Error("use jpeg, png or webp photos");
      const photos = await Promise.all(
        picked.map(async (f) => {
          const dataUrl = await new Promise<string>((resolve, reject) => {
            const fr = new FileReader();
            fr.onload = () => resolve(fr.result as string);
            fr.onerror = () => reject(new Error("could not read file"));
            fr.readAsDataURL(f);
          });
          return { mime: f.type, data: dataUrl.split(",")[1] ?? "" };
        }),
      );
      const r = await fetch("/api/avatar", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ photos }),
      });
      const d = await r.json();
      if (!r.ok) throw new Error(d.error ?? "could not create your avatar");
      setAvatars((prev) => [d.character, ...prev]);
      setAvatarSel(d.character.id);
      setAvatarMsg("Avatar ready — it now stars in every scene.");
    } catch (e) {
      setAvatarMsg(e instanceof Error ? e.message : "could not create your avatar");
    } finally {
      setAvatarBusy(false);
      if (avatarFileRef.current) avatarFileRef.current.value = "";
    }
  }

  async function deleteAvatar(id: string) {
    setAvatars((prev) => prev.filter((a) => a.id !== id));
    if (avatarSel === id) setAvatarSel(null);
    fetch(`/api/avatar?id=${id}`, { method: "DELETE" }).catch(() => {});
  }

  function toggleConn(id: string) {
    setSelectedConns((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  async function postToSelected() {
    if (!jobId || selectedConns.size === 0) return;
    setPublishBusy(true);
    setPublishMsg(null);
    try {
      const r = await fetch("/api/social/publish", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ connectionIds: [...selectedConns], jobId, caption: title.slice(0, 280) }),
      });
      const d = await r.json();
      if (!r.ok) throw new Error(d.error ?? "publish failed");
      const map: Record<string, PublishResult> = {};
      for (const res of (d.results ?? []) as (PublishResult & { connectionId: string })[]) {
        map[res.connectionId] = { ok: res.ok, url: res.url, error: res.error, note: res.note };
      }
      setPublishResults((prev) => ({ ...prev, ...map }));
    } catch (e) {
      setPublishMsg(e instanceof Error ? e.message : "publish failed");
    } finally {
      setPublishBusy(false);
    }
  }

  useEffect(() => {
    if (!jobId) return;
    pollRef.current = setInterval(async () => {
      const { data } = await supabase
        .from("render_jobs")
        .select("status,progress,output_path,error")
        .eq("id", jobId)
        .single<JobRow>();
      if (!data) return;
      setJob(data);
      if (data.status === "done" && data.output_path) {
        if (pollRef.current) clearInterval(pollRef.current);
        const { data: signed } = await supabase.storage
          .from("outputs")
          .createSignedUrl(data.output_path, 3600);
        if (signed) setVideoUrl(signed.signedUrl);
      }
      if (data.status === "error" && pollRef.current) clearInterval(pollRef.current);
    }, 2500);
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, [jobId, supabase]);

  function togglePreview(key: string, src: string | null) {
    if (!src) return;
    if (playingKey === key) {
      audioRef.current?.pause();
      setPlayingKey(null);
      return;
    }
    if (!audioRef.current) audioRef.current = new Audio();
    const a = audioRef.current;
    a.pause();
    a.src = src;
    a.onended = () => setPlayingKey(null);
    a.play().then(() => setPlayingKey(key)).catch(() => setPlayingKey(null));
  }

  async function startRecording() {
    setCloneMsg(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true },
      });
      recChunks.current = [];
      const rec = new MediaRecorder(stream);
      rec.ondataavailable = (e) => { if (e.data.size > 0) recChunks.current.push(e.data); };
      rec.onstop = () => {
        stream.getTracks().forEach((t) => t.stop());
        const blob = new Blob(recChunks.current, { type: rec.mimeType || "audio/webm" });
        setSample(new File([blob], "sample.webm", { type: blob.type }));
      };
      recRef.current = rec;
      rec.start();
      setRecSeconds(0);
      setRecState("recording");
      recTimer.current = setInterval(() => {
        setRecSeconds((s) => {
          if (s + 1 >= 60) stopRecording(); // 60s is plenty for an instant clone
          return s + 1;
        });
      }, 1000);
    } catch {
      setCloneMsg("Microphone unavailable — upload a sample instead.");
    }
  }

  function stopRecording() {
    if (recTimer.current) clearInterval(recTimer.current);
    recTimer.current = null;
    recRef.current?.stop();
    setRecState("idle");
  }

  async function submitClone() {
    if (!sample) return;
    setCloneBusy(true);
    setCloneMsg(null);
    try {
      const form = new FormData();
      form.append("name", cloneName.trim() || "My voice");
      form.append("files", sample);
      const r = await fetch("/api/faceless/clone", { method: "POST", body: form });
      const d = await r.json();
      if (!r.ok) throw new Error(d.error ?? "clone failed");
      setCloneMsg(`"${d.name}" cloned — selected below.`);
      setSample(null);
      const vr = await fetch("/api/faceless/voices").then((x) => x.json());
      setElVoices(vr.voices ?? []);
      setVoiceSel({ provider: "elevenlabs", id: d.voice_id, name: d.name });
    } catch (e) {
      setCloneMsg(e instanceof Error ? e.message : "clone failed");
    } finally {
      setCloneBusy(false);
    }
  }

  async function generate() {
    setError(null);
    setBusy(true);
    try {
      const castPayload =
        castMode === "duo"
          ? {
              mode: "dialogue" as const,
              characters: [charA, charB].map((c) => {
                const el = c.v.startsWith("e:");
                const [, id, ...nm] = c.v.split(":");
                return {
                  description: c.desc.trim(),
                  voiceProvider: el ? ("elevenlabs" as const) : ("gemini" as const),
                  voice: el ? undefined : id,
                  voiceId: el ? id : undefined,
                  voiceName: el ? nm.join(":") : id,
                };
              }),
            }
          : { mode: "single" as const };
      const r = await fetch("/api/faceless", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          topic: mode === "topic" ? topic.trim() : undefined,
          script: mode === "script" ? script.trim() : undefined,
          voice: voiceSel.provider === "gemini" ? voiceSel.id : "Charon",
          voiceProvider: voiceSel.provider,
          voiceId: voiceSel.provider === "elevenlabs" ? voiceSel.id : undefined,
          style: look === "film" ? "cinematic_film" : look === "clean" ? "clean_ugc" : "cinematic",
          sceneStyle: look,
          sceneDirection: direction.trim(),
          avatarSheet:
            castMode === "single" && avatarSel
              ? avatars.find((a) => a.id === avatarSel)?.sheet
              : undefined,
          lengthSec: Number(lengthSec),
          resolution,
          animate: sceneMode === "motion",
          cinematic: sceneMode === "motion" && cinematic,
          ...castPayload,
        }),
      });
      const data = await r.json();
      if (!r.ok) throw new Error(data.error ?? "generation failed");
      setJobId(data.jobId);
      setTitle(data.title ?? "");
      setJob({ status: "queued", progress: 0, output_path: null, error: null });
    } catch (e) {
      setError(e instanceof Error ? e.message : "generation failed");
    } finally {
      setBusy(false);
    }
  }

  function reset() {
    if (pollRef.current) clearInterval(pollRef.current);
    setJobId(null); setJob(null); setVideoUrl(null); setTitle(""); setError(null);
  }

  const duoOk =
    castMode === "single" ||
    (charA.desc.trim().length > 2 &&
      charB.desc.trim().length > 2 &&
      castProvider(charA.v) === castProvider(charB.v));
  const inputOk = (mode === "topic" ? topic.trim().length > 2 : script.trim().length > 20) && duoOk;
  const clonedVoices = elVoices.filter((v) => v.category !== "premade");
  const premadeVoices = elVoices.filter((v) => v.category === "premade");

  // Opt-in auto-generate: fire the render ~3.5s after the input is valid AND stable (idle, no
  // active job), once per DISTINCT input — never mid-typing, never a surprise repeat on the same
  // text. The explicit "Generate" button always works regardless of this toggle.
  useEffect(() => {
    if (autoTimer.current) { clearTimeout(autoTimer.current); autoTimer.current = null; }
    if (!autoGen || !inputOk || busy || job) return;
    const sig = mode === "topic" ? `t:${topic.trim()}` : `s:${script.trim()}`;
    if (lastFiredInput.current === sig) return;
    autoTimer.current = setTimeout(() => {
      const now = mode === "topic" ? `t:${topic.trim()}` : `s:${script.trim()}`;
      if (autoGen && inputOk && !busy && !job && lastFiredInput.current !== now) {
        lastFiredInput.current = now;
        generate();
      }
    }, 3500);
    return () => { if (autoTimer.current) clearTimeout(autoTimer.current); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoGen, inputOk, busy, job, topic, script, mode]);

  return (
    <div className="mx-auto w-full max-w-3xl px-4 py-10 sm:px-6">
      <p className="text-sm font-semibold text-[var(--accent)]">Faceless studio</p>
      <h1 className="mt-1 text-3xl font-bold tracking-tight sm:text-4xl">
        No camera. <span className="brand-grad-text">Still premium.</span>
      </h1>
      <p className="mt-2 max-w-xl text-sm leading-relaxed text-white/60">
        Give it a topic. It writes the narration in your blueprint voice, speaks it with a
        studio voice — or <span className="text-white/80">your own cloned voice</span> — paints
        every beat as an AI scene in the style you pick, and captions it karaoke-style.
      </p>

      {!jobId && (
        <Card className="mt-7 space-y-5">
          <Seg label="Start from" value={mode}
            options={[["topic", "Give me a topic"], ["script", "I have a script"]] as const}
            onChange={setMode} />

          {mode === "topic" ? (
            <textarea
              value={topic}
              onChange={(e) => setTopic(e.target.value)}
              rows={2}
              placeholder="e.g. Why most creators burn out in 90 days — and the system that prevents it"
              className="w-full rounded-xl border border-white/10 bg-white/[0.03] px-4 py-3 text-sm text-white outline-none transition focus:border-[var(--accent)]/60 focus:ring-2 focus:ring-[var(--accent)]/25"
            />
          ) : (
            <textarea
              value={script}
              onChange={(e) => setScript(e.target.value)}
              rows={6}
              placeholder="Paste the exact narration to speak…"
              className="w-full rounded-xl border border-white/10 bg-white/[0.03] px-4 py-3 text-sm text-white outline-none transition focus:border-[var(--accent)]/60 focus:ring-2 focus:ring-[var(--accent)]/25"
            />
          )}

          <Seg label="Narration" value={castMode}
            options={[["single", "Single narrator"], ["duo", "Two characters (dialogue)"]] as const}
            onChange={setCastMode} />

          {castMode === "single" && (
            <div className="rounded-xl border border-white/10 bg-white/[0.02] p-4">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <p className="text-sm font-semibold">Star yourself</p>
                  <p className="mt-0.5 text-xs text-white/50">
                    <b className="text-white/70">Photoreal:</b> record yourself → a real talking clone in your voice.
                    Or <b className="text-white/70">Drawn:</b> 1–3 photos → a stylized you in every scene.
                  </p>
                </div>
                <div className="flex shrink-0 flex-col gap-1.5">
                  <button
                    type="button"
                    onClick={() => setShowAvatarStudio(true)}
                    className="press rounded-lg bg-[var(--accent)] px-3 py-2 text-xs font-semibold text-white transition hover:opacity-90"
                  >
                    ✨ Photoreal avatar
                  </button>
                  <button
                    type="button"
                    disabled={avatarBusy}
                    onClick={() => avatarFileRef.current?.click()}
                    className="press rounded-lg border border-white/15 bg-white/[0.04] px-3 py-2 text-xs font-semibold text-white/80 transition hover:bg-white/10 disabled:opacity-50"
                  >
                    {avatarBusy ? "Reading photos…" : "Drawn (from photos)"}
                  </button>
                </div>
              </div>
              <input
                ref={avatarFileRef}
                type="file"
                accept="image/jpeg,image/png,image/webp"
                multiple
                className="hidden"
                onChange={(e) => createAvatar(e.target.files)}
              />
              {avatars.length > 0 && (
                <div className="mt-3 flex flex-wrap gap-2">
                  {avatars.map((a) => {
                    const active = avatarSel === a.id;
                    return (
                      <span key={a.id} className="inline-flex items-center">
                        <button
                          type="button"
                          onClick={() => setAvatarSel(active ? null : a.id)}
                          aria-pressed={active}
                          className={`press rounded-l-lg border px-3 py-1.5 text-xs transition-colors ${
                            active
                              ? "border-[var(--accent)]/60 bg-[var(--accent)]/15 text-white"
                              : "border-white/10 bg-white/[0.03] text-white/70 hover:bg-white/5"
                          }`}
                        >
                          {a.name}
                        </button>
                        <button
                          type="button"
                          aria-label={`delete ${a.name}`}
                          onClick={() => deleteAvatar(a.id)}
                          className="press rounded-r-lg border border-l-0 border-white/10 bg-white/[0.03] px-2 py-1.5 text-xs text-white/40 transition hover:bg-white/10 hover:text-white/80"
                        >
                          ×
                        </button>
                      </span>
                    );
                  })}
                </div>
              )}
              {avatarMsg && <p className="mt-2 text-xs text-white/55">{avatarMsg}</p>}
              {showAvatarStudio && <AvatarStudio onClose={() => setShowAvatarStudio(false)} />}
            </div>
          )}

          {castMode === "duo" && (
            <div className="grid gap-3 sm:grid-cols-2">
              {([["A", charA, setCharA], ["B", charB, setCharB]] as const).map(([label, ch, setCh]) => (
                <div key={label} className="rounded-xl border border-white/10 bg-white/[0.02] p-4">
                  <p className="text-sm font-semibold">Character {label}</p>
                  <input
                    value={ch.desc}
                    onChange={(e) => setCh({ ...ch, desc: e.target.value.slice(0, 160) })}
                    placeholder={label === "A" ? "e.g. a wise old clay owl professor" : "e.g. a curious young clay robot"}
                    className="mt-2 w-full rounded-lg border border-white/10 bg-white/[0.03] px-3 py-2 text-sm text-white outline-none transition focus:border-[var(--accent)]/60"
                  />
                  <select
                    value={ch.v}
                    onChange={(e) => setCh({ ...ch, v: e.target.value })}
                    className="mt-2 w-full rounded-lg border border-white/10 bg-[var(--surface)] px-3 py-2 text-sm text-white outline-none transition focus:border-[var(--accent)]/60"
                  >
                    <optgroup label="Studio voices">
                      {VOICES.map((v) => (
                        <option key={v.id} value={`g:${v.id}`}>{v.name} — {v.vibe}</option>
                      ))}
                    </optgroup>
                    {elConnected && elVoices.length > 0 && (
                      <optgroup label="Your ElevenLabs voices">
                        {elVoices.map((v) => (
                          <option key={v.voice_id} value={`e:${v.voice_id}:${v.name}`}>
                            {v.name}{v.category !== "premade" ? " ✦" : ""}
                          </option>
                        ))}
                      </optgroup>
                    )}
                  </select>
                </div>
              ))}
            </div>
          )}
          {castMode === "duo" && castProvider(charA.v) !== castProvider(charB.v) && (
            <p className="rounded-lg border border-amber-400/20 bg-amber-400/5 px-3 py-2 text-xs text-amber-200">
              Both characters need voices from the same provider (both Studio, or both ElevenLabs).
            </p>
          )}

          {castMode === "single" && (<>
          <div>
            <p className="mb-1.5 text-xs font-medium text-white/65">Studio voices <span className="text-white/35">— tap ▶ to hear</span></p>
            <div className="grid grid-cols-2 gap-1.5 sm:grid-cols-3">
              {VOICES.map((v) => {
                const active = voiceSel.provider === "gemini" && voiceSel.id === v.id;
                return (
                  <button
                    key={v.id}
                    type="button"
                    onClick={() => setVoiceSel({ provider: "gemini", id: v.id })}
                    aria-pressed={active}
                    className={`press flex items-center justify-between gap-2 rounded-xl border px-3 py-2.5 text-left transition-colors ${
                      active
                        ? "border-[var(--accent)]/60 bg-[var(--accent)]/15"
                        : "border-white/10 bg-white/[0.03] hover:bg-white/5"
                    }`}
                  >
                    <span>
                      <span className="block text-sm font-semibold">{v.name}</span>
                      <span className="block text-xs text-white/55">{v.vibe}</span>
                    </span>
                    <PlayDot
                      playing={playingKey === `g:${v.id}`}
                      onClick={() => togglePreview(`g:${v.id}`, `/voices/${v.id.toLowerCase()}.wav`)}
                    />
                  </button>
                );
              })}
            </div>
          </div>

          <div>
            <p className="mb-1.5 text-xs font-medium text-white/65">
              Your voice <span className="text-white/35">— ElevenLabs</span>
            </p>
            {elConnected === false && (
              <div className="rounded-xl border border-white/10 bg-white/[0.02] px-4 py-3 text-sm text-white/55">
                Narrate in <span className="text-white/80">your own voice</span>: connect your ElevenLabs key in{" "}
                <Link href="/connections" className="text-[var(--accent)] hover:underline">Connections</Link>,
                then clone yourself right here. Voice generation runs on your ElevenLabs plan.
              </div>
            )}
            {elConnected && (
              <div className="space-y-3">
                {elVoices.length > 0 && (
                  <div className="grid grid-cols-2 gap-1.5 sm:grid-cols-3">
                    {[...clonedVoices, ...premadeVoices].map((v) => {
                      const active = voiceSel.provider === "elevenlabs" && voiceSel.id === v.voice_id;
                      return (
                        <button
                          key={v.voice_id}
                          type="button"
                          onClick={() => setVoiceSel({ provider: "elevenlabs", id: v.voice_id, name: v.name })}
                          aria-pressed={active}
                          className={`press flex items-center justify-between gap-2 rounded-xl border px-3 py-2.5 text-left transition-colors ${
                            active
                              ? "border-[var(--accent)]/60 bg-[var(--accent)]/15"
                              : "border-white/10 bg-white/[0.03] hover:bg-white/5"
                          }`}
                        >
                          <span className="min-w-0">
                            <span className="block truncate text-sm font-semibold">{v.name}</span>
                            <span className={`block text-xs ${v.category !== "premade" ? "text-[var(--accent)]" : "text-white/55"}`}>
                              {v.category !== "premade" ? "✦ your clone" : "ElevenLabs"}
                            </span>
                          </span>
                          <PlayDot
                            playing={playingKey === `e:${v.voice_id}`}
                            onClick={() => togglePreview(`e:${v.voice_id}`, v.preview_url)}
                            disabled={!v.preview_url}
                          />
                        </button>
                      );
                    })}
                  </div>
                )}

                <div className="rounded-xl border border-dashed border-white/15 bg-white/[0.02] p-4">
                  <p className="text-sm font-semibold">Clone your voice</p>
                  <p className="mt-1 text-xs text-white/50">
                    Read anything naturally for 30–60 seconds — or upload a clean sample. The clone
                    lands in your ElevenLabs library and is instantly usable here.
                  </p>
                  <div className="mt-3 flex flex-wrap items-center gap-2">
                    <input
                      value={cloneName}
                      onChange={(e) => setCloneName(e.target.value)}
                      placeholder="Voice name (e.g. Cory)"
                      className="h-9 w-44 rounded-lg border border-white/10 bg-white/[0.03] px-3 text-sm text-white outline-none transition focus:border-[var(--accent)]/60"
                    />
                    {recState === "idle" ? (
                      <Button variant="outline" onClick={startRecording} type="button" className="h-9 px-3 text-xs">
                        ● Record
                      </Button>
                    ) : (
                      <Button variant="outline" onClick={stopRecording} type="button" className="h-9 animate-pulse px-3 text-xs">
                        ■ Stop ({recSeconds}s)
                      </Button>
                    )}
                    <label className="press inline-flex h-9 cursor-pointer items-center rounded-lg border border-white/15 px-3 text-xs font-medium text-white/70 transition-colors hover:bg-white/5">
                      Upload sample
                      <input
                        type="file"
                        accept="audio/*,video/webm"
                        className="hidden"
                        onChange={(e) => { setSample(e.target.files?.[0] ?? null); setCloneMsg(null); }}
                      />
                    </label>
                    {sample && (
                      <span className="max-w-[12rem] truncate text-xs text-white/55">
                        {sample.name} · {(sample.size / 1048576).toFixed(1)}MB
                      </span>
                    )}
                    <Button onClick={submitClone} disabled={!sample || cloneBusy} type="button" className="h-9 px-4 text-xs">
                      {cloneBusy ? "Cloning…" : "Create clone"}
                    </Button>
                  </div>
                  {cloneMsg && <p className="mt-2 text-xs text-white/60">{cloneMsg}</p>}
                </div>
              </div>
            )}
          </div>
          </>)}

          <div>
            <p className="mb-1.5 text-xs font-medium text-white/65">
              Look <span className="text-white/35">— every AI scene renders in this style</span>
            </p>
            <div className="grid grid-cols-3 gap-2 sm:grid-cols-4">
              {LOOKS.map(([key, label, hint]) => {
                const active = look === key;
                return (
                  <button
                    key={key}
                    type="button"
                    onClick={() => setLook(key)}
                    aria-pressed={active}
                    title={hint}
                    className={`press group relative aspect-square overflow-hidden rounded-xl border text-left transition-all ${
                      active
                        ? "border-[var(--accent)] ring-2 ring-[var(--accent)]/40 shadow-[0_0_24px_rgba(110,123,255,0.25)]"
                        : "border-white/10 hover:border-white/30"
                    }`}
                  >
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img
                      src={`${TILE_BASE}/${key}.jpg`}
                      alt={`${label} style example`}
                      loading="lazy"
                      className={`absolute inset-0 h-full w-full object-cover transition duration-300 ${
                        active ? "scale-105" : "group-hover:scale-105 opacity-90 group-hover:opacity-100"
                      }`}
                    />
                    <span className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/85 via-black/40 to-transparent px-2 pb-1.5 pt-6 text-xs font-semibold text-white">
                      {label}
                      {active && <span className="ml-1 text-[var(--accent)]">✓</span>}
                    </span>
                  </button>
                );
              })}
            </div>
          </div>

          <div>
            <p className="mb-1.5 text-xs font-medium text-white/65">
              Direct the scenes <span className="text-white/35">— optional</span>
            </p>
            <textarea
              value={direction}
              onChange={(e) => setDirection(e.target.value.slice(0, 400))}
              rows={2}
              placeholder='e.g. "A tiny clay robot stars in every scene" · "Make me a viking exploring each idea" · "Warm sunset palette, lots of close-ups"'
              className="w-full rounded-xl border border-white/10 bg-white/[0.03] px-4 py-3 text-sm text-white outline-none transition focus:border-[var(--accent)]/60 focus:ring-2 focus:ring-[var(--accent)]/25"
            />
          </div>

          <div>
            <p className="mb-1.5 text-xs font-medium text-white/65">
              Length <span className="text-white/35">— longer videos unlock on higher plans</span>
            </p>
            <div className="flex flex-wrap gap-1.5">
              {LENGTHS.map(([val, label]) => {
                const sec = Number(val);
                const locked = sec > maxLengthSec;
                const active = lengthSec === val;
                const need = sec <= 300 ? "Creator" : "Agency";
                return (
                  <button
                    key={val}
                    type="button"
                    disabled={locked}
                    onClick={() => setLengthSec(val)}
                    aria-pressed={active}
                    title={locked ? `Unlock ${label} on the ${need} plan` : undefined}
                    className={`press rounded-xl border px-3.5 py-2 text-sm font-medium transition-colors ${
                      active
                        ? "border-[var(--accent)]/60 bg-[var(--accent)]/15 text-white"
                        : locked
                          ? "cursor-not-allowed border-white/5 bg-white/[0.02] text-white/25"
                          : "border-white/10 bg-white/[0.03] text-white/60 hover:bg-white/5 hover:text-white/85"
                    }`}
                  >
                    {label}
                    {locked && <span className="ml-1 text-[10px] text-[var(--accent)]/70">{need}</span>}
                  </button>
                );
              })}
            </div>
          </div>

          <Seg label="Quality" value={resolution}
            options={[["1080p", "1080p"], ["4k", "4K Ultra"]] as const}
            onChange={setResolution} />

          <div>
            <Seg label="Scenes" value={sceneMode}
              options={[["stills", "Stills (cinematic push)"], ["motion", "Animated (AI motion)"]] as const}
              onChange={setSceneMode} />
            {sceneMode === "motion" && (
              <p className="mt-1.5 text-xs text-white/45">
                Every scene becomes a real motion clip on our own GPUs — characters and
                camera genuinely move. 3 tokens per scene and a longer render.
              </p>
            )}
            {sceneMode === "motion" && (
              <div className="mt-3 flex items-center justify-between gap-3 rounded-lg border border-white/10 px-3 py-2">
                <span id="cinematic-label" className="text-xs text-white/55">
                  <b className="text-white/80">Cinematic motion</b>
                  {!cinematicAllowed && (
                    <span className="ml-1.5 rounded-md border border-[var(--accent)]/30 bg-[var(--accent)]/10 px-1.5 py-0.5 text-[10px] font-semibold text-[var(--accent)]">
                      Agency
                    </span>
                  )}
                  {" "}— {cinematicAllowed
                    ? cinematicLengthOk
                      ? "film-grade motion from our biggest video model, on dedicated GPUs"
                      : "available on videos up to 90s — pick a shorter length"
                    : "film-grade motion from our biggest video model. Upgrade to Agency to unlock"}
                </span>
                <button
                  type="button"
                  role="switch"
                  aria-checked={cinematic}
                  aria-labelledby="cinematic-label"
                  disabled={!cinematicAllowed || !cinematicLengthOk}
                  title={!cinematicAllowed ? "Unlock Cinematic motion on the Agency plan" : undefined}
                  onClick={() => setCinematic((v) => !v)}
                  className={`relative h-6 w-11 shrink-0 rounded-full transition-colors disabled:cursor-not-allowed disabled:opacity-40 ${
                    cinematic ? "bg-[var(--accent)]" : "bg-white/15"
                  }`}
                >
                  <span className={`absolute top-0.5 h-5 w-5 rounded-full bg-white transition-transform ${cinematic ? "translate-x-[22px]" : "translate-x-0.5"}`} />
                </button>
              </div>
            )}
          </div>

          {error && (
            <p className="rounded-xl border border-red-500/20 bg-red-500/5 px-3 py-2 text-sm text-red-300">
              {error}
            </p>
          )}

          <div className="mb-3 flex items-center justify-between gap-3 rounded-lg border border-white/10 px-3 py-2">
            <span id="autogen-label" className="text-xs text-white/55">
              <b className="text-white/80">Auto-generate</b> — start ~3s after your {mode === "topic" ? "topic" : "script"} is ready, no click
            </span>
            <button
              type="button"
              role="switch"
              aria-checked={autoGen}
              aria-labelledby="autogen-label"
              onClick={() => setAutoGen((v) => { const nv = !v; try { localStorage.setItem("ch_autogen", nv ? "1" : "0"); } catch { /* ignore */ } return nv; })}
              className={`relative h-6 w-11 shrink-0 rounded-full transition-colors ${autoGen ? "bg-[var(--accent)]" : "bg-white/15"}`}
            >
              <span className={`absolute top-0.5 h-5 w-5 rounded-full bg-white transition-transform ${autoGen ? "translate-x-[22px]" : "translate-x-0.5"}`} />
            </button>
          </div>
          <div className="flex items-center justify-between gap-3">
            <p className="text-xs text-white/45">
              ≈ {scenes} AI scenes · {sceneMode === "motion" ? scenes * 3 : scenes} tokens
              {sceneMode === "motion" && (cinematic ? " · cinematic motion" : " · animated")}
              {castMode === "duo"
                ? " · two-voice dialogue"
                : voiceSel.provider === "elevenlabs"
                  ? " · voiced as " + ("name" in voiceSel ? voiceSel.name : "your clone")
                  : ""}
            </p>
            <Button onClick={generate} disabled={busy || !inputOk} className="min-w-44">
              {busy ? "Writing & voicing…" : "Generate video"}
            </Button>
          </div>
        </Card>
      )}

      {jobId && job && job.status !== "done" && job.status !== "error" && (
        <Card className="mt-7 space-y-4">
          {title && <h2 className="text-base font-semibold">{title}</h2>}
          <div>
            <div className="h-2 overflow-hidden rounded-full bg-white/5">
              <div
                className="h-full rounded-full transition-[width] duration-700"
                style={{ width: `${Math.max(4, Math.round(job.progress * 100))}%`, background: "var(--brand-grad)" }}
              />
            </div>
            <p className="mt-2 text-sm text-white/60">{stageFor(job.progress, job.status)}</p>
          </div>
          <p className="text-xs text-white/40">
            You can leave this page — the video keeps rendering and lands in your Library.
          </p>
        </Card>
      )}

      {job?.status === "error" && (
        <Card className="mt-7 space-y-3 border-red-500/20">
          <h2 className="text-base font-semibold text-red-300">That render failed</h2>
          <p className="text-sm text-white/60">{job.error ?? "Unknown error."} Your tokens for unrendered scenes were not consumed.</p>
          <Button variant="outline" onClick={reset}>Try again</Button>
        </Card>
      )}

      {job?.status === "done" && videoUrl && (
        <div className="mt-7 space-y-4">
          {title && <h2 className="text-lg font-semibold">{title}</h2>}
          <video
            src={videoUrl}
            controls
            playsInline
            className="mx-auto aspect-[9/16] w-full max-w-[320px] rounded-2xl border border-white/10 bg-black"
          />
          <div className="mx-auto flex max-w-[320px] gap-2">
            <a href={videoUrl} download="clouthook-faceless.mp4" className="flex-1">
              <Button className="w-full">Download</Button>
            </a>
            <Button variant="outline" onClick={reset}>Make another</Button>
          </div>
          <div className="mx-auto max-w-[320px]">
            <p className="mb-1.5 text-center text-xs font-medium text-white/55">Post directly to</p>
            {connections.length === 0 ? (
              <p className="text-center text-xs text-white/45">
                <Link href="/connections" className="text-[var(--accent)] hover:underline">Connect an account</Link>{" "}
                to post straight to your socials.
              </p>
            ) : (
              <>
                <div className="space-y-3">
                  {PLATFORM_ORDER.filter((p) => connsByPlatform[p]?.length).map((p) => (
                    <div key={p}>
                      <p className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-white/40">
                        {PLATFORM_LABELS[p]}
                      </p>
                      <div className="space-y-1">
                        {connsByPlatform[p].map((c) => {
                          const res = publishResults[c.id];
                          const checked = selectedConns.has(c.id);
                          return (
                            <label
                              key={c.id}
                              className={`flex cursor-pointer items-center justify-between gap-2 rounded-lg border px-3 py-2 text-sm transition-colors ${
                                res?.ok
                                  ? "border-emerald-400/40 bg-emerald-400/10"
                                  : res?.error
                                    ? "border-red-400/30 bg-red-400/5"
                                    : checked
                                      ? "border-[var(--accent)]/50 bg-[var(--accent)]/10"
                                      : "border-white/10 bg-white/[0.03] hover:bg-white/5"
                              }`}
                            >
                              <span className="flex min-w-0 items-center gap-2">
                                <input
                                  type="checkbox"
                                  checked={checked}
                                  onChange={() => toggleConn(c.id)}
                                  className="h-4 w-4 shrink-0 accent-[var(--accent)]"
                                />
                                <span className="truncate text-white/85">
                                  @{c.label || c.username || PLATFORM_LABELS[p]}
                                </span>
                              </span>
                              {res?.ok && res.url ? (
                                <a
                                  href={res.url}
                                  target="_blank"
                                  rel="noreferrer"
                                  onClick={(e) => e.stopPropagation()}
                                  className="shrink-0 text-xs text-emerald-300 underline-offset-2 hover:underline"
                                >
                                  View
                                </a>
                              ) : res?.error ? (
                                <span className="shrink-0 text-xs text-red-300" title={res.error}>Failed</span>
                              ) : null}
                            </label>
                          );
                        })}
                      </div>
                    </div>
                  ))}
                </div>
                <Button
                  onClick={postToSelected}
                  disabled={publishBusy || selectedConns.size === 0}
                  className="mt-3 w-full"
                >
                  {publishBusy ? "Posting…" : `Post to selected (${selectedConns.size})`}
                </Button>
                {publishNotes.length > 0 && (
                  <div className="mt-1.5 space-y-0.5">
                    {publishNotes.map((n) => (
                      <p key={n} className="text-center text-xs text-white/50">{n}</p>
                    ))}
                  </div>
                )}
              </>
            )}
            {publishMsg && <p className="mt-1.5 text-center text-xs text-white/55">{publishMsg}</p>}
          </div>
        </div>
      )}
    </div>
  );
}
