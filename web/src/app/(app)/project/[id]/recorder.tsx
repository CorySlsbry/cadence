"use client";

import { useEffect, useRef, useState } from "react";
import { Teleprompter } from "./teleprompter";

/** In-browser A-roll capture (getUserMedia + MediaRecorder). The engine re-normalizes
 *  to 1080×1920/60fps CFR, so the exact webcam resolution doesn't need to be perfect. */
export function Recorder({ onRecorded, onRecordStart }: { onRecorded: (blob: Blob) => void; onRecordStart?: () => void }) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunks = useRef<Blob[]>([]);
  const cdRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const [recording, setRecording] = useState(false);
  const [countdown, setCountdown] = useState<number | null>(null);
  const [seconds, setSeconds] = useState(0);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    navigator.mediaDevices
      .getUserMedia({
        video: { width: { ideal: 1080 }, height: { ideal: 1920 }, facingMode: "user" },
        audio: { echoCancellation: true, noiseSuppression: true },
      })
      .then((stream) => {
        if (!active) {
          stream.getTracks().forEach((t) => t.stop());
          return;
        }
        streamRef.current = stream;
        if (videoRef.current) videoRef.current.srcObject = stream;
      })
      .catch((e) => setError(e instanceof Error ? e.message : "camera unavailable"));
    return () => {
      active = false;
      streamRef.current?.getTracks().forEach((t) => t.stop());
    };
  }, []);

  useEffect(() => {
    if (!recording) return;
    const t = setInterval(() => setSeconds((s) => s + 1), 1000);
    return () => clearInterval(t);
  }, [recording]);

  // Clear any in-flight countdown on unmount.
  useEffect(() => () => { if (cdRef.current) clearInterval(cdRef.current); }, []);

  function startRecording() {
    if (!streamRef.current) return;
    chunks.current = [];
    setSeconds(0);
    const mime = MediaRecorder.isTypeSupported("video/webm;codecs=vp9,opus")
      ? "video/webm;codecs=vp9,opus"
      : "video/webm";
    const rec = new MediaRecorder(streamRef.current, { mimeType: mime, videoBitsPerSecond: 8_000_000 });
    rec.ondataavailable = (e) => {
      if (e.data.size > 0) chunks.current.push(e.data);
    };
    rec.onstop = () => onRecorded(new Blob(chunks.current, { type: "video/webm" }));
    recorderRef.current = rec;
    rec.start();
    setRecording(true); // -> teleprompter starts scrolling
  }

  function beginCountdown() {
    if (!streamRef.current || recording || countdown !== null) return;
    onRecordStart?.(); // auto-clear any prior take/result so each Record starts fresh
    let n = 3;
    setCountdown(n);
    cdRef.current = setInterval(() => {
      n -= 1;
      if (n <= 0) {
        if (cdRef.current) clearInterval(cdRef.current);
        cdRef.current = null;
        setCountdown(null);
        startRecording();
      } else {
        setCountdown(n);
      }
    }, 1000);
  }

  function onRecordClick() {
    if (recording) {
      recorderRef.current?.stop();
      setRecording(false);
      return;
    }
    beginCountdown(); // 3-2-1, then startRecording()
  }

  if (error) {
    return (
      <div className="rounded-xl border border-red-500/20 bg-red-500/5 p-4 text-sm text-red-300">
        Camera/mic unavailable: {error}. You can upload a file instead.
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <Teleprompter recording={recording} />

      <div className="relative mx-auto aspect-[9/16] max-w-[240px] overflow-hidden rounded-2xl border border-white/10 bg-black">
        <video ref={videoRef} autoPlay muted playsInline className="h-full w-full object-cover" />
        {recording && (
          <div className="absolute left-3 top-3 flex items-center gap-1.5 rounded-full bg-black/60 px-2.5 py-1 text-xs">
            <span className="h-2 w-2 rounded-full bg-red-500 animate-pulse-dot" />
            {Math.floor(seconds / 60)}:{(seconds % 60).toString().padStart(2, "0")}
          </div>
        )}
        {countdown !== null && (
          <div className="absolute inset-0 z-20 flex flex-col items-center justify-center gap-2 bg-black/55">
            <span key={countdown} className="animate-countdown-pop text-8xl font-extrabold tabular-nums text-white drop-shadow-lg">
              {countdown}
            </span>
            <span className="text-xs font-medium uppercase tracking-wide text-white/70">Get ready…</span>
          </div>
        )}
      </div>

      <button
        onClick={onRecordClick}
        disabled={countdown !== null}
        className={`flex w-full items-center justify-center gap-2 rounded-xl px-4 py-3 text-sm font-semibold transition disabled:cursor-not-allowed disabled:opacity-70 ${
          recording ? "bg-white/10 text-white hover:bg-white/15" : "bg-red-500 text-white hover:bg-red-600"
        }`}
      >
        {recording ? (
          <><span className="h-3 w-3 rounded-[2px] bg-white" /> Stop recording</>
        ) : countdown !== null ? (
          <>Starting in {countdown}…</>
        ) : (
          <><span className="h-2.5 w-2.5 rounded-full bg-white" /> Record</>
        )}
      </button>

      <p className="text-center text-xs text-white/35">
        Hit Record — you get a 3-second countdown, then the teleprompter scrolls. Keep talking through
        mistakes; Cadence removes silence, fillers, and bad takes.
      </p>
    </div>
  );
}
