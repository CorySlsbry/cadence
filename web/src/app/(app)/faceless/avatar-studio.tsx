"use client";

import { useEffect, useRef, useState } from "react";

// Photoreal talking-avatar studio: record a guided reference (or upload a photo) → record an
// on-camera consent line + affirm checkboxes → create (multipart /api/avatar) → optionally
// render a first video (/api/avatar/[id]/render). Consent is captured here and enforced
// fail-closed server-side. Capture reuses MediaRecorder, like the studio recorder.

type Created = { id: string; name: string; voice_id: string | null };

const TELEPROMPTER = [
  "Hey — quick one. I want to show you something that changed how I make videos.",
  "Picture this: you record once, and the whole thing edits itself — captions, b-roll, the works.",
  "It feels almost unfair how fast it is. I went from hours of editing to minutes.",
  "So here's my honest take, and a question for you at the end…",
  "(now hold still, mouth closed, for three seconds)",
];

const CONSENT_LINE =
  "I'm [say your name], and I consent to CloutHook creating an AI avatar and voice of myself, for my own videos.";

const FRAMINGS = [
  ["lower_third", "Lower-third bust"],
  ["full", "Full-frame presenter"],
  ["corner", "Corner bubble"],
] as const;

export default function AvatarStudio({ onClose, onCreated }: { onClose: () => void; onCreated?: (c: Created) => void }) {
  const [mode, setMode] = useState<"video" | "phone" | "photo">("video");
  const [refBlob, setRefBlob] = useState<Blob | null>(null);
  const [photoFile, setPhotoFile] = useState<File | null>(null);
  const [phone, setPhone] = useState<{ token: string; url: string; qr: string } | null>(null);
  const [phonePath, setPhonePath] = useState<string | null>(null);
  const [phoneWaiting, setPhoneWaiting] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const [consentBlob, setConsentBlob] = useState<Blob | null>(null);
  const [name, setName] = useState("My avatar");
  const [checks, setChecks] = useState({ ownFace: false, ownVoice: false, tos: false });
  const [framing, setFraming] = useState<string>("lower_third");
  const [recording, setRecording] = useState<null | "ref" | "consent">(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [created, setCreated] = useState<Created | null>(null);

  const videoRef = useRef<HTMLVideoElement | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const recRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<BlobPart[]>([]);

  useEffect(
    () => () => {
      streamRef.current?.getTracks().forEach((t) => t.stop());
      if (pollRef.current) clearInterval(pollRef.current);
    },
    [],
  );

  async function ensureCam() {
    if (streamRef.current) return streamRef.current;
    const s = await navigator.mediaDevices.getUserMedia({
      video: { width: { ideal: 1920 }, height: { ideal: 1080 }, facingMode: "user" },
      audio: true,
    });
    streamRef.current = s;
    if (videoRef.current) {
      videoRef.current.srcObject = s;
      await videoRef.current.play().catch(() => {});
    }
    return s;
  }

  async function startRec(target: "ref" | "consent") {
    setError(null);
    try {
      const s = await ensureCam();
      chunksRef.current = [];
      const rec = new MediaRecorder(s, { mimeType: "video/webm" });
      rec.ondataavailable = (e) => e.data.size && chunksRef.current.push(e.data);
      rec.onstop = () => {
        const blob = new Blob(chunksRef.current, { type: "video/webm" });
        if (target === "ref") setRefBlob(blob);
        else setConsentBlob(blob);
      };
      rec.start();
      recRef.current = rec;
      setRecording(target);
    } catch {
      setError("Camera/mic access is required to record. Allow it and try again.");
    }
  }

  function stopRec() {
    recRef.current?.stop();
    setRecording(null);
  }

  // Phone handoff: mint a QR-linked session, then poll until the phone uploads its clip.
  async function startPhone() {
    setError(null);
    setPhonePath(null);
    try {
      const r = await fetch("/api/avatar/phone-session", { method: "POST" });
      const d = await r.json();
      if (!r.ok) throw new Error(d.error ?? "could not start a phone session");
      setPhone({ token: d.token, url: d.url, qr: d.qr });
      setPhoneWaiting(true);
      if (pollRef.current) clearInterval(pollRef.current);
      pollRef.current = setInterval(async () => {
        try {
          const s = await fetch(`/api/avatar/phone-session/${d.token}`);
          if (!s.ok) return;
          const sj = await s.json();
          if (sj.status === "uploaded" && sj.recording_path) {
            setPhonePath(sj.recording_path as string);
            setPhoneWaiting(false);
            if (pollRef.current) clearInterval(pollRef.current);
          }
        } catch {
          /* transient — keep polling */
        }
      }, 3000);
    } catch (e) {
      setError(e instanceof Error ? e.message : "could not start a phone session");
    }
  }

  const consentReady = checks.ownFace && checks.ownVoice && checks.tos && !!consentBlob;
  const refReady = mode === "photo" ? !!photoFile : mode === "phone" ? !!phonePath : !!refBlob;

  async function create() {
    if (!refReady) return setError("Record (or upload) your reference first.");
    if (!consentReady) return setError("Record the consent line and check all three boxes.");
    setBusy(true);
    setError(null);
    try {
      const fd = new FormData();
      fd.set("name", name.trim() || "My avatar");
      fd.set("source_kind", mode === "photo" ? "photo" : "video");
      fd.set("framing_default", framing);
      fd.set("tos_version", "v1");
      fd.set("consent_script_version", "v1");
      fd.set("checkbox_set", JSON.stringify(checks));
      if (mode === "phone") {
        fd.set("source_path", phonePath!); // high-quality clip already uploaded from the phone
      } else {
        fd.set(
          "source",
          mode === "photo" ? photoFile! : new File([refBlob!], "reference.webm", { type: "video/webm" }),
        );
      }
      fd.set("consent_video", new File([consentBlob!], "consent.webm", { type: "video/webm" }));
      // The consent clip's audio doubles as the voice-clone sample (ElevenLabs BYOK).
      fd.set("voice_sample", new File([consentBlob!], "voice.webm", { type: "video/webm" }));
      const r = await fetch("/api/avatar", { method: "POST", body: fd });
      const d = await r.json();
      if (!r.ok) throw new Error(d.error ?? "could not create your avatar");
      setCreated(d.character as Created);
      onCreated?.(d.character as Created);
      streamRef.current?.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    } catch (e) {
      setError(e instanceof Error ? e.message : "could not create your avatar");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/70 p-4 sm:items-center">
      <div className="w-full max-w-lg rounded-2xl border border-white/10 bg-[var(--background)] p-5 shadow-2xl">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-base font-semibold">Create a photoreal avatar</h2>
          <button onClick={onClose} className="press text-white/50 hover:text-white" aria-label="close">×</button>
        </div>

        {created ? (
          <CreatedPanel created={created} framing={framing} onClose={onClose} />
        ) : (
          <>
            {/* live preview */}
            <div className="relative overflow-hidden rounded-xl border border-white/10 bg-black" style={{ aspectRatio: "9 / 16", maxHeight: 360 }}>
              <video ref={videoRef} muted playsInline className="h-full w-full object-cover" />
              {recording === "ref" && (
                <div className="absolute inset-x-0 bottom-0 max-h-[45%] overflow-hidden bg-gradient-to-t from-black/85 to-transparent p-3 text-center text-sm text-white/90">
                  {TELEPROMPTER.map((l, i) => <p key={i} className="mb-1">{l}</p>)}
                </div>
              )}
              <div className="absolute left-2 top-2 rounded-full bg-black/60 px-2 py-0.5 text-[10px] text-white/70">
                Look at the lens • waist-up • even light
              </div>
            </div>

            {/* mode + reference */}
            <div className="mt-3 grid grid-cols-3 gap-2">
              {([
                ["video", "Webcam"],
                ["phone", "Phone · best"],
                ["photo", "Photo"],
              ] as const).map(([m, label]) => (
                <button key={m} onClick={() => setMode(m)} aria-pressed={mode === m}
                  className={`press rounded-lg border px-2 py-2 text-xs ${mode === m ? "border-[var(--accent)]/60 bg-[var(--accent)]/15 text-white" : "border-white/10 bg-white/[0.03] text-white/70"}`}>
                  {label}
                </button>
              ))}
            </div>

            <div className="mt-2">
              {mode === "video" && (
                <button onClick={() => (recording === "ref" ? stopRec() : startRec("ref"))}
                  className="press w-full rounded-lg border border-white/15 bg-white/[0.04] px-3 py-2 text-sm">
                  {recording === "ref" ? "■ Stop recording" : refBlob ? "↻ Re-record reference ✓" : "● Record reference (60–90s)"}
                </button>
              )}
              {mode === "phone" && (
                <div className="rounded-lg border border-white/15 bg-white/[0.04] p-3 text-center">
                  {phonePath ? (
                    <p className="text-sm text-emerald-300">✓ Phone clip received — create your avatar below.</p>
                  ) : phone ? (
                    <>
                      {/* eslint-disable-next-line @next/next/no-img-element */}
                      <img src={phone.qr} alt="Scan to record on your phone" width={176} height={176}
                        className="mx-auto rounded-lg bg-white p-2" />
                      <p className="mt-2 text-xs text-white/70">Scan with your phone camera, record, and it lands here automatically.</p>
                      <p className="mt-1 text-[10px] text-white/40 break-all">{phone.url}</p>
                      {phoneWaiting && <p className="mt-1 text-[11px] text-[var(--accent)]">Waiting for your phone…</p>}
                    </>
                  ) : (
                    <button onClick={startPhone}
                      className="press w-full rounded-lg border border-white/15 bg-white/[0.04] px-3 py-2 text-sm">
                      📱 Show QR to record on my phone
                    </button>
                  )}
                  <p className="mt-2 text-[10px] text-white/40">A phone shoots far sharper than a webcam — best avatar quality.</p>
                </div>
              )}
              {mode === "photo" && (
                <label className="press block w-full cursor-pointer rounded-lg border border-white/15 bg-white/[0.04] px-3 py-2 text-center text-sm">
                  {photoFile ? `Photo selected ✓ (${photoFile.name})` : "Choose a clear, well-lit photo"}
                  <input type="file" accept="image/png,image/jpeg,image/webp" className="hidden"
                    onChange={(e) => setPhotoFile(e.target.files?.[0] ?? null)} />
                </label>
              )}
            </div>

            {/* consent */}
            <div className="mt-4 rounded-xl border border-amber-400/20 bg-amber-400/[0.04] p-3">
              <p className="text-xs font-semibold text-amber-200/90">Consent (required — this clones your real likeness + voice)</p>
              <p className="mt-1 text-xs italic text-white/65">Read on camera: “{CONSENT_LINE}”</p>
              <button onClick={() => (recording === "consent" ? stopRec() : startRec("consent"))}
                className="press mt-2 w-full rounded-lg border border-white/15 bg-white/[0.04] px-3 py-2 text-sm">
                {recording === "consent" ? "■ Stop" : consentBlob ? "↻ Re-record consent ✓" : "● Record consent line"}
              </button>
              {([
                ["ownFace", "This is me — I'm not cloning anyone else."],
                ["ownVoice", "I consent to cloning my voice for my own videos."],
                ["tos", "I agree to the Terms & AI-likeness policy."],
              ] as const).map(([k, label]) => (
                <label key={k} className="mt-2 flex items-start gap-2 text-xs text-white/75">
                  <input type="checkbox" checked={checks[k]} onChange={(e) => setChecks((c) => ({ ...c, [k]: e.target.checked }))} className="mt-0.5" />
                  {label}
                </label>
              ))}
            </div>

            {/* name + framing */}
            <div className="mt-3 flex gap-2">
              <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Avatar name"
                className="input flex-1" />
              <select value={framing} onChange={(e) => setFraming(e.target.value)} className="input">
                {FRAMINGS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
              </select>
            </div>

            {error && <p className="mt-3 text-xs text-red-300">{error}</p>}
            <button onClick={create} disabled={busy || !refReady || !consentReady}
              className="press mt-4 w-full rounded-lg bg-[var(--accent)] px-3 py-2.5 text-sm font-semibold text-white disabled:opacity-40">
              {busy ? "Creating your avatar…" : "Create avatar"}
            </button>
          </>
        )}
      </div>
    </div>
  );
}

function CreatedPanel({ created, framing, onClose }: { created: Created; framing: string; onClose: () => void }) {
  const [mode, setMode] = useState<"standalone" | "presenter">("standalone");
  const [topic, setTopic] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function render() {
    if (!topic.trim()) return setMsg("Add a topic (or paste a script) to generate a video.");
    setBusy(true);
    setMsg(null);
    try {
      const r = await fetch(`/api/avatar/${created.id}/render`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ mode, framing, topic, look: "cinematic" }),
      });
      const d = await r.json();
      if (!r.ok) throw new Error(d.error ?? "could not start the render");
      setMsg("Rendering — it'll appear in your Library shortly.");
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "could not start the render");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <p className="text-sm text-white/80">✓ <b>{created.name}</b> is ready{created.voice_id ? " (voice cloned)" : ""}.</p>
      <p className="mt-1 text-xs text-white/50">Generate your first video, or close and use it from the Faceless tab.</p>
      <div className="mt-3 flex gap-2">
        {(["standalone", "presenter"] as const).map((m) => (
          <button key={m} onClick={() => setMode(m)} aria-pressed={mode === m}
            className={`press flex-1 rounded-lg border px-3 py-2 text-xs ${mode === m ? "border-[var(--accent)]/60 bg-[var(--accent)]/15 text-white" : "border-white/10 bg-white/[0.03] text-white/70"}`}>
            {m === "standalone" ? "Just me talking" : "Me as presenter (in scenes)"}
          </button>
        ))}
      </div>
      <textarea value={topic} onChange={(e) => setTopic(e.target.value)} placeholder="What's the video about? (or paste a full script)"
        className="input mt-2 h-20 w-full" />
      {msg && <p className="mt-2 text-xs text-white/60">{msg}</p>}
      <p className="mt-2 text-[11px] text-white/45">
        💎 Costs <b className="text-white/70">8 tokens</b> · Creator plan · up to 20 avatar videos / month
      </p>
      <div className="mt-2 flex gap-2">
        <button onClick={render} disabled={busy} className="press flex-1 rounded-lg bg-[var(--accent)] px-3 py-2.5 text-sm font-semibold text-white disabled:opacity-40">
          {busy ? "Starting…" : "Generate video"}
        </button>
        <button onClick={onClose} className="press rounded-lg border border-white/15 px-3 py-2.5 text-sm">Done</button>
      </div>
    </div>
  );
}
