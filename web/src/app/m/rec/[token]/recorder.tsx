"use client";

import { useCallback, useEffect, useRef, useState } from "react";

const TIPS = [
  "Talk naturally for 30–60 seconds — like you're telling a friend something.",
  "Bright, even light on your face. Phone steady (prop it up). Look at the lens.",
  "Hold still with your mouth closed for the last 3 seconds.",
];

type Phase = "intro" | "live" | "recording" | "review" | "uploading" | "done" | "error";

export default function PhoneRecorder({ token }: { token: string }) {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const recRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const [phase, setPhase] = useState<Phase>("intro");
  const [err, setErr] = useState("");
  const [blob, setBlob] = useState<Blob | null>(null);
  const [previewUrl, setPreviewUrl] = useState("");
  const [secs, setSecs] = useState(0);

  const stopTracks = useCallback(() => {
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
  }, []);

  useEffect(() => () => stopTracks(), [stopTracks]);

  const startCamera = useCallback(async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: {
          facingMode: "user",
          width: { ideal: 1920 },
          height: { ideal: 1080 },
          frameRate: { ideal: 30 },
        },
        audio: true,
      });
      streamRef.current = stream;
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        await videoRef.current.play().catch(() => {});
      }
      setPhase("live");
    } catch {
      setErr("Couldn't open your camera. Allow camera + microphone access, then reload this page.");
      setPhase("error");
    }
  }, []);

  const startRec = () => {
    if (!streamRef.current) return;
    chunksRef.current = [];
    // iOS Safari MediaRecorder outputs mp4; everything else webm. Detect, don't assume.
    const mt =
      typeof MediaRecorder !== "undefined" && MediaRecorder.isTypeSupported("video/mp4")
        ? "video/mp4"
        : "video/webm";
    const rec = new MediaRecorder(streamRef.current, { mimeType: mt });
    rec.ondataavailable = (e) => {
      if (e.data.size) chunksRef.current.push(e.data);
    };
    rec.onstop = () => {
      const b = new Blob(chunksRef.current, { type: mt });
      setBlob(b);
      setPreviewUrl(URL.createObjectURL(b));
      setPhase("review");
    };
    recRef.current = rec;
    rec.start();
    setSecs(0);
    setPhase("recording");
  };

  useEffect(() => {
    if (phase !== "recording") return;
    const id = setInterval(() => setSecs((s) => s + 1), 1000);
    return () => clearInterval(id);
  }, [phase]);

  const retake = () => {
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    setBlob(null);
    setPreviewUrl("");
    setPhase("live");
  };

  const upload = async () => {
    if (!blob) return;
    setPhase("uploading");
    try {
      const ext = blob.type.includes("mp4") ? "mp4" : "webm";
      const fd = new FormData();
      fd.set("video", new File([blob], `phone-reference.${ext}`, { type: blob.type }));
      const r = await fetch(`/api/avatar/phone-session/${token}/upload`, { method: "POST", body: fd });
      if (!r.ok) {
        const j = await r.json().catch(() => ({}));
        throw new Error(j.error || "Upload failed — try again.");
      }
      stopTracks();
      setPhase("done");
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Upload failed — try again.");
      setPhase("error");
    }
  };

  const mmss = `${String(Math.floor(secs / 60)).padStart(2, "0")}:${String(secs % 60).padStart(2, "0")}`;

  return (
    <main className="min-h-dvh bg-neutral-950 text-neutral-100 flex flex-col">
      <header className="px-5 pt-5 pb-2 text-center">
        <div className="text-sm font-semibold tracking-tight text-violet-300">CloutHook · Record your avatar</div>
      </header>

      {phase === "intro" && (
        <div className="flex-1 flex flex-col items-center justify-center gap-5 px-6 text-center">
          <p className="text-neutral-300 max-w-xs">
            Your phone shoots far sharper than a webcam — this becomes your AI avatar. Record one
            good clip and it lands on your computer automatically.
          </p>
          <ul className="text-left text-sm text-neutral-400 space-y-2 max-w-xs">
            {TIPS.map((t) => (
              <li key={t} className="flex gap-2">
                <span className="text-violet-400">•</span>
                <span>{t}</span>
              </li>
            ))}
          </ul>
          <button
            onClick={startCamera}
            className="mt-2 w-full max-w-xs rounded-full bg-violet-600 py-4 text-base font-semibold active:scale-[0.98] transition"
          >
            Open camera
          </button>
        </div>
      )}

      {(phase === "live" || phase === "recording") && (
        <div className="flex-1 flex flex-col">
          <div className="relative flex-1 bg-black">
            <video
              ref={videoRef}
              playsInline
              muted
              className="absolute inset-0 h-full w-full object-cover [transform:scaleX(-1)]"
            />
            {phase === "recording" && (
              <div className="absolute top-4 left-1/2 -translate-x-1/2 flex items-center gap-2 rounded-full bg-black/60 px-3 py-1 text-sm">
                <span className="h-2.5 w-2.5 rounded-full bg-red-500 animate-pulse" />
                {mmss}
              </div>
            )}
          </div>
          <div className="p-6 flex items-center justify-center">
            {phase === "live" ? (
              <button
                onClick={startRec}
                aria-label="Start recording"
                className="h-18 w-18 rounded-full border-4 border-white p-1 active:scale-95 transition"
              >
                <span className="block h-full w-full rounded-full bg-red-500" />
              </button>
            ) : (
              <button
                onClick={() => recRef.current?.stop()}
                aria-label="Stop recording"
                className="h-18 w-18 rounded-full border-4 border-white grid place-items-center active:scale-95 transition"
              >
                <span className="h-7 w-7 rounded bg-red-500" />
              </button>
            )}
          </div>
        </div>
      )}

      {phase === "review" && (
        <div className="flex-1 flex flex-col">
          <div className="relative flex-1 bg-black">
            <video
              src={previewUrl}
              controls
              playsInline
              className="absolute inset-0 h-full w-full object-contain"
            />
          </div>
          <div className="p-5 grid grid-cols-2 gap-3">
            <button
              onClick={retake}
              className="rounded-full border border-neutral-700 py-4 font-semibold text-neutral-200 active:scale-[0.98] transition"
            >
              Retake
            </button>
            <button
              onClick={upload}
              className="rounded-full bg-violet-600 py-4 font-semibold active:scale-[0.98] transition"
            >
              Use this
            </button>
          </div>
        </div>
      )}

      {phase === "uploading" && (
        <div className="flex-1 flex flex-col items-center justify-center gap-4 px-6 text-center">
          <div className="h-10 w-10 rounded-full border-2 border-violet-400 border-t-transparent animate-spin" />
          <p className="text-neutral-300">Sending to your account…</p>
        </div>
      )}

      {phase === "done" && (
        <div className="flex-1 flex flex-col items-center justify-center gap-3 px-6 text-center">
          <div className="text-5xl">✓</div>
          <h1 className="text-xl font-semibold">Sent!</h1>
          <p className="text-neutral-400 max-w-xs">
            Head back to CloutHook on your computer — your recording is there. You can close this tab.
          </p>
        </div>
      )}

      {phase === "error" && (
        <div className="flex-1 flex flex-col items-center justify-center gap-4 px-6 text-center">
          <div className="text-4xl">⚠️</div>
          <p className="text-neutral-300 max-w-xs">{err}</p>
          <button
            onClick={() => {
              setErr("");
              setPhase("intro");
            }}
            className="rounded-full border border-neutral-700 px-6 py-3 font-semibold active:scale-[0.98] transition"
          >
            Try again
          </button>
        </div>
      )}
    </main>
  );
}
